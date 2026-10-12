"""Admin-controlled vendor verification and lifecycle."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Vendor, User
from app.schemas import VendorOut
from app.security import require_roles

router = APIRouter(prefix='/api/vendors', tags=['Vendors'])


@router.get('', response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    return db.scalars(select(Vendor).order_by(Vendor.created_at.desc())).all()


@router.get('/me', response_model=VendorOut)
def my_vendor(db: Session = Depends(get_db), user: User = Depends(require_roles('vendor'))):
    return db.get(Vendor, user.vendor_id)


@router.patch('/{vendor_id}/status', response_model=VendorOut)
def set_vendor_status(vendor_id: int, status: Literal['approved', 'suspended', 'rejected'],
                      db: Session = Depends(get_db), _: User = Depends(require_roles('admin'))):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Vendor not found')
    vendor.status = status
    db.commit()
    db.refresh(vendor)
    return vendor
