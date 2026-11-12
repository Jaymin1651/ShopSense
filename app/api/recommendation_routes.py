"""Segment-level and per-customer recommendations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import admin, scope, staff, with_meta
from app.database import get_db
from app.models import User
from app.routers.products import serialize_product
from app.services import bi, intelligence

router = APIRouter(tags=['Recommendations'])


@router.get('/api/recommendations/segments')
def by_segment(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Products each K-Means segment buys more than average (lift)."""
    return with_meta(bi.serve(db, 'segment_recommendations', scope(user)))


@router.get('/api/recommend/{customer_id}')
def for_customer(customer_id: int, limit: int = Query(default=5, ge=1, le=30), db: Session = Depends(get_db),
                 _: User = Depends(admin)):
    """Path named in the Milestone 3 plan: hybrid recommendations for any customer (admin)."""
    customer = db.get(User, customer_id)
    if not customer or customer.role != 'customer':
        raise HTTPException(404, 'Customer not found')
    picks = intelligence.recommend_for(db, customer_id, limit)
    return {'customer': customer_id, 'recommendations': [
        {'product': serialize_product(p).model_dump(mode='json'), 'score': r['score'], 'reason': r['reason']}
        for p, r in picks]}
