"""Advanced revenue analysis and marketplace benchmarking (Milestone 3, Module 2).

Pandas functions take the sales-line frame produced by
``app.services.intelligence.load_sales`` (columns ``order_id``, ``customer_id``,
``product_id``, ``vendor_id``, ``timestamp``, ``date``, ``quantity``,
``unit_price``, ``amount``, ``category``). ``live_kpis`` runs SQL directly so
the real-time dashboard always matches the database.

Definitions
* GMV: sum of quantity x unit price on non-cancelled orders.
* AOV: GMV / number of orders.
* Growth: (current - previous) / previous x 100, for equal-length periods.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

FREQ = {'day': 'D', 'week': 'W-SUN', 'month': 'ME'}


# ----------------------------------------------------------------------- live
def live_kpis(db: Session, vendor_id: int | None = None) -> dict:
    """Headline KPIs straight from the database (no cache)."""
    scope = 'AND oi.vendor_id = :vid' if vendor_id is not None else ''
    stock_scope = 'AND p.vendor_id = :vid' if vendor_id is not None else ''
    now = datetime.now(timezone.utc)
    params = {'vid': vendor_id, 'today': now.replace(hour=0, minute=0, second=0, microsecond=0),
              'hour': now - timedelta(hours=1)}
    row = db.execute(text(f"""
        SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gmv,
               COUNT(DISTINCT oi.order_id) AS orders,
               COALESCE(SUM(oi.quantity), 0) AS units,
               COUNT(DISTINCT o.customer_id) AS customers,
               COALESCE(SUM(CASE WHEN o.created_at >= :today THEN oi.quantity * oi.unit_price END), 0) AS gmv_today,
               COUNT(DISTINCT CASE WHEN o.created_at >= :today THEN oi.order_id END) AS orders_today,
               COUNT(DISTINCT CASE WHEN o.created_at >= :hour THEN oi.order_id END) AS orders_last_hour
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.status != 'cancelled' {scope}"""), params).one()
    stock = db.execute(text(f"""
        SELECT COUNT(*) AS products,
               COALESCE(SUM(CASE WHEN i.quantity <= i.low_stock_threshold THEN 1 ELSE 0 END), 0) AS low_stock,
               COALESCE(SUM(CASE WHEN i.quantity <= 0 THEN 1 ELSE 0 END), 0) AS out_of_stock,
               COALESCE(SUM(i.quantity), 0) AS units_in_stock
        FROM products p JOIN inventory i ON i.product_id = p.id
        WHERE p.is_active {stock_scope}"""), params).one()
    gmv, orders = float(row.gmv), int(row.orders)
    return {
        'gmv': round(gmv, 2), 'orders': orders, 'units_sold': int(row.units), 'customers': int(row.customers),
        'average_order_value': round(gmv / orders, 2) if orders else 0.0,
        'gmv_today': round(float(row.gmv_today), 2), 'orders_today': int(row.orders_today),
        'orders_last_hour': int(row.orders_last_hour),
        'products': int(stock.products), 'low_stock_products': int(stock.low_stock),
        'out_of_stock_products': int(stock.out_of_stock), 'units_in_stock': int(stock.units_in_stock),
        'as_of': now.isoformat(timespec='seconds'),
    }


# ------------------------------------------------------------------- revenue
def _prep(sales: pd.DataFrame) -> pd.DataFrame:
    frame = sales.copy()
    frame['date'] = pd.to_datetime(frame['date']).dt.tz_localize(None).dt.normalize()
    return frame


def revenue_series(sales: pd.DataFrame, granularity: str = 'month', periods: int = 12,
                   as_of: pd.Timestamp | None = None) -> list[dict]:
    """GMV, orders, units and AOV per period with period-over-period growth.

    A period that has not finished yet (the current week or month) is kept but
    marked ``partial`` and gets no growth figure, so a half month is never
    read as a drop.
    """
    if sales.empty:
        return []
    frame = _prep(sales)
    end = pd.Timestamp(as_of).normalize() if as_of is not None else frame['date'].max()
    grouped = (frame.set_index('date').groupby(pd.Grouper(freq=FREQ[granularity]))
               .agg(gmv=('amount', 'sum'), orders=('order_id', 'nunique'), units=('quantity', 'sum'),
                    customers=('customer_id', 'nunique')))
    grouped['aov'] = (grouped['gmv'] / grouped['orders'].replace(0, np.nan)).round(2)
    grouped['growth_pct'] = (grouped['gmv'].pct_change() * 100).replace([np.inf, -np.inf], np.nan).round(1)
    if granularity == 'day':
        grouped['gmv_7d_avg'] = grouped['gmv'].rolling(7, min_periods=1).mean().round(2)
        grouped['partial'] = False
    else:
        grouped['partial'] = grouped.index > end  # label is the period's last day
        grouped.loc[grouped['partial'], 'growth_pct'] = np.nan
    grouped = grouped.tail(periods).reset_index()
    grouped['period'] = grouped['date'].dt.strftime('%Y-%m-%d' if granularity != 'month' else '%Y-%m')
    grouped['gmv'] = grouped['gmv'].round(2)
    grouped['partial'] = grouped['partial'].astype(bool)
    return _records(grouped.drop(columns='date'))


def growth_summary(sales: pd.DataFrame, as_of: pd.Timestamp | None = None) -> dict:
    """Last 30 days vs the 30 before, and the last complete month vs the one before."""
    if sales.empty:
        return {'last_30_days_gmv': 0, 'previous_30_days_gmv': 0, 'growth_30d_pct': None,
                'last_month': None, 'last_month_gmv': 0, 'month_over_month_pct': None}
    frame = _prep(sales)
    end = pd.Timestamp(as_of).normalize() if as_of is not None else frame['date'].max()
    last = frame.loc[frame['date'] > end - pd.to_timedelta(30, unit='D'), 'amount'].sum()
    prev = frame.loc[(frame['date'] <= end - pd.to_timedelta(30, unit='D')) & (frame['date'] > end - pd.to_timedelta(60, unit='D')),
                     'amount'].sum()
    monthly = frame.set_index('date')['amount'].resample('ME').sum()
    complete = monthly[monthly.index < end.to_period('M').start_time]
    mom = None
    if len(complete) >= 2 and complete.iloc[-2] > 0:
        mom = round(float(complete.iloc[-1] / complete.iloc[-2] - 1) * 100, 1)
    return {
        'last_30_days_gmv': round(float(last), 2), 'previous_30_days_gmv': round(float(prev), 2),
        'growth_30d_pct': round(float(last / prev - 1) * 100, 1) if prev > 0 else None,
        'last_month': complete.index[-1].strftime('%Y-%m') if len(complete) else None,
        'last_month_gmv': round(float(complete.iloc[-1]), 2) if len(complete) else 0,
        'month_over_month_pct': mom,
    }


def category_mix(sales: pd.DataFrame, parents: dict[str, str] | None = None, days: int = 90,
                 as_of: pd.Timestamp | None = None) -> list[dict]:
    """GMV share by category for the last ``days`` and growth vs the period before."""
    if sales.empty:
        return []
    frame = _prep(sales)
    end = pd.Timestamp(as_of).normalize() if as_of is not None else frame['date'].max()
    cur = frame.loc[frame['date'] > end - pd.to_timedelta(days, unit='D')]
    prev = frame.loc[(frame['date'] <= end - pd.to_timedelta(days, unit='D')) & (frame['date'] > end - pd.to_timedelta(2 * days, unit='D'))]
    a = cur.groupby('category')['amount'].sum()
    b = prev.groupby('category')['amount'].sum()
    out = pd.DataFrame({'gmv': a, 'previous_gmv': b}).fillna(0)
    out['share_pct'] = (out['gmv'] / out['gmv'].sum() * 100).round(1) if out['gmv'].sum() else 0
    out['growth_pct'] = np.where(out['previous_gmv'] > 0, ((out['gmv'] / out['previous_gmv'] - 1) * 100).round(1), np.nan)
    out = out.reset_index().rename(columns={'index': 'category'}).sort_values('gmv', ascending=False)
    out['parent'] = out['category'].map(parents or {}).fillna(out['category'])
    out['gmv'] = out['gmv'].round(2)
    out['previous_gmv'] = out['previous_gmv'].round(2)
    return _records(out)


def pareto(sales: pd.DataFrame, key: str = 'product_id') -> dict:
    """How concentrated GMV is: share earned by the top 20% of products or vendors."""
    if sales.empty:
        return {'top_20_pct_share': None, 'items': 0, 'curve': []}
    totals = sales.groupby(key)['amount'].sum().sort_values(ascending=False)
    cum = totals.cumsum() / totals.sum() * 100
    n = len(totals)
    top = max(1, int(np.ceil(n * 0.2)))
    curve = [{'items_pct': round((i + 1) / n * 100, 1), 'gmv_pct': round(float(v), 1)} for i, v in enumerate(cum)]
    return {'top_20_pct_share': round(float(cum.iloc[top - 1]), 1), 'items': n, 'top_items': top, 'curve': curve}


def cohort_retention(sales: pd.DataFrame, months: int = 12) -> dict:
    """Monthly acquisition cohorts: share of each cohort buying again k months later."""
    if sales.empty:
        return {'cohorts': [], 'matrix': []}
    frame = _prep(sales)
    frame['month'] = frame['date'].dt.to_period('M')
    first = frame.groupby('customer_id')['month'].min().rename('cohort')
    frame = frame.join(first, on='customer_id')
    frame['age'] = (frame['month'] - frame['cohort']).apply(lambda d: d.n)
    active = frame.groupby(['cohort', 'age'])['customer_id'].nunique().unstack(fill_value=0)
    sizes = active[0] if 0 in active else active.iloc[:, 0]
    rate = (active.div(sizes, axis=0) * 100).round(1)
    rate = rate.iloc[-months:, : months + 1]
    last = frame['month'].max()
    matrix, month1 = [], []
    for cohort, row in rate.iterrows():
        reachable = (last - cohort).n  # months this cohort has had time to come back
        matrix.append([float(row[a]) if a <= reachable else None for a in rate.columns])
        if reachable >= 1 and 1 in rate.columns:
            month1.append(float(row[1]))
    return {
        'cohorts': [str(c) for c in rate.index], 'sizes': [int(sizes[c]) for c in rate.index],
        'ages': [int(a) for a in rate.columns], 'matrix': matrix,
        'average_month_1_pct': round(float(np.mean(month1)), 1) if month1 else None,
    }


# --------------------------------------------------------------- benchmarking
def vendor_benchmark(sales: pd.DataFrame, vendors: pd.DataFrame, inventory: pd.DataFrame | None = None,
                     days: int = 90, as_of: pd.Timestamp | None = None) -> dict:
    """Rank vendors on GMV, growth, AOV and repeat rate for the last ``days``.

    ``vendors`` needs ``vendor_id`` and ``vendor``. Percentiles are 0-100
    (100 = best in marketplace). The composite score is the mean of the four
    percentiles, so no single metric dominates.
    """
    if sales.empty or vendors.empty:
        return {'days': days, 'vendors': [], 'marketplace': {}}
    frame = _prep(sales)
    end = pd.Timestamp(as_of).normalize() if as_of is not None else frame['date'].max()
    cur = frame.loc[frame['date'] > end - pd.to_timedelta(days, unit='D')]
    prev = frame.loc[(frame['date'] <= end - pd.to_timedelta(days, unit='D')) & (frame['date'] > end - pd.to_timedelta(2 * days, unit='D'))]
    g = cur.groupby('vendor_id')
    table = pd.DataFrame({
        'gmv': g['amount'].sum(), 'orders': g['order_id'].nunique(), 'units': g['quantity'].sum(),
        'customers': g['customer_id'].nunique(),
    })
    per_customer = cur.groupby(['vendor_id', 'customer_id'])['order_id'].nunique()
    table['repeat_rate_pct'] = (per_customer.gt(1).groupby(level=0).mean() * 100).round(1)
    table['previous_gmv'] = prev.groupby('vendor_id')['amount'].sum()
    table = table.reindex(vendors['vendor_id']).fillna({'gmv': 0, 'orders': 0, 'units': 0, 'customers': 0,
                                                         'repeat_rate_pct': 0, 'previous_gmv': 0})
    table['aov'] = np.where(table['orders'] > 0, table['gmv'] / table['orders'], 0).round(2)
    table['growth_pct'] = np.where(table['previous_gmv'] > 0, (table['gmv'] / table['previous_gmv'] - 1) * 100,
                                   np.nan).round(1)
    total = table['gmv'].sum()
    table['share_pct'] = (table['gmv'] / total * 100).round(1) if total else 0.0
    table['rank'] = table['gmv'].rank(ascending=False, method='min').astype(int)
    for col in ('gmv', 'growth_pct', 'aov', 'repeat_rate_pct'):
        table[f'{col}_percentile'] = (table[col].rank(pct=True, method='average') * 100).round(0)
    table['score'] = table[[c for c in table.columns if c.endswith('_percentile')]].mean(axis=1).round(0)
    if inventory is not None and not inventory.empty:
        stock = inventory.groupby('vendor_id').agg(products=('product_id', 'count'),
                                                   out_of_stock=('current_stock', lambda s: int((s <= 0).sum())))
        table = table.join(stock)
        table['in_stock_rate_pct'] = ((1 - table['out_of_stock'] / table['products']) * 100).round(1)
    table = table.join(vendors.set_index('vendor_id')['vendor']).reset_index().sort_values('rank')
    table['gmv'] = table['gmv'].round(2)
    market = {
        'vendors': int(len(table)), 'gmv': round(float(total), 2),
        'median_gmv': round(float(table['gmv'].median()), 2),
        'p25_gmv': round(float(table['gmv'].quantile(.25)), 2), 'p75_gmv': round(float(table['gmv'].quantile(.75)), 2),
        'median_growth_pct': _num(table['growth_pct'].median()), 'median_aov': round(float(table['aov'].median()), 2),
        'median_repeat_rate_pct': _num(table['repeat_rate_pct'].median()),
    }
    return {'days': days, 'as_of': end.date().isoformat(), 'vendors': _records(table.drop(columns=['previous_gmv'])),
            'marketplace': market}


def anonymise_benchmark(bench: dict, vendor_id: int) -> dict:
    """A vendor's own row plus marketplace distribution, without other vendors' identities."""
    own = next((v for v in bench['vendors'] if v['vendor_id'] == vendor_id), None)
    peers = sorted(v['gmv'] for v in bench['vendors'])
    return {'days': bench['days'], 'as_of': bench.get('as_of'), 'you': own, 'marketplace': bench['marketplace'],
            'peer_gmv_distribution': peers}


# ------------------------------------------------------------------- helpers
def _num(v):
    return None if v is None or pd.isna(v) else round(float(v), 1)


def _records(frame: pd.DataFrame) -> list[dict]:
    out = frame.astype(object).where(pd.notna(frame), None)
    rows = out.to_dict('records')
    for row in rows:
        for k, v in row.items():
            if isinstance(v, np.integer):
                row[k] = int(v)
            elif isinstance(v, np.floating):
                row[k] = float(v)
            elif isinstance(v, pd.Period):
                row[k] = str(v)
    return rows
