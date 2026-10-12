"""Create safe synthetic demo data. Only available in development environments.

Usage: python -m scripts.seed_demo
Demo accounts are printed. Do not use this in production or on real data.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from app.database import SessionLocal
from app.config import settings
from app.models import User, Vendor, CustomerProfile, Product, Inventory, Order, OrderItem, InventoryMovement, Interaction
from app.security import hash_password


def main():
    if settings.environment == 'production':
        raise SystemExit('Demo data loading is forbidden in production')
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == 'demo.admin@example.com')):
            print('Demo data already loaded')
            return
        admin = User(email='demo.admin@example.com', password_hash=hash_password('DemoAdmin123!'), role='admin')
        db.add(admin)
        vendors = []
        for name, category, email in [
            ('Aurora Electronics','Electronics','aurora@example.com'),
            ('The Reading Room','Books','books@example.com'),
            ('Urban Essentials','Home','urban@example.com')]:
            v = Vendor(business_name=name, owner_name='Demo Seller', email=email, phone='1234567890', category=category, status='approved')
            db.add(v)
            db.flush()
            db.add(User(email=email, password_hash=hash_password('DemoVendor123!'), role='vendor', vendor_id=v.id))
            vendors.append(v)
        customers = []
        for n in range(1, 9):
            u = User(email=f'customer{n}@example.com', password_hash=hash_password('DemoCustomer123!'), role='customer')
            db.add(u)
            db.flush()
            db.add(CustomerProfile(user_id=u.id, full_name=f'Demo Customer {n}'))
            customers.append(u)
        products = []
        sample = [
            (0,'Mechanical Keyboard','Compact typing comfort', 'Electronics', Decimal('79.00'), 26),
            (0,'Wireless Headphones','All-day listening', 'Electronics', Decimal('129.00'), 14),
            (0,'USB-C Dock','Powerful desk setup', 'Electronics', Decimal('59.00'), 6),
            (1,'Data Science Handbook','Practical learning reference', 'Books', Decimal('38.00'), 34),
            (1,'Python Cookbook','Recipes for developers', 'Books', Decimal('44.00'), 17),
            (1,'Productivity Planner','Paper goals, real progress', 'Books', Decimal('22.00'), 11),
            (2,'Desk Organizer','A tidier workspace', 'Home', Decimal('18.00'), 36),
            (2,'LED Desk Lamp','Warm adjustable light', 'Home', Decimal('36.00'), 9),
            (2,'Ceramic Coffee Mug','Simple everyday style', 'Home', Decimal('16.00'), 18)]
        for v_idx, name, description, category, price, stock in sample:
            p = Product(vendor_id=vendors[v_idx].id, name=name, description=description, category=category, price=price)
            p.inventory = Inventory(quantity=stock, low_stock_threshold=7)
            db.add(p)
            db.flush()
            products.append(p)
            db.add(InventoryMovement(product_id=p.id, delta=stock, reason='initial_stock'))
        # Synthetic order history spread across recent days and products.
        now = datetime.now(timezone.utc)
        for n in range(36):
            p = products[(n*5 + n//3) % len(products)]
            qty = 1 + (n % 2)
            o = Order(customer_id=customers[n % len(customers)].id,
                      created_at=now-timedelta(days=1+(n % 18), hours=n % 10), total=p.price*qty)
            db.add(o)
            db.flush()
            db.add(OrderItem(order_id=o.id, product_id=p.id, vendor_id=p.vendor_id, quantity=qty, unit_price=p.price))
            p.inventory.quantity = max(0, p.inventory.quantity-qty)
            db.add(InventoryMovement(product_id=p.id, delta=-qty, reason='sale', created_at=o.created_at))
        for n in range(12):
            db.add(Interaction(customer_id=customers[n%8].id, product_id=products[(n+2)%9].id,
                               event_type='view', created_at=now-timedelta(days=n)))
        db.commit()
        print('Demo loaded. Admin: demo.admin@example.com / DemoAdmin123!')
        print('Vendor: aurora@example.com / DemoVendor123!')
        print('Customer: customer1@example.com / DemoCustomer123!')


if __name__ == '__main__':
    main()
