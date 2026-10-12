"""Authentication and vendor/customer sign-up."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Vendor, User, CustomerProfile
from app.schemas import VendorRegister, CustomerRegister, TokenResponse, LoginRequest, UserOut
from app.security import hash_password, verify_password, create_token, current_user

router = APIRouter(prefix='/api/auth', tags=['Authentication'])


@router.post('/register/vendor', response_model=UserOut, status_code=201)
def register_vendor(payload: VendorRegister, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) or db.scalar(select(Vendor.id).where(Vendor.email == email)):
        raise HTTPException(409, 'Email already registered')
    vendor = Vendor(business_name=payload.business_name, owner_name=payload.owner_name,
                    email=email, phone=payload.phone, category=payload.category, status='pending')
    db.add(vendor)
    db.flush()
    user = User(email=email, password_hash=hash_password(payload.password), role='vendor', vendor_id=vendor.id)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email already registered') from None
    db.refresh(user)
    return user


@router.post('/register/customer', response_model=UserOut, status_code=201)
def register_customer(payload: CustomerRegister, db: Session = Depends(get_db)):
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, 'Email already registered')
    user = User(email=email, password_hash=hash_password(payload.password), role='customer')
    db.add(user)
    db.flush()
    db.add(CustomerProfile(user_id=user.id, full_name=payload.full_name))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email already registered') from None
    db.refresh(user)
    return user


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, 'Invalid email or password')
    return TokenResponse(access_token=create_token(user))


@router.get('/me', response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
