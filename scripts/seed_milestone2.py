"""Load the synthetic Milestone 2 dataset (``data/*.csv``) into the database.

Usage: python -m scripts.seed_milestone2

Development only. Creates 3 warehouses, a two-level category tree, 5 approved
vendors, 58 products, 1,400 customers and two years of orders, stock
movements and browsing events. Dates are shifted so the history ends
yesterday, which keeps "last 30 days" charts and forecasts meaningful.

Logins printed at the end:
  admin    demo.admin@example.com    / DemoAdmin123!
  vendor   vendor1@shopsense.example / DemoVendor123!
  customer shopper1@shopsense.example / DemoShopper123!
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, select

from app.config import settings
from app.database import SessionLocal
from app.models import (Category, CustomerProfile, Interaction, Inventory, InventoryMovement, Order, OrderItem,
                        Product, User, Vendor, Warehouse)
from app.security import hash_password

DATA = Path(__file__).resolve().parents[1] / 'data'


def _read(name: str) -> pd.DataFrame:
    path = DATA / f'{name}.csv'
    if not path.exists():
        raise SystemExit(f'Missing {path}. Run: python -m scripts.generate_milestone2_data')
    return pd.read_csv(path)


def main():
    if settings.environment == 'production':
        raise SystemExit('Demo data loading is forbidden in production')
    tables = {n: _read(n) for n in ('warehouses', 'categories', 'vendors', 'products', 'inventory', 'customers',
                                     'transactions', 'interactions')}
    tx = tables['transactions']
    tx['ts'] = pd.to_datetime(tx['timestamp'])
    yesterday = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=1)
    shift = yesterday - tx['ts'].max().normalize().to_pydatetime()
    tx['ts'] = tx['ts'] + shift

    with SessionLocal() as db:
        if db.scalar(select(Warehouse).where(Warehouse.name == 'West Hub')):
            print('Milestone 2 data already loaded')
            return
        if not db.scalar(select(User).where(User.email == 'demo.admin@example.com')):
            db.add(User(email='demo.admin@example.com', password_hash=hash_password('DemoAdmin123!'), role='admin'))

        warehouses = {}
        for w in tables['warehouses'].itertuples():
            obj = Warehouse(name=w.warehouse_name, location=w.location)
            db.add(obj)
            warehouses[w.warehouse_id] = obj
        categories = {}
        for c in tables['categories'].itertuples():
            existing = db.scalar(select(Category).where(Category.name == c.category_name))
            obj = existing or Category(name=c.category_name)
            if pd.notna(c.parent_id):
                obj.parent_id = categories[int(c.parent_id)].id
            db.add(obj)
            db.flush()
            categories[c.category_id] = obj

        vendor_hash = hash_password('DemoVendor123!')
        vendors = {}
        for v in tables['vendors'].itertuples():
            email = f'vendor{v.vendor_id}@shopsense.example'
            obj = Vendor(business_name=v.business_name, owner_name='Demo Seller', email=email, phone='9876543210',
                         category=v.category, status='approved')
            db.add(obj)
            db.flush()
            db.add(User(email=email, password_hash=vendor_hash, role='vendor', vendor_id=obj.id))
            vendors[v.vendor_id] = obj
        db.flush()

        inv = tables['inventory'].set_index('product_id')
        products = {}
        for p in tables['products'].itertuples():
            row = inv.loc[p.product_id]
            obj = Product(vendor_id=vendors[p.vendor_id].id, name=p.product_name, category=p.category,
                          description=f'{p.parent_category} / {p.category}', price=Decimal(str(p.price)),
                          unit_cost=Decimal(str(p.unit_cost)))
            obj.inventory = Inventory(quantity=int(row.current_stock), low_stock_threshold=int(row.reorder_level),
                                      lead_time_days=int(row.lead_time_days),
                                      warehouse_id=warehouses[int(row.warehouse_id)].id)
            db.add(obj)
            products[p.product_id] = obj
        db.flush()

        shopper_hash = hash_password('DemoShopper123!')
        users = {}
        for c in tables['customers'].itertuples():
            u = User(email=f'shopper{c.customer_id}@shopsense.example', password_hash=shopper_hash, role='customer',
                     created_at=pd.Timestamp(c.signup_date).to_pydatetime() + shift)
            db.add(u)
            users[c.customer_id] = u
        db.flush()
        db.execute(insert(CustomerProfile), [{'user_id': u.id, 'full_name': f'Demo Shopper {cid}'}
                                             for cid, u in users.items()])

        print(f'Loading {tx["order_id"].nunique():,} orders...')
        for order_id, lines in tx.groupby('order_id', sort=False):
            first = lines.iloc[0]
            order = Order(customer_id=users[int(first.customer_id)].id, status='placed',
                          total=Decimal(str(round(float(lines['amount'].sum()), 2))),
                          created_at=first.ts.to_pydatetime().replace(tzinfo=timezone.utc))
            order.items = [OrderItem(product_id=products[int(r.product_id)].id, vendor_id=products[int(r.product_id)].vendor_id,
                                     quantity=int(r.quantity), unit_price=Decimal(str(r.unit_price)))
                           for r in lines.itertuples()]
            db.add(order)
        db.flush()

        # Ledger: opening stock covers everything later sold, so deltas sum to current stock.
        start = (tx['ts'].min() - timedelta(days=1)).to_pydatetime().replace(tzinfo=timezone.utc)
        sold = tx.groupby('product_id')['quantity'].sum()
        movements = [{'product_id': obj.id, 'delta': int(obj.inventory.quantity + sold.get(pid, 0)),
                      'reason': 'initial_stock', 'created_at': start} for pid, obj in products.items()]
        movements += [{'product_id': products[int(r.product_id)].id, 'delta': -int(r.quantity), 'reason': 'sale',
                       'created_at': r.ts.to_pydatetime().replace(tzinfo=timezone.utc)} for r in tx.itertuples()]
        db.execute(insert(InventoryMovement), movements)

        events = tables['interactions']
        events['ts'] = pd.to_datetime(events['timestamp']) + shift
        db.execute(insert(Interaction), [
            {'customer_id': users[int(e.customer_id)].id, 'product_id': products[int(e.product_id)].id,
             'event_type': e.event_type, 'created_at': e.ts.to_pydatetime().replace(tzinfo=timezone.utc)}
            for e in events.itertuples()])
        db.commit()
    print('Milestone 2 demo data loaded (synthetic).')
    print('  admin    demo.admin@example.com     / DemoAdmin123!')
    print('  vendor   vendor1@shopsense.example  / DemoVendor123!')
    print('  customer shopper1@shopsense.example / DemoShopper123!')


if __name__ == '__main__':
    main()
