"""Customer intelligence: churn risk, lifetime value and segment summaries."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import scope, staff, with_meta
from app.database import get_db
from app.models import User
from app.services import bi

router = APIRouter(tags=['Customer Intelligence'])


@router.get('/api/customer-intelligence/overview')
def overview(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Churn risk counts, value at risk, per-segment value and model quality."""
    return with_meta(bi.serve(db, 'customer_intelligence', scope(user)))


@router.get('/api/customer-intelligence/at-risk')
def at_risk(limit: int = Query(default=20, ge=1, le=50), db: Session = Depends(get_db), user: User = Depends(staff)):
    """Highest-spending customers with a high churn risk."""
    data = bi.serve(db, 'customer_intelligence', scope(user))['data']
    return data.get('high_risk_customers', [])[:limit]


@router.get('/api/analytics/customers')
def customer_metrics(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Path named in the Milestone 3 plan: customer count and average spend."""
    s = bi.serve(db, 'customer_overview', scope(user))['data']['summary']
    return {'customers': s['customers'], 'avg_spend': s['average_spending'],
            'average_order_value': s['average_order_value'], 'repeat_rate_pct': s['repeat_rate_pct']}
