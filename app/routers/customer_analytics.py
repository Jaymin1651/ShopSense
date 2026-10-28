"""Milestone 2 customer behaviour analytics and K-Means segmentation."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import require_roles
from app.services import intelligence as svc

router = APIRouter(prefix='/api/customer-analytics', tags=['Customer Analytics'])
staff = require_roles('admin', 'vendor')


def scope(user: User):
    return user.vendor_id if user.role == 'vendor' else None


@router.get('/overview')
def overview(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Average spending, order value, repeat rate, top customers and the view-cart-buy funnel."""
    return svc.customer_overview(db, scope(user))


@router.get('/segments')
def segments(k: int | None = Query(default=3, ge=2, le=6), auto_k: bool = False,
             db: Session = Depends(get_db), user: User = Depends(staff)):
    """K-Means on log recency, frequency and spend; ``auto_k`` picks k by silhouette."""
    return svc.customer_segments(db, scope(user), None if auto_k else k)
