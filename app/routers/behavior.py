"""Customer interaction telemetry and personalised recommendations."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Interaction, Product, User
from app.schemas import InteractionCreate, ProductOut
from app.routers.products import serialize_product
from app.security import require_roles
from app.services import intelligence

router = APIRouter(prefix='/api/customers', tags=['Customer Insights'])


@router.post('/interactions', status_code=201)
def log_interaction(payload: InteractionCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_roles('customer'))):
    product = db.get(Product, payload.product_id)
    if not product or not product.is_active:
        raise HTTPException(404, 'Product not found')
    db.add(Interaction(customer_id=user.id, product_id=payload.product_id, event_type=payload.event_type))
    db.commit()
    return {'recorded': True}


@router.get('/recommendations/me', response_model=list[ProductOut])
def recommendations(db: Session = Depends(get_db), user: User = Depends(require_roles('customer')),
                    limit: int = Query(default=8, ge=1, le=30)):
    """Hybrid collaborative-filtering recommendations, excluding anything the
    customer has already viewed, carted or bought. ``/api/recommendations/me``
    returns the same engine's picks with scores and reasons."""
    return [serialize_product(p) for p, _ in intelligence.recommend_for(db, user.id, limit, exclude='seen')]
