# ShopSense: genuine e-commerce dataset → analysis dashboard

## Dataset provenance

- **Original publisher:** Olist, *Brazilian E-Commerce Public Dataset by Olist*.
- **Official dataset:** https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- **Coverage:** about 100,000 anonymized marketplace orders in Brazil, 2016–2018.
- **License:** Creative Commons Attribution–NonCommercial–ShareAlike 4.0 (CC BY-NC-SA 4.0). Attribution is required. Do not assume commercial reuse rights.
- **CSV mirror used by automatic loading:** https://github.com/spdrio/Brazilian-E-Commerce-Public-Dataset-by-Olist/tree/master/files — a third-party copy of the published data, not an official Olist API. If the mirror is unavailable, download the original ZIP from Kaggle yourself.

ShopSense does **not** claim that historical seller IDs are real vendor business names or that Olist provides owner emails, product titles, or current stock. Do not add invented vendor names, contact numbers, or current inventory to historical metrics.

## Relevant source files

| CSV | Primary columns used | Relationship |
| --- | --- | --- |
| `olist_order_items_dataset.csv` | `order_id`, `order_item_id`, `product_id`, `seller_id`, `price` | Central item-level fact table |
| `olist_orders_dataset.csv` | `order_id`, `order_status`, `order_purchase_timestamp` | Join on `order_id` |
| `olist_products_dataset.csv` | `product_id`, `product_category_name` | Join on `product_id` |
| `olist_sellers_dataset.csv` | `seller_id`, `seller_city`, `seller_state` | Join on `seller_id` |
| `product_category_name_translation.csv` | `product_category_name`, `product_category_name_english` | Join on Portuguese category |

Each item row counts as **one unit** in the Olist data. A single order can contain multiple items and sellers. Therefore, order counts are always **distinct `order_id`**, not counts of item rows.

## Processing logic

`dashboard/historical_data.py` validates unique dimension keys and `(order_id, order_item_id)` uniqueness, performs verified many-to-one joins, keeps `order_status == "delivered"`, excludes item rows with invalid price/timestamp, translates categories, and records exclusion totals in a data-quality audit.

- **Item sales value (R$):** sum of `price` for delivered order items; excludes `freight_value`, fees and any refund accounting. This is **not profit, gross payment collected, or recognized revenue**.
- **Vendor / product value:** sum the same item `price` by the anonymized `seller_id` / `product_id`.
- **Top-selling products:** rank by number of item rows (`units`), with sales value as secondary sorting.
- **Monthly sales:** group by purchase month from `order_purchase_timestamp`.
- **Filters:** purchase date range, seller state, product category.

This is a separate historical analytics module: it does **not** populate ShopSense's live vendor registration, inventory, checkout or PostgreSQL sales tables. This prevents mixing anonymized historical Olist sales with 2026 demonstration orders.

## View the live dashboard (Streamlit Community Cloud)

Streamlit automatically discovers the new `dashboard/pages/1_Historical_Analytics.py` page when `dashboard/dashboard.py` is the app entry point. In the Streamlit sidebar, select **Historical Analytics**. The page downloads the five public CSV files on first open, caches them, and shows real historical charts. First load can take a little time due to the original CSV sizes.

If external downloads fail, get the five files from the official Kaggle URL, place them in a directory, set `OLIST_DATA_DIR=/path/to/that/directory` and restart Streamlit. Source CSVs are cached in `/tmp/shopsense_olist` by default on cloud hosting. These files may disappear when a hosted container restarts.

## Reproduce analysis locally

Install dashboard dependencies (`pip install -r requirements-dashboard.txt`), then run:

```bash
python -m scripts.analyze_olist --download
```

Or download the original dataset ZIP from Kaggle, extract its five selected CSV files into `data/olist`, and run:

```bash
python -m scripts.analyze_olist --data-dir data/olist
```

Outputs are created under `data/processed`:
- `seller_ranking.csv`
- `product_ranking.csv`
- `monthly_sales.csv`
- `audit.json`

The script prints computed counts and totals. Do not replace its output with hardcoded example figures.

## Validate behavior

```bash
pytest -q tests/test_historical_data.py
```

The unit tests use small **synthetic fixtures to check the math and joins**. The dashboard itself analyzes the actual Olist CSV files. A passing test suite alone is not proof that the remote files are currently available; confirm the deployed Historical Analytics page loads and its data-quality totals are nonzero.