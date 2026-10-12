"""Aggregate business metrics from immutable order item price snapshots."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Order, OrderItem, Product, Vendor, Inventory, Interaction, CustomerProfile, User


def sales_rows(db: Session, vendor_id: int | None = None):
    stmt = (select(OrderItem, Order).join(Order, Order.id == OrderItem.order_id)
            .where(Order.status != 'cancelled').order_by(Order.created_at))
    if vendor_id is not None:
        stmt = stmt.where(OrderItem.vendor_id == vendor_id)
    return db.execute(stmt).all()


def get_summary(db: Session, vendor_id: int | None = None):
    rows = sales_rows(db, vendor_id)
    gmv = sum((line.quantity*line.unit_price for line, _ in rows), Decimal('0.00'))
    order_ids = {order.id for _, order in rows}
    if vendor_id is None:
        order_count = db.query(Order).filter(Order.status != 'cancelled').count()
        product_stmt = select(Product)
    else:
        order_count = len(order_ids)
        product_stmt = select(Product).where(Product.vendor_id == vendor_id)
    products = db.scalars(product_stmt).all()
    low_stock = sum(1 for p in products if p.inventory and p.inventory.quantity <= p.inventory.low_stock_threshold)
    active = sum(1 for p in products if p.is_active)
    return {'gmv': float(gmv), 'orders': order_count,
            'average_order_value': round(float(gmv)/order_count, 2) if order_count else 0,
            'products': len(products), 'active_products': active, 'low_stock_products': low_stock,
            'note': 'GMV = item selling price × quantity; payment settlement, shipping, tax, fees, refunds and profit not included.'}


def get_trends(db: Session, vendor_id: int | None = None, days: int = 30):
    start = datetime.now(timezone.utc).date() - timedelta(days=days-1)
    aggregates = defaultdict(Decimal)
    for line, order in sales_rows(db, vendor_id):
        d = order.created_at.date()
        if d >= start:
            aggregates[d] += line.unit_price * line.quantity
    return [{'date': (start + timedelta(days=i)).isoformat(), 'gmv': float(aggregates[start+timedelta(days=i)])}
            for i in range(days)]


def get_top_products(db: Session, vendor_id: int | None = None, limit: int = 10):
    amounts = defaultdict(Decimal)
    units = defaultdict(int)
    for line, _ in sales_rows(db, vendor_id):
        amounts[line.product_id] += line.quantity*line.unit_price
        units[line.product_id] += line.quantity
    ranked = sorted(amounts, key=lambda p: amounts[p], reverse=True)[:limit]
    names = {p.id: p.name for p in db.scalars(select(Product).where(Product.id.in_(ranked))).all()} if ranked else {}
    return [{'product_id': pid, 'product': names.get(pid, f'#{pid}'), 'gmv': float(amounts[pid]), 'units': units[pid]} for pid in ranked]


def get_vendor_ranking(db: Session):
    amounts = defaultdict(Decimal)
    for line, _ in sales_rows(db):
        amounts[line.vendor_id] += line.quantity*line.unit_price
    return [{'vendor_id': v.id, 'vendor': v.business_name, 'status': v.status, 'gmv': float(amounts[v.id])}
            for v in sorted(db.scalars(select(Vendor)).all(), key=lambda v: amounts[v.id], reverse=True)]


def get_forecast(db: Session, product_id: int, horizon: int = 7):
    """Moving-average baseline; 7-day daily demand, not a trained ML forecast."""
    product = db.get(Product, product_id)
    if not product:
        return None
    today = datetime.now(timezone.utc).date()
    units = defaultdict(int)
    for item, order in db.execute(select(OrderItem, Order).join(Order).where(OrderItem.product_id == product_id, Order.status != 'cancelled')).all():
        units[order.created_at.date()] += item.quantity
    window = [units[today-timedelta(days=d)] for d in range(1, 8)]
    mean = round(sum(window)/len(window), 2)
    return {'product_id': product_id, 'product': product.name, 'method': '7_day_moving_average_baseline',
            'history_days': 7, 'predicted_daily_units': mean,
            'forecast': [{'date': (today+timedelta(days=d)).isoformat(), 'predicted_units': mean} for d in range(1, horizon+1)],
            'current_stock': product.inventory.quantity, 'estimated_days_of_stock':
                round(product.inventory.quantity/mean, 1) if mean > 0 else None,
            'warning': 'Baseline estimate only; not validated or ML-trained.'}


def get_customer_segments(db: Session, vendor_id: int | None = None):
    """Transparent rule-based segments from distinct historical customer purchases."""
    today = datetime.now(timezone.utc)
    data = defaultdict(lambda: {'orders': set(), 'total': Decimal(0), 'last': None})
    for item, order in sales_rows(db, vendor_id):
        record = data[order.customer_id]
        record['orders'].add(order.id)
        record['total'] += item.unit_price*item.quantity
        if record['last'] is None or order.created_at > record['last']:
            record['last'] = order.created_at
    segments = defaultdict(int)
    for customer in data.values():
        last = customer['last']
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        inactive_days = (today-last).days
        if inactive_days > 60:
            segment = 'At risk'
        elif len(customer['orders']) >= 3:
            segment = 'Loyal'
        elif len(customer['orders']) == 1:
            segment = 'New'
        else:
            segment = 'Repeat'
        segments[segment] += 1
    return {'method': 'rule_based_purchase_frequency_recency', 'segments': [{'segment': s, 'customers': segments[s]} for s in ['New','Repeat','Loyal','At risk']]}
