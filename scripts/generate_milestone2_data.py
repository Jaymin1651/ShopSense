"""Generate the reproducible synthetic Milestone 2 dataset in ``data/``.

Usage: python -m scripts.generate_milestone2_data [--seed 42] [--out data]

Everything here is synthetic. Customers are simulated with behavioural
personas (frequent, regular, occasional, lapsed) and stable category
preferences, demand follows a yearly festive-season pattern plus a mild trend,
and every random draw comes from one seeded generator so the files are
byte-for-byte reproducible. The ``persona`` column is the simulation's ground
truth and is only used to audit clustering; models never train on it.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

START = pd.Timestamp('2024-10-01')
END = pd.Timestamp('2026-09-30')

WAREHOUSES = [
    (1, 'West Hub', 'Ahmedabad'),
    (2, 'North Hub', 'Delhi'),
    (3, 'South Hub', 'Bengaluru'),
]

# (category_id, name, parent_id)  parent rows first.
CATEGORIES = [
    (1, 'Electronics', None), (2, 'Fashion', None), (3, 'Home', None), (4, 'Books', None),
    (5, 'Mobile', 1), (6, 'Laptop', 1), (7, 'Accessories', 1),
    (8, 'Men', 2), (9, 'Women', 2),
    (10, 'Kitchen', 3), (11, 'Decor', 3),
    (12, 'Fiction', 4), (13, 'Technical', 4),
]

# leaf -> (price median, n products, relative popularity, vendor_id)
LEAVES = {
    'Mobile': (420.0, 5, 1.0, 1), 'Laptop': (900.0, 4, 0.5, 1), 'Accessories': (35.0, 8, 1.6, 2),
    'Men': (45.0, 7, 1.2, 3), 'Women': (55.0, 8, 1.4, 3),
    'Kitchen': (40.0, 6, 1.0, 4), 'Decor': (30.0, 6, 0.8, 4),
    'Fiction': (16.0, 8, 1.1, 5), 'Technical': (42.0, 6, 0.7, 5),
}
VENDORS = [
    (1, 'Aurora Electronics', 'Electronics', 6),
    (2, 'Gadget Lane', 'Electronics', 4),
    (3, 'Thread & Loom', 'Fashion', 9),
    (4, 'Urban Nest', 'Home', 7),
    (5, 'The Reading Room', 'Books', 5),
]
# Shopping season (yearly). Values are multipliers on daily order intensity.
MONTH_FACTOR = {1: .85, 2: .82, 3: .92, 4: .95, 5: 1.0, 6: .95, 7: .9, 8: 1.0,
                9: 1.05, 10: 1.3, 11: 1.55, 12: 1.3}
# Category-specific bumps on top of the global season.
CATEGORY_SEASON = {
    'Electronics': {10: 1.25, 11: 1.45},
    'Fashion': {3: 1.15, 10: 1.35, 11: 1.2},
    'Home': {10: 1.3, 11: 1.15, 12: 1.1},
    'Books': {6: 1.35, 7: 1.3, 12: 1.15},
}
PERSONAS = {
    # share, orders per 30 days, items per order (poisson mean + 1), active fraction of period
    'frequent': (0.08, 2.4, 1.6, 1.0),
    'regular': (0.30, 0.75, 0.9, 1.0),
    'occasional': (0.42, 0.16, 0.5, 1.0),
    'lapsed': (0.20, 0.55, 0.7, 0.35),
}


def _parents():
    by_id = {c[0]: c for c in CATEGORIES}
    return {name: by_id[parent][1] for _, name, parent in CATEGORIES if parent}


def build(seed: int = 42, n_customers: int = 1400) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    parent_of = _parents()
    days = pd.date_range(START, END, freq='D')
    n_days = len(days)
    day_start = [d.to_pydatetime() for d in days]
    month = days.month.to_numpy()
    weekday = days.weekday.to_numpy()
    trend = 1 + 0.18 * np.arange(n_days) / 365
    season = np.array([MONTH_FACTOR[m] for m in month]) * np.where(weekday >= 5, 1.12, 1.0) * trend

    # Products
    rows, pid = [], 101
    for leaf, (median, count, _, vendor_id) in LEAVES.items():
        for rank in range(count):
            price = round(float(median * rng.lognormal(0, .35)), 2)
            margin = rng.uniform(.25, .45)
            rows.append({'product_id': pid, 'vendor_id': vendor_id,
                         'product_name': f'{leaf} item {rank + 1:02d}', 'category': leaf,
                         'parent_category': parent_of[leaf], 'price': price,
                         'unit_cost': round(price * (1 - margin), 2), 'popularity_rank': rank + 1})
            pid += 1
    products = pd.DataFrame(rows)
    leaf_names = list(LEAVES)
    leaf_weight = np.array([LEAVES[c][2] for c in leaf_names])
    leaf_weight = leaf_weight / leaf_weight.sum()
    # Zipf-like popularity inside each leaf category.
    in_leaf = {leaf: products.loc[products.category == leaf] for leaf in leaf_names}
    leaf_probs = {leaf: (1 / df.popularity_rank.to_numpy() ** 0.9) / (1 / df.popularity_rank.to_numpy() ** 0.9).sum()
                  for leaf, df in in_leaf.items()}

    # Customers
    persona_names = list(PERSONAS)
    shares = np.array([PERSONAS[p][0] for p in persona_names])
    personas = rng.choice(persona_names, size=n_customers, p=shares / shares.sum())
    customers, lines, interactions = [], [], []
    order_id, line_id = 1, 1
    for cid, persona in enumerate(personas, start=1):
        _, rate, basket, active_share = PERSONAS[persona]
        rate = rate * rng.lognormal(0, .25)
        signup = int(rng.integers(0, int(n_days * (0.15 if persona in ('frequent', 'lapsed') else 0.7))))
        stop = n_days if active_share >= 1 else int(signup + n_days * active_share * rng.uniform(.6, 1.1))
        stop = min(stop, n_days)
        favourites = rng.choice(leaf_names, size=2, replace=False, p=leaf_weight)
        customers.append({'customer_id': cid, 'signup_date': days[signup].date().isoformat(),
                          'city': rng.choice(['Ahmedabad', 'Mumbai', 'Delhi', 'Bengaluru', 'Pune', 'Jaipur']),
                          'favourite_categories': '|'.join(favourites), 'persona': persona})
        intensity = rate / 30 * season[signup:stop]
        order_days = np.flatnonzero(rng.random(stop - signup) < intensity) + signup
        for d in order_days:
            n_items = 1 + min(rng.poisson(basket), 4)
            m = int(month[d])
            chosen = set()
            for _ in range(n_items):
                if rng.random() < 0.78:
                    leaf = favourites[0] if rng.random() < 0.62 else favourites[1]
                else:
                    w = leaf_weight * np.array([CATEGORY_SEASON.get(parent_of[c], {}).get(m, 1.0) for c in leaf_names])
                    leaf = rng.choice(leaf_names, p=w / w.sum())
                product = int(rng.choice(in_leaf[leaf].product_id.to_numpy(), p=leaf_probs[leaf]))
                if product in chosen:
                    continue
                chosen.add(product)
                qty = 1 + int(rng.random() < (0.28 if persona == 'frequent' else 0.15))
                price = float(products.loc[products.product_id == product, 'price'].iloc[0])
                vendor = int(products.loc[products.product_id == product, 'vendor_id'].iloc[0])
                ts = day_start[d] + timedelta(minutes=int(rng.integers(8 * 60, 23 * 60)))
                lines.append({'transaction_id': line_id, 'order_id': order_id, 'customer_id': cid,
                              'product_id': product, 'vendor_id': vendor, 'timestamp': ts,
                              'quantity': qty, 'unit_price': price, 'amount': round(price * qty, 2)})
                # Funnel events that preceded the purchase.
                for minutes, event in ((-35, 'view'), (-12, 'cart')):
                    interactions.append({'customer_id': cid, 'product_id': product, 'event_type': event,
                                         'timestamp': ts + timedelta(minutes=minutes)})
                line_id += 1
            if chosen:
                order_id += 1
        # Browsing that did not convert: mostly inside favourite categories.
        n_browse = rng.poisson(max(len(order_days), 1) * 1.6)
        for _ in range(n_browse):
            d = int(rng.integers(signup, stop)) if stop > signup else signup
            leaf = rng.choice(favourites) if rng.random() < 0.7 else rng.choice(leaf_names, p=leaf_weight)
            product = int(rng.choice(in_leaf[leaf].product_id.to_numpy(), p=leaf_probs[leaf]))
            ts = day_start[min(d, n_days - 1)] + timedelta(minutes=int(rng.integers(8 * 60, 23 * 60)))
            event = 'cart' if rng.random() < 0.12 else 'view'
            interactions.append({'customer_id': cid, 'product_id': product, 'event_type': event, 'timestamp': ts})

    transactions = pd.DataFrame(lines).sort_values(['timestamp', 'transaction_id']).reset_index(drop=True)
    transactions['date'] = transactions['timestamp'].dt.date.astype(str)
    transactions['timestamp'] = transactions['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S')
    interactions_df = pd.DataFrame(interactions).sort_values('timestamp').reset_index(drop=True)
    interactions_df['timestamp'] = interactions_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S')

    customers_df = pd.DataFrame(customers)
    totals = (transactions.groupby('customer_id')
              .agg(total_orders=('order_id', 'nunique'), total_spent=('amount', 'sum')).reset_index())
    customers_df = customers_df.merge(totals, on='customer_id', how='left')
    customers_df['total_orders'] = customers_df['total_orders'].fillna(0).astype(int)
    customers_df['total_spent'] = customers_df['total_spent'].fillna(0).round(2)

    sales_history = (transactions.groupby(['date', 'product_id'], as_index=False)['quantity'].sum()
                     .rename(columns={'quantity': 'quantity_sold'}))

    # Inventory snapshot at END: stock cover between a few days and two months.
    cutoff = (END - pd.DateOffset(days=56)).date().isoformat()
    last8 = transactions.loc[transactions['date'] > cutoff]
    daily = last8.groupby('product_id')['quantity'].sum() / 56
    inv_rows = []
    lead_by_vendor = {1: 10, 2: 7, 3: 6, 4: 9, 5: 5}
    for p in products.itertuples():
        rate = float(daily.get(p.product_id, 0.05))
        lead = lead_by_vendor[p.vendor_id]
        reorder = max(5, int(np.ceil(rate * lead * 1.3)))
        cover_days = rng.choice([rng.uniform(0, 4), rng.uniform(4, 14), rng.uniform(14, 70)], p=[.15, .3, .55])
        inv_rows.append({'product_id': p.product_id, 'vendor_id': p.vendor_id,
                         'warehouse_id': 1 + (p.product_id % 3), 'current_stock': int(round(rate * cover_days)),
                         'reorder_level': reorder, 'lead_time_days': lead,
                         'last_updated': END.date().isoformat()})
    inventory = pd.DataFrame(inv_rows)

    return {
        'warehouses': pd.DataFrame(WAREHOUSES, columns=['warehouse_id', 'warehouse_name', 'location']),
        'categories': pd.DataFrame(CATEGORIES, columns=['category_id', 'category_name', 'parent_id'])
        .astype({'parent_id': 'Int64'}),
        'vendors': pd.DataFrame(VENDORS, columns=['vendor_id', 'business_name', 'category', 'lead_time_days'])
        .assign(lead_time_days=lambda d: d.vendor_id.map(lead_by_vendor)),
        'products': products.drop(columns='popularity_rank'),
        'inventory': inventory,
        'customers': customers_df,
        'transactions': transactions[['transaction_id', 'order_id', 'customer_id', 'product_id', 'vendor_id',
                                      'date', 'timestamp', 'quantity', 'unit_price', 'amount']],
        'sales_history': sales_history,
        'interactions': interactions_df,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--customers', type=int, default=1400)
    parser.add_argument('--out', default='data')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = build(args.seed, args.customers)
    for name, frame in tables.items():
        frame.to_csv(out / f'{name}.csv', index=False)
        print(f'{name:>14}: {len(frame):>7,} rows -> {out / (name + ".csv")}')


if __name__ == '__main__':
    main()
