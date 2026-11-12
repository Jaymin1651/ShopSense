"""Versioned analytics snapshots shared by API workers and workflows.

Every heavy analytics result is stored with the *data version* it was computed
from. The version is a cheap fingerprint of orders, order lines, cancellations,
stock movements and interactions, so any new order or stock change produces a
new version.

Reading rules (``serve``):
* stored version == current version   -> return it (fresh, consistent)
* stored version is older              -> return it at once, marked with how many
                                          orders it is behind, and queue a refresh
                                          (at most one per key every
                                          ``MIN_REFRESH_SECONDS``, one at a time)
* nothing stored yet, or older than ``MAX_AGE_SECONDS``
                                       -> compute now, store, return

Live KPIs never go through this layer; they are computed with SQL on every
request (see ``app.analytics.revenue_analysis.live_kpis``).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AnalyticsSnapshot

# Background refresh is switched off in tests (single in-memory connection).
SWR_ENABLED = os.getenv('SHOPSENSE_BACKGROUND_REFRESH', '1') == '1'
MIN_REFRESH_SECONDS = int(os.getenv('SHOPSENSE_MIN_REFRESH_SECONDS', '30'))
MAX_AGE_SECONDS = int(os.getenv('SHOPSENSE_MAX_AGE_SECONDS', '21600'))  # 6 h: then recompute in the request

_MEMO: dict[tuple[str, str], tuple[str, float, object]] = {}
_LOCK = threading.Lock()

VERSION_SQL = text("""
SELECT
  (SELECT COUNT(*) FROM orders) AS orders,
  (SELECT COALESCE(MAX(id), 0) FROM orders) AS max_order,
  (SELECT COUNT(*) FROM orders WHERE status = 'cancelled') AS cancelled,
  (SELECT COALESCE(MAX(id), 0) FROM order_items) AS max_line,
  (SELECT COALESCE(MAX(id), 0) FROM inventory_movements) AS max_move,
  (SELECT COALESCE(MAX(id), 0) FROM interactions) AS max_event,
  (SELECT COUNT(*) FROM products) AS products
""")


def data_version(db: Session) -> str:
    """Fingerprint of everything analytics depend on (one small query)."""
    row = db.execute(VERSION_SQL).one()
    return '-'.join(str(int(v or 0)) for v in row)


def orders_in(version: str) -> int:
    return int(version.split('-')[0])


def _store(db: Session, name: str, scope: str, version: str, payload) -> None:
    body = json.dumps(payload, default=str)
    row = db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.name == name, AnalyticsSnapshot.scope == scope))
    try:
        if row is None:
            db.add(AnalyticsSnapshot(name=name, scope=scope, data_version=version, payload=body))
        else:
            row.data_version, row.payload, row.created_at = version, body, datetime.now(timezone.utc)
        db.commit()
    except IntegrityError:  # another worker stored it first
        db.rollback()


def _load(db: Session, name: str, scope: str):
    row = db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.name == name, AnalyticsSnapshot.scope == scope))
    if row is None:
        return None
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    return row.data_version, created.timestamp(), json.loads(row.payload)


def compute_and_store(db: Session, name: str, scope: str, compute) -> tuple[str, object]:
    version = data_version(db)
    payload = compute(db)
    _store(db, name, scope, version, payload)
    with _LOCK:
        _MEMO[(name, scope)] = (version, time.time(), payload)
    return version, payload


def _refresh_in_background(db: Session, name: str, scope: str, compute) -> None:
    from app.analytics import refresher
    bind = db.get_bind()

    def work():
        with Session(bind=bind) as session:
            compute_and_store(session, name, scope, compute)
    refresher.submit(f'snapshot:{name}:{scope}', work, MIN_REFRESH_SECONDS)


def serve(db: Session, name: str, scope: str, compute, max_age: int | None = None) -> dict:
    """Return ``{'data': payload, 'meta': {...}}`` following the rules above."""
    max_age = MAX_AGE_SECONDS if max_age is None else max_age
    version = data_version(db)
    key = (name, scope)
    with _LOCK:
        memo = _MEMO.get(key)
    hit = memo if memo else _load(db, name, scope)
    if hit and not memo:
        with _LOCK:
            _MEMO[key] = hit
    if hit and hit[0] == version:
        return {'data': hit[2], 'meta': _meta(version, hit, fresh=True)}
    if hit and SWR_ENABLED and time.time() - hit[1] < max_age:
        _refresh_in_background(db, name, scope, compute)
        return {'data': hit[2], 'meta': _meta(version, hit, fresh=False)}
    stored_version, payload = compute_and_store(db, name, scope, compute)
    return {'data': payload, 'meta': _meta(version, (stored_version, time.time(), payload), fresh=True)}


def _meta(current: str, hit, fresh: bool) -> dict:
    behind = max(0, orders_in(current) - orders_in(hit[0]))
    return {'data_version': hit[0], 'current_version': current, 'fresh': fresh and hit[0] == current,
            'orders_behind': behind,
            'computed_at': datetime.fromtimestamp(hit[1], timezone.utc).isoformat(timespec='seconds')}


def clear_memo():
    from app.analytics import refresher
    with _LOCK:
        _MEMO.clear()
        _RESULTS.clear()
    refresher.reset()


# ------------------------------------------------- per-version response memo
_RESULTS: dict[tuple, tuple[str, object]] = {}
_RESULTS_MAX = 512


def by_version(db: Session, key: tuple, compute, version: str | None = None):
    """Memoise a cheap-to-store result until the data version changes.

    Exactly consistent: any order, cancellation, stock movement or event
    changes the version, so the next call recomputes.
    """
    version = version or data_version(db)
    with _LOCK:
        hit = _RESULTS.get(key)
    if hit and hit[0] == version:
        return hit[1]
    value = compute()
    with _LOCK:
        if len(_RESULTS) >= _RESULTS_MAX:
            _RESULTS.pop(next(iter(_RESULTS)))
        _RESULTS[key] = (version, value)
    return value


def clear_results():
    with _LOCK:
        _RESULTS.clear()
