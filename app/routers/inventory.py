"""Milestone 2 inventory intelligence: stock status, alerts, replenishment,
turnover, ML demand forecasts and stock movement history.

Vendors only ever see their own products; admins see the whole marketplace.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InventoryMovement, Product, User
from app.security import require_roles
from app.services import intelligence as svc

router = APIRouter(prefix='/api/inventory', tags=['Inventory Intelligence'])
staff = require_roles('admin', 'vendor')


def scope(user: User):
    return user.vendor_id if user.role == 'vendor' else None


def owned_product(db: Session, product_id: int, user: User) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, 'Product not found')
    if user.role == 'vendor' and product.vendor_id != user.vendor_id:
        raise HTTPException(403, 'Limited to your own products')
    return product


@router.get('/overview')
def overview(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Dashboard KPIs: stock, low stock, turnover, forecast demand, reorder needs."""
    return svc.inventory_overview(db, scope(user))


@router.get('/status')
def status(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Every product with stock status, forecast daily demand and days of cover."""
    return svc.stock_status(db, scope(user))


@router.get('/alerts')
def alerts(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Products at or below reorder level, or forecast to run out within lead time."""
    return svc.alerts(db, scope(user))


@router.get('/replenishment')
def replenishment(service_level: float = Query(default=0.95, ge=0.8, le=0.99),
                  review_days: int = Query(default=7, ge=1, le=60), include_all: bool = False,
                  db: Session = Depends(get_db), user: User = Depends(staff)):
    """Recommended order quantities (order-up-to policy with safety stock)."""
    return svc.replenishment_plan(db, scope(user), service_level, review_days, include_all)


@router.get('/turnover')
def turnover(days: int = Query(default=90, ge=7, le=365), db: Session = Depends(get_db),
             user: User = Depends(staff)):
    """Inventory turnover per product and for the whole portfolio."""
    return svc.turnover(db, scope(user), days)


@router.get('/forecast/{product_id}')
def forecast(product_id: int, weeks: int = Query(default=4, ge=1, le=12), db: Session = Depends(get_db),
             user: User = Depends(staff)):
    """Weekly demand forecast from the pooled Random Forest (moving average if history is short)."""
    return svc.product_forecast(db, owned_product(db, product_id, user), weeks)


@router.get('/movements/{product_id}')
def movements(product_id: int, limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db),
              user: User = Depends(staff)):
    """Immutable stock movement ledger (sales, restocks, manual adjustments)."""
    owned_product(db, product_id, user)
    rows = db.scalars(select(InventoryMovement).where(InventoryMovement.product_id == product_id)
                      .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc()).limit(limit)).all()
    return [{'id': m.id, 'delta': m.delta, 'reason': m.reason, 'created_at': m.created_at.isoformat()} for m in rows]
