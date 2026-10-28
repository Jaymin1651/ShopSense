"""Milestone 2 personalised recommendations, click tracking and evaluation."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Interaction, Product, User, Vendor
from app.routers.products import serialize_product
from app.schemas import RecommendationFeedback, RecommendationOut
from app.security import require_roles
from app.services import intelligence as svc

router = APIRouter(tags=['Recommendations'])


@router.get('/api/recommendations/me', response_model=list[RecommendationOut])
def my_recommendations(limit: int = Query(default=8, ge=1, le=30), db: Session = Depends(get_db),
                       user: User = Depends(require_roles('customer'))):
    """Hybrid collaborative-filtering picks with a score and a plain-language reason."""
    return [RecommendationOut(product=serialize_product(p), score=r['score'], reason=r['reason'])
            for p, r in svc.recommend_for(db, user.id, limit)]


@router.post('/api/recommendations/feedback', status_code=201)
def feedback(payload: RecommendationFeedback, db: Session = Depends(get_db),
             user: User = Depends(require_roles('customer'))):
    """Record that recommendations were shown (impression) or opened (click)."""
    valid = {pid for (pid,) in db.query(Product.id).join(Vendor).filter(
        Product.id.in_(payload.product_ids), Product.is_active.is_(True), Vendor.status == 'approved').all()}
    event = 'rec_impression' if payload.event == 'impression' else 'rec_click'
    for pid in dict.fromkeys(payload.product_ids):
        if pid in valid:
            db.add(Interaction(customer_id=user.id, product_id=pid, event_type=event))
    db.commit()
    return {'recorded': len(valid)}


@router.get('/api/recommendations/metrics')
def metrics(db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    """Live click-through rate and purchases that followed a recommendation click."""
    return svc.recommendation_metrics(db)


@router.get('/api/evaluation/milestone2')
def milestone2_report(_: User = Depends(require_roles('admin', 'vendor'))):
    """Latest offline evaluation (scripts/evaluate_milestone2.py) against the Milestone 2 targets."""
    report = svc.evaluation_report()
    return report or {'available': False, 'reason': 'Run python -m scripts.evaluate_milestone2 to create the report.'}
