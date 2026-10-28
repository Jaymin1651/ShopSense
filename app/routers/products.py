"""Public product catalog, with vendor-owned product and stock management."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.models import Product, Vendor, Inventory, InventoryMovement, User, Warehouse
from app.schemas import ProductIn, ProductUpdate, ProductOut, InventorySet, InventoryOut
from app.security import require_roles

router = APIRouter(prefix='/api/products', tags=['Products & Inventory'])


def serialize_product(product: Product, vendor_status: str = 'approved') -> ProductOut:
    """Explain the visibility rule in the vendor dashboard without changing the DB."""
    visible = vendor_status == 'approved' and product.is_active
    if vendor_status != 'approved':
        note = f'Vendor account is {vendor_status}'
    elif not product.is_active:
        note = 'Product is hidden by vendor'
    elif product.inventory.quantity == 0:
        note = 'Visible, but out of stock'
    else:
        note = 'Visible in customer catalog'
    return ProductOut(
        id=product.id, vendor_id=product.vendor_id, name=product.name,
        description=product.description, category=product.category, price=product.price,
        is_active=product.is_active, quantity=product.inventory.quantity,
        low_stock_threshold=product.inventory.low_stock_threshold,
        visible_to_customers=visible, visibility_note=note, unit_cost=product.unit_cost,
        warehouse_id=product.inventory.warehouse_id, lead_time_days=product.inventory.lead_time_days or 7,
    )


@router.get('', response_model=list[ProductOut])
def list_products(db: Session = Depends(get_db), search: str | None = Query(default=None, max_length=100),
                  category: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, ge=1, le=500)):
    stmt = (select(Product).join(Vendor).where(Vendor.status == 'approved', Product.is_active.is_(True))
            .options(selectinload(Product.inventory)).order_by(Product.id.desc()).limit(limit))
    if search:
        stmt = stmt.where(Product.name.ilike(f'%{search}%'))
    if category:
        stmt = stmt.where(Product.category == category)
    return [serialize_product(p) for p in db.scalars(stmt).all()]


@router.get('/mine', response_model=list[ProductOut])
def my_products(db: Session = Depends(get_db), user: User = Depends(require_roles('vendor'))):
    stmt = select(Product).where(Product.vendor_id == user.vendor_id).options(selectinload(Product.inventory))
    vendor = db.get(Vendor, user.vendor_id)
    return [serialize_product(p, vendor.status if vendor else 'missing') for p in db.scalars(stmt).all()]


@router.post('', response_model=ProductOut, status_code=201)
def add_product(payload: ProductIn, db: Session = Depends(get_db), user: User = Depends(require_roles('vendor'))):
    vendor = db.get(Vendor, user.vendor_id)
    if not vendor or vendor.status != 'approved':
        raise HTTPException(403, 'Vendor approval required before listing products')
    if payload.warehouse_id is not None and not db.get(Warehouse, payload.warehouse_id):
        raise HTTPException(404, 'Warehouse not found')
    product = Product(vendor_id=user.vendor_id, name=payload.name, description=payload.description,
                      category=payload.category, price=payload.price, unit_cost=payload.unit_cost)
    product.inventory = Inventory(quantity=payload.quantity, low_stock_threshold=payload.low_stock_threshold,
                                  warehouse_id=payload.warehouse_id, lead_time_days=payload.lead_time_days)
    db.add(product)
    db.flush()
    if payload.quantity:
        db.add(InventoryMovement(product_id=product.id, delta=payload.quantity, reason='initial_stock'))
    db.commit()
    db.refresh(product)
    return serialize_product(product)


@router.patch('/{product_id}', response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_roles('vendor', 'admin'))):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, 'Product not found')
    if user.role == 'vendor' and product.vendor_id != user.vendor_id:
        raise HTTPException(403, 'Cannot modify another vendor\'s product')
    if user.role == 'vendor' and db.get(Vendor, user.vendor_id).status != 'approved':
        raise HTTPException(403, 'Vendor account is not approved')
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    vendor = db.get(Vendor, product.vendor_id)
    return serialize_product(product, vendor.status if vendor else 'missing')


@router.put('/{product_id}/inventory', response_model=InventoryOut)
def update_inventory(product_id: int, payload: InventorySet, db: Session = Depends(get_db),
                     user: User = Depends(require_roles('vendor', 'admin'))):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, 'Product not found')
    if user.role == 'vendor' and product.vendor_id != user.vendor_id:
        raise HTTPException(403, 'Cannot modify another vendor\'s inventory')
    if user.role == 'vendor' and db.get(Vendor, user.vendor_id).status != 'approved':
        raise HTTPException(403, 'Vendor account is not approved')
    if payload.warehouse_id is not None and not db.get(Warehouse, payload.warehouse_id):
        raise HTTPException(404, 'Warehouse not found')
    inv = db.scalar(select(Inventory).where(Inventory.product_id == product_id).with_for_update())
    diff = payload.quantity - inv.quantity
    inv.quantity = payload.quantity
    if payload.low_stock_threshold is not None:
        inv.low_stock_threshold = payload.low_stock_threshold
    if payload.warehouse_id is not None:
        inv.warehouse_id = payload.warehouse_id
    if payload.lead_time_days is not None:
        inv.lead_time_days = payload.lead_time_days
    if diff:
        db.add(InventoryMovement(product_id=product_id, delta=diff, reason='manual_adjustment'))
    db.commit()
    return InventoryOut(product_id=product_id, quantity=inv.quantity, low_stock_threshold=inv.low_stock_threshold,
                        warehouse_id=inv.warehouse_id, lead_time_days=inv.lead_time_days)
