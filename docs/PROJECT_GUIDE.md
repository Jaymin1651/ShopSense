# ShopSense — Project Documentation & Mentor Guide

**Project type:** Individual / solo academic project  
**Project title:** ShopSense — Multi-Vendor E-Commerce Analytics Platform  
**Repository:** https://github.com/Jaymin1651/ShopSense  
**Live Streamlit dashboard:** https://shopsense-new.streamlit.app/  
**API documentation (deployed):** Open the deployed Render API URL followed by `/docs`.  
**Documentation status:** Describes the repository implementation reviewed on 16 October 2026.

---

## 1. Project overview

ShopSense is an academic MVP for managing a multi-vendor marketplace and analyzing e-commerce sales. It has two intentionally separate data paths:

1. **Live marketplace:** vendor/customer registration, login, vendor approval, product listings, inventory, simulated orders, customer interactions, and operational analytics. FastAPI exposes the API; SQLAlchemy persists operational data in the configured database; Streamlit is the user interface.
2. **Historical analytics:** a separate dashboard analyzes the public Brazilian E-Commerce Public Dataset by Olist. Pandas cleans and joins the seller, product, order, and order-item CSV files; Plotly visualizes historical seller, product, category, and monthly sales performance.

Historical Olist sellers are anonymized and are not the same entities as vendors registered in the live ShopSense database. Keeping these data paths separate avoids mixing Brazilian historical data from 2016–2018 with the current demonstration marketplace.

### Project problem

Marketplace operators need a central place to manage vendors and products and to understand sales performance. ShopSense demonstrates the basic workflow and turns transaction data into understandable charts and reports.

### Main objectives

- Register customers and vendors with input validation.
- Authenticate users and apply Admin, Vendor, and Customer permissions.
- Allow an admin to approve, reject, or suspend vendors.
- Allow approved vendors to create products and manage stock.
- Let customers browse products and place simulated orders.
- Calculate GMV, order counts, average order value, product rankings, and sales trends.
- Record customer interactions and show simple recommendations/segments.
- Analyze genuine historical e-commerce records and export historical ranking CSVs.
- Test the code and deploy the API and dashboard.

### Important scope statement

This is a demonstration/academic MVP. Checkout records an order but **does not charge a payment card**. GMV and item sales value are not the same as cash collected, accounting revenue, or profit. Demand forecasting is a moving-average baseline, not a trained and validated machine-learning model.

---

## 2. System architecture

~~~text
                         ┌───────────────────────────────┐
                         │       Streamlit UI            │
                         │ dashboard/dashboard.py        │
                         │ Admin / Vendor / Customer     │
                         └──────────────┬────────────────┘
                                        │ HTTP + JWT
                                        ▼
                         ┌───────────────────────────────┐
                         │          FastAPI API           │
                         │ app/main.py                    │
                         │ auth, vendors, products,       │
                         │ orders, behavior, analytics    │
                         └──────────────┬────────────────┘
                                        │ SQLAlchemy
                                        ▼
                         ┌───────────────────────────────┐
                         │ Configured database            │
                         │ PostgreSQL in hosted setup;    │
                         │ SQLite can be used locally     │
                         └───────────────────────────────┘


  Olist public CSV files
          │
          ▼
  dashboard/historical_data.py
  Download → validate → clean → join → aggregate
          │
          ▼
  dashboard/pages/1_Historical_Analytics.py
  Pandas results → Plotly charts → CSV downloads
  (separate from live marketplace tables)
~~~

### Technology stack

| Technology | Why it is used |
|---|---|
| Python | Main application language |
| FastAPI | REST endpoints, request handling, automatic OpenAPI documentation |
| Pydantic | Validates request payloads and response schemas |
| SQLAlchemy | Maps Python models to relational database tables and performs queries |
| PostgreSQL | Persistent hosted relational database; SQLite is available for local development |
| Alembic | Versioned database schema migrations |
| Pandas | Cleaning, joining, grouping, and aggregating CSV data |
| Streamlit | Interactive dashboard and role-based user interface |
| Plotly | Interactive sales charts |
| PyJWT / password hashing | Login tokens and password protection |
| ReportLab | PDF sales overview export |
| pytest | Automated API, data-processing, and session tests |
| Docker / GitHub Actions | Repeatable packaging and continuous integration |

---

## 3. Repository folder and file guide

| File or folder | Responsibility |
|---|---|
| `app/main.py` | Creates the FastAPI application, adds CORS middleware, includes routers, and defines health/readiness endpoints. |
| `app/config.py` | Reads environment settings such as DATABASE_URL, JWT_SECRET, ENVIRONMENT, and CORS_ORIGINS. |
| `app/database.py` | Creates the SQLAlchemy engine and session factory; provides the database dependency used by routes. |
| `app/models.py` | Defines database entities: User, Vendor, Product, Inventory, InventoryMovement, CustomerProfile, Order, OrderItem, and Interaction. |
| `app/schemas.py` | Defines Pydantic input/output schemas and validation rules. |
| `app/security.py` | Password hashing, JWT handling, current-user resolution, and role-based access checks. |
| `app/routers/auth.py` | Vendor/customer registration, login, and current-user endpoint. |
| `app/routers/vendors.py` | Admin vendor listing and approval/rejection/suspension; vendor’s own profile. |
| `app/routers/products.py` | Public product catalog, vendor product creation/editing, visibility rules, and inventory updates. |
| `app/routers/orders.py` | Simulated checkout, order-item creation, stock deduction, and insufficient-stock checks. |
| `app/routers/behavior.py` | Customer product-interaction logging and basic recommendations. |
| `app/routers/analytics.py` | Protected analytics API endpoints and CSV/PDF report responses. |
| `app/services/analytics.py` | Database-based GMV, order count, AOV, trends, product/vendor rankings, customer segments, and moving-average forecast. |
| `dashboard/dashboard.py` | Main Streamlit app for login, registration, role-based marketplace pages, products, orders, stock, and live marketplace analytics. |
| `dashboard/session.py` | Safely restores a user profile after a Streamlit rerun or clears an invalid partial session. |
| `dashboard/historical_data.py` | Downloads/reads Olist CSVs, validates keys, joins tables, filters invalid rows, computes historical metrics, and builds the data-quality audit. |
| `dashboard/pages/1_Historical_Analytics.py` | Separate Olist historical analytics page with filters, KPIs, Plotly charts, rankings, and CSV downloads. |
| `scripts/bootstrap_admin.py` | Creates the initial admin from environment variables. |
| `scripts/seed_demo.py` | Loads synthetic development/demo users, vendors, products, and transactions; must not be used in production. |
| `scripts/analyze_olist.py` | Runs historical analysis from downloaded/local Olist files and exports rankings/audit files. |
| `alembic/versions/0001_initial.py` | Initial database migration. |
| `alembic/env.py`, `alembic.ini` | Alembic migration configuration. |
| `tests/test_api.py` | API, permissions, vendor approval, catalog visibility, order/stock behavior, and analytics tests. |
| `tests/test_historical_data.py` | Historical data joins, data-quality checks, and aggregation tests using small test fixtures. |
| `tests/test_dashboard_session.py` | Tests missing/invalid Streamlit login sessions. |
| `requirements.txt` | Backend runtime dependencies. |
| `requirements-dashboard.txt` | Streamlit, Pandas, Requests, and Plotly dependencies. |
| `requirements-dev.txt` | Development/test dependencies. |
| `Dockerfile.api`, `Dockerfile.dashboard`, `docker-compose.yml` | Build and run the API, dashboard, and local database. |
| `.github/workflows/ci.yml` | Runs tests, migration checks, Python compilation, and Docker builds in GitHub Actions. |
| `.github/workflows/deploy-render.yml` | Optional Render deploy-hook workflow when secrets are configured. |
| `.github/workflows/historical-data.yml` | Checks the real-data processing workflow and produces analysis artifacts. |
| `docs/OLIST_DATASET.md` | Dataset provenance, license, data joins, metric definitions, and reproducibility instructions. |
| `docs/DEPLOYMENT.md` | Hosting, environment variables, deployment, and smoke-test guide. |
| `docs/ROADMAP.md` | Implemented MVP versus future milestones. |
| `.env.example` | Example configuration keys; never put real secrets in Git. |

**Structure difference from the initial notes:** the submitted notes propose separate files such as `app/models/vendor.py`, `app/schemas/vendor_schema.py`, `app/routes/vendor_routes.py`, and `create_tables.py`. The actual repository organizes these responsibilities into `app/models.py`, `app/schemas.py`, `app/routers/`, and Alembic migrations. This is a different organization of the same core responsibilities, not a requirement to duplicate the files.

---

## 4. Data model: what is stored and where

The live marketplace is stored in the configured relational database through SQLAlchemy.

| Entity/table | What it stores |
|---|---|
| `users` | Login email, password hash, role, and optional vendor link |
| `vendors` | Business name, owner, contact information, category, commission rate, status, and creation time |
| `customer_profiles` | Customer profile information linked to a user |
| `products` | Vendor-owned product name, description, category, price, and active/hidden state |
| `inventory` | Current stock and low-stock threshold for each product |
| `inventory_movements` | Stock adjustment history and reason |
| `orders` | Customer, order status, order total, and timestamp |
| `order_items` | Product, vendor, quantity, and unit-price snapshot at purchase time |
| `interactions` | Customer product view/cart-style events and timestamps |

The repository does not currently define a separate marketplace “services catalog” table. The folder `app/services/` means application business-logic services; it currently contains analytics logic. If the mentor means service listings that customers can buy, that would be a separate feature to add.

### Why use a database instead of Python lists?

The example `vendors = []` and `products = []` lists are useful for teaching a minimal route, but they lose data when a server restarts and do not provide relational constraints. ShopSense uses SQLAlchemy-backed records so data persists and orders can refer to the correct product/vendor.

---

## 5. Two data sources: do not mix them

### A. Live marketplace data

Live registration, products, stock, interactions, and demonstration orders are stored in the ShopSense database. The customer checkout creates an order record and deducts stock, but no payment is processed.

Live GMV is calculated from order-item price snapshots:

**GMV = sum(quantity × unit price) for non-cancelled order items.**

This is not collected cash or profit. The current model does not account for payment settlement, refunds, tax, shipping, discounts, or business costs.

### B. Historical Olist data

Source: [Brazilian E-Commerce Public Dataset by Olist on Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). It contains anonymized Brazilian marketplace records from 2016–2018 and is licensed CC BY-NC-SA 4.0. See [dataset methodology](OLIST_DATASET.md) before redistributing or reusing data.

The dashboard uses five source tables:

| CSV | Purpose |
|---|---|
| `olist_sellers_dataset.csv` | Seller ID, city, state |
| `olist_products_dataset.csv` | Product ID and category |
| `olist_order_items_dataset.csv` | Order, item, product, seller, price, freight |
| `olist_orders_dataset.csv` | Order status and purchase timestamp |
| `product_category_name_translation.csv` | Portuguese-to-English category mapping |

The processing pipeline validates keys, joins order items to orders/products/sellers, translates categories, filters to delivered items with valid price/date, and records excluded rows in a quality audit.

**Historical item sales value = sum of item price for delivered order items.** It excludes freight and is not profit or verified payment revenue. An order can contain multiple items and sellers, so the order KPI counts distinct order IDs, not item rows.

The historical Olist IDs are not imported as live ShopSense vendors/products. This separation is intentional.

### C. Synthetic demo data

`scripts/seed_demo.py` creates fake data for local demonstration only. It is not the genuine Olist dataset and must not be run in production. When presenting results, always say whether a chart comes from live demo transactions or historical Olist data.

---

## 6. Step-by-step audit against the mentor's Steps 1–20

The shared notes jump from Step 5 to Step 9; Steps 6–8 are not described in those notes. Their general model/product/inventory responsibilities are present in the actual repository, but the original step numbers and code were not supplied.

### Step 1 — Project structure

**Status: Implemented with a different folder layout.**

The code is divided into application code, dashboard, scripts, tests, migrations, documentation, and CI workflows.

**Explain to mentor:** “I organized the code by responsibility. The API is in app/routers, database models and validation are centralized in app/models.py and app/schemas.py, the main dashboard is in dashboard, and tests and deployment documentation are separate.”

### Step 2 — Install packages

**Status: Implemented.**

Backend dependencies are in `requirements.txt`; dashboard dependencies are in `requirements-dashboard.txt`; development/test dependencies are in `requirements-dev.txt`.

**Why:** This makes installation repeatable instead of requiring a developer to remember each package manually.

### Step 3 — Create the database

**Status: Implemented through configuration and migrations, not a hard-coded SQL command.**

Local development defaults to SQLite. Hosted deployment uses the PostgreSQL URL supplied in the `DATABASE_URL` environment variable. The PostgreSQL database itself must exist in the database provider before the API connects.

**Explain:** “I keep database credentials outside the source code. I can point the same application at a local SQLite database or hosted PostgreSQL by changing configuration.”

### Step 4 — Database connection

**Status: Implemented in `app/database.py`.**

It creates the SQLAlchemy engine, session factory, and `get_db` dependency. Routes request a database session and close it after the request.

### Step 5 — Vendor table

**Status: Implemented in `app/models.py` as `Vendor`.**

The model stores business name, owner, email, phone, category, commission rate, status, and creation timestamp. A linked `User` record handles login and role permissions.

**Explain:** “Vendor profile information and vendor login identity are related but separate responsibilities.”

### Steps 6–8 — Product, inventory, transaction/order models

**Status: The supplied notes do not define these numbered steps; the core models exist in the repository.**

- `Product` stores product details and owning vendor.
- `Inventory` stores current stock and threshold.
- `InventoryMovement` records stock changes.
- `Order` and `OrderItem` store checkout records and item-level sales snapshots.

**Explain:** “The schema is relational: each product points to a vendor, each order item points to a product/vendor/order, and stock changes are tracked separately.”

### Step 9 — Create database tables

**Status: Implemented using Alembic migrations. There is no `create_tables.py` in the current repository.**

The initial schema is in `alembic/versions/0001_initial.py`. Apply it using:

~~~bash
alembic upgrade head
~~~

**Why:** Migrations record schema changes and can be applied consistently on local and hosted databases.

### Step 10 — Vendor registration schema

**Status: Implemented in `app/schemas.py` as `VendorRegister`.**

Pydantic checks field types and constraints, including a valid email format, string length bounds, and a minimum password length. Duplicate email handling is also performed by the registration flow/database constraint.

**Explain:** “The API validates the request before storing it, so malformed payloads receive a validation error rather than being accepted as a vendor.”

### Step 11 — Vendor API

**Status: Implemented, but the registration endpoint lives in the authentication router.**

- `POST /api/auth/register/vendor` registers a vendor and creates a pending application.
- `GET /api/vendors` lists vendors for the admin.
- `GET /api/vendors/me` returns the signed-in vendor profile.
- `PATCH /api/vendors/{vendor_id}/status` lets an admin approve, reject, or suspend a vendor.

File locations: `app/routers/auth.py` and `app/routers/vendors.py`.

**Difference from the notes:** the application does not store vendors in a temporary Python list. It writes database records.

### Step 12 — Validation logic and the 99% target

**Status: Input validation exists; the ≥99% evaluation target has not been demonstrated by the current tests.**

Current checks include Pydantic schema constraints, email validation, password-length requirements, duplicate-email protection, and role/approval checks. These are functional safeguards. They do not automatically prove 99% accuracy over 1,000 labeled registrations.

To prove the target, prepare a labeled set of valid and invalid vendor payloads, specify the expected accept/reject decision for each, run them through the registration validation logic, and calculate:

**Validation accuracy = correctly classified cases ÷ all labeled test cases × 100.**

For 1,000 labeled cases, at least 990 must be classified correctly to reach 99%. Include valid, missing-field, malformed-email, too-short values, duplicate email, invalid phone, and boundary cases. Do not write “99.5% achieved” unless a real evaluation run produced that result.

### Step 13 — Product API

**Status: Implemented in `app/routers/products.py`.**

- `GET /api/products`: public customer catalog.
- `GET /api/products/mine`: a vendor's own listings and visibility explanation.
- `POST /api/products`: approved vendor adds a product.
- `PATCH /api/products/{product_id}`: update a product.
- `PUT /api/products/{product_id}/inventory`: update stock.

The Pydantic `ProductIn`, `ProductUpdate`, and `InventorySet` schemas validate the payloads.

**Product visibility rule:** the vendor must be approved and the product must be active. A product with zero stock can still appear in the catalog, but checkout cannot add more units than are available.

### Step 14 — Sales dataset

**Status: The example `data/transactions.csv` is not a committed source file; there are two actual data paths instead.**

1. Live ShopSense orders are stored in the database in `orders` and `order_items`.
2. Historical analysis downloads/reads the Olist CSVs through `dashboard/historical_data.py`.

**Explain:** “I replaced the tiny five-row sample with a real public e-commerce dataset for historical analysis. I keep that dataset separate from live orders because the time period, currency, anonymized sellers, and purpose are different.”

### Step 15 — Sales analytics module

**Status: Implemented in two modules.**

- `app/services/analytics.py` calculates live marketplace GMV, order count, average order value, trends, top products, vendor rankings, rule-based customer segments, and a 7-day moving-average demand baseline.
- `dashboard/historical_data.py` calculates Olist delivered-item sales value, seller/product rankings, category/state comparisons, monthly sales, and data-quality counts.

**Explain:** “Pandas is used for the historical CSV pipeline. For the live marketplace, SQLAlchemy reads saved order and order-item records and aggregates the values.”

**Important:** Neither module calculates profit margin because product costs and all relevant expenses are not modeled.

### Step 16 — Analytics API

**Status: The analytics API is implemented; the exact example route `/analytics/revenue` is not present.**

The current endpoints are under `app/routers/analytics.py`:

| Endpoint | Purpose |
|---|---|
| `GET /api/analytics/summary` | GMV, orders, average order value, products, low stock |
| `GET /api/analytics/trends` | Daily GMV trend |
| `GET /api/analytics/top-products` | Best-selling product ranking |
| `GET /api/analytics/vendors` | Admin vendor ranking |
| `GET /api/analytics/customer-segments` | Rule-based purchase segments |
| `GET /api/analytics/forecast` | Moving-average baseline for a product |
| `GET /api/analytics/sales.csv` | CSV transaction export |
| `GET /api/analytics/sales.pdf` | PDF overview |

**If the mentor specifically requires `GET /api/analytics/revenue`:** add a small route that returns the summary GMV with a clear metric definition, or ask whether `/api/analytics/summary` meets the requirement. Do not label GMV as collected revenue without explaining its definition.

### Step 17 — Main application

**Status: Implemented in `app/main.py`.**

The file creates the FastAPI app, configures CORS, includes the auth/vendor/product/order/customer-behavior/analytics routers, and exposes `/health` and `/ready`.

**Explain:** “The routers keep endpoints modular, while main.py combines them into one API application.”

### Step 18 — Run the project

**Status: Implemented.**

For a local run without Docker, use Python 3.12+ and install dependencies in a virtual environment:

~~~bash
python -m venv .venv
~~~

Windows PowerShell:

~~~powershell
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt -r requirements-dashboard.txt
alembic upgrade head
~~~

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in the environment, then bootstrap the admin:

~~~bash
python -m scripts.bootstrap_admin
uvicorn app.main:app --reload
~~~

Open a second terminal and run:

~~~bash
streamlit run dashboard/dashboard.py
~~~

Useful local URLs:

- API documentation: http://127.0.0.1:8000/docs
- API readiness: http://127.0.0.1:8000/ready
- Dashboard: http://localhost:8501

Docker Compose is also supported; see [DEPLOYMENT.md](DEPLOYMENT.md) and the root README.

### Step 19 — Dashboard and charts

**Status: The dashboards and bar/line/area charts exist; pie charts and histograms are not present in the reviewed chart calls.**

- `dashboard/dashboard.py` is the live marketplace UI with role-specific pages, revenue trend, best-selling products, vendor comparison, demand baseline, customer segments, and reports.
- `dashboard/pages/1_Historical_Analytics.py` is the historical Olist dashboard with date/state/category filters, KPI metrics, monthly line chart, category/state bar charts, seller/product rankings, audit information, and CSV downloads.

If the evaluation explicitly requires a **pie chart and histogram**, add them to the appropriate page and test the displayed data. The current bar/line charts do not satisfy those two chart types by themselves.

### Step 20 — Testing and evaluation

**Status: Automated tests exist; the 99% registration and 98% transaction consistency targets still need a formal measured report.**

Test files:

- `tests/test_api.py`: registration, permissions, product visibility, order creation, stock validation, analytics endpoints.
- `tests/test_historical_data.py`: data joins, duplicate keys, invalid values, aggregation, and empty-filter behavior.
- `tests/test_dashboard_session.py`: missing/expired login-session recovery.

Run:

~~~bash
pytest -q
~~~

For a meaningful transaction consistency evaluation, independently recompute each audited order total as the sum of its item quantity × unit-price snapshots, compare it with the saved order total, and count exact matches:

**Transaction consistency = correctly reconciled transactions ÷ all audited transactions × 100.**

For 1,000 audited transactions, at least 980 correct reconciliations are required to reach 98%. The sample numbers in the original notes are only examples; don't report them as results unless an actual test run confirms them.

A passing functional test suite is valuable, but it is not automatically proof of a 99%/98% rate over a 1,000-record evaluation set.

---

## 7. How to demonstrate ShopSense to the mentor

Use this order in the meeting. It shows the workflow from input to storage to analysis.

### Demo A — Vendor registration and approval

1. Open the Streamlit app and register a new vendor with valid information.
2. Explain that the API validates the payload with Pydantic and stores the user/vendor records in the database.
3. Explain that the new vendor starts with status `pending`.
4. Sign in as Admin and approve the vendor.
5. Show that a pending/unapproved vendor cannot create listings.

**Say:** “Registration, validation, and approval are separate steps. A valid registration does not automatically make the vendor approved.”

### Demo B — Product and inventory

1. Sign in as the approved vendor.
2. Open My products and create a product with name, category, price, and stock.
3. Show the product's visibility status.
4. Open the customer catalog and confirm that the active product from the approved vendor is visible.
5. Change inventory and show the updated stock.

**Say:** “The product is linked to the vendor ID, and inventory is stored separately. Customer visibility depends on vendor approval and the product's active state.”

### Demo C — Simulated order and live analytics

1. Sign in as Customer.
2. Browse products and place a simulated order.
3. Explain that the order is recorded and stock is reduced, but no real payment is collected.
4. Return to Admin/Vendor analytics.
5. Show the GMV, order count, trends, top products, and report exports.

**Say:** “The analytics service aggregates saved order-item snapshots. This keeps the dashboard connected to stored marketplace transactions instead of manually typed chart values.”

### Demo D — Genuine historical dataset

1. Open the **Historical Analytics** page from the Streamlit sidebar.
2. Show the data source and explain that the first load downloads/caches the Olist CSV files.
3. Show date, seller-state, and category filters.
4. Show monthly sales, seller rankings, category performance, and product rankings.
5. Open Data quality & source and explain the excluded-row audit and the metric definition.
6. Download a seller or product ranking CSV.

**Say:** “This dashboard is a separate historical-data analysis. I clean and join public seller, product, order, and order-item data, filter delivered records, and aggregate item sales value. These anonymous historical sellers are not the users registered in the live marketplace.”

### Demo E — API and tests

1. Open the deployed API's `/docs` URL.
2. Point out the auth, vendors, products, orders, customer insights, and analytics groups.
3. Explain that FastAPI generates the OpenAPI documentation from the route definitions and Pydantic schemas.
4. Show the GitHub Actions run and test files.
5. State the actual test result and any remaining evaluation target honestly.

---

## 8. Ready-to-say mentor explanation

Use this as a speaking guide; adjust it to your own words.

> “I built ShopSense as an individual project. It is a multi-vendor marketplace and analytics platform. I used FastAPI for the backend, SQLAlchemy with a relational database for persistent data, and Streamlit for the user interface.
>
> “The live part supports vendor and customer registration, login, admin approval, product listing, inventory updates, and simulated orders. Vendors can only publish after approval, and customers see active products from approved vendors. The order API checks stock, stores order-item price snapshots, and updates inventory.
>
> “For analytics, the live dashboard calculates GMV, order count, average order value, product rankings, and trends from the saved orders. I also added a separate historical analytics page using the public Olist Brazilian e-commerce dataset. I use Pandas to validate and join seller, product, order, and item data, then display monthly, seller, category, and product performance with Plotly.
>
> “I keep historical data separate from live demo orders because the historical dataset is anonymized and from 2016–2018. The checkout is simulated, so I do not claim real payment revenue or profit. I have automated tests, and I am separately verifying the formal 99% registration validation and 98% transaction consistency evaluation criteria.”

---

## 9. Questions the mentor may ask

**Q. Why FastAPI?**  
A. It makes it straightforward to create REST endpoints, validate requests using Pydantic, control access, and expose interactive API documentation at `/docs`.

**Q. Why SQLAlchemy and PostgreSQL?**  
A. They provide persistent relational records and relationships between users, vendors, products, inventory, and orders. This is safer than in-memory lists for an application with multiple users.

**Q. What happens when a vendor registers?**  
A. The API validates the request, checks for duplicate email, creates the login identity and vendor profile, and marks the vendor as pending. The admin must approve the vendor before the vendor can publish products.

**Q. Why might an approved vendor's product not appear to a customer?**  
A. Approval alone is not enough. The vendor must be approved, the product must be active, and the customer dashboard must point to the same backend/database. The vendor product page includes a visibility note to help debug this.

**Q. How do you calculate sales?**  
A. Live marketplace GMV is the sum of quantity multiplied by unit price for non-cancelled order items. Historical item sales value is the sum of item prices for delivered Olist items. These are different metrics and neither means profit or confirmed cash collected.

**Q. Is the forecasting feature machine learning?**  
A. The current implementation is a 7-day moving-average baseline. It is not a trained or validated ML model. A trained model with a time-based evaluation can be a later extension.

**Q. How do you know registration validation is 99% accurate?**  
A. I should only claim that after evaluating a labeled valid/invalid registration set and reporting the number of correct decisions divided by total test cases. The existing schema checks and unit tests are not, by themselves, a measured 99% result.

**Q. How do you know transactions are 98% consistent?**  
A. Recompute order totals independently from order-item snapshots, compare them with stored totals, and report the proportion that matches. I should show the actual evaluation output, not the illustrative numbers from the initial notes.

**Q. Why is the historical dataset not used as live vendors?**  
A. Olist's seller IDs are anonymized historical identifiers and do not include the current account/contact data required for registration. Keeping them separate prevents false identities and mixing historical sales with current demonstration transactions.

**Q. What is not completed yet?**  
A. The 99% and 98% evaluation reports have not been established by the existing tests; the exact `/api/analytics/revenue` route in the sample is not present; pie charts and histograms were not found in the current chart calls; real payment processing, refunds, profit margins, and trained ML are outside the current MVP.

---

## 10. Remaining items before final submission

Prioritize these in order:

- [ ] Run the full test suite on the current commit and save the actual output.
- [ ] Test the deployed API, login, vendor approval, product visibility, customer checkout, stock update, and analytics.
- [ ] Decide with the mentor whether `/api/analytics/summary` satisfies Step 16 or the exact `/api/analytics/revenue` route is required.
- [ ] Add a pie chart and histogram if those chart types are mandatory.
- [ ] Build a labeled registration-validation evaluation set and report the actual accuracy.
- [ ] Reconcile a transaction test set and report the actual consistency percentage.
- [ ] Verify the Historical Analytics page on the live Streamlit deployment and record screenshots.
- [ ] Include dataset attribution, license, metric definitions, and screenshots in the final submission.
- [ ] Never claim the illustrative 99.5% or 98.5% values as measured results without test evidence.

### Local commands

~~~bash
# Run tests
pytest -q

# Start API (after dependencies, database migration, and admin setup)
uvicorn app.main:app --reload

# Start dashboard in another terminal
streamlit run dashboard/dashboard.py

# Run historical Olist CSV analysis and export rankings/audit
python -m scripts.analyze_olist --download
~~~

### Official project links

- Repository: https://github.com/Jaymin1651/ShopSense
- Live dashboard: https://shopsense-new.streamlit.app/
- Olist dataset: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- [Dataset methodology](OLIST_DATASET.md)
- [Deployment guide](DEPLOYMENT.md)
- [Implementation roadmap](ROADMAP.md)

---

## Final note

The most credible presentation is to demonstrate what works, explain the code responsible for it, show actual test results, and identify remaining items clearly. The project is an individual MVP; advanced machine learning, payment processing, and unmeasured evaluation percentages should be presented as future work until implemented and verified.
