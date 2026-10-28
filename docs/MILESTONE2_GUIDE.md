# Milestone 2 guide: inventory intelligence and customer analytics

This guide explains what was built for Milestone 2 (weeks 3–4), how each part works, where it differs from the sample code in the brief and why, and how the evaluation targets were measured.

## 1. What maps to what

| Brief item | Where it lives |
| --- | --- |
| Inventory, warehouse and category models | `app/models.py` (`Inventory`, `Warehouse`, `Category`), migration `alembic/versions/0002_milestone2_inventory.py` |
| Inventory tracking and turnover | `app/inventory/inventory_tracking.py` |
| Inventory forecasting | `app/inventory/inventory_forecasting.py` |
| Low-stock alerts and replenishment | `app/inventory/stock_alert.py` |
| Customer behaviour analytics | `app/customer/analytics.py` |
| K-Means segmentation | `app/customer/segmentation.py` |
| Recommendation engine and evaluation | `app/recommendation/recommendation.py` |
| Inventory API | `app/routers/inventory.py`, `app/routers/catalog.py` |
| Customer and recommendation API | `app/routers/customer_analytics.py`, `app/routers/recommendations.py` |
| Datasets (`data/*.csv`) | `scripts/generate_milestone2_data.py` |
| Dashboards | `dashboard/pages/2_…` to `5_…`, shared styling in `dashboard/ui.py` |
| Evaluation | `scripts/evaluate_milestone2.py` → `reports/` |

The analytics modules take pandas DataFrames and know nothing about the database. `app/services/intelligence.py` loads live rows into DataFrames, calls the modules, and caches trained models until the data changes. The same code therefore runs on the CSV files, on the live database and in unit tests.

The brief's `Inventory` model had `vendor_id`, `current_stock` and `reorder_level`. The existing ShopSense schema already stored stock in `inventory.quantity` and the reorder point in `inventory.low_stock_threshold`, and the vendor on `products.vendor_id`, so those were kept and only the missing fields were added: `warehouse_id`, `lead_time_days`, `last_updated` and `products.unit_cost`.

## 2. Datasets

`python -m scripts.generate_milestone2_data` writes nine CSVs with seed 42: 3 warehouses, 13 categories (4 parents, 9 leaves), 5 vendors, 58 products, 1,400 customers, about 34,500 order lines over two years (Oct 2024–Sep 2026), daily `sales_history.csv` in the brief's format, and about 97,000 browsing events.

It is synthetic. Customers follow four simulated personas (frequent, regular, occasional, lapsed), each with two favourite categories. Demand has a yearly festive peak (October–December), category-specific bumps and an 18% yearly growth trend. The `persona` column is the ground truth; models never train on it, and it is used only to check how well clustering recovers it.

`python -m scripts.seed_milestone2` loads the same data into the live database (development only), shifting dates so history ends yesterday.

The evaluation can also run on real data: the public Olist Brazilian e-commerce dataset, already used by the Historical Analytics page.

## 3. Inventory tracking

**Status.** `Out of stock` if stock ≤ 0, `Low stock` if stock ≤ reorder level, otherwise `Available`. The brief used `current_stock > reorder_level` for Available, which is the same rule.

**Turnover.** `turnover = COGS ÷ average inventory value`, as in the brief (`turnover_rate(100000, 25000) = 4.0`). COGS = units sold × unit cost. Average inventory is the mean of the daily stock level, rebuilt by walking the immutable `inventory_movements` ledger backwards from today's stock. When unit cost is missing, the same ratio is computed in units and labelled `basis: units`.

**Days of cover** = current stock ÷ forecast daily demand.

## 4. Demand forecasting

**What the brief proposed.** A Random Forest on `month` and `quarter`, a random 80/20 split of 7 rows, scored with R². That cannot give a meaningful number: 2 test rows, future months leak into training, and R² on two points is unstable.

**What was built.**

1. Sales are summed into complete weeks (Monday–Sunday) per product, per category, or for the whole store. Missing weeks count as zero; half-finished first and last weeks are dropped.
2. Features use only earlier weeks: sales 1, 2, 3, 4 and 52 weeks ago, 4/8/13-week averages, share of the last 8 weeks with any sale, and the week of the year as sine and cosine.
3. Every value is divided by the series' previous 13-week average, so one model can learn from all products at once and still follow a growing trend. Predictions are multiplied back.
4. One `RandomForestRegressor` (300 trees, min 5 samples per leaf) is trained on all series together.
5. The forecast for future weeks is recursive: each predicted week feeds the next. The shaded range is the 10th–90th percentile of training errors, widened by 1.8 and by √(weeks ahead).

**Accuracy.** `accuracy = 1 − WAPE`, where `WAPE = Σ|actual − forecast| ÷ Σ actual`. This is the usual retail "forecast accuracy" and, unlike MAPE, does not break when a week has zero sales.

**Protocol.** The last 12 weeks are never seen in training. Each held-out week is forecast one week ahead from the true history up to the previous week, which is how a weekly reorder review uses it. The model is compared with three baselines on exactly the same weeks: last week's sales, the same week last year, and the 4-week average.

| Level (synthetic) | Random Forest | Best baseline |
| --- | --- | --- |
| Product (58 series) | 68.7% | 68.8% (4-week average) |
| Category (9) | **84.2%** | 82.9% |
| Parent category (4) | 89.6% | 89.2% |
| Store total | 95.0% | 94.0% |

The ≥ 80% target is reported at category level, a normal planning level. At product level the model is no better than a 4-week average: a product selling about 7 units a week has random week-to-week variation of roughly ±40%, which caps achievable accuracy. On real Olist data the model reaches 75.5% for the top 20 categories (better than all baselines) but 81.1% for the store total, which is worse than simply repeating last week (83.5%). Both facts are in the report.

## 5. Low-stock alerts and replenishment

**Alert** when stock ≤ reorder level, or when days of cover < lead time.

- `critical`: out of stock, or forecast to sell out before a new order could arrive.
- `warning`: at or below the reorder level but not yet critical.

**Reorder quantity** (order-up-to policy):

```
safety stock = z × σ_daily × √(lead time)          z = 1.65 at 95% service level
order up to  = max(daily demand × (lead time + review days) + safety stock, 2 × reorder level)
reorder qty  = max(0, ⌈order up to − current stock⌉)
```

Daily demand is next week's ML forecast ÷ 7 (or the last 8 weeks' average for products with under 12 weeks of history); σ is the standard deviation of daily sales over the last 8 weeks. The `2 × reorder level` floor keeps the plan consistent with the alerts: anything flagged as low always gets an order. Products with no sales history use the brief's rule, `2 × reorder level − current stock`.

## 6. Customer analytics and segmentation

`customer_stats` gives, per customer: orders, total spent, average order value, days since last order, tenure, orders per month and number of distinct products and categories. The overview adds average and median spend, repeat rate, top customers, an orders-per-customer histogram and a view → cart → purchase funnel.

**Segmentation.** K-Means on days since last order, number of orders and total spend. All three are very skewed, so they are log-transformed and standardised first. `n_init=10`, `random_state=42`.

The brief mapped `{0: 'High Value', 1: 'Regular', 2: 'Dormant'}` directly. K-Means cluster numbers are arbitrary and change between runs, so that mapping would mislabel groups. Instead each centroid gets a value score (more orders + more spend − more days since last order) and names are assigned by rank.

**Quality metrics.**

| Metric (synthetic, k=3) | Value | Meaning |
| --- | --- | --- |
| Silhouette | 0.34 | Separation of groups, −1 to 1 (target 0.85: not met) |
| Bootstrap stability | 0.88 | Adjusted Rand index between the full clustering and re-fits on resampled customers |
| Davies-Bouldin | 1.05 | Lower is better |
| Best silhouette, k = 2…6 | 0.46 (k=2) | |
| Olist real customers, k=3 | 0.43 | |

A silhouette of 0.85 requires groups that are far apart with almost nothing between them. Customer behaviour is a continuum, so published RFM clusterings usually score 0.3–0.6. The synthetic data was not tuned to hit the target; doing so would make the number meaningless. The segments are stable (0.88) and clearly different in their averages, which is what makes them useful.

## 7. Recommendations

**What the brief proposed.** A customer × product rating pivot, customer-to-customer cosine similarity, and a function that returned the similarity scores rather than products. The precision example hard-coded 80 relevant out of 100.

**What was built.**

- Events become weights per customer–product pair: view 1, wishlist 2, cart 3, purchase 5. Totals are dampened with `log1p`.
- Item-to-item cosine similarity on that matrix ("people who engaged with X also engaged with Y").
- Score = 0.70 × collaborative score + 0.20 × the customer's share of activity in the product's category + 0.10 × product popularity. Customers with no history get the most popular products.
- Already-bought products are excluded; `/api/customers/recommendations/me` keeps its original rule of also excluding anything viewed. Only active, in-stock products from approved vendors are recommended.
- Each pick has a reason naming the most similar product the customer engaged with.

**Live tracking.** The dashboard records an impression when picks are shown and a click on "Add to cart". `/api/recommendations/metrics` reports click-through rate and how many clicked products were later bought.

**Offline evaluation.** Train on everything before a cutoff 60 days before the end; for each of 519 customers who newly bought something after the cutoff, check their top-K list.

| K = 10 | Hybrid | Most popular |
| --- | --- | --- |
| HitRate (relevance) | **75.1%** | 51.3% |
| Precision | 10.7% | 6.5% |
| Recall | 60.4% | 37.0% |
| Catalogue coverage | 100% | 74% |

"Relevance" is reported as HitRate@10: the share of customers whose top 10 contains at least one product they went on to buy. Precision@10 is much lower because most customers buy only one or two new products in 60 days. With only 58 products, a top-10 list covers 17% of the catalogue, which makes hits easier than in a real store. The recommender was not evaluated on Olist because only about 3% of Olist customers ever order twice.

## 8. Reproducing everything

```bash
python -m scripts.generate_milestone2_data       # identical CSVs every time (seed 42)
pytest -q                                        # 43 tests
python -m scripts.evaluate_milestone2 --olist    # about 2 minutes; downloads Olist on first run
```

## 9. Viva notes

- **Why not R² for forecast accuracy?** R² measures variance explained on the test set; with a handful of test points it swings wildly and can be negative. WAPE-based accuracy is what retailers report and is stable with zeros.
- **Why a chronological split?** A random split lets the model see the future (later weeks) while predicting the past, which inflates accuracy.
- **Why compare with baselines?** An accuracy number alone does not show the model adds anything. At product level it does not; at category level it does.
- **Why log-transform RFM?** Spend and order counts have long tails; without the log, K-Means splits mostly on a few extreme spenders.
- **Why does silhouette miss the target?** See section 6. Reporting it honestly, with stability as supporting evidence, is stronger than tuning data to a number.
- **Why item-based rather than user-based CF?** Items are few and stable (58), customers are many; item similarities are cheaper to compute, easier to explain ("because you liked X") and less noisy for customers with short histories.
- **Known limits:** synthetic data, a small catalogue, no cost data from real suppliers, weekly not daily forecasts, no A/B test of recommendations.
