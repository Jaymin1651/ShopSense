"""Customer interaction telemetry and simple explainable recommendations."""
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Interaction, Product, Vendor, OrderItem, Order, User
from app.schemas import InteractionCreate, ProductOut
from app.routers.products import serialize_product
from app.security import require_roles

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
    """Category affinity from interactions and purchases; globally popular fallback."""
    viewed_ids = db.scalars(select(Interaction.product_id).where(Interaction.customer_id == user.id)).all()
    purchased_ids = db.scalars(select(OrderItem.product_id).join(Order).where(Order.customer_id == user.id)).all()
    exclude = set(viewed_ids) | set(purchased_ids)
    history = db.scalars(select(Product).where(Product.id.in_(exclude))).all() if exclude else []
    affinities = Counter(p.category for p in history)
    popularity = Counter(db.scalars(select(OrderItem.product_id)).all())
    available = db.scalars(select(Product).join(Vendor).where(Product.is_active.is_(True), Vendor.status == 'approved')).all()
    available = [p for p in available if p.id not in exclude and p.inventory and p.inventory.quantity > 0]
    available.sort(key=lambda p: (affinities[p.category]*5 + popularity[p.id], -p.id), reverse=True)
    return [serialize_product(p) for p in available[:limit]]
