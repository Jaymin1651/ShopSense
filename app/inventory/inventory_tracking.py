"""Inventory tracking: stock status, turnover rate and days of cover.

All functions take plain pandas DataFrames so they work the same on the
synthetic CSV files in ``data/`` and on rows loaded from the live database.

Expected inventory columns: ``product_id``, ``current_stock``, ``reorder_level``.
"""
from __future__ import annotations

import pandas as pd

STATUS_ORDER = ['Out of stock', 'Low stock', 'Available']


def inventory_status(inventory: pd.DataFrame) -> pd.DataFrame:
    """Label each row Available, Low stock (at or below reorder level) or Out of stock.

    The milestone brief used ``current_stock > reorder_level``; stock exactly at
    the reorder point is treated as low, which matches how a reorder point works.
    """
    result = inventory.copy()
    stock = result['current_stock']
    result['status'] = 'Available'
    result.loc[stock <= result['reorder_level'], 'status'] = 'Low stock'
    result.loc[stock <= 0, 'status'] = 'Out of stock'
    return result


def turnover_rate(cogs: float, avg_inventory: float) -> float:
    """Inventory turnover = cost of goods sold / average inventory (both in money).

    >>> turnover_rate(100000, 25000)
    4.0
    """
    if avg_inventory <= 0:
        raise ValueError('Average inventory must be positive')
    return round(cogs / avg_inventory, 2)


def reconstruct_stock_levels(current_stock: int, movements: pd.DataFrame,
                             start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Rebuild end-of-day stock for one product by walking movements backwards.

    ``movements`` needs ``created_at`` and ``delta`` (signed units). Today's
    stock is known, so stock at the end of an earlier day equals current stock
    minus every movement recorded after that day.
    """
    days = pd.date_range(start.normalize(), end.normalize(), freq='D')
    if movements.empty:
        return pd.Series(float(current_stock), index=days)
    moved = movements.assign(day=pd.to_datetime(movements['created_at'], utc=True)
                             .dt.tz_localize(None).dt.normalize())
    daily = moved.groupby('day')['delta'].sum()
    after_end = daily[daily.index > days[-1]].sum()
    in_window = daily.reindex(days, fill_value=0)
    # Stock at end of day d = stock at end of window - movements after d.
    end_of_window = current_stock - after_end
    later = in_window[::-1].cumsum()[::-1].shift(-1, fill_value=0)
    return (end_of_window - later).clip(lower=0).astype(float)


def turnover_table(inventory: pd.DataFrame, sales: pd.DataFrame, days: int = 90,
                   end: pd.Timestamp | None = None, movements: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-product turnover over the last ``days`` days.

    ``sales`` needs ``product_id``, ``date`` and ``quantity``; ``unit_cost`` on
    ``inventory`` turns unit turnover into the money-based COGS formula. When
    stock movements are available, average inventory is the mean of the
    reconstructed daily stock level; otherwise it is the mean of opening and
    closing stock, where opening = closing + units sold in the window.
    """
    end = pd.Timestamp(end or pd.Timestamp.now()).normalize()
    start = end - pd.to_timedelta(days - 1, unit='D')
    window = sales.loc[pd.to_datetime(sales['date']).between(start, end + pd.to_timedelta(86399, unit='s'))]
    sold = window.groupby('product_id')['quantity'].sum()
    rows = []
    for item in inventory.itertuples(index=False):
        units = float(sold.get(item.product_id, 0))
        if movements is not None and not movements.empty:
            levels = reconstruct_stock_levels(item.current_stock, movements.loc[movements['product_id'] == item.product_id],
                                              start, end)
            avg_units = float(levels.mean())
        else:
            avg_units = (item.current_stock + (item.current_stock + units)) / 2
        cost = getattr(item, 'unit_cost', None)
        has_cost = cost is not None and pd.notna(cost) and float(cost) > 0
        unit_turnover = round(units / avg_units, 2) if avg_units > 0 else None
        daily = units / days
        rows.append({
            'product_id': item.product_id,
            'units_sold': int(units),
            'average_inventory_units': round(avg_units, 1),
            'turnover': unit_turnover,
            'annualised_turnover': round(unit_turnover * 365 / days, 2) if unit_turnover is not None else None,
            'cogs': round(units * float(cost), 2) if has_cost else None,
            'days_of_cover': round(item.current_stock / daily, 1) if daily > 0 else None,
            'basis': 'cost' if has_cost else 'units',
        })
    return pd.DataFrame(rows)


def portfolio_turnover(table: pd.DataFrame, inventory: pd.DataFrame) -> dict:
    """Store-wide turnover: COGS / average inventory value when costs exist, else units."""
    merged = table.merge(inventory[['product_id'] + (['unit_cost'] if 'unit_cost' in inventory else [])],
                         on='product_id', how='left')
    if 'unit_cost' in merged and merged['unit_cost'].notna().all() and len(merged):
        avg_value = float((merged['average_inventory_units'] * merged['unit_cost']).sum())
        cogs = float(merged['cogs'].sum())
        value = turnover_rate(cogs, avg_value) if avg_value > 0 else None
        return {'turnover': value, 'basis': 'cost', 'cogs': round(cogs, 2), 'average_inventory_value': round(avg_value, 2)}
    avg_units = float(merged['average_inventory_units'].sum()) if len(merged) else 0
    units = float(merged['units_sold'].sum()) if len(merged) else 0
    return {'turnover': round(units / avg_units, 2) if avg_units > 0 else None, 'basis': 'units',
            'units_sold': int(units), 'average_inventory_units': round(avg_units, 1)}
