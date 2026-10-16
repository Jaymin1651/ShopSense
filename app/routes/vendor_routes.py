from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate
from app.validation.vendor_validation import validate_vendor

router = APIRouter(prefix="/vendors", tags=["Vendors"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/", status_code=status.HTTP_201_CREATED)
def register_vendor(vendor: VendorCreate, db: Session = Depends(get_db)):
    if not validate_vendor(vendor.dict()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validation failed: required fields are missing or invalid"
        )

    existing = db.query(Vendor).filter(Vendor.email == vendor.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vendor already exists"
        )

    db_vendor = Vendor(
        business_name=vendor.business_name,
        owner_name=vendor.owner_name,
        email=vendor.email,
        phone=vendor.phone,
        address=vendor.address
    )

    db.add(db_vendor)
    db.commit()
    db.refresh(db_vendor)

    return {
        "status": "success",
        "message": "Vendor Registered",
        "vendor": {
            "id": db_vendor.id,
            "business_name": db_vendor.business_name,
            "owner_name": db_vendor.owner_name,
            "email": db_vendor.email,
            "phone": db_vendor.phone,
            "address": db_vendor.address
        }
    }
