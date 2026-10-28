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
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    warehouse_id: int | None = None
    lead_time_days: int = Field(default=7, ge=1, le=180)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, min_length=2, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
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
    unit_cost: Decimal | None = None
    warehouse_id: int | None = None
    lead_time_days: int = 7


class InventorySet(BaseModel):
    quantity: int = Field(ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)
    warehouse_id: int | None = None
    lead_time_days: int | None = Field(default=None, ge=1, le=180)


class InventoryOut(BaseModel):
    product_id: int
    quantity: int
    low_stock_threshold: int
    warehouse_id: int | None = None
    lead_time_days: int = 7


class WarehouseIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    location: str = Field(default='', max_length=200)


class WarehouseOut(DBModel):
    id: int
    name: str
    location: str


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    parent_id: int | None = None


class CategoryOut(DBModel):
    id: int
    name: str
    parent_id: int | None


class RecommendationOut(BaseModel):
    product: 'ProductOut'
    score: float
    reason: str


class RecommendationFeedback(BaseModel):
    event: Literal['impression', 'click']
    product_ids: list[int] = Field(min_length=1, max_length=50)


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
