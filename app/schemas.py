"""Request / response validation with Pydantic v2."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class DBModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VendorRegister(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=30)
    category: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)


class CustomerRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class UserOut(DBModel):
    id: int
    email: EmailStr
    role: str
    vendor_id: int | None


class VendorOut(DBModel):
    id: int
    business_name: str
    owner_name: str
    email: EmailStr
    phone: str
    category: str
    status: str
    commission_rate: Decimal
    created_at: datetime


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default='', max_length=5000)
    category: str = Field(min_length=2, max_length=100)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=5, ge=0)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, min_length=2, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    is_active: bool | None = None


class ProductOut(DBModel):
    id: int
    vendor_id: int
    name: str
    description: str
    category: str
    price: Decimal
    is_active: bool
    quantity: int
    low_stock_threshold: int
    visible_to_customers: bool
    visibility_note: str


class InventorySet(BaseModel):
    quantity: int = Field(ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class InventoryOut(BaseModel):
    product_id: int
    quantity: int
    low_stock_threshold: int


class OrderLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100)


class OrderCreate(BaseModel):
    items: list[OrderLine] = Field(min_length=1, max_length=50)

    @field_validator('items')
    @classmethod
    def unique_items(cls, items):
        if len({item.product_id for item in items}) != len(items):
            raise ValueError('Each product may appear only once per order')
        return items


class OrderItemOut(DBModel):
    product_id: int
    vendor_id: int
    quantity: int
    unit_price: Decimal


class OrderOut(DBModel):
    id: int
    customer_id: int
    status: str
    total: Decimal
    created_at: datetime
    items: list[OrderItemOut]


class InteractionCreate(BaseModel):
    product_id: int
    event_type: Literal['view', 'wishlist', 'cart']
