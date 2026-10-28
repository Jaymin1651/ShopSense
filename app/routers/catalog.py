"""Warehouses and the product category hierarchy."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, User, Warehouse
from app.schemas import CategoryIn, CategoryOut, WarehouseIn, WarehouseOut
from app.security import require_roles
from app.services.intelligence import category_tree

router = APIRouter(tags=['Warehouses & Categories'])


@router.get('/api/warehouses', response_model=list[WarehouseOut])
def list_warehouses(db: Session = Depends(get_db), _: User = Depends(require_roles('admin', 'vendor'))):
    return db.scalars(select(Warehouse).order_by(Warehouse.name)).all()


@router.post('/api/warehouses', response_model=WarehouseOut, status_code=201)
def add_warehouse(payload: WarehouseIn, db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    if db.scalar(select(Warehouse).where(Warehouse.name == payload.name)):
        raise HTTPException(409, 'A warehouse with this name already exists')
    warehouse = Warehouse(name=payload.name, location=payload.location)
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.get('/api/categories')
def list_categories(db: Session = Depends(get_db)):
    """Category tree, e.g. Electronics > Mobile, Laptop."""
    return category_tree(db)


@router.post('/api/categories', response_model=CategoryOut, status_code=201)
def add_category(payload: CategoryIn, db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    if db.scalar(select(Category).where(Category.name == payload.name)):
        raise HTTPException(409, 'Category already exists')
    if payload.parent_id is not None and not db.get(Category, payload.parent_id):
        raise HTTPException(404, 'Parent category not found')
    category = Category(name=payload.name, parent_id=payload.parent_id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category
