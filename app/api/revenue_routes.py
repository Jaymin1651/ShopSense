"""Revenue analytics, live KPIs and vendor benchmarking."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics import snapshots
from app.analytics.revenue_analysis import anonymise_benchmark, live_kpis
from app.api.deps import scope, staff, with_meta
from app.database import get_db
from app.models import User
from app.services import bi

router = APIRouter(tags=['Revenue Analytics'])


@router.get('/api/live/kpis')
def live(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Real-time KPIs straight from the database.

    Memoised only until the data version changes (any order, cancellation or
    stock movement) or the minute changes, so the numbers are always exact.
    """
    from datetime import datetime, timezone
    version = snapshots.data_version(db)
    minute = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    vid = scope(user)
    kpis = snapshots.by_version(db, ('live_kpis', vid, minute), lambda: live_kpis(db, vid), version)
    # Same data version means the numbers are still exact now.
    return {**kpis, 'as_of': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'data_version': version}


@router.get('/api/live/version')
def version(db: Session = Depends(get_db), _: User = Depends(staff)):
    """Cheap fingerprint of the data; changes whenever orders, stock or events change."""
    return {'data_version': snapshots.data_version(db)}


@router.get('/api/revenue/overview')
def overview(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Growth, monthly/weekly/daily series, category mix and Pareto concentration."""
    return with_meta(bi.serve(db, 'revenue_overview', scope(user)))


@router.get('/api/revenue/cohorts')
def cohorts(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Monthly acquisition cohorts and the share of each that bought again."""
    return with_meta(bi.serve(db, 'cohorts', scope(user)))


@router.get('/api/revenue/benchmark')
def benchmark(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Vendor ranking (admin). Vendors get their own row and anonymous marketplace figures."""
    result = bi.serve(db, 'benchmark', None)
    data = result['data'] if user.role == 'admin' else anonymise_benchmark(result['data'], user.vendor_id)
    return {**data, 'meta': result['meta']}


# Paths named in the Milestone 3 plan.
@router.get('/api/analytics/revenue')
def revenue_analysis(db: Session = Depends(get_db), user: User = Depends(staff)):
    vid = scope(user)
    k = snapshots.by_version(db, ('live_kpis_total', vid), lambda: live_kpis(db, vid))
    growth = bi.serve(db, 'revenue_overview', vid)['data']['growth']
    return {'total_revenue': k['gmv'], 'orders': k['orders'], 'average_order_value': k['average_order_value'],
            **growth}


@router.get('/api/analytics/vendor-performance')
def vendor_performance(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db),
                       user: User = Depends(staff)):
    data = bi.serve(db, 'benchmark', None)['data']
    if user.role == 'vendor':
        return [anonymise_benchmark(data, user.vendor_id)['you']]
    return data['vendors'][:limit]
