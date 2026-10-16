# ShopSense

ShopSense is a small FastAPI-based marketplace API for managing vendors, products, and sales analytics.

## Project purpose
- Vendor management for registration and validation
- Product management
- Sales analytics and revenue reporting
- Dashboard for vendor and product performance

## Folder guide
- app/main.py
  Main FastAPI app. This file includes all routers and starts the application.

- app/core/database.py
  Database engine and SQLAlchemy session setup.

- app/models/
  SQLAlchemy database models for vendors and products.

- app/schemas/
  Pydantic validation models used to validate request payloads.

- app/validation/
  Validation helpers for business rules.

- app/routes/
  API endpoints:
  - vendor_routes.py: vendor registration
  - product_routes.py: add products
  - analytics_routes.py: revenue and product analytics

- app/analytics/
  Data analysis logic for totals, vendor revenue, product revenue, and top-product detection.

- dashboard/dashboard.py
  Streamlit dashboard for visual analytics.

- data/transactions.csv
  Sample sales dataset used for analytics.

- tests/
  Automated test validation for vendor registration and analytics logic.

## Run the project

### Install dependencies
```bash
pip install -r requirements.txt
```

### Start API
```bash
uvicorn app.main:app --reload
```

Open:
http://127.0.0.1:8000/docs

### Run dashboard
```bash
streamlit run dashboard/dashboard.py
```

### Tests

Run tests with:

```bash
pytest -q
```
