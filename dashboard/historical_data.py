"""Read the public Olist dataset and calculate transparent historical sales metrics.

This module does not touch the live ShopSense database. Olist's historical
sellers are anonymized dataset identifiers, not registered ShopSense vendors.
"""
from pathlib import Path

import pandas as pd
import requests

SOURCE = 'https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce'
MIRROR = ('https://raw.githubusercontent.com/spdrio/'
          'Brazilian-E-Commerce-Public-Dataset-by-Olist/master/files')
FILES = {
    'items': 'olist_order_items_dataset.csv',
    'orders': 'olist_orders_dataset.csv',
    'products': 'olist_products_dataset.csv',
    'sellers': 'olist_sellers_dataset.csv',
    'categories': 'product_category_name_translation.csv',
}
COLUMNS = [
    'order_id', 'product_id', 'seller_id', 'seller_city', 'seller_state',
    'category', 'purchase_date', 'month', 'price_brl', 'units',
]


def download_dataset(directory: Path) -> Path:
    """Cache unmodified CSV source files; use the original Kaggle ZIP instead if preferred."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for filename in FILES.values():
        destination = directory / filename
        if destination.is_file() and destination.stat().st_size > 0:
            continue
        temporary = destination.with_suffix('.csv.tmp')
        try:
            with requests.get(f'{MIRROR}/{filename}', stream=True, timeout=(15, 120)) as response:
                response.raise_for_status()
                with temporary.open('wb') as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            output.write(block)
            if not temporary.stat().st_size:
                raise ValueError(f'Empty dataset file: {filename}')
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return directory


def read_dataset(directory: Path) -> dict[str, pd.DataFrame]:
    """Load five source tables with their original identifier strings."""
    directory = Path(directory)
    data = {}
    for key, filename in FILES.items():
        path = directory / filename
        if not path.exists():
            raise FileNotFoundError(f'Missing {filename}. Download Olist CSVs from {SOURCE}')
        data[key] = pd.read_csv(path, dtype={'order_id': 'string', 'product_id': 'string',
                                               'seller_id': 'string'}, encoding='utf-8-sig')
    return data


def _unique(table: pd.DataFrame, key: str, table_name: str) -> pd.DataFrame:
    if key not in table.columns or table[key].isna().any() or table[key].duplicated().any():
        raise ValueError(f'{table_name}: {key} must be present, non-null and unique')
    return table


def build_sales(dataset: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict]:
    """Return delivered-item fact rows and an audit trail of excluded rows.

    Each Olist order-item row is a single purchased unit. An order may have
    multiple items and sellers, so order IDs are only counted once for KPIs.
    Price is the item value excluding freight; this is not net revenue/profit.
    """
    required = {
        'items': {'order_id', 'order_item_id', 'product_id', 'seller_id', 'price'},
        'orders': {'order_id', 'order_status', 'order_purchase_timestamp'},
        'products': {'product_id', 'product_category_name'},
        'sellers': {'seller_id', 'seller_city', 'seller_state'},
        'categories': {'product_category_name', 'product_category_name_english'},
    }
    for name, cols in required.items():
        if name not in dataset:
            raise ValueError(f'Missing table: {name}')
        missing = cols - set(dataset[name].columns)
        if missing:
            raise ValueError(f'{name}: missing columns {sorted(missing)}')

    items = dataset['items'].copy()
    for col in ('order_id', 'product_id', 'seller_id'):
        if items[col].isna().any():
            raise ValueError(f'items: null {col} identifier')
    if items.duplicated(['order_id', 'order_item_id']).any():
        raise ValueError('items: duplicate order_id/order_item_id')
    orders = _unique(dataset['orders'].copy(), 'order_id', 'orders')
    products = _unique(dataset['products'].copy(), 'product_id', 'products')
    sellers = _unique(dataset['sellers'].copy(), 'seller_id', 'sellers')
    categories = _unique(dataset['categories'].copy(), 'product_category_name', 'categories')

    raw_count = len(items)
    delivered = orders[['order_id', 'order_status', 'order_purchase_timestamp']]
    items = items.merge(delivered, on='order_id', how='left', validate='many_to_one', indicator=True)
    missing_orders = int(items['_merge'].eq('left_only').sum())
    items = items.loc[items['_merge'].eq('both') & items['order_status'].eq('delivered')].drop(columns='_merge')
    delivered_count = len(items)
    items = items.merge(products[['product_id', 'product_category_name']], on='product_id',
                        how='left', validate='many_to_one')
    items = items.merge(sellers[['seller_id', 'seller_city', 'seller_state']], on='seller_id',
                        how='left', validate='many_to_one')
    items = items.merge(categories[['product_category_name', 'product_category_name_english']],
                        on='product_category_name', how='left', validate='many_to_one')
    items['price_brl'] = pd.to_numeric(items['price'], errors='coerce')
    items['purchase_date'] = pd.to_datetime(items['order_purchase_timestamp'], errors='coerce')
    valid = items['price_brl'].ge(0) & items['purchase_date'].notna()
    excluded_bad_values = int((~valid).sum())
    items = items.loc[valid].copy()
    items['category'] = (items['product_category_name_english']
                         .fillna(items['product_category_name']).fillna('unknown'))
    items['seller_city'] = items['seller_city'].fillna('unknown')
    items['seller_state'] = items['seller_state'].fillna('unknown')
    items['month'] = items['purchase_date'].dt.to_period('M').astype(str)
    items['units'] = 1
    result = items[COLUMNS].reset_index(drop=True)
    audit = {
        'source_item_rows': raw_count,
        'missing_order_items': missing_orders,
        'not_delivered_or_missing_order': raw_count - delivered_count,
        'invalid_price_or_date': excluded_bad_values,
        'analyzed_item_rows': len(result),
        'matched_seller_rows': int(items['seller_city'].ne('unknown').sum()),
        'matched_product_category_rows': int(items['category'].ne('unknown').sum()),
        'sales_value_definition': 'Sum of item prices for delivered orders; excludes freight, fees and refunds.',
    }
    return result, audit


def summarize(sales: pd.DataFrame) -> dict:
    return {
        'item_sales_brl': round(float(sales['price_brl'].sum()), 2),
        'orders': int(sales['order_id'].nunique()),
        'sellers': int(sales['seller_id'].nunique()),
        'products': int(sales['product_id'].nunique()),
        'units': int(sales['units'].sum()),
    }


def group_sales(sales: pd.DataFrame, fields: list[str], limit: int | None = None) -> pd.DataFrame:
    result = (sales.groupby(fields, dropna=False)
              .agg(item_sales_brl=('price_brl', 'sum'), units=('units', 'sum'),
                   orders=('order_id', 'nunique'))
              .reset_index().sort_values('item_sales_brl', ascending=False))
    if limit is not None:
        result = result.head(limit)
    return result.reset_index(drop=True)