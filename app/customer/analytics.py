"""Customer behaviour analytics from order lines and interaction events.

Transactions need ``customer_id``, ``order_id``, ``product_id``, ``date`` and
``amount`` (line value). Interactions need ``customer_id``, ``product_id`` and
``event_type`` (view / cart / wishlist).
"""
from __future__ import annotations

import pandas as pd


def customer_stats(transactions: pd.DataFrame, as_of: pd.Timestamp | None = None,
                   categories: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per customer: orders, spend, AOV, recency, tenure and breadth."""
    tx = transactions.copy()
    tx['date'] = pd.to_datetime(tx['date']).dt.tz_localize(None).dt.normalize()
    as_of = pd.Timestamp(as_of).normalize() if as_of is not None else tx['date'].max() + pd.to_timedelta(1, unit='D')
    if categories is not None and 'category' not in tx:
        tx = tx.merge(categories[['product_id', 'category']], on='product_id', how='left')
    agg = {'orders': ('order_id', 'nunique'), 'total_spent': ('amount', 'sum'), 'items': ('quantity', 'sum'),
           'first_purchase': ('date', 'min'), 'last_purchase': ('date', 'max'),
           'distinct_products': ('product_id', 'nunique')}
    if 'category' in tx:
        agg['distinct_categories'] = ('category', 'nunique')
    stats = tx.groupby('customer_id').agg(**agg).reset_index()
    stats['average_order_value'] = (stats['total_spent'] / stats['orders']).round(2)
    stats['recency_days'] = (as_of - stats['last_purchase']).dt.days
    stats['tenure_days'] = (as_of - stats['first_purchase']).dt.days
    months_active = (stats['tenure_days'] / 30.44).clip(lower=1)
    stats['orders_per_month'] = (stats['orders'] / months_active).round(3)
    stats['total_spent'] = stats['total_spent'].round(2)
    return stats


def behaviour_summary(stats: pd.DataFrame, top_n: int = 10) -> dict:
    """Headline KPIs for the customer dashboard."""
    if stats.empty:
        return {'customers': 0, 'average_spending': 0, 'average_order_value': 0, 'repeat_rate_pct': 0,
                'median_recency_days': None, 'top_customers': []}
    total_orders = stats['orders'].sum()
    top = stats.sort_values('total_spent', ascending=False).head(top_n)
    return {
        'customers': int(len(stats)),
        'average_spending': round(float(stats['total_spent'].mean()), 2),
        'median_spending': round(float(stats['total_spent'].median()), 2),
        'average_order_value': round(float(stats['total_spent'].sum() / total_orders), 2) if total_orders else 0,
        'orders_per_customer': round(float(stats['orders'].mean()), 2),
        'repeat_rate_pct': round(float((stats['orders'] > 1).mean() * 100), 1),
        'median_recency_days': int(stats['recency_days'].median()),
        'top_customers': top[['customer_id', 'orders', 'total_spent', 'average_order_value', 'recency_days']]
        .to_dict('records'),
    }


def purchase_frequency_distribution(stats: pd.DataFrame) -> list[dict]:
    bins = [0, 1, 2, 4, 9, 19, float('inf')]
    labels = ['1 order', '2 orders', '3-4 orders', '5-9 orders', '10-19 orders', '20+ orders']
    counts = pd.cut(stats['orders'], bins=bins, labels=labels).value_counts().reindex(labels, fill_value=0)
    return [{'bucket': k, 'customers': int(v)} for k, v in counts.items()]


def conversion_funnel(interactions: pd.DataFrame, transactions: pd.DataFrame) -> dict:
    """Customer-product pairs that were viewed, carted and bought."""
    if interactions.empty:
        return {'viewed': 0, 'carted': 0, 'purchased': 0, 'view_to_cart_pct': None, 'cart_to_purchase_pct': None}
    pairs = lambda df: set(zip(df['customer_id'], df['product_id']))  # noqa: E731
    viewed = pairs(interactions.loc[interactions['event_type'] == 'view'])
    carted = pairs(interactions.loc[interactions['event_type'] == 'cart'])
    bought = pairs(transactions)
    carted_after_view = carted & viewed
    bought_after_cart = bought & carted
    return {
        'viewed': len(viewed), 'carted': len(carted), 'purchased': len(bought),
        'view_to_cart_pct': round(len(carted_after_view) / len(viewed) * 100, 1) if viewed else None,
        'cart_to_purchase_pct': round(len(bought_after_cart) / len(carted) * 100, 1) if carted else None,
    }
