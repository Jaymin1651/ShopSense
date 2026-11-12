# Milestone 3 guide: advanced analytics, APIs and reporting

Milestone 3 (weeks 5–6) turns the Milestone 2 analytics into a platform: analytics APIs, revenue analysis and vendor benchmarking, a model registry, scheduled workflows and business-intelligence dashboards with exports.

## 1. Plan to code

| Plan item | Where it lives |
| --- | --- |
| Module 1: FastAPI analytics services (`api/revenue_routes.py`, `forecast_routes.py`, `customer_routes.py`, `recommendation_routes.py`) | `app/api/` (plus `ops_routes.py` for MLflow, workflows, reports) |
| Module 2: advanced revenue analysis, vendor benchmarking and ranking | `app/analytics/revenue_analysis.py` |
| Module 3: MLflow model registry (`track_inventory.py`) | `app/mlflow_tracking/tracking.py`, `models.py`; serving in `app/forecasting/service.py` |
| Module 4: automated workflow pipeline (`scheduler.py`, APScheduler) | `app/scheduler/jobs.py`, `runner.py`, `__main__.py` |
| Module 5: BI dashboards (`admin_dashboard.py`, `vendor_dashboard.py`, `customer_dashboard.py`) | `dashboard/pages/6_Admin_Dashboard.py`, `7_Vendor_Dashboard.py`, `8_Customer_Dashboard.py`, plus `9_Models_and_Workflows.py`, `10_Milestone_3_Results.py` |
| `reports/pdf_reports.py`, `reports/excel_reports.py` | `app/reports/pdf_reports.py`, `excel_reports.py` (inside `app/` so the API can import them) |
| `customer_intelligence/` | `app/customer_intelligence/churn.py` |
| `recommendations/` | `app/recommendations/segment_recommendations.py` (segment-level); individual picks stay in `app/recommendation/` from Milestone 2 |

Streamlit needs dashboard pages inside `dashboard/pages/`, so the plan's three dashboard files are pages there with a number in front for menu order.

## 2. Where the build differs from the plan's sample code, and why

| Plan sample | Built instead | Why |
| --- | --- | --- |
| Routes read `data/transactions.csv` | Routes read the live database | A CSV is a frozen copy; dashboards must reflect new orders. |
| `/forecast/{month}` with a model loaded from `models/inventory_model.pkl` | `/api/forecast/{product_id}` and `/api/forecast/summary`, served from `models:/InventoryForecast@production` in MLflow | Demand is forecast per product, and the registry decides which version serves. |
| `/recommend/{customer_id}` returning "Wireless Mouse" | Real hybrid recommendations (`/api/recommend/{customer_id}`) | Hard-coded output is not a recommender. |
| `mlflow.start_run()` with one accuracy metric | One experiment per model family, parameters, several metrics, evaluation artifact, registry versions and aliases | Lets a new model replace the old one only when it is at least as good. |
| `BlockingScheduler` with one `retrain_model` job | Six jobs with run history, retries, success rate, and a standalone or in-API scheduler | The plan's target is "no operational failures", which has to be measured. |
| Dashboard with hard-coded metrics ("₹12.5 L", "84%") | Every number comes from the API | Hard-coded numbers cannot update in near real time. |

## 3. How it works

### 3.1 Two speeds of analytics

* **Live tier.** `/api/live/kpis` runs SQL aggregates (GMV, orders, units, customers, today, last hour, stock counts) against the database. Results are remembered only until the *data version* changes, so they are always exact. The admin and vendor dashboards poll it every 5 seconds with `st.fragment(run_every=5)`.
* **Snapshot tier.** Heavier results (revenue series, cohorts, benchmark, churn scoring, segment picks, forecast summary) are stored in `analytics_snapshots` with the data version they were computed from (`app/analytics/snapshots.py`). If the version still matches, the snapshot is returned. If not, the last snapshot is returned straight away with `orders_behind` in its `meta`, and a refresh is queued. All API workers share the same table, and the `refresh_snapshots` workflow recomputes every scope every 10 minutes.

The *data version* is one small query: counts and highest ids of orders, cancellations, order lines, stock movements, interactions and products. Any order, cancellation or stock change produces a new version.

### 3.2 Keeping the API fast

Background refreshes run on **one** worker thread (`app/analytics/refresher.py`), each key at most every 30 seconds (models every 2 minutes). Without this, every new order triggered several retrains at once and p95 latency rose to 6.7 seconds in the first trial. Other measures:
* per-product forecasts are computed for all products in one batch (one model call per week ahead);
* Random Forest prediction uses one thread, since threads only add overhead for a few rows;
* responses carry a `Server-Timing` header so time inside the API can be told apart from queueing.

### 3.3 Revenue analysis and benchmarking

* **Growth:** last 30 days vs the 30 before, and the last complete month vs the one before. **AOV** = GMV ÷ orders.
* **Category mix:** share and growth over the last 90 days.
* **Pareto:** share of GMV from the top 20% of products.
* **Cohorts:** customers grouped by first-purchase month, with the share who buy again k months later. Months a cohort has not reached yet are blank, not zero.
* **Vendor benchmarking** (last 90 days): GMV, share, growth, AOV, repeat-buyer rate and in-stock rate. Each measure becomes a percentile among vendors (100 = best). The **score** is the average of the four percentiles, and **rank** is by GMV. Vendors only receive their own row, the marketplace medians and an anonymous list of peer GMVs.

### 3.4 Customer intelligence

**Churn** = no order in the next 90 days. The features are recency, frequency, spend, AOV, tenure, orders and spend in the last 90 days, and the average gap between orders. The model is logistic regression (log transform, standardised, `class_weight='balanced'`).

Training is time-based: the model fits on the window ending 90 days before the test window, so it never sees the period it is scored on. On demo data it reaches **ROC AUC 0.88**, against 0.86 for a recency-only rule, with precision 0.72, recall 0.81 and top-decile lift 2.15. Risk bands are Low < 0.4 ≤ Medium < 0.7 ≤ High.

**12-month value** = recent monthly order rate × 12 × (1 − churn probability) × AOV. This is a heuristic and is labelled as one.

**Segment picks:** for each K-Means segment, lift = the product's share among the segment's buyers ÷ its share among all buyers. A product needs at least 5 buyers in the segment to qualify.

### 3.5 MLflow registry

* **Tracking store:** `MLFLOW_TRACKING_URI`, default `sqlite:///mlflow.db`, separate from the shop database. Artifacts go to `./mlruns`.
* **InventoryForecast:** a pyfunc wrapper around the Milestone 2 forecaster. It logs its parameters, category and product accuracy, best-baseline accuracy and an evaluation JSON.
* **ChurnRisk:** an sklearn pipeline, logged with ROC AUC, baseline AUC, precision, recall and lift.
* **Segmentation and recommender quality** are logged as runs on each evaluation, so trends show in the MLflow UI.
* **Champion/challenger:** a new version gets the `production` alias only if its metric is at least the current production metric minus a small tolerance (0.5 accuracy points, 0.005 AUC). Otherwise it gets `challenger`.
* **Serving:** the API checks the production alias every 60 seconds and loads a newer version when there is one.

### 3.6 Workflows

| Job | Schedule (UTC) | Does |
| --- | --- | --- |
| refresh_snapshots | every 10 min | recompute every analytics snapshot for the marketplace and each vendor |
| data_quality | hourly | negative stock, order totals vs lines, orders without lines, stock ledger vs stock, products without inventory |
| retrain_forecast | 02:00 | train, log, register and maybe promote InventoryForecast |
| retrain_churn | 02:30 | the same for ChurnRisk |
| evaluate_models | 03:00 | log segmentation and recommender quality |
| scheduled_reports | 06:00 | write Excel and PDF reports to `reports/generated/` (keeps the last 7) |

`run_job` records each run in `workflow_runs` (status, attempts, duration, message, metrics) and retries failures twice with exponential backoff. Jobs use `max_instances=1`, `coalesce=True` and a one-hour misfire grace.

There are three ways to run the jobs:
* `python -m app.scheduler` is the plan's BlockingScheduler;
* `--run JOB|all` runs jobs now;
* `--accelerated SECONDS --every N` runs a real scheduler with short intervals.

Set `SCHEDULER_IN_API=true` to run the scheduler inside the API process instead.

### 3.7 Reports

The Excel workbook (openpyxl) has these sheets:
* Summary,
* Monthly revenue, with a line chart,
* Categories, with a bar chart,
* Vendor benchmark,
* Customers, with churn risk,
* Segment picks,
* Forecast & reorder.

The PDF (reportlab) has KPIs, a monthly revenue chart, category mix, benchmark, customer risk, segment picks and stock shortfalls. Vendors get their own data only.

## 4. Evaluation

Run with the API up: `python -m scripts.evaluate_milestone3` (or in stages: `--stages latency`, `sweep`, `consistency`, `workflows`).

* **Response time.** Simulated users log in as the admin (35%), vendors (40%) or customers (25%). They call analytical endpoints and pause 0.5–2 s between clicks, while one new order arrives every second. Every endpoint is called once before timing, to exclude one-off model loading. The 95th percentile covers all analytical GET requests; exports are file downloads and are not included.
* **Consistency.** While orders arrive, each check reads the database, reads `/api/live/kpis`, then reads the database again. If both database reads agree, the API must equal them. Checks where an order landed in between are skipped and counted. The script also times how long a new order takes to appear.
* **Workflows.** One on-demand run of each job, then a real APScheduler with every job every 15 s for 2 minutes.

| Target | Result |
| --- | --- |
| API p95 ≤ 300 ms | **169 ms** at 25 users (1,201 requests, 0 errors, 19/19 endpoints under 300 ms; p99 268 ms; inside-API p95 105 ms) |
| Load sweep | 10 users 88 ms · 25 users 169 ms · 50 users 244 ms (p95) |
| Dashboard consistency ≥ 99% | **100%** (193/193 checks; new orders visible in 29 ms) |
| Workflow success 100% | **100%** (36/36 runs, 0 retries) |

**Conditions:** a single CPU core shared by the API, the load generator and nothing else; SQLite; 17,800 synthetic orders. On a server with more cores, or with PostgreSQL and several workers, response times should be the same or better.

**Honest limits:**
* Snapshot panels can lag behind new orders by up to about 30 s plus compute time. They say so with "N orders behind". Only the live KPIs are exact at every moment.
* The Milestone 2 silhouette target (0.85) is still not met (0.34).
* Load was simulated, not real traffic.

## 5. Viva notes

* **Why snapshots and not compute-on-request?** Some analytics take 0.2–3 s. Users would wait, and with orders arriving every second the server would spend all its time recomputing.
* **How can it be consistent if snapshots lag?** The consistency target covers the live KPIs, which are exact. Snapshot panels carry their data version and say how far behind they are.
* **Why one background worker?** On one core, parallel retrains starve requests. The first trial showed p95 6.7 s, and after the change 169 ms.
* **What does champion/challenger protect against?** A retrain on bad or unusual data replacing a better model. In the trial runs, later churn versions scored 0.873 against production's 0.881, so they stayed challengers.
* **What happens if a workflow fails?** It is retried twice. If it still fails, the run is saved as failed with the error, and it shows on the Models & workflows page.
* **Why does a data-quality job "succeed" when it finds problems?** Success means the check ran. The problems are its findings, reported as metrics.
