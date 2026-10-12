# ShopSense development roadmap and source-to-implementation map

Based on the uploaded **"concept 8 oct 26"** (ShopSense Multi-Vendor E-Commerce Analytics Platform), especially its sections **Outcomes**, **Modules to be Implemented**, and **Milestone 1 (Weeks 1–2)**. The document specifies Milestone 1 at Week 2 with a vendor registration correctness target of at least **99%**, transaction consistency **98%**, and successful marketplace visualizations. Those are **targets**, not measured achievements in this starter.

## Actual vs planned scope

| Source module | Implemented MVP | Remaining work |
| --- | --- | --- |
| 1. Vendor Management & Marketplace Onboarding | Vendor registration, pending review, admin approval/rejection/suspension, JWT roles | Government/business compliance checks, vendor commission settlement, contact verification |
| 2. Product & Inventory Analytics | Products, stock updates, audit movements, low-stock counts, moving-average baseline | Supplier feeds, warehouse modeling, trained seasonal replenishment forecasting, alert delivery |
| 3. Sales & Revenue Intelligence | Order records, snapshots, GMV, AOV, top products, trends, admin/vendor scope | Payments, refunds, discounts, taxes, fees, net revenue and profit margins, true realtime streaming |
| 4. Customer Behavior & Recommendation | Interaction logging, category-affinity suggestions, rule-based recency/frequency segments | Collaborative filtering, clustering, predictive churn, retention experiments |
| 5. Data Management & Analytics Infrastructure | PostgreSQL/SQLAlchemy, Alembic, seed records | Scheduled ETL from outside systems, data-validation jobs, MLflow registry and data contracts |
| 6. API, Reporting & CI Integration | FastAPI REST, CSV and PDF, Docker, tests, GitHub Actions CI, optional CD hooks | Scheduled reports/email, distributed job runner, production release verification |
| 7. Optional BI Dashboard | Streamlit sales/stock/vendor/segment dashboard | Advanced side-by-side vendor benchmarking, cohort conversion and CLV analytics |

## Milestone 1: Weeks 1–2 — foundation

1. **Repository & infrastructure:** main + a stable main branch, CI, PostgreSQL, migrations and Docker startup.
2. **Vendor onboarding:** register a vendor, enter `pending`, admin approves or rejects, login blocked from new listings until approval.
3. **Catalog/inventory:** vendor creates priced products and manages stock; only approved vendor listings are public.
4. **Sales baseline:** record demo checkout and aggregate consistent GMV, product and vendor metrics.
5. **Demo:** admin registers/approves, vendor lists products, customer orders, dashboard reflects stock and GMV.

**Evaluation:** verify at least 100 registration cases with valid, invalid and duplicate payloads; compute `successful_expected_outcomes / test_cases` for the 99% benchmark. Reconcile per-order item line sums with all-vendor GMV under refund-free seed data and compute transactional consistency relative to a reference SQL query for the 98% target. A few passing functional tests do *not* prove these percentage targets.

## Milestone 2: Weeks 3–4 — transactional accuracy

- Add order idempotency key, order lifecycle + cancellations with stock compensation.
- Payment status and refund models, **test/sandbox only** until a compliant payment provider is integrated.
- Unit economics: gross/net GMV, fees, vendor commissions and consistent currency/tax conventions.
- Stock adjustment history and configurable low-stock alert thresholds.
- Add vendor/customer access-control matrix tests, concurrent checkout PostgreSQL tests, refunds and overflow tests.

**Exit:** every synthetic order has traceable stock movements and accounting invariants.

## Milestone 3: Weeks 5–6 — real analytics & ML

- Implement ETL pipeline for a clean synthetic/consented sample dataset with explicit data dictionary, schema checks and deduplication.
- Forecast units sold per product using daily features (lags, rolling averages, weekday, month, holidays) with chronological train/validation splits; include at least naive moving average, seasonal naive and trained model.
- Track MAE, RMSE, MAPE/sMAPE (with zero-demand safeguards), bias and retraining timestamps; store experiment metadata in **MLflow**.
- Customer RFM clustering using scikit-learn with privacy-safe identifiers; validate silhouette and stability as appropriate.
- Personalized recommendations blending content and collaborative interactions; offline metrics such as Precision@K and Recall@K.
- Add churn definition, label windows, class imbalance handling and precision/recall for churn-risk classification.

**Exit:** reproducible dataset and model comparison artifacts showing whether ML beats a naive baseline.

## Milestone 4: Weeks 7–8 — productization and deployment

- Advanced BI (vendor comparisons, seasonal plots, funnel/conversion, retained cohorts, CLV definitions).
- Periodic ETL jobs and quality thresholds, drift checks, scheduled CSV/PDF reporting.
- Privacy/legal consent and deletion flows for behavior tracking.
- Production concerns: error tracking, rate limiting, backups and recovery, migrations, HTTPS and least privilege.
- CI/CD with staging deploy, automated smoke checks, secret scanning and tagged releases.

**Exit:** repeatable deploy with rollback and privacy/security review. No real-money processing until a payment-provider integration is audited.

## Solo development approach

The concept document names a multi-person team, but this implementation is a solo project. For the 16 October deadline, focus on a demonstrable API and dashboard: registration, approval, product catalog, order, inventory and analytics. Save trained machine learning, MLflow and scheduled ETL for later work. Maintain a short list of bugs and manual test cases instead of splitting work among team members.

## Release standard

- No code or passwords in `.env` committed to git.
- API endpoints have clear access controls and schema validation.
- Automated tests prove tenant data isolation, order financial calculations, stock safety and migrations.
- Admin/vendor/customer demo successful with dummy data.
- Documented, deployed API and dashboard URLs; alerting and backups configured.
- Claims about 99% or 98% source evaluation targets supported by an actual evaluation protocol and results.
