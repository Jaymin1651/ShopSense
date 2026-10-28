"""Load live marketplace rows into DataFrames and run the Milestone 2 engines.

Routers call these helpers; the analytics themselves live in
``app.inventory``, ``app.customer`` and ``app.recommendation`` and know
nothing about SQLAlchemy. Trained models are cached in-process and keyed by a
fingerprint of the data, so a new order or interaction triggers a retrain on
the next request while repeat requests stay fast.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customer.analytics import behaviour_summary, conversion_funnel, customer_stats, purchase_frequency_distribution
from app.customer.segmentation import segment_customers
from app.inventory.inventory_forecasting import DemandForecaster, MIN_TRAIN_WEEKS, forecast_series, weekly_series
from app.inventory.inventory_tracking import inventory_status, portfolio_turnover, turnover_table
from app.inventory.stock_alert import demand_from_history, low_stock_alert, replenishment
from app.models import (Category, Interaction, Inventory, InventoryMovement, Order, OrderItem, Product, Vendor,
                        Warehouse)
from app.recommendation.recommendation import HybridRecommender, build_events

REPORT_PATH = Path(__file__).resolve().parents[2] / 'reports' / 'milestone2_evaluation.json'
_CACHE: dict[str, tuple[float, object, object]] = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 900


def _cached(name: str, fingerprint, build):
    with _LOCK:
        hit = _CACHE.get(name)
        if hit and hit[1] == fingerprint and time.time() - hit[0] < CACHE_SECONDS:
            return hit[2]
    value = build()
    with _LOCK:
        _CACHE[name] = (time.time(), fingerprint, value)
    return value


def clear_cache():
    with _LOCK:
        _CACHE.clear()


def _now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)


# ---------------------------------------------------------------------- loaders

def load_sales(db: Session, vendor_id: int | None = None) -> pd.DataFrame:
    stmt = (select(OrderItem.order_id, Order.customer_id, OrderItem.product_id, OrderItem.vendor_id,
                   Order.created_at, OrderItem.quantity, OrderItem.unit_price, Product.category)
            .join(Order, Order.id == OrderItem.order_id).join(Product, Product.id == OrderItem.product_id)
            .where(Order.status != 'cancelled'))
    if vendor_id is not None:
        stmt = stmt.where(OrderItem.vendor_id == vendor_id)
    rows = db.execute(stmt).all()
    frame = pd.DataFrame(rows, columns=['order_id', 'customer_id', 'product_id', 'vendor_id', 'timestamp',
                                        'quantity', 'unit_price', 'category'])
    if frame.empty:
        return frame.assign(date=pd.Series(dtype='datetime64[ns]'), amount=pd.Series(dtype=float))
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True).dt.tz_localize(None)
    frame['date'] = frame['timestamp'].dt.normalize()
    frame['unit_price'] = frame['unit_price'].astype(float)
    frame['amount'] = frame['unit_price'] * frame['quantity']
    return frame


def load_inventory(db: Session, vendor_id: int | None = None) -> pd.DataFrame:
    stmt = (select(Product.id, Product.name, Product.category, Product.vendor_id, Vendor.business_name,
                   Product.price, Product.unit_cost, Product.is_active, Inventory.quantity,
                   Inventory.low_stock_threshold, Inventory.lead_time_days, Inventory.warehouse_id,
                   Warehouse.name, Inventory.last_updated)
            .join(Inventory, Inventory.product_id == Product.id).join(Vendor, Vendor.id == Product.vendor_id)
            .outerjoin(Warehouse, Warehouse.id == Inventory.warehouse_id).order_by(Product.id))
    if vendor_id is not None:
        stmt = stmt.where(Product.vendor_id == vendor_id)
    frame = pd.DataFrame(db.execute(stmt).all(), columns=[
        'product_id', 'name', 'category', 'vendor_id', 'vendor', 'price', 'unit_cost', 'is_active',
        'current_stock', 'reorder_level', 'lead_time_days', 'warehouse_id', 'warehouse', 'last_updated'])
    for col in ('price', 'unit_cost'):
        frame[col] = pd.to_numeric(frame[col], errors='coerce')
    frame['lead_time_days'] = frame['lead_time_days'].fillna(7).astype(int)
    return frame


def load_movements(db: Session, product_ids: list[int] | None = None) -> pd.DataFrame:
    stmt = select(InventoryMovement.product_id, InventoryMovement.delta, InventoryMovement.reason,
                  InventoryMovement.created_at)
    if product_ids is not None:
        stmt = stmt.where(InventoryMovement.product_id.in_(product_ids))
    return pd.DataFrame(db.execute(stmt).all(), columns=['product_id', 'delta', 'reason', 'created_at'])


def load_interactions(db: Session) -> pd.DataFrame:
    stmt = select(Interaction.customer_id, Interaction.product_id, Interaction.event_type, Interaction.created_at)
    return pd.DataFrame(db.execute(stmt).all(), columns=['customer_id', 'product_id', 'event_type', 'timestamp'])


def sales_fingerprint(db: Session):
    return tuple(db.execute(select(func.count(OrderItem.id), func.max(OrderItem.id))).one())


def events_fingerprint(db: Session):
    return sales_fingerprint(db) + tuple(db.execute(select(func.count(Interaction.id),
                                                           func.max(Interaction.id))).one())


# --------------------------------------------------------------------- inventory

def forecaster(db: Session) -> tuple[DemandForecaster | None, pd.DataFrame]:
    """Pooled weekly model trained on every product's sales (cached)."""
    def build():
        sales = load_sales(db)
        if sales.empty:
            return None, pd.DataFrame(columns=['series', 'week', 'units'])
        weekly = weekly_series(sales, 'product_id', end=_now())
        weeks = weekly['week'].nunique() if not weekly.empty else 0
        if weeks < MIN_TRAIN_WEEKS:
            return None, weekly
        return DemandForecaster(n_estimators=150).fit(weekly), weekly
    return _cached('forecaster', sales_fingerprint(db), build)


def demand_table(db: Session, products: list[int]) -> pd.DataFrame:
    """Expected daily demand per product: next-week ML forecast / 7 if a model
    exists, otherwise the last 8 weeks' empirical average (cached)."""
    table = _cached('demand', sales_fingerprint(db), lambda: _demand_all(db))
    table = table.loc[table['product_id'].isin(products)].reset_index(drop=True)
    for col in ('daily_demand', 'daily_demand_std'):
        if col in table:
            table[col] = pd.to_numeric(table[col], errors='coerce').astype(float)
    return table


def _demand_all(db: Session) -> pd.DataFrame:
    products = list(db.scalars(select(Product.id)).all())
    sales = load_sales(db)
    empirical = demand_from_history(sales, end=_now()) if not sales.empty else pd.DataFrame(
        columns=['product_id', 'daily_demand', 'daily_demand_std'])
    model, weekly = forecaster(db)
    if model is None or weekly.empty:
        return empirical.assign(demand_source='8_week_average')
    rows = []
    for pid in products:
        history = weekly.loc[weekly['series'] == str(pid)].set_index('week')['units'].sort_index()
        if len(history) >= MIN_TRAIN_WEEKS:
            rows.append({'product_id': pid, 'daily_demand': model.predict_next(history, str(pid)) / 7})
    ml = pd.DataFrame(rows, columns=['product_id', 'daily_demand'])
    merged = empirical.drop(columns='daily_demand').merge(ml, on='product_id', how='outer')
    merged['demand_source'] = np.where(merged['daily_demand'].notna(), 'random_forest_weekly', '8_week_average')
    fallback = empirical.set_index('product_id')['daily_demand']
    merged['daily_demand'] = merged['daily_demand'].fillna(merged['product_id'].map(fallback))
    return merged


def _clean(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    frame = frame[[c for c in columns if c in frame]].copy()
    frame = frame.astype(object).where(pd.notna(frame), None)
    for col in frame.columns:
        frame[col] = frame[col].map(lambda v: v.isoformat() if hasattr(v, 'isoformat') else
                                    (float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else v))
    return frame.to_dict('records')


STATUS_COLUMNS = ['product_id', 'name', 'category', 'vendor', 'warehouse', 'current_stock', 'reorder_level',
                  'lead_time_days', 'status', 'daily_demand', 'days_of_cover', 'demand_source', 'last_updated']


def stock_status(db: Session, vendor_id: int | None) -> list[dict]:
    inv = load_inventory(db, vendor_id)
    if inv.empty:
        return []
    demand = demand_table(db, inv['product_id'].tolist())
    frame = inventory_status(inv).merge(demand, on='product_id', how='left')
    frame['daily_demand'] = frame['daily_demand'].round(2)
    frame['days_of_cover'] = np.where(frame['daily_demand'] > 0,
                                      (frame['current_stock'] / frame['daily_demand']).round(1), np.nan)
    return _clean(frame, STATUS_COLUMNS)


def alerts(db: Session, vendor_id: int | None) -> list[dict]:
    inv = load_inventory(db, vendor_id)
    if inv.empty:
        return []
    inv = inv.loc[inv['is_active']]
    demand = demand_table(db, inv['product_id'].tolist())
    frame = low_stock_alert(inv, demand)
    frame['daily_demand'] = frame['daily_demand'].round(2)
    return _clean(frame, ['product_id', 'name', 'vendor', 'warehouse', 'current_stock', 'reorder_level',
                          'lead_time_days', 'daily_demand', 'days_of_cover', 'severity', 'message'])


def replenishment_plan(db: Session, vendor_id: int | None, service_level: float, review_days: int,
                       include_all: bool = False) -> list[dict]:
    inv = load_inventory(db, vendor_id)
    if inv.empty:
        return []
    inv = inv.loc[inv['is_active']]
    demand = demand_table(db, inv['product_id'].tolist())
    frame = replenishment(inv, demand, service_level=service_level, review_days=review_days,
                          only_needed=not include_all)
    frame['daily_demand'] = frame['daily_demand'].round(2)
    return _clean(frame, ['product_id', 'name', 'vendor', 'warehouse', 'current_stock', 'reorder_level',
                          'lead_time_days', 'daily_demand', 'days_of_cover', 'safety_stock', 'order_up_to',
                          'reorder_qty', 'order_value', 'method'])


def turnover(db: Session, vendor_id: int | None, days: int) -> dict:
    inv = load_inventory(db, vendor_id)
    if inv.empty:
        return {'days': days, 'portfolio': {'turnover': None, 'basis': 'units'}, 'products': []}
    sales = load_sales(db, vendor_id)
    movements = load_movements(db, inv['product_id'].tolist())
    table = turnover_table(inv, sales if not sales.empty else pd.DataFrame(columns=['product_id', 'date', 'quantity']),
                           days=days, end=_now(), movements=movements)
    table = table.merge(inv[['product_id', 'name', 'category']], on='product_id')
    return {'days': days, 'portfolio': portfolio_turnover(table, inv),
            'products': _clean(table.sort_values('turnover', ascending=False, na_position='last'),
                               ['product_id', 'name', 'category', 'units_sold', 'average_inventory_units', 'turnover',
                                'annualised_turnover', 'cogs', 'days_of_cover', 'basis']),
            'formula': 'turnover = COGS / average inventory value (cost basis) or units sold / average units (units basis)'}


def product_forecast(db: Session, product: Product, weeks: int) -> dict:
    model, weekly = forecaster(db)
    result = forecast_series(weekly, str(product.id), weeks, model)
    stock = product.inventory.quantity
    next_week = result['weekly'][0]['forecast'] if result['weekly'] else 0
    daily = next_week / 7
    cumulative, runs_out = 0.0, None
    for row in result['weekly']:
        cumulative += row['forecast']
        if runs_out is None and cumulative >= stock:
            runs_out = row['week']
    result.update({
        'product_id': product.id, 'product': product.name, 'current_stock': stock,
        'reorder_level': product.inventory.low_stock_threshold, 'lead_time_days': product.inventory.lead_time_days,
        'predicted_daily_units': round(daily, 2),
        'forecast_units_total': round(sum(r['forecast'] for r in result['weekly']), 1),
        'estimated_days_of_stock': round(stock / daily, 1) if daily > 0 else None,
        'stock_runs_out_week': runs_out,
        'interval': 'Approximate 80% range from training residuals, widened with horizon.',
    })
    return result


def inventory_overview(db: Session, vendor_id: int | None) -> dict:
    status = stock_status(db, vendor_id)
    if not status:
        return {'products': 0, 'units_in_stock': 0, 'low_stock': 0, 'out_of_stock': 0, 'turnover_90d': None,
                'forecast_units_next_7_days': 0, 'reorder_lines': 0, 'reorder_units': 0, 'forecast_method': None}
    frame = pd.DataFrame(status)
    plan = replenishment_plan(db, vendor_id, 0.95, 7)
    turn = turnover(db, vendor_id, 90)['portfolio']
    model, _ = forecaster(db)
    return {
        'products': len(frame), 'units_in_stock': int(frame['current_stock'].sum()),
        'low_stock': int((frame['status'] == 'Low stock').sum()),
        'out_of_stock': int((frame['status'] == 'Out of stock').sum()),
        'turnover_90d': turn.get('turnover'), 'turnover_basis': turn.get('basis'),
        'forecast_units_next_7_days': round(float(frame['daily_demand'].fillna(0).sum() * 7), 1),
        'reorder_lines': len(plan), 'reorder_units': int(sum(p['reorder_qty'] for p in plan)),
        'reorder_value': round(sum(p.get('order_value') or 0 for p in plan), 2),
        'forecast_method': 'random_forest_weekly' if model is not None else '8_week_average',
        'by_status': frame['status'].value_counts().to_dict(),
    }


# ---------------------------------------------------------------------- customers

def customer_overview(db: Session, vendor_id: int | None) -> dict:
    sales = load_sales(db, vendor_id)
    if sales.empty:
        return {'summary': behaviour_summary(pd.DataFrame()), 'frequency': [], 'funnel': None, 'monthly_active': []}
    stats = customer_stats(sales, as_of=_now())
    interactions = load_interactions(db)
    if vendor_id is not None and not interactions.empty:
        own = set(load_inventory(db, vendor_id)['product_id'])
        interactions = interactions.loc[interactions['product_id'].isin(own)]
    monthly = (sales.assign(month=sales['date'].dt.to_period('M').astype(str))
               .groupby('month').agg(active_customers=('customer_id', 'nunique'), orders=('order_id', 'nunique'),
                                     revenue=('amount', 'sum')).reset_index().tail(18))
    monthly['revenue'] = monthly['revenue'].round(2)
    return {'summary': behaviour_summary(stats), 'frequency': purchase_frequency_distribution(stats),
            'funnel': conversion_funnel(interactions, sales), 'monthly_active': monthly.to_dict('records')}


def customer_segments(db: Session, vendor_id: int | None, k: int | None) -> dict:
    sales = load_sales(db, vendor_id)
    stats = customer_stats(sales, as_of=_now()) if not sales.empty else pd.DataFrame()

    def build():
        return segment_customers(stats, k=k, stability_runs=5)
    if len(stats) < 10:
        return {'available': False, 'reason': 'K-Means needs at least 10 customers with purchases.',
                'customers': int(len(stats))}
    result = _cached(f'segments:{vendor_id}:{k}', sales_fingerprint(db), build)
    points = result['assignments'].sample(min(1500, len(result['assignments'])), random_state=1)
    return {'available': True, 'k': result['k'], 'method': result['method'], 'metrics': result['metrics'],
            'profiles': result['profiles'].to_dict('records'),
            'points': _clean(points, ['customer_id', 'recency_days', 'orders', 'total_spent', 'segment'])}


# ----------------------------------------------------------------- recommendations

def recommender(db: Session) -> HybridRecommender | None:
    def build():
        events = build_events(load_interactions(db), load_sales(db))
        if events.empty:
            return None
        products = pd.DataFrame(db.execute(select(Product.id, Product.name, Product.category)).all(),
                                columns=['product_id', 'name', 'category'])
        return HybridRecommender().fit(events, products)
    return _cached('recommender', events_fingerprint(db), build)


def available_products(db: Session) -> dict[int, Product]:
    stmt = (select(Product).join(Vendor).join(Inventory)
            .where(Product.is_active.is_(True), Vendor.status == 'approved', Inventory.quantity > 0))
    return {p.id: p for p in db.scalars(stmt).all()}


def recommend_for(db: Session, customer_id: int, limit: int, exclude: str = 'purchased') -> list[tuple[Product, dict]]:
    catalogue = available_products(db)
    model = recommender(db)
    if model is None:
        ranked = [{'product_id': pid, 'score': 0.0, 'reason': 'New in the catalogue'} for pid in sorted(catalogue, reverse=True)]
    else:
        ranked = model.recommend(customer_id, k=limit, exclude=exclude, candidates=set(catalogue))
        if len(ranked) < limit:  # products the model has never seen
            known = {r['product_id'] for r in ranked} | (model.seen.get(customer_id, set()) if exclude == 'seen'
                                                          else model.purchased.get(customer_id, set()))
            ranked += [{'product_id': pid, 'score': 0.0, 'reason': 'New in the catalogue'}
                       for pid in sorted(catalogue, reverse=True) if pid not in known]
    return [(catalogue[r['product_id']], r) for r in ranked[:limit] if r['product_id'] in catalogue]


def recommendation_metrics(db: Session) -> dict:
    rows = pd.DataFrame(db.execute(select(Interaction.customer_id, Interaction.product_id, Interaction.event_type,
                                          Interaction.created_at)
                                   .where(Interaction.event_type.in_(['rec_impression', 'rec_click']))).all(),
                        columns=['customer_id', 'product_id', 'event_type', 'timestamp'])
    impressions = int((rows['event_type'] == 'rec_impression').sum()) if not rows.empty else 0
    clicks = int((rows['event_type'] == 'rec_click').sum()) if not rows.empty else 0
    by_product = []
    attributed = 0
    if not rows.empty:
        counts = rows.pivot_table(index='product_id', columns='event_type', values='customer_id',
                                  aggfunc='count', fill_value=0)
        for col in ('rec_impression', 'rec_click'):
            if col not in counts:
                counts[col] = 0
        counts['ctr_pct'] = np.where(counts['rec_impression'] > 0,
                                     (counts['rec_click'] / counts['rec_impression'] * 100).round(1), 0.0)
        names = dict(db.execute(select(Product.id, Product.name).where(Product.id.in_(counts.index.tolist()))).all())
        counts = counts.reset_index().sort_values('rec_click', ascending=False).head(15)
        by_product = [{'product_id': int(r.product_id), 'product': names.get(int(r.product_id), f'#{r.product_id}'),
                       'impressions': int(r.rec_impression), 'clicks': int(r.rec_click), 'ctr_pct': float(r.ctr_pct)}
                      for r in counts.itertuples()]
        clicked = rows.loc[rows['event_type'] == 'rec_click']
        if not clicked.empty:
            sales = load_sales(db)
            first_click = clicked.groupby(['customer_id', 'product_id'])['timestamp'].min().reset_index()
            first_click['timestamp'] = pd.to_datetime(first_click['timestamp'], utc=True).dt.tz_localize(None)
            joined = sales.merge(first_click, on=['customer_id', 'product_id'], suffixes=('', '_click'))
            attributed = int((joined['timestamp'] >= joined['timestamp_click']).sum())
    return {'impressions': impressions, 'clicks': clicks,
            'ctr_pct': round(clicks / impressions * 100, 2) if impressions else None,
            'purchases_after_click': attributed, 'by_product': by_product}


def evaluation_report() -> dict | None:
    if not REPORT_PATH.exists():
        return None
    return json.loads(REPORT_PATH.read_text())


def category_tree(db: Session) -> list[dict]:
    rows = db.scalars(select(Category).order_by(Category.name)).all()
    children: dict[int | None, list[Category]] = {}
    for c in rows:
        children.setdefault(c.parent_id, []).append(c)

    def node(c: Category) -> dict:
        return {'id': c.id, 'name': c.name, 'parent_id': c.parent_id,
                'children': [node(x) for x in children.get(c.id, [])]}
    return [node(c) for c in children.get(None, [])]
