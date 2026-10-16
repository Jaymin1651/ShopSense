# ShopSense — End-to-End Implementation Guide for Mentor Demo

**Project:** ShopSense — Multi-Vendor E-Commerce Analytics Platform  
**Project type:** Individual academic MVP  
**Repository:** https://github.com/Jaymin1651/ShopSense  
**Dashboard:** https://shopsense-new.streamlit.app/  
**Reviewed against repository code:** 16 October 2026

This guide explains the current implementation from problem statement to architecture, code, tests, and a live demonstration. The snippets are short, representative excerpts from the repository; the linked source files remain the source of truth.

## 1. Start with the project explanation

### What problem does ShopSense solve?

A multi-vendor marketplace needs to manage vendor applications, product listings, inventory, customer orders, and sales reporting in one place. ShopSense is an academic MVP that demonstrates these connected workflows and adds analytics on top of the resulting transaction data.

### Main objectives

1. Let vendors and customers register and sign in.
2. Protect passwords and use role-based permissions.
3. Let an admin approve, reject, or suspend vendors.
4. Let approved vendors create products, publish or hide listings, and update stock.
5. Let customers browse the catalog and place a simulated order.
6. Check stock before checkout and reduce stock after an order is recorded.
7. Show live marketplace sales metrics and downloadable reports.
8. Analyze a separate real historical e-commerce dataset using Pandas and Plotly.
9. Test important workflows and document deployment.

### 30-second introduction to say to the mentor

> “I built ShopSense as an individual project. It combines a multi-vendor marketplace with sales analytics. FastAPI handles the backend APIs, SQLAlchemy stores data in a relational database, and Streamlit provides the user interface. Vendors register and wait for admin approval; after approval, they can list products and manage stock. Customers can browse and place simulated orders, which update inventory. The live analytics summarize these saved transactions. I also built a separate historical analytics page using the public Olist Brazilian e-commerce dataset, with Pandas data preparation and Plotly charts. This is an academic MVP: checkout does not collect real payments, and the demand forecast is a simple moving-average baseline rather than a trained ML model.”

Do not claim that the system charges a payment card, uses a trained forecasting model, or has measured validation percentages unless that functionality and evidence are added.

## 2. Architecture: how the parts communicate

~~~text
                    LIVE MARKETPLACE
┌───────────────────────────────────────────────────────────┐
│ Streamlit UI: dashboard/dashboard.py                      │
│ Admin | Vendor | Customer                                 │
└──────────────────────────┬────────────────────────────────┘
                           │ HTTP requests + Bearer JWT
                           ▼
┌───────────────────────────────────────────────────────────┐
│ FastAPI: app/main.py                                      │
│ auth | vendors | products | orders | behavior | analytics │
└──────────────────────────┬────────────────────────────────┘
                           │ SQLAlchemy ORM
                           ▼
┌───────────────────────────────────────────────────────────┐
│ Relational database                                       │
│ PostgreSQL when hosted / SQLite for local development     │
│ users, vendors, products, inventory, orders, order_items… │
└───────────────────────────────────────────────────────────┘

                  HISTORICAL ANALYTICS
Olist public CSV files (2016–2018)
             │
             ▼
dashboard/historical_data.py
Download → validate → join → clean → aggregate → audit
             │
             ▼
dashboard/pages/1_Historical_Analytics.py
Filters → KPIs → Plotly charts → rankings → CSV downloads

Important: the historical Olist data path does not write into the live marketplace database.
~~~

### Explain each technology

| Technology | How it is used |
|---|---|
| Python | Main programming language |
| FastAPI | Defines REST endpoints and serves the backend |
| Pydantic | Validates incoming request fields and response structures |
| SQLAlchemy | Maps Python objects to relational tables and performs database queries |
| PostgreSQL / SQLite | Stores persistent marketplace records |
| Alembic | Creates and versions the database schema |
| PyJWT | Creates and verifies signed login tokens |
| PBKDF2-HMAC-SHA256 | Hashes passwords before storage |
| Streamlit | Builds the admin, vendor, customer, and historical analytics interface |
| Pandas | Reads, validates, joins, filters, and aggregates CSV data |
| Plotly | Displays interactive charts |
| ReportLab | Generates a one-page PDF overview |
| pytest | Tests API behavior and historical data processing |
| Docker Compose | Runs the database, API, and dashboard together |
| GitHub Actions | Runs automated checks and builds when code is pushed |

### Request lifecycle

1. A person performs an action in the Streamlit interface.
2. The dashboard helper sends an HTTP request to the configured API_URL.
3. If the person is signed in, the dashboard sends an Authorization Bearer token.
4. FastAPI validates the request schema and resolves the current user.
5. A role guard checks whether that role may use the endpoint.
6. The route reads or changes data using a SQLAlchemy database session.
7. The API returns JSON or a file response.
8. Streamlit reruns and displays the updated data.

The API can also be tested directly through the interactive OpenAPI page at /docs.

## 3. Repository map: which file to open

| File | Responsibility |
|---|---|
| app/main.py | Creates FastAPI, registers routers, configures CORS, and defines health/readiness endpoints |
| app/config.py | Reads environment configuration and normalizes PostgreSQL connection URLs |
| app/database.py | Creates the SQLAlchemy engine/session and provides get_db() |
| app/models.py | Defines relational tables and relationships |
| app/schemas.py | Defines Pydantic request/response models and validation |
| app/security.py | Password hashing, JWT creation/verification, current-user lookup, role checks |
| app/routers/auth.py | Vendor/customer registration, login, and /me |
| app/routers/vendors.py | Admin vendor listing/status changes and vendor profile |
| app/routers/products.py | Public catalog, vendor products, visibility rules, inventory changes |
| app/routers/orders.py | Checkout validation, order items, and stock deduction |
| app/routers/behavior.py | Customer interaction logging and simple recommendations |
| app/routers/analytics.py | Protected analytics endpoints and CSV/PDF exports |
| app/services/analytics.py | Live sales metrics, rankings, segments, and forecast baseline |
| dashboard/dashboard.py | Streamlit login/registration, role-specific tabs, products, orders, reports, live charts |
| dashboard/session.py | Restores or clears the user's Streamlit session safely |
| dashboard/historical_data.py | Downloads, validates, joins, and aggregates Olist CSV files |
| dashboard/pages/1_Historical_Analytics.py | Historical filters, KPIs, charts, seller/product tables, CSV downloads |
| scripts/bootstrap_admin.py | Creates the initial admin from environment variables |
| scripts/seed_demo.py | Adds synthetic demo users/products/orders for development only |
| scripts/analyze_olist.py | Runs Olist analysis and writes ranking/audit outputs |
| alembic/versions/0001_initial.py | Initial database schema migration |
| tests/test_api.py | Tests authentication, permissions, approval, stock, orders, analytics, exports |
| tests/test_historical_data.py | Tests data joins, validation, exclusions, and aggregation calculations |
| tests/test_dashboard_session.py | Tests session restoration behavior |
| docs/OLIST_DATASET.md | Olist source, license, table joins, metric definitions, reproducibility |
| docs/DEPLOYMENT.md | Local/hosted deployment and verification checklist |
| docs/ROADMAP.md | Current MVP versus future features |

**Structure difference from a tutorial layout:** the current repository consolidates models into app/models.py, schemas into app/schemas.py, and routes into app/routers/. It uses Alembic migrations rather than a separate create_tables.py file. Do not create duplicate files just to match a sample directory tree.

## 4. Set up and run the project

### Option A — Docker Compose (recommended for a consistent demo)

Requirements: Git and Docker Desktop.

From the repository root, copy the example environment file:

~~~powershell
Copy-Item .env.example .env
~~~

Edit .env and choose your own strong values for POSTGRES_PASSWORD, JWT_SECRET, ADMIN_EMAIL, and ADMIN_PASSWORD. Never commit the real .env file.

Run:

~~~powershell
docker compose up --build -d
docker compose ps
docker compose logs -f api
~~~

Open:

- Dashboard: http://localhost:8501
- API documentation: http://localhost:8000/docs
- API health: http://localhost:8000/health
- Database readiness: http://localhost:8000/ready

The Compose setup starts PostgreSQL, the API, and the dashboard. The API container runs the migration/admin-bootstrap steps described in the README and deployment guide. Optional synthetic demo data is for development only:

~~~powershell
docker compose exec api python -m scripts.seed_demo
~~~

The seeder prints synthetic demo accounts. Do not run it in production or present those synthetic transactions as Olist data.

Stop the local services with:

~~~powershell
docker compose down
~~~

The database volume remains. Running docker compose down -v removes the volume and erases its stored data.

### Option B — Run locally without Docker

Use Python 3.12 or later. From the project root:

~~~powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt -r requirements-dashboard.txt
alembic upgrade head
~~~

Set the initial admin credentials in the current PowerShell session:

~~~powershell
$env:ADMIN_EMAIL = "admin@example.com"
$env:ADMIN_PASSWORD = "UseYourOwnStrongPassword123!"
python -m scripts.bootstrap_admin
~~~

Start the API in Terminal 1:

~~~powershell
uvicorn app.main:app --reload
~~~

Start the dashboard in Terminal 2:

~~~powershell
.venv\Scripts\Activate.ps1
streamlit run dashboard/dashboard.py
~~~

The local dashboard defaults to http://localhost:8000 for its API. If the API is hosted elsewhere, set API_URL before launching Streamlit.

Run tests from the project root:

~~~powershell
pytest -q
~~~

# Part A — Vendor Management System

## 5. What the vendor subsystem does

The vendor subsystem controls who can sell products and what customers can see. It connects user identity, approval status, product ownership, inventory, and order records.

### Roles and permissions

| Role | Allowed activities |
|---|---|
| Admin | View vendors, approve/reject/suspend vendors, see marketplace-wide analytics, administer records |
| Vendor | View own profile/products/orders, create products after approval, edit own listings and stock, see own analytics |
| Customer | Browse published catalog, record product interactions, place simulated orders, see own orders and recommendations |

A vendor must be approved before creating product listings. A product must be active and belong to an approved vendor to appear in the public catalog. Zero-stock products may still be visible, but checkout must not allow purchasing unavailable quantities.

## 6. Step 1 — Design the database entities

Open app/models.py. SQLAlchemy models define the tables that store marketplace state.

| Table/model | Why it exists |
|---|---|
| User | Login email, password hash, role, and optional link to a vendor |
| Vendor | Business details, category, commission rate, and status |
| CustomerProfile | Customer name connected to a user account |
| Product | Vendor-owned product details, price, category, active/hidden flag |
| Inventory | Current quantity and low-stock threshold for a product |
| InventoryMovement | History of stock additions, removals, and adjustments |
| Order | Customer, order status, total, and timestamp |
| OrderItem | Product/vendor, quantity, and unit-price snapshot at purchase time |
| Interaction | Customer product view/wishlist/cart-style event |

One vendor can own many products. Each product has one inventory record. An order can contain multiple order items. Each order item stores vendor_id as well as product_id, supporting vendor-scoped reporting even when a customer buys from multiple vendors. OrderItem.unit_price preserves the price at the time of the order, even if the current product price changes later. InventoryMovement records reasons such as initial_stock, manual_adjustment, and sale.

### Why not keep everything in Python lists?

A list is lost when the process restarts and does not provide relational records. ShopSense uses a database so vendor, product, stock, and order records remain connected and can be analyzed later.

## 7. Step 2 — Validate incoming data

Open app/schemas.py. Pydantic models validate the request before route logic runs.

Representative vendor schema from the current project:

~~~python
class VendorRegister(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=30)
    category: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)
~~~

Explain the checks:

- Business and owner names must be within defined lengths.
- EmailStr checks that the email has a valid email format.
- Phone is currently validated by length bounds, not by a country-specific phone-number library.
- Password must be 10–128 characters for public vendor/customer registration.
- Product price must be greater than zero; stock and low-stock threshold cannot be negative.
- Order line quantity must be positive and at most 100.
- An order cannot contain the same product ID twice; OrderCreate rejects duplicate product IDs.
- Invalid payloads normally produce HTTP 422.

**Do not say the project has 99% validation accuracy.** These are schema rules and tests. A percentage requires a defined labeled test set, measured results, and a documented calculation.

## 8. Step 3 — Register vendors and customers

Open app/routers/auth.py. Vendor registration follows this sequence:

1. Validate the payload with VendorRegister.
2. Normalize the email to lowercase.
3. Check that the email is not already used by a user or vendor.
4. Create a Vendor with status pending.
5. Flush the vendor to obtain its database ID.
6. Create a User with role vendor, password hash, and vendor ID.
7. Commit the records together.
8. Return the safe UserOut response, not the password hash.

Representative excerpt:

~~~python
vendor = Vendor(
    business_name=payload.business_name,
    owner_name=payload.owner_name,
    email=email,
    phone=payload.phone,
    category=payload.category,
    status='pending',
)
db.add(vendor)
db.flush()

user = User(
    email=email,
    password_hash=hash_password(payload.password),
    role='vendor',
    vendor_id=vendor.id,
)
db.add(user)
db.commit()
~~~

The customer registration route creates a customer user and a linked CustomerProfile. It does not require admin approval.

**Mentor explanation:** “I separated the login identity from the vendor business profile. The users record controls authentication and role permissions; the vendors record contains business information and approval status. Registration creates a pending vendor, so registering alone does not grant selling permissions.”

## 9. Step 4 — Secure passwords and sessions

Open app/security.py.

### Password hashing

The application hashes passwords with PBKDF2-HMAC-SHA256 using a random salt and 480,000 iterations. It stores the algorithm, iteration count, salt, and digest—not the original password.

### JWT authentication

After successful login, create_token() signs a token with the user ID and expiry. The dashboard stores the token in Streamlit session state and sends it with API requests:

~~~python
headers = {'Authorization': f'Bearer {token}'} if token else {}
~~~

The backend current_user() decodes the token, checks its expiry/signature, and loads the user. Dependencies such as require_roles('admin') and require_roles('vendor') restrict endpoints.

- HTTP 401: missing, invalid, or expired token.
- HTTP 403: the user is logged in but does not have the required role or tries to modify another vendor's record.

Do not share real passwords, JWT tokens, database URLs, or deployment secrets in a presentation or commit them to GitHub.

## 10. Step 5 — Admin approves or rejects a vendor

Open app/routers/vendors.py. Important endpoints:

- GET /api/vendors — admin only; returns the vendor list.
- GET /api/vendors/me — vendor only; returns the current vendor's profile.
- PATCH /api/vendors/{vendor_id}/status?status=approved — admin only; updates status.

Representative route:

~~~python
@router.patch('/{vendor_id}/status', response_model=VendorOut)
def set_vendor_status(
    vendor_id: int,
    status: Literal['approved', 'suspended', 'rejected'],
    db: Session = Depends(get_db),
    _: User = Depends(require_roles('admin')),
):
    vendor = db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(404, 'Vendor not found')
    vendor.status = status
    db.commit()
    db.refresh(vendor)
    return vendor
~~~

The Literal type restricts status values to the three supported options. The database is committed, then refreshed so the response reflects the stored record.

**Mentor explanation:** “The vendor lifecycle is controlled by the admin. The default state is pending. Approval changes the status, but it does not automatically create a product. The vendor still has to add a product, and that product must be active to appear in the customer catalog.”

## 11. Step 6 — Create and publish a product

Open app/routers/products.py.

### Product visibility rule

The helper serialize_product() returns visible_to_customers and a readable visibility_note:

~~~python
visible = vendor_status == 'approved' and product.is_active
if vendor_status != 'approved':
    note = f'Vendor account is {vendor_status}'
elif not product.is_active:
    note = 'Product is hidden by vendor'
elif product.inventory.quantity == 0:
    note = 'Visible, but out of stock'
else:
    note = 'Visible in customer catalog'
~~~

The stock quantity does not determine whether a product is published; it determines whether the customer can order it.

### Product creation flow

1. The vendor sends name, description, category, price, quantity, and low-stock threshold.
2. The API identifies the current vendor from the JWT.
3. It checks that the vendor exists and has approved status.
4. It creates the product and inventory record.
5. It records initial stock in inventory_movements if starting quantity is above zero.
6. It commits and returns the product with visibility information.

Representative excerpt:

~~~python
vendor = db.get(Vendor, user.vendor_id)
if not vendor or vendor.status != 'approved':
    raise HTTPException(403, 'Vendor approval required before listing products')

product = Product(
    vendor_id=user.vendor_id,
    name=payload.name,
    description=payload.description,
    category=payload.category,
    price=payload.price,
)
product.inventory = Inventory(
    quantity=payload.quantity,
    low_stock_threshold=payload.low_stock_threshold,
)
db.add(product)
db.flush()
~~~

### Product ownership and inventory

For edits and inventory changes, the route checks that a vendor is changing only their own product. Admins have broader permissions. A vendor cannot use another shop's product ID to change its stock.

The inventory update route reads existing stock, calculates the difference, updates the quantity and optional threshold, and writes an InventoryMovement when the quantity changes.

## 12. Step 7 — Browse the public catalog

GET /api/products is public. It returns active products belonging to approved vendors. It supports optional search, category filtering, and a bounded result limit.

The customer page in dashboard/dashboard.py calls this endpoint and renders each product with price, description, and available quantity. The catalog does not show products from pending, rejected, or suspended vendors, nor products that a vendor has hidden.

### If the product is missing

1. Sign in as admin and confirm vendor status is approved.
2. Sign in as the vendor and open My products.
3. If there are no products, create one. Approval alone does not create a product.
4. Confirm visible_to_customers is True.
5. If hidden, use Show or hide a product and make it active.
6. Sign in as customer and refresh Product catalog.
7. Open GET /api/products in /docs. If the API returns the product but the dashboard does not, compare API_URL for the dashboard and the backend/database used by the vendor.

Out-of-stock products can appear in the catalog but cannot be ordered.

## 13. Step 8 — Record customer behavior and recommendations

Open app/routers/behavior.py.

POST /api/customers/interactions records a customer event such as view, wishlist, or cart. The route checks that the product exists and is active, then saves the event with the authenticated customer ID.

GET /api/customers/recommendations/me uses a simple, explainable ranking:

1. Read products the customer has viewed or purchased.
2. Build category affinity from those products.
3. Count overall product purchases as a popularity signal.
4. Exclude products already viewed/purchased.
5. Keep only active products from approved vendors with positive stock.
6. Rank candidates using category affinity and popularity.

This is a transparent rule-based recommender, not a trained collaborative-filtering or deep-learning model.

## 14. Step 9 — Place a simulated order and update inventory

Open app/routers/orders.py. This is the key end-to-end transaction flow.

1. Only a customer can call POST /api/orders.
2. The request schema checks that there is at least one line, quantities are valid, and product IDs are unique.
3. The route locks product and inventory rows in a stable sorted order to reduce lock-order deadlocks on PostgreSQL.
4. It checks that each product exists, is active, belongs to an approved vendor, and has enough stock.
5. If any line is invalid or stock is insufficient, the request fails before the order is committed.
6. It calculates total from product price × quantity.
7. It creates the order.
8. It creates an OrderItem per line, including vendor ID and unit-price snapshot.
9. It decreases inventory and records a negative stock movement with reason sale.
10. It commits and returns the order.

Representative excerpt:

~~~python
if stocks[product.id].quantity < line.quantity:
    raise HTTPException(409, f'Insufficient stock for product {line.product_id}')

total = sum(
    (products[line.product_id].price * line.quantity for line in payload.items),
    Decimal('0.00'),
)
order = Order(customer_id=user.id, total=total, status='placed')
db.add(order)
db.flush()
~~~

For each line, the code reduces stock and creates the order item and inventory movement before committing.

If stock is insufficient, the API returns HTTP 409 Conflict. Tests check that stock and order totals are not changed after rejected checkout.

**Payment caveat:** the app records a simulated order only. No payment card is charged and there is no payment gateway.

### Multi-vendor orders

A customer can put products from different vendors in one order. Each OrderItem stores vendor ID. When a vendor views order history, the route returns only that vendor's items and vendor-only subtotal. Admin and customer views can see the complete order.

## 15. Vendor-management API reference

Use http://localhost:8000/docs for a local demo. Authenticate with the Authorize control when an endpoint requires a token.

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| POST | /api/auth/register/vendor | Public | Register a pending vendor |
| POST | /api/auth/register/customer | Public | Register a customer |
| POST | /api/auth/login | Public | Get a JWT token |
| GET | /api/auth/me | Logged-in user | Inspect current identity/role |
| GET | /api/vendors | Admin | List vendor applications |
| PATCH | /api/vendors/{id}/status?status=approved | Admin | Approve, reject, or suspend |
| GET | /api/vendors/me | Vendor | View own vendor profile |
| GET | /api/products | Public | Browse published catalog |
| GET | /api/products/mine | Vendor | View own listings and visibility notes |
| POST | /api/products | Approved vendor | Create a product and opening stock |
| PATCH | /api/products/{id} | Owner vendor or admin | Edit product fields/visibility |
| PUT | /api/products/{id}/inventory | Owner vendor or admin | Set stock/low-stock threshold |
| POST | /api/orders | Customer | Record simulated checkout |
| GET | /api/orders | Customer/vendor/admin | Own, vendor-scoped, or all orders |
| POST | /api/customers/interactions | Customer | Record product behavior |
| GET | /api/customers/recommendations/me | Customer | Return simple recommendations |

## 16. Exact API demo in Swagger

These examples use fake data. Use a fresh email if you run the demo more than once.

### A. Register a vendor

POST /api/auth/register/vendor

~~~json
{
  "business_name": "Campus Stationery",
  "owner_name": "Demo Vendor",
  "email": "campus.vendor@example.com",
  "phone": "1234567890",
  "category": "Stationery",
  "password": "CampusVendor123!"
}
~~~

Expected result: HTTP 201; vendor status is initially pending. The returned user response contains role and vendor ID.

### B. Approve the vendor as admin

Sign in through POST /api/auth/login with the configured admin account and use its token in Swagger's Authorize control. Then call PATCH /api/vendors/{vendor_id}/status?status=approved, substituting the vendor ID returned during registration.

Expected result: vendor status becomes approved.

### C. Sign in as the vendor and add a product

Call POST /api/auth/login with the vendor email/password and authorize with that token. Then call POST /api/products:

~~~json
{
  "name": "Campus Notebook",
  "description": "100-page ruled notebook",
  "category": "Stationery",
  "price": "49.00",
  "quantity": 10,
  "low_stock_threshold": 3
}
~~~

Expected result: HTTP 201, product ID, quantity, and visible_to_customers: true.

### D. Confirm the product is public

Call GET /api/products without a token. The newly created active product should be included because its vendor is approved.

### E. Register and sign in as a customer

POST /api/auth/register/customer:

~~~json
{
  "full_name": "Demo Customer",
  "email": "campus.customer@example.com",
  "password": "CampusCustomer123!"
}
~~~

Sign in using POST /api/auth/login and authorize with the customer token.

### F. Place an order

POST /api/orders:

~~~json
{
  "items": [
    {
      "product_id": 1,
      "quantity": 2
    }
  ]
}
~~~

Replace 1 with the actual product ID returned by product creation. If price is 49.00, order total should be 98.00 and stock should fall from 10 to 8.

### G. Verify the effect

- Call GET /api/products: stock should now be 8.
- Call GET /api/orders as customer: the new order should appear.
- Call /api/analytics/summary as vendor/admin: order and GMV should be reflected.
- Call /api/analytics/sales.csv and /api/analytics/sales.pdf to verify exports.

Product/order IDs depend on the database. Do not assume IDs are always 1.

# Part B — Analytics System

## 17. Explain the two analytics modules first

ShopSense has live operational analytics and historical Olist analytics. They answer different questions and use different data.

| Topic | Live marketplace analytics | Historical analytics |
|---|---|---|
| Source | ShopSense database orders/products/vendors | Public Olist CSV files |
| Period | Demo transactions created in ShopSense | Historical Brazilian e-commerce records from 2016–2018 |
| Purpose | Monitor the current demo marketplace | Explore historical seller/product/category/month patterns |
| Currency label | Dashboard currently uses $ as demo display format; it does not convert currencies | Brazilian reais (R$) |
| Processing | SQLAlchemy queries and Python aggregations | Pandas validation, joins, filters, group-by aggregations |
| Output | KPIs, trends, rankings, segments, forecast, CSV/PDF | KPIs, charts, ranking tables, quality audit, CSV |
| Data connection | Live marketplace tables | Does not populate/update live marketplace tables |

## 18. Live analytics: where the code is

- app/services/analytics.py contains calculations.
- app/routers/analytics.py exposes them as protected API endpoints.
- dashboard/dashboard.py calls the endpoints and renders metrics/charts.
- tests/test_api.py verifies key analytics outputs after a sample order.

This separation keeps business calculations out of the Streamlit layout and allows the API results to be tested independently of the UI.

## 19. Live metric 1 — GMV, order count, AOV, and stock alerts

The main function is get_summary(db, vendor_id=None) in app/services/analytics.py. It obtains order-item rows, sums quantity × unit-price, counts orders, reads products for the correct scope, and counts low-stock/active products.

~~~python
rows = sales_rows(db, vendor_id)
gmv = sum(
    (line.quantity * line.unit_price for line, _ in rows),
    Decimal('0.00'),
)
order_ids = {order.id for _, order in rows}
~~~

Metric definitions:

- **GMV (Gross Merchandise Value):** sum of item quantity × unit-price snapshot for non-cancelled order items.
- **Orders:** number of non-cancelled orders. For vendor scope, the service counts distinct orders that include that vendor's items.
- **Average order value (AOV):** GMV divided by order count; zero when there are no orders.
- **Products:** number of products in the selected scope.
- **Active products:** products with is_active=True.
- **Low-stock products:** products whose quantity is less than or equal to their configured low-stock threshold.

**Business caveat:** GMV is not cash collected, accounting revenue, or profit. The implementation does not subtract refunds, shipping, tax, payment fees, vendor commissions, or costs.

### Admin scope versus vendor scope

The analytics router uses scoped_vendor(user). For a vendor, it returns that vendor's ID so the service limits sales/product calculations to their own items. For an admin, it returns None, meaning marketplace-wide scope. This is a privacy boundary as well as an analytics feature: one vendor should not see another vendor's sales.

## 20. Live metric 2 — Sales trend

Endpoint: GET /api/analytics/trends?days=30.

The service calculates the requested date range, groups non-cancelled item GMV by order date, and returns one row for each date, including zero-GMV dates. The main dashboard draws an area chart using Plotly.

**How to explain it:** “The chart is not a static image. The dashboard requests the API's date series and builds a Plotly chart from the returned values. If I create another simulated order, the database changes, and the next API/dashboard read can reflect the new transaction.”

The current trend is based on the order's creation date in the ShopSense database, not Olist's historical purchase date.

## 21. Live metric 3 — Best-selling products and vendor ranking

- GET /api/analytics/top-products calls get_top_products().
- The service aggregates item value and quantity per product, sorts by GMV, and returns the highest-ranked products.
- GET /api/analytics/vendors calls get_vendor_ranking() and is admin-only. It sums item value by vendor and includes vendor status.
- The dashboard shows the top-product bar chart; the demand insights area can show the admin's vendor comparison table.

Rankings are calculated from ShopSense order records. A product with a high selling price and small unit count may rank differently by GMV than by units sold.

## 22. Live metric 4 — Customer segments

Endpoint: GET /api/analytics/customer-segments.

The current implementation uses purchase recency and order-frequency rules:

- **At risk:** last recorded purchase was more than 60 days ago.
- **Loyal:** at least three distinct orders and not already classified as at risk.
- **New:** exactly one order and not already classified as at risk.
- **Repeat:** remaining repeat-purchase customers.

This is a rule-based summary, not K-means clustering, RFM modeling, or a trained classification model. The implementation aggregates customers represented in the order history; customers with no orders are not included in this purchase-based result.

## 23. Live metric 5 — Demand estimate and days of stock

Endpoint: GET /api/analytics/forecast?product_id=1&days=7.

The service looks at the previous seven calendar days of recorded product units, calculates the mean daily quantity, and repeats that mean for each requested future date.

~~~text
Predicted daily units = units sold in previous 7 days / 7
Estimated days of stock = current stock / predicted daily units
~~~

The days-of-stock estimate is returned only when predicted demand is greater than zero. The API response includes method name 7_day_moving_average_baseline and a warning that it is not validated or ML-trained.

**How to explain the limitation:** “I implemented a simple baseline to demonstrate the complete path from transaction history to a stock estimate. It is useful as a starting point, but it is not a trained machine-learning forecast. A stronger model would need enough historical data, a time-based train/test split, a baseline comparison, and metrics such as MAE or RMSE.”

## 24. Live analytics endpoints and exports

| Method | Endpoint | Permission | Result |
|---|---|---|---|
| GET | /api/analytics/summary | Admin/vendor | Main KPI summary |
| GET | /api/analytics/trends?days=30 | Admin/vendor | Daily GMV series |
| GET | /api/analytics/top-products | Admin/vendor | Product ranking |
| GET | /api/analytics/vendors | Admin only | Vendor GMV ranking |
| GET | /api/analytics/customer-segments | Admin/vendor | Rule-based segments |
| GET | /api/analytics/forecast?product_id=1&days=7 | Admin/vendor | Moving-average baseline |
| GET | /api/analytics/sales.csv | Admin/vendor | Transaction-line CSV |
| GET | /api/analytics/sales.pdf | Admin/vendor | One-page PDF KPI overview |

### CSV export

app/routers/analytics.py writes a CSV with order ID, date, vendor ID, product ID, quantity, unit price, and line GMV. The vendor export is scoped to that vendor's items.

### PDF export

The PDF is a one-page executive summary created with ReportLab. It includes GMV, orders, AOV, active products, low-stock products, generation time, and a note about the meaning of GMV. Detailed transaction rows belong in the CSV.

### How to demo live analytics

1. Sign in as admin or vendor.
2. Show summary KPI cards and revenue trend.
3. Open the best-selling products chart.
4. Open demand insights and explain the forecast disclaimer.
5. Show customer segments and, as admin, vendor comparison.
6. Open Reports and download CSV and PDF.
7. Place a new simulated order as customer, return to analytics, and explain how the saved order changes the data.

## 25. Historical analytics: the genuine Olist dataset

The historical module is in dashboard/historical_data.py and dashboard/pages/1_Historical_Analytics.py.

### Dataset source and responsible use

- Dataset: Brazilian E-Commerce Public Dataset by Olist.
- Original source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- Coverage: anonymized Brazilian marketplace records from 2016–2018.
- License documented by the project: CC BY-NC-SA 4.0. Attribution is required; do not assume unrestricted commercial reuse.
- The current loader downloads five CSVs from a public mirror. The mirror is not an official Olist API. If it fails, download the original dataset and set OLIST_DATA_DIR to the folder.

Do not invent seller names, seller contacts, product titles, or current stock from these anonymized records. Olist seller IDs are dataset identifiers, not live ShopSense vendor accounts.

## 26. Historical step 1 — Download and read the source CSV files

The five source files are:

| File | Information used |
|---|---|
| olist_order_items_dataset.csv | Order ID, item ID, product ID, seller ID, item price |
| olist_orders_dataset.csv | Order status and purchase timestamp |
| olist_products_dataset.csv | Product ID and category |
| olist_sellers_dataset.csv | Seller ID, city, and state |
| product_category_name_translation.csv | Portuguese category and English translation |

download_dataset() creates a local cache directory, downloads missing files to temporary paths, checks that each file is non-empty, and renames a temporary file only after a successful download. read_dataset() loads CSVs with identifiers as strings so IDs are not accidentally treated as numeric values.

The Streamlit page caches the resulting historical dataset for one hour. On hosted dashboard, the default cache path is /tmp/shopsense_olist, which may be cleared when the container restarts.

## 27. Historical step 2 — Validate source tables before joining

build_sales() checks that required tables and columns exist. It also verifies:

- Order IDs, product IDs, and seller IDs in the item table are not null.
- The combination (order_id, order_item_id) is unique.
- Order, product, seller, and category dimension keys are present, non-null, and unique.
- Join relationships are many-to-one where expected, using Pandas validate='many_to_one'.

Representative code:

~~~python
if items.duplicated(['order_id', 'order_item_id']).any():
    raise ValueError('items: duplicate order_id/order_item_id')

orders = _unique(dataset['orders'].copy(), 'order_id', 'orders')
products = _unique(dataset['products'].copy(), 'product_id', 'products')
sellers = _unique(dataset['sellers'].copy(), 'seller_id', 'sellers')
categories = _unique(
    dataset['categories'].copy(),
    'product_category_name',
    'categories',
)
~~~

These checks reduce the risk of accidental duplicate rows or inflated sales totals after a join.

## 28. Historical step 3 — Join, filter, and clean

The pipeline is:

1. Join order items to order status and purchase timestamp using order_id.
2. Count item rows with no matching order.
3. Keep only matched orders with order_status == delivered.
4. Join product category using product_id.
5. Join seller city/state using seller_id.
6. Join the category translation.
7. Convert item price to numeric and purchase timestamp to datetime.
8. Exclude invalid price/date rows.
9. Fill unknown category/location labels where necessary.
10. Derive purchase month and units = 1.
11. Return a normalized sales DataFrame and a data-quality audit.

Representative join and filter:

~~~python
items = items.merge(
    delivered,
    on='order_id',
    how='left',
    validate='many_to_one',
    indicator=True,
)
missing_orders = int(items['_merge'].eq('left_only').sum())

items = items.loc[
    items['_merge'].eq('both')
    & items['order_status'].eq('delivered')
].drop(columns='_merge')
~~~

Product, seller, and category data are then joined with the same many-to-one protection. Invalid prices or timestamps are counted and excluded rather than silently included.

**Why keep only delivered orders?** The dashboard compares completed deliveries, not delivered sales mixed with cancelled or otherwise incomplete orders. The code documents which rows are excluded so the result is auditable.

## 29. Historical step 4 — Calculate KPIs and groupings

The normalized dataset includes order ID, product ID, seller ID, seller city/state, category, purchase date/month, item price in BRL, and units.

The summary function computes:

- **Item sales value (R$):** sum of item prices for delivered order-item rows.
- **Distinct orders:** number of unique order IDs.
- **Active sellers in the filtered data:** number of unique seller IDs.
- **Products sold:** number of unique product IDs.
- **Units sold:** sum of item rows, with each Olist item row counted as one unit.

The group-by helper aggregates sales value, units, and distinct orders by the requested columns:

~~~python
result = (
    sales.groupby(fields, dropna=False)
    .agg(
        item_sales_brl=('price_brl', 'sum'),
        units=('units', 'sum'),
        orders=('order_id', 'nunique'),
    )
    .reset_index()
    .sort_values('item_sales_brl', ascending=False)
)
~~~

One order can contain multiple items and multiple sellers. Therefore, the order KPI uses nunique(order_id), not the number of item rows. Item price excludes freight and is not net revenue, profit, or proof of payment settlement.

## 30. Historical step 5 — Apply interactive filters

In dashboard/pages/1_Historical_Analytics.py, sidebar filters include:

- Purchase date range
- Seller state
- Product category

Each filter narrows the historical sales DataFrame before KPI and chart functions run. These filters affect only the historical page; they do not change live vendor listings, stock, or orders.

## 31. Historical step 6 — Visualize and export results

The page has four tabs.

### Overview
- Monthly delivered-item sales value as a Plotly line chart.
- Top categories by item sales value as a horizontal bar chart.
- Seller-state comparison as a bar chart.

### Seller analysis
- Seller ranking table with seller ID, city, state, item sales value, units, and orders.
- Download button for olist_seller_ranking.csv.

### Product analysis
- Product ranking table sorted by units sold, with item sales value as a secondary criterion.
- Download button for olist_product_ranking.csv.

### Data quality & source
- Shows the audit dictionary: raw rows, missing-order items, excluded non-delivered/missing-order rows, invalid price/date rows, analyzed rows, and source-matching counts.
- Displays the dataset source, license, and date period.

The historical page uses Plotly for interactive visualizations and Pandas for aggregation. It does not currently claim to provide pie charts, histograms, or a trained predictive model.

## 32. Reproduce the historical analysis from the command line

From the repository root, install dashboard dependencies if needed:

~~~powershell
pip install -r requirements-dashboard.txt
~~~

Download CSV files and run the analysis script:

~~~powershell
python -m scripts.analyze_olist --download
~~~

The documented outputs are under data/processed:

- seller_ranking.csv
- product_ranking.csv
- monthly_sales.csv
- audit.json

To use CSVs already downloaded from the official dataset, place the selected files in a folder and pass it to the script:

~~~powershell
python -m scripts.analyze_olist --data-dir data/olist
~~~

Run historical dashboard tests:

~~~powershell
pytest -q tests/test_historical_data.py
~~~

Unit tests use small synthetic fixtures to verify joins, duplicate detection, invalid-price handling, and aggregation math. They do not prove that the public mirror is reachable today; verify that the deployed Historical Analytics page loads before the mentor demo.

## 33. A polished 8–10 minute mentor demo plan

Prepare a fresh test database or known demo database. Keep admin, vendor, and customer accounts ready. Never expose real secrets.

### Minute 0–1 — Introduce the project
- Open the GitHub repository and README.
- Give the 30-second project explanation from Section 1.
- Explain the two data paths: live marketplace and historical Olist.

### Minute 1–3 — Demonstrate vendor management
- Open the dashboard while signed out.
- Register a new vendor with a unique email.
- Sign in as admin and open Vendors.
- Change the new vendor from pending to approved.
- Sign in as vendor and open My products.
- Create a product with price, quantity, and low-stock threshold.
- Show visible_to_customers and visibility_note.

### Minute 3–5 — Demonstrate customer order and inventory
- Sign in as customer.
- Open Product catalog and show the newly published product.
- Add the product to cart and place a simulated order.
- Open My orders.
- Return to vendor/admin view and show stock decreased.
- State clearly that the order is simulated and no real payment was processed.

### Minute 5–7 — Demonstrate live analytics
- Show GMV, order count, AOV, and low-stock metrics.
- Show daily sales trend and best-selling product chart.
- Show customer segments and moving-average forecast.
- Explain the forecast is a baseline, not validated ML.
- Download CSV and PDF reports.

### Minute 7–9 — Demonstrate historical analytics
- Open Historical Analytics from the Streamlit sidebar.
- Show the monthly sales chart.
- Change date range, seller-state filter, or category filter.
- Show seller/product ranking tables and download a CSV.
- Open Data quality & source and explain delivered-only filtering, distinct order counting, the 2016–2018 date period, and Olist license.

### Minute 9–10 — Explain tests and limitations
- Show tests/test_api.py and tests/test_historical_data.py.
- Explain that tests cover critical behaviors, but a passing suite is not the same as measured 99% validation accuracy.
- Summarize future work: payment gateway, richer order lifecycle, production security/rate limiting, validated forecasting.

## 34. What tests prove

The current API tests cover, among other things:

- Health/readiness endpoints and invalid login.
- A pending vendor cannot create a product.
- An approved vendor's active product appears in the public catalog.
- Product stock updates are reflected.
- Successful order placement reduces stock and changes analytics.
- Insufficient-stock checkout returns 409 without changing state.
- Customer interactions and recommendations behave as expected.
- A vendor cannot change another vendor's product/inventory.
- A multi-vendor order is scoped correctly when each vendor views orders/GMV.
- CSV and PDF exports return the expected file types.
- Product approval/active visibility regression behavior is tested.

Historical tests cover valid joins, delivered-order aggregation, duplicate order-item detection, missing required columns, invalid-price handling, and empty filtered results.

Run the complete test suite:

~~~powershell
pytest -q
~~~

For the demo, report the actual command output. Do not invent a pass count, coverage percentage, validation accuracy, or transaction-consistency percentage.

## 35. Important limitations to disclose honestly

1. **Payments:** checkout records orders only; no card/UPI gateway, payment webhook, or settlement.
2. **GMV meaning:** GMV is item price × quantity. It is not profit, collected cash, or accounting revenue.
3. **Currency:** the live dashboard's currency helper uses a $ display format for demo values and performs no conversion. Historical Olist values are in Brazilian reais (R$).
4. **Forecasting:** the current demand endpoint repeats a 7-day moving average; it is not a trained or validated ML model.
5. **Customer segments:** current segments are rule-based by purchase recency/frequency, not clustering.
6. **Recommendations:** current recommendations use category affinity and purchase popularity, not a trained recommendation model.
7. **Historical data:** Olist sellers are anonymized, records are from 2016–2018, and historical records are separate from the live database.
8. **Dataset licensing:** Olist is documented as CC BY-NC-SA 4.0; attribution is required and commercial reuse should not be assumed.
9. **Validation scores:** field validation and tests exist, but percentages such as 99% registration validation or 98% transaction consistency require a defined methodology and actual results.
10. **Production readiness:** before accepting real customers/payments, the system needs a payment provider, stronger monitoring, rate limiting, clear currency/tax/refund handling, privacy/retention workflows, backups, and further load/security testing.

## 36. Questions a mentor may ask

**Q1. Why use FastAPI?**  
It makes REST endpoint development clear, supports Pydantic validation, and automatically generates OpenAPI/Swagger documentation.

**Q2. Why use SQLAlchemy?**  
It maps Python models to database tables and allows routes and analytics to query related records without hand-writing every SQL statement.

**Q3. Why is vendor approval separate from registration?**  
Registration creates an application in pending status. Admin approval is a separate authorization step controlling whether the vendor may list products.

**Q4. Why are models and schemas different?**  
A model describes how data is stored. A Pydantic schema describes what the API accepts or returns. This separation helps avoid exposing database-only fields such as password hashes.

**Q5. How do you prevent one vendor from editing another vendor's stock?**  
The update routes check the authenticated role and compare the product's vendor_id with the logged-in vendor's ID before applying the change.

**Q6. How do you stop checkout from overselling stock?**  
The route locks product and inventory rows, checks available quantity before committing, and returns 409 Conflict if stock is insufficient. Tests verify the failure does not change stock/order state.

**Q7. Why store unit price on OrderItem?**  
It preserves the sale-time price snapshot so historical order totals do not change when the current product price is edited later.

**Q8. How is GMV calculated?**  
For each non-cancelled order item, multiply quantity by stored unit price and sum the results. It excludes profit, tax, freight, refunds, and payment settlement.

**Q9. Why use Olist?**  
It provides public historical e-commerce records for demonstrating data cleaning, joins, aggregation, and visualization. Its anonymized sellers are kept separate from the live marketplace.

**Q10. Why count distinct orders instead of rows?**  
An order can contain several items and sellers. Counting item rows as orders would overcount orders.

**Q11. Is the forecast machine learning?**  
No. The current endpoint is a seven-day moving-average baseline. A proper ML model would require training/evaluation data and measured performance.

**Q12. How do you know data preparation is correct?**  
The code validates required columns, key uniqueness, and join cardinality; filters delivered rows and invalid price/date values; records exclusions in an audit; and uses unit tests for edge cases. A production pipeline would add more monitoring and reconciliation.

**Q13. What is the difference between unit tests and accuracy?**  
Unit tests check expected behavior on chosen inputs. A percentage such as validation accuracy needs a defined test population and a measured numerator/denominator.

**Q14. What would you add next?**  
A payment integration, fuller order/refund lifecycle, improved inventory replenishment logic, forecast evaluation, data-quality monitoring, and production security/observability.

## 37. Closing explanation to say to the mentor

> “I implemented ShopSense in layers. First I defined database entities and input schemas. Then I added authentication and role-based authorization, followed by vendor registration and admin approval. After that I implemented vendor-owned product listings, stock movement tracking, and simulated checkout with stock checks. The live analytics service reads saved order-item records and calculates GMV, AOV, trends, product/vendor rankings, customer segments, and a moving-average stock estimate. Separately, the historical analytics pipeline downloads five Olist CSVs, validates identifiers, joins tables, filters to delivered orders, audits excluded rows, and uses Pandas and Plotly for charts and CSV rankings. I test important API and data-processing cases with pytest. The current version is an academic MVP, so I distinguish simulated orders and baseline analytics from real payments or validated machine learning.”

## Before the mentor meeting

- [ ] Confirm API /ready and dashboard URLs work.
- [ ] Check the admin can sign in.
- [ ] Check vendor approval → product creation → customer catalog.
- [ ] Place one simulated order and confirm stock decreases.
- [ ] Confirm live analytics reflect the order.
- [ ] Download CSV and PDF reports.
- [ ] Open Historical Analytics and confirm the dataset loads.
- [ ] Run pytest -q and record the actual output.
- [ ] Do not show credentials, tokens, .env contents, or deployment secrets.
- [ ] State limitations accurately.

**Related repository documents:** [Main project guide](PROJECT_GUIDE.md) · [Olist dataset methodology](OLIST_DATASET.md) · [Deployment guide](DEPLOYMENT.md) · [Implementation roadmap](ROADMAP.md)
