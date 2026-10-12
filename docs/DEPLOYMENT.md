# ShopSense — GitHub-to-deployment guide

This is the step-by-step checklist to take the runnable local project from a newly created GitHub repository to two hosted HTTPS services. The suggested example uses **Render for the API, dashboard and PostgreSQL**. You can use any equivalent managed host supporting Docker + PostgreSQL.

## 0. Requirements and local verification

- Git, GitHub account, GitHub CLI (`gh`, optional), Docker and Docker Compose.
- Download/extract ShopSense project so that `README.md`, `docker-compose.yml` and `app/` are at the root.
- `cp .env.example .env`; generate distinct random secrets; **never commit** `.env`.
- Run `docker compose up --build -d`, then open `http://localhost:8000/ready` and `http://localhost:8501`.
- Optionally load *synthetic* demo records using `docker compose exec api python -m scripts.seed_demo`.
- In the project root run `pytest -q` after `pip install -r requirements-dev.txt`.

## 1. Existing GitHub repository and solo workflow

The repository is **https://github.com/Jaymin1651/ShopSense**. It has already been created.

Clone your remote code to a computer using:

```bash
git clone https://github.com/Jaymin1651/ShopSense.git
cd ShopSense
```

Use `main` for the stable submitted version. For changes, create a short feature branch if useful, run `pytest -q`, commit, and merge to `main`. As a solo developer, you don't need collaborators or a project-board workflow.

## 3. Create a hosted PostgreSQL database

In Render, create a PostgreSQL instance in your desired region. Use a strong database password, backups and an appropriate retention setting. Obtain the database **internal connection URL** if the two Render web services are in the same region. Store this value in the **API service environment** as `DATABASE_URL`. ShopSense converts `postgresql://` and `postgres://` prefixes to SQLAlchemy's `postgresql+psycopg://` driver automatically.

> Do not commit the URL. Confirm backup/restore strategy before moving beyond synthetic demo data.

## 4. Deploy the FastAPI backend

In the Render dashboard:

1. Choose **New → Web Service**, link your `shopsense` GitHub repository.
2. Choose **Docker**; repository root; **Dockerfile path: `Dockerfile.api`**.
3. Configure service name (e.g. `shopsense-api`) and a compute plan suitable for your use.
4. Add these environment variables:

   | Variable | Setting |
   | --- | --- |
   | `DATABASE_URL` | Hosted PostgreSQL connection URL (secret) |
   | `ENVIRONMENT` | `production` |
   | `JWT_SECRET` | 32+ character cryptographically random secret |
   | `ADMIN_EMAIL` | Your admin email |
   | `ADMIN_PASSWORD` | Unique strong password, at least 12 characters |
   | `CORS_ORIGINS` | Hosted dashboard HTTPS URL (once known) |

5. Health check path: `/ready`.
6. Deploy. The container runs Alembic migrations, bootstraps the admin if the admin env vars exist, then starts Uvicorn on the platform's `PORT`.
7. Open `https://YOUR-API.onrender.com/ready` and `https://YOUR-API.onrender.com/docs`.

If API startup fails, check environment values and Render logs first. Do not add demo seed or SQLite database to production.

## 5. Deploy the Streamlit web dashboard

Create a second Render **Web Service** linked to the same repo:

1. Choose Docker with **Dockerfile path: `Dockerfile.dashboard`**.
2. Set `API_URL=https://YOUR-API.onrender.com` (exact real API URL). This variable is a service-to-service endpoint, *not* an authentication token.
3. Deploy. The container runs Streamlit on `0.0.0.0` and the provided `PORT`.
4. Open `https://YOUR-DASHBOARD.onrender.com`, sign in as the admin, and try vendor approval/product creation/order dashboard.
5. Return to the API environment settings and put your actual dashboard URL in `CORS_ORIGINS` (without trailing slash); redeploy the API if necessary.

Choose HTTPS URLs; avoid relying on a browser-side reference to `http://localhost` after hosting.

## 6. Configure continuous integration and deploys

Already included:

- `.github/workflows/ci.yml`: on pushes/PRs to `main`, installs dependencies, tests migrations, runs pytest, compiles Python and builds both Docker images.
- `.github/workflows/deploy-render.yml`: after a **successful main-branch push CI run**, calls the deploy hooks *only if configured*.

Recommended for fully controlled deployments: disable ordinary Render auto-deploy for each service, and keep deployment gates in GitHub Actions.

To enable automated release:

1. Render API service → **Settings → Deploy Hook**. Copy the URL.
2. GitHub → repo **Settings → Secrets and variables → Actions → New repository secret**. Save as `RENDER_API_DEPLOY_HOOK`.
3. Repeat for the Streamlit service using `RENDER_DASHBOARD_DEPLOY_HOOK`.
4. Commit a safe test change to `main`. CI should pass, then the deployment workflow should trigger the service hooks.

These URLs are secrets and must never be pasted into committed YAML. Hooks **trigger** deploys; the workflow does not assert deploy health. Check the Render Deploys logs, API `/ready` and dashboard after each release. The two hooks are triggered sequentially without guaranteeing that the API is healthy before the dashboard deploy starts.

## 7. Acceptance smoke test

Use a **test database**, not live customer data:

- [ ] API `/ready` returns a healthy response; `/docs` shows routes.
- [ ] Admin logs in and sees marketplace metrics.
- [ ] A vendor can register but cannot publish until approval.
- [ ] Admin approves a vendor; vendor can add a product and stock.
- [ ] Customer registers, browses, logs an interaction and places a simulated order.
- [ ] Inventory falls by the purchased quantity; insufficient-stock checkout returns HTTP 409.
- [ ] Admin sees full GMV; vendor sees only their own GMV/order item subtotal.
- [ ] Sales CSV and PDF download correctly.
- [ ] GitHub Actions test + build jobs pass; deployment health is rechecked.

## 8. Rollback, backups and maintenance

- Re-deploy the previous known-good Git commit in Render if application code is broken.
- **Database migrations are not automatically rolled back by redeploying code.** Prefer forward-compatible migration steps and take a database backup before schema changes.
- Monitor error rates, database health, API response times and login failures. Define retention/deletion rules for customer behavior events.
- For traffic beyond classroom demonstrations, add request throttling, financial reconciliation, tax/currency definitions, payment webhook verification, robust order idempotency, concurrency stress tests, observability and privacy controls.

## Submission checklist (12–16 October 2026)

- **12 October:** Commit source code and test the vendor-to-customer product flow.
- **13 October:** Check vendor approval, product listing, order placement and stock updates manually.
- **14 October:** Verify analytics and record screenshots for the report.
- **15 October:** Configure Render PostgreSQL/API/dashboard and test deployment using demo accounts.
- **16 October:** Submit project URL, working demo and brief explanation of results.

Do not claim the optional MLflow/ETL/advanced ML modules were completed; those are future extensions.

The base download implements many of these initial capabilities. Later weeks reflect **new work**, not claims of current completion.
