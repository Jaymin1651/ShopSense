"""Relational schema for multi-vendor marketplace and analytics."""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import String, Integer, DateTime, ForeignKey, Numeric, UniqueConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # admin/vendor/customer
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey('vendors.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vendor(Base):
    __tablename__ = 'vendors'
    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(200))
    owner_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(100))
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('10.00'))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey('vendors.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(100), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    inventory: Mapped['Inventory'] = relationship(back_populates='product', uselist=False, cascade='all,delete-orphan')


class Inventory(Base):
    __tablename__ = 'inventory'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), unique=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)
    product: Mapped[Product] = relationship(back_populates='inventory')


class InventoryMovement(Base):
    __tablename__ = 'inventory_movements'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerProfile(Base):
    __tablename__ = 'customer_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))


class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='placed')
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    items: Mapped[list['OrderItem']] = relationship(back_populates='order', cascade='all,delete-orphan', lazy='selectin')


class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    vendor_id: Mapped[int] = mapped_column(ForeignKey('vendors.id'), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # snapshot at time of sale
    order: Mapped[Order] = relationship(back_populates='items')


class Interaction(Base):
    __tablename__ = 'interactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


Index('ix_order_items_vendor_order', OrderItem.vendor_id, OrderItem.order_id)
