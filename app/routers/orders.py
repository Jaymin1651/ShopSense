"""Customer checkout (order records only; no payment processing)."""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Product, Vendor, Inventory, InventoryMovement, Order, OrderItem
from app.schemas import OrderCreate, OrderOut
from app.security import require_roles

router = APIRouter(prefix='/api/orders', tags=['Orders'])


@router.post('', response_model=OrderOut, status_code=201)
def place_order(payload: OrderCreate, db: Session = Depends(get_db), user: User = Depends(require_roles('customer'))):
    # Sort IDs before acquiring row locks to reduce lock-order deadlocks in PostgreSQL.
    ids = sorted(item.product_id for item in payload.items)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)).order_by(Product.id).with_for_update()).all()}
    stocks = {s.product_id: s for s in db.scalars(select(Inventory).where(Inventory.product_id.in_(ids)).order_by(Inventory.product_id).with_for_update()).all()}
    vendors = {v.id: v for v in db.scalars(select(Vendor).where(Vendor.id.in_({p.vendor_id for p in products.values()}))).all()}
    for line in payload.items:
        product = products.get(line.product_id)
        if not product or not product.is_active or vendors[product.vendor_id].status != 'approved':
            raise HTTPException(400, f'Product {line.product_id} is unavailable')
        if stocks[product.id].quantity < line.quantity:
            raise HTTPException(409, f'Insufficient stock for product {line.product_id}')
    total = sum((products[line.product_id].price * line.quantity for line in payload.items), Decimal('0.00'))
    order = Order(customer_id=user.id, total=total, status='placed')
    db.add(order)
    db.flush()
    for line in payload.items:
        product = products[line.product_id]
        stocks[product.id].quantity -= line.quantity
        db.add(OrderItem(order_id=order.id, product_id=product.id, vendor_id=product.vendor_id,
                         quantity=line.quantity, unit_price=product.price))
        db.add(InventoryMovement(product_id=product.id, delta=-line.quantity, reason='sale'))
    db.commit()
    db.refresh(order)
    return order


@router.get('', response_model=list[OrderOut])
def list_orders(db: Session = Depends(get_db), user: User = Depends(require_roles('customer', 'vendor', 'admin'))):
    stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(200)
    if user.role == 'customer':
        stmt = stmt.where(Order.customer_id == user.id)
    if user.role == 'vendor':
        # Avoid revealing another vendor's line items inside a mixed-vendor order.
        stmt = stmt.join(OrderItem).where(OrderItem.vendor_id == user.vendor_id).distinct()
        results = db.scalars(stmt).all()
        return [OrderOut(id=o.id, customer_id=o.customer_id, status=o.status,
                         total=sum((i.unit_price*i.quantity for i in o.items if i.vendor_id == user.vendor_id), Decimal('0.00')),
                         created_at=o.created_at,
                         items=[i for i in o.items if i.vendor_id == user.vendor_id]) for o in results]
    return db.scalars(stmt).all()
