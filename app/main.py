"""ShopSense REST API; schema is managed with Alembic migrations."""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends
from app.config import settings
from app.database import get_db
from app.routers import (auth, vendors, products, orders, behavior, analytics, inventory, catalog,
                         customer_analytics, recommendations)
from app.api import (customer_routes, forecast_routes, ops_routes, recommendation_routes, revenue_routes)

@asynccontextmanager
async def lifespan(_app):
    """Optionally run the workflow scheduler inside the API process.

    Production runs it as its own process (``python -m app.scheduler``); set
    SCHEDULER_IN_API=true for a single-process setup.
    """
    scheduler = None
    if os.getenv('SCHEDULER_IN_API', 'false').lower() == 'true':
        from app.scheduler.runner import build_scheduler
        scheduler = build_scheduler('background')
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title='ShopSense Marketplace & Analytics API', version='0.3.0',
              description='Multi-vendor marketplace analytics platform: inventory intelligence, customer '
                          'segmentation and recommendations (Milestone 2), plus revenue analysis, vendor '
                          'benchmarking, churn risk, MLflow model registry, automated workflows and Excel/PDF '
                          'reporting (Milestone 3).', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH', 'PUT'],
                   allow_headers=['Authorization', 'Content-Type'])
@app.middleware('http')
async def server_timing(request, call_next):
    """Report time spent inside the API, so load tests can separate it from network and client time."""
    started = time.perf_counter()
    response = await call_next(request)
    response.headers['Server-Timing'] = f'app;dur={(time.perf_counter() - started) * 1000:.1f}'
    return response


for router in (auth.router, vendors.router, products.router, orders.router, behavior.router, analytics.router,
               inventory.router, catalog.router, customer_analytics.router, recommendations.router,
               revenue_routes.router, customer_routes.router, forecast_routes.router, recommendation_routes.router,
               ops_routes.router):
    app.include_router(router)


@app.get('/health', tags=['System'])
def health():
    return {'status': 'ok', 'environment': settings.environment}


@app.get('/ready', tags=['System'])
def ready(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready'}
