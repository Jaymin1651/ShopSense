"""Automated analytical workflows and their run history.

Every job runs through ``run_job``, which records a ``WorkflowRun`` row
(start, end, duration, attempts, status, message, metrics) and retries
transient failures with exponential backoff before marking a run failed.

=====================  ==========================  ==========================================
Job                    Default schedule (UTC)      What it does
=====================  ==========================  ==========================================
refresh_snapshots      every 10 minutes            recompute dashboard analytics for all scopes
data_quality           every hour                  integrity checks on orders, stock and ledger
retrain_forecast       daily 02:00                 train, log and register InventoryForecast
retrain_churn          daily 02:30                 train, log and register ChurnRisk
evaluate_models        daily 03:00                 log segmentation and recommender quality
scheduled_reports      daily 06:00                 write Excel and PDF business reports
=====================  ==========================  ==========================================
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Vendor, WorkflowRun

log = logging.getLogger('shopsense.workflows')
REPORT_DIR = Path(__file__).resolve().parents[2] / 'reports' / 'generated'


@dataclass(frozen=True)
class Job:
    name: str
    description: str
    trigger: str        # 'cron' or 'interval'
    schedule: dict      # APScheduler trigger arguments
    func: object


# ------------------------------------------------------------------ the jobs
def refresh_snapshots(db: Session) -> dict:
    from app.analytics import snapshots
    from app.services import bi
    vendor_ids = [v for (v,) in db.execute(select(Vendor.id).where(Vendor.status == 'approved')).all()]
    done = 0
    for name, (compute, per_vendor) in bi.SNAPSHOTS.items():
        for vid in [None] + (vendor_ids if per_vendor else []):
            snapshots.compute_and_store(db, name, bi.scope_key(vid), lambda s, c=compute, v=vid: c(s, v))
            done += 1
    return {'snapshots': done, 'scopes': 1 + len(vendor_ids), 'data_version': snapshots.data_version(db)}


def data_quality(db: Session) -> dict:
    """Integrity checks. Problems are reported in metrics; the job itself only
    fails if it cannot run."""
    checks = {
        'negative_stock': "SELECT COUNT(*) FROM inventory WHERE quantity < 0",
        'order_total_mismatch': """SELECT COUNT(*) FROM orders o JOIN (SELECT order_id, SUM(quantity * unit_price) AS s
                                   FROM order_items GROUP BY order_id) t ON t.order_id = o.id
                                   WHERE ABS(o.total - t.s) > 0.01""",
        'orders_without_items': """SELECT COUNT(*) FROM orders o WHERE NOT EXISTS
                                   (SELECT 1 FROM order_items i WHERE i.order_id = o.id)""",
        'ledger_mismatch': """SELECT COUNT(*) FROM inventory i LEFT JOIN (SELECT product_id, SUM(delta) AS s
                              FROM inventory_movements GROUP BY product_id) m ON m.product_id = i.product_id
                              WHERE m.s IS NOT NULL AND m.s != i.quantity""",
        'products_without_inventory': """SELECT COUNT(*) FROM products p WHERE NOT EXISTS
                                         (SELECT 1 FROM inventory i WHERE i.product_id = p.id)""",
    }
    results = {name: int(db.execute(text(sql)).scalar() or 0) for name, sql in checks.items()}
    results['issues'] = sum(results.values())
    results['orders_checked'] = int(db.execute(text('SELECT COUNT(*) FROM orders')).scalar() or 0)
    return results


def retrain_forecast(db: Session) -> dict:
    from app.forecasting.service import reset
    from app.mlflow_tracking import tracking
    from app.services import intelligence
    sales = intelligence.load_sales(db)
    if sales.empty:
        return {'skipped': 'no sales yet'}
    try:
        result = tracking.train_forecast(sales)
    except ValueError as exc:  # not enough history yet: nothing to train, not an operational failure
        return {'skipped': str(exc)}
    reset()
    intelligence.clear_cache()
    return result


def retrain_churn(db: Session) -> dict:
    from app.mlflow_tracking import tracking
    from app.services import intelligence
    sales = intelligence.load_sales(db)
    if sales.empty:
        return {'skipped': 'no sales yet'}
    try:
        return tracking.train_churn(sales)
    except ValueError as exc:
        return {'skipped': str(exc)}


def evaluate_models(db: Session) -> dict:
    from app.customer.analytics import customer_stats
    from app.customer.segmentation import segment_customers
    from app.mlflow_tracking import tracking
    from app.recommendation.recommendation import build_events, evaluate
    from app.services import intelligence
    sales = intelligence.load_sales(db)
    out = {}
    stats = customer_stats(sales, as_of=intelligence._now()) if not sales.empty else []
    if len(stats) >= 10:
        seg = segment_customers(stats, k=3, stability_runs=5)
        tracking.log_segmentation({k: v for k, v in seg['metrics'].items() if k != 'silhouette_by_k'}, seg['k'])
        out['silhouette'] = seg['metrics']['silhouette']
    events = build_events(intelligence.load_interactions(db), sales)
    try:
        rec = evaluate(events, None, k=10, test_days=60)
        tracking.log_recommender(rec)
        out['hit_rate_at_10_pct'] = rec['relevance_pct']
    except (ValueError, KeyError) as exc:
        out['recommender_skipped'] = str(exc)
    return out or {'skipped': 'not enough data'}


def scheduled_reports(db: Session) -> dict:
    from app.reports.data import collect
    from app.reports.excel_reports import build_workbook
    from app.reports.pdf_reports import build_pdf
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    data = collect(db, None)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    xlsx, pdf = REPORT_DIR / f'shopsense-business-{stamp}.xlsx', REPORT_DIR / f'shopsense-business-{stamp}.pdf'
    xlsx.write_bytes(build_workbook(data))
    pdf.write_bytes(build_pdf(data))
    for pattern in ('*.xlsx', '*.pdf'):  # keep the latest 7 of each
        for old in sorted(REPORT_DIR.glob(pattern))[:-7]:
            old.unlink(missing_ok=True)
    return {'excel': xlsx.name, 'pdf': pdf.name, 'excel_kb': round(xlsx.stat().st_size / 1024, 1),
            'pdf_kb': round(pdf.stat().st_size / 1024, 1)}


JOBS: dict[str, Job] = {j.name: j for j in [
    Job('refresh_snapshots', 'Recompute dashboard analytics for every scope', 'interval', {'minutes': 10},
        refresh_snapshots),
    Job('data_quality', 'Integrity checks on orders, stock and the stock ledger', 'interval', {'hours': 1},
        data_quality),
    Job('retrain_forecast', 'Train, log and register the demand forecast (MLflow)', 'cron', {'hour': 2, 'minute': 0},
        retrain_forecast),
    Job('retrain_churn', 'Train, log and register the churn model (MLflow)', 'cron', {'hour': 2, 'minute': 30},
        retrain_churn),
    Job('evaluate_models', 'Log segmentation and recommender quality (MLflow)', 'cron', {'hour': 3, 'minute': 0},
        evaluate_models),
    Job('scheduled_reports', 'Write Excel and PDF business reports', 'cron', {'hour': 6, 'minute': 0},
        scheduled_reports),
]}


# ---------------------------------------------------------------- the runner
def run_job(name: str, trigger: str = 'schedule', session_factory=SessionLocal, retries: int = 2,
            backoff_seconds: float = 2.0) -> dict:
    """Run one job with retries and record it. Returns the run as a dict."""
    job = JOBS[name]
    with session_factory() as db:
        run = WorkflowRun(job=name, trigger=trigger, status='running', attempts=0)
        db.add(run)
        db.commit()
        run_id = run.id
    started = time.perf_counter()
    status, message, metrics, attempts = 'failed', '', {}, 0
    for attempt in range(1, retries + 2):
        attempts = attempt
        try:
            with session_factory() as db:
                metrics = job.func(db) or {}
            status, message = 'success', 'ok' if attempt == 1 else f'ok after {attempt} attempts'
            break
        except Exception as exc:  # recorded, then retried
            message = f'{type(exc).__name__}: {exc}'
            log.warning('workflow %s attempt %s failed: %s', name, attempt, message)
            if attempt <= retries:
                time.sleep(backoff_seconds * 2 ** (attempt - 1))
            else:
                message += '\n' + traceback.format_exc(limit=3)
    duration = int((time.perf_counter() - started) * 1000)
    with session_factory() as db:
        run = db.get(WorkflowRun, run_id)
        run.status, run.attempts, run.duration_ms = status, attempts, duration
        run.finished_at = datetime.now(timezone.utc)
        run.message, run.metrics = message[:4000], json.dumps(metrics, default=str)
        db.commit()
    log.info('workflow %s %s in %s ms (%s attempt(s))', name, status, duration, attempts)
    return {'id': run_id, 'job': name, 'status': status, 'attempts': attempts, 'duration_ms': duration,
            'message': message, 'metrics': metrics}


def run_summary(db: Session, since: datetime | None = None) -> list[dict]:
    """Per-job totals and success rate (finished runs only)."""
    stmt = select(WorkflowRun.job, WorkflowRun.status, func.count(), func.avg(WorkflowRun.duration_ms),
                  func.max(WorkflowRun.started_at)).where(WorkflowRun.status != 'running')
    if since is not None:
        stmt = stmt.where(WorkflowRun.started_at >= since)
    rows = db.execute(stmt.group_by(WorkflowRun.job, WorkflowRun.status)).all()
    out = {name: {'job': name, 'description': j.description, 'schedule': describe(j), 'runs': 0, 'success': 0,
                  'failed': 0, 'avg_duration_ms': None, 'last_run': None} for name, j in JOBS.items()}
    for job, status, count, avg, last in rows:
        entry = out.setdefault(job, {'job': job, 'description': '', 'schedule': '', 'runs': 0, 'success': 0,
                                     'failed': 0, 'avg_duration_ms': None, 'last_run': None})
        entry['runs'] += count
        entry[status if status in ('success', 'failed') else 'failed'] += count
        if status == 'success':
            entry['avg_duration_ms'] = int(avg or 0)
        last_iso = last.isoformat(timespec='seconds') if last else None
        entry['last_run'] = max(filter(None, [entry['last_run'], last_iso]), default=None)
    for entry in out.values():
        entry['success_rate_pct'] = round(entry['success'] / entry['runs'] * 100, 1) if entry['runs'] else None
    return list(out.values())


def describe(job: Job) -> str:
    s = job.schedule
    if job.trigger == 'interval':
        unit, value = next(iter(s.items()))
        return f'every {unit.rstrip("s")}' if value == 1 else f'every {value} {unit}'
    return f"daily at {s.get('hour', 0):02d}:{s.get('minute', 0):02d} UTC"
