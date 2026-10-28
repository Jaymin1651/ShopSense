"""Low-stock alerts and replenishment recommendations.

Inventory columns used: ``product_id``, ``current_stock``, ``reorder_level`` and
optionally ``lead_time_days``. Demand columns (optional, per product):
``daily_demand`` (forecast mean units/day) and ``daily_demand_std``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# One-sided z values for common cycle service levels.
Z_SCORES = {0.80: 0.84, 0.85: 1.04, 0.90: 1.28, 0.95: 1.65, 0.975: 1.96, 0.99: 2.33}


def z_for(service_level: float) -> float:
    closest = min(Z_SCORES, key=lambda s: abs(s - service_level))
    return Z_SCORES[closest]


def low_stock_alert(inventory: pd.DataFrame, demand: pd.DataFrame | None = None,
                    default_lead_time: int = 7) -> pd.DataFrame:
    """Rows at or below their reorder level, ranked by urgency.

    Severity:
    * ``critical``: out of stock, or forecast says stock runs out before a new
      order could arrive (days of cover < lead time).
    * ``warning``: at or below the reorder level.
    """
    frame = _with_demand(inventory, demand, default_lead_time)
    flagged = frame.loc[(frame['current_stock'] <= frame['reorder_level'])
                        | (frame['days_of_cover'].notna() & (frame['days_of_cover'] < frame['lead_time_days']))].copy()
    runs_out = flagged['days_of_cover'].notna() & (flagged['days_of_cover'] < flagged['lead_time_days'])
    flagged['severity'] = np.where((flagged['current_stock'] <= 0) | runs_out, 'critical', 'warning')
        # apply() on an empty frame returns a DataFrame, so build the column from a list.
    flagged['message'] = [_message(row) for _, row in flagged.iterrows()]
    order = {'critical': 0, 'warning': 1}
    flagged['_rank'] = flagged['severity'].map(order)
    flagged = flagged.sort_values(['_rank', 'days_of_cover', 'current_stock'], na_position='last')
    return flagged.drop(columns='_rank').reset_index(drop=True)


def replenishment(inventory: pd.DataFrame, demand: pd.DataFrame | None = None, service_level: float = 0.95,
                  review_days: int = 7, default_lead_time: int = 7, only_needed: bool = True) -> pd.DataFrame:
    """Recommended order quantity per product (order-up-to policy).

    With a demand forecast:
        safety stock   = z * daily_std * sqrt(lead_time)
        order-up-to    = max(daily_demand * (lead_time + review_days) + safety stock,
                             2 * reorder_level)
        reorder_qty    = max(0, ceil(order-up-to - current_stock))
    The ``2 * reorder_level`` floor keeps the plan consistent with the alerts:
    a product at or below its reorder level always gets an order.
    Without one (new product, no sales yet) it falls back to the milestone
    brief's rule: reorder_qty = 2 * reorder_level - current_stock.
    """
    frame = _with_demand(inventory, demand, default_lead_time)
    z = z_for(service_level)
    has = frame['daily_demand'].notna() & (frame['daily_demand'] > 0)
    lead = frame['lead_time_days'].astype(float)
    std = frame['daily_demand_std'].fillna(frame['daily_demand'].pow(0.5))  # Poisson-like default
    safety = (z * std * np.sqrt(lead)).where(has)
    target = np.maximum(frame['daily_demand'] * (lead + review_days) + safety,
                        2 * frame['reorder_level']).where(has)
    fallback = 2 * frame['reorder_level'] - frame['current_stock']
    qty = np.where(has, target - frame['current_stock'], fallback)
    frame['safety_stock'] = safety.round(1)
    frame['order_up_to'] = target.round(1)
    frame['reorder_qty'] = [max(0, math.ceil(q)) if pd.notna(q) else 0 for q in qty]
    frame['method'] = np.where(has, f'forecast_order_up_to_sl{int(service_level * 100)}', 'rule_2x_reorder_level')
    frame['needs_order'] = (frame['reorder_qty'] > 0) & (
        (frame['current_stock'] <= frame['reorder_level'])
        | (frame['days_of_cover'].notna() & (frame['days_of_cover'] < lead + review_days)))
    if only_needed:
        frame = frame.loc[frame['needs_order']]
    if 'unit_cost' in frame:
        frame['order_value'] = (frame['reorder_qty'] * frame['unit_cost']).round(2)
    return frame.sort_values(['days_of_cover', 'current_stock'], na_position='last').reset_index(drop=True)


def _with_demand(inventory: pd.DataFrame, demand: pd.DataFrame | None, default_lead_time: int) -> pd.DataFrame:
    frame = inventory.copy()
    if 'lead_time_days' not in frame:
        frame['lead_time_days'] = default_lead_time
    frame['lead_time_days'] = frame['lead_time_days'].fillna(default_lead_time).astype(int)
    if demand is not None and not demand.empty:
        cols = ['product_id'] + [c for c in ('daily_demand', 'daily_demand_std') if c in demand]
        frame = frame.drop(columns=[c for c in cols[1:] if c in frame]).merge(demand[cols], on='product_id', how='left')
    for col in ('daily_demand', 'daily_demand_std'):
        if col not in frame:
            frame[col] = np.nan
    rate = frame['daily_demand']
    frame['days_of_cover'] = np.where(rate > 0, (frame['current_stock'] / rate).round(1), np.nan)
    return frame


def _message(row) -> str:
    if row['current_stock'] <= 0:
        return 'Out of stock. Reorder now.'
    if pd.notna(row['days_of_cover']) and row['days_of_cover'] < row['lead_time_days']:
        left = max(1, round(row['days_of_cover']))
        return (f"About {left} day{'s' if left != 1 else ''} of stock left; a new order takes "
                f"{row['lead_time_days']} days to arrive.")
    return f"{int(row['current_stock'])} in stock, at or below the reorder level of {int(row['reorder_level'])}."


def demand_from_history(sales: pd.DataFrame, end: pd.Timestamp | None = None, days: int = 56) -> pd.DataFrame:
    """Empirical daily demand mean and standard deviation over a recent window."""
    end = pd.Timestamp(end or pd.Timestamp.now()).normalize()
    start = end - pd.to_timedelta(days - 1, unit='D')
    dates = pd.to_datetime(sales['date']).dt.tz_localize(None).dt.normalize()
    window = sales.loc[dates.between(start, end)].assign(day=dates)
    grid = pd.date_range(start, end, freq='D')
    rows = []
    for pid, grp in window.groupby('product_id'):
        daily = grp.groupby('day')['quantity'].sum().reindex(grid, fill_value=0)
        rows.append({'product_id': pid, 'daily_demand': float(daily.mean()), 'daily_demand_std': float(daily.std(ddof=1))})
    return pd.DataFrame(rows, columns=['product_id', 'daily_demand', 'daily_demand_std'])
