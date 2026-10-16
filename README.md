# ShopSense — Multi-Vendor E-Commerce Analytics Platform

A solo college project based on my October 2026 ShopSense concept. The application pairs a **FastAPI + PostgreSQL** marketplace backend with a **Streamlit + Plotly** administrative/vendor/customer web interface. Includes Docker Compose, initial Alembic migration, role-based JWT authentication, automated tests, and optional Render deployment hooks.

> **Scope:** This is a demonstration / academic MVP, not a finished financial marketplace. Checkout **records orders without charging cards**. GMV is order-item value, not collected cash, recognized revenue, or profit. Predictive demand is an explicit moving-average **baseline**, not a validated trained ML model. See [Roadmap](docs/ROADMAP.md) for advanced functionality required by the source concept.

## Quick start with Docker (recommended)

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# Edit .env with your own strong credentials and JWT_SECRET
# You can generate JWT_SECRET with: python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up --build -d
# Admin is bootstrapped automatically on first container start from ADMIN_EMAIL/ADMIN_PASSWORD in .env.
# Re-running this manually is safe and will not reset an existing password:
docker compose exec api python -m scripts.bootstrap_admin
# Optional synthetic demo data (development only):
docker compose exec api python -m scripts.seed_demo
```

- Dashboard: **http://localhost:8501**
- OpenAPI API documentation: **http://localhost:8000/docs**
- API health: **http://localhost:8000/health**
- Check logs: `docker compose logs -f api`
- Shut down: `docker compose down` (keeps your database volume)
- Delete demo volume: `docker compose down -v` (**erases all data**)

The demo script prints three synthetic demo login accounts. Don't seed production; all real passwords must be changed before exposure.

## Run without Docker (SQLite development)

Use Python 3.12+ and create a virtual environment:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements-dashboard.txt
# SQLite is the default DATABASE_URL for local development.
alembic upgrade head
# Set ADMIN_EMAIL and ADMIN_PASSWORD, then:
python -m scripts.bootstrap_admin
uvicorn app.main:app --reload
# Separate terminal:
streamlit run dashboard/dashboard.py
```

For PostgreSQL locally, use Docker Compose. To run tests independently of a running server:

```bash
pytest -q
```

## What works today

| Area | Features |
| --- | --- |
| Identity | Customer/vendor self-registration, admin bootstrap, JWT login, role permissions |
| Vendor operations | Pending application, approval/rejection/suspension, vendor-specific access |
| Catalog & inventory | Public catalog, vendor product creation and editing, stock updates, immutable stock movement records |
| Customer flow | Browse, view and cart interaction events, simulated order placement, customer order history |
| Sales intelligence | GMV, order count, AOV, trends, top products, vendor leaderboard, low-stock counts |
| Customer intelligence | Category-affinity product suggestions, rule-based purchase segments |
| Demand | 7-day moving-average baseline and days-of-stock estimate |
| Reporting | Protected vendor-scoped CSV transactions and PDF overview |
| Delivery | PostgreSQL + Alembic, Docker Compose, GitHub Actions tests/build, optional Render hooks |

**Not yet included:** payment gateway, returns/refunds, real supplier/warehouse feeds, privacy consent workflows, production rate-limiting, trained inventory forecasting, collaborative filtering, clustering, churn prediction, full ETL/scheduling, MLflow integration. These are later milestones; don't describe them as completed.

## Project documentation and mentor guide

- **[End-to-End Mentor Implementation Guide](docs/MENTOR_IMPLEMENTATION_GUIDE.md)** — code walkthrough for vendor management, live analytics, Olist historical analytics, API examples, test coverage, and a timed demo script.
- [Project Documentation & Mentor Guide](docs/PROJECT_GUIDE.md) — Steps 1–20 audit, repository/file guide, database design, implementation gaps, and viva preparation.
- [Olist Dataset Methodology](docs/OLIST_DATASET.md) — dataset provenance, licensing, joins, metric definitions, and reproducibility.
- [Deployment Guide](docs/DEPLOYMENT.md) — local setup, Render environment configuration, smoke tests, and rollback.

## Folder structure

```text
ShopSense/
├── app/
│   ├── main.py, config.py, database.py, models.py, schemas.py, security.py
│   ├── routers/  auth.py vendors.py products.py orders.py behavior.py analytics.py
│   └── services/ analytics.py
├── dashboard/dashboard.py
├── scripts/bootstrap_admin.py, seed_demo.py
├── alembic/versions/0001_initial.py
├── tests/  conftest.py test_api.py
├── docs/ DEPLOYMENT.md ROADMAP.md
├── .github/workflows/ ci.yml deploy-render.yml
├── Dockerfile.api, Dockerfile.dashboard, docker-compose.yml
├── requirements*.txt, .env.example, Makefile
└── README.md
```

## Authorization model

- **Admin:** approve/suspend vendors; all-vendor overview, rankings, exports and product inventory administration.
- **Vendor:** only see **their own** products, stock and sales; must be approved to create/update listings.
- **Customer:** browse, purchase simulated items, record their own interactions, and access their own order history/recommendations.

A single checkout can include multiple vendors; vendor order views return only that vendor's line items and vendor-only subtotal. Customer and admin orders show the complete order.

## API overview

Open `http://localhost:8000/docs` for request and response schemas.

| Method | Endpoint | Permission |
| --- | --- | --- |
| POST | `/api/auth/register/vendor` | Public |
| POST | `/api/auth/register/customer` | Public |
| POST | `/api/auth/login` | Public |
| GET | `/api/auth/me` | Authenticated |
| GET | `/api/vendors` | Admin |
| PATCH | `/api/vendors/{id}/status?status=approved` | Admin |
| GET | `/api/vendors/me` | Vendor |
| GET | `/api/products` | Public |
| POST | `/api/products` | Approved vendor |
| PATCH | `/api/products/{id}` | Owner vendor or admin |
| PUT | `/api/products/{id}/inventory` | Owner vendor or admin |
| POST | `/api/orders` | Customer |
| GET | `/api/orders` | Own orders; vendor-scoped; or all (admin) |
| POST | `/api/customers/interactions` | Customer |
| GET | `/api/customers/recommendations/me` | Customer |
| GET | `/api/analytics/summary` | Vendor/admin |
| GET | `/api/analytics/trends` | Vendor/admin |
| GET | `/api/analytics/top-products` | Vendor/admin |
| GET | `/api/analytics/forecast?product_id=1` | Vendor/admin |
| GET | `/api/analytics/vendors` | Admin |
| GET | `/api/analytics/customer-segments` | Vendor/admin |
| GET | `/api/analytics/sales.csv` | Vendor/admin |
| GET | `/api/analytics/sales.pdf` | Vendor/admin |
| GET | `/health`, `/ready` | Public |

## Deploy to GitHub and hosting

See [**Deployment guide**](docs/DEPLOYMENT.md) for GitHub repository creation, branch workflow, Render + managed PostgreSQL steps, secrets, deployment hooks, verification and rollback. See [**Implementation roadmap**](docs/ROADMAP.md) for the original 1–2 week foundation milestone and all subsequent ML/ETL modules.

## Security checklist

- Use unique strong `JWT_SECRET`, `ADMIN_PASSWORD`, and DB credentials in **environment secrets** (never commit `.env`).
- Always run HTTPS behind a trusted host. Turn off demo seeding and sample accounts for production.
- Run database migrations and keep reliable backups; configure alerts, audit logging and rate limiting before real customers.
- Define currency/tax handling, compliant payment provider and order lifecycle before accepting money.
- Do not store payment-card numbers or sensitive credentials in ShopSense.
- Benchmark heavy analytics queries and add indexes/aggregated tables as data volume grows.

## Vendor products not showing to customers?

A vendor being approved is **not** the same thing as publishing a product. Try this flow:

1. Sign in as **Admin** and approve the vendor in the **Vendors** tab.
2. Sign out, sign in as that **Vendor**, and open **My products**.
3. Add at least one product. Its **Customer visibility** column should read `True`.
4. If the product is hidden, use **Show or hide a product** to activate it.
5. Sign in as a **Customer**, and open **Product catalog**. The product should appear.

Active products from approved shops are shown even when stock is zero, but the Add to cart button is disabled. For quick debugging, open `GET /api/products` in `/docs`; no login is needed for that endpoint. If this endpoint returns the product but the dashboard doesn't, make sure the dashboard `API_URL` points to the same backend/database as the vendor dashboard. The status shown on **My products** explains why an item is hidden.

## Solo project deadline (16 October 2026)

- **12 Oct:** Upload repository, verify local setup, fix customer catalog visibility.
- **13 Oct:** Manually demo vendor approval, product creation, orders and stock changes.
- **14 Oct:** Add screenshots, verify sales charts and write test results.
- **15 Oct:** Deploy the API, database and dashboard; check live URLs and secrets.
- **16 Oct:** Final demo, README cleanup and submission.

This is an educational MVP with explainable rules. I am keeping the ML forecast as a baseline rather than presenting it as a trained model. See [Roadmap](docs/ROADMAP.md) for stretch goals.

## Historical real-data analytics (Olist)

ShopSense now includes a **separate historical analytics page** powered by the Brazilian E-Commerce Public Dataset by Olist (about 100k anonymized orders from 2016–2018). Open **Historical Analytics** in the Streamlit sidebar to see actual seller/product performance, monthly delivered-item sales, category comparisons, state filters, and CSV ranking exports. The first launch downloads five original CSVs from a public mirror; it may take a little time.

Historical prices are denominated in **Brazilian reais (R$)**; `item sales value` sums delivered-item `price` and is **not profit, payments or net revenue**. Olist's anonymous seller IDs are **not** users registered in the 2026 live marketplace. The historical page never modifies the marketplace PostgreSQL tables.

To reproduce the analysis locally after installing `requirements-dashboard.txt`:

```bash
python -m scripts.analyze_olist --download
pytest -q tests/test_historical_data.py
```

**Source, data dictionary, quality checks, alternate official Kaggle download, license CC BY-NC-SA 4.0 and metric definitions:** [Olist dataset methodology](docs/OLIST_DATASET.md).
