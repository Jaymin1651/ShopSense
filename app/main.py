"""ShopSense REST API; schema is managed with Alembic migrations."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends
from app.config import settings
from app.database import get_db
from app.routers import (auth, vendors, products, orders, behavior, analytics, inventory, catalog,
                         customer_analytics, recommendations)

app = FastAPI(title='ShopSense Marketplace & Analytics API', version='0.2.0',
              description='Multi-vendor marketplace with inventory intelligence (ML demand forecasting, alerts, '
                          'replenishment), customer segmentation and hybrid product recommendations.')
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                   allow_credentials=True, allow_methods=['GET', 'POST', 'PATCH', 'PUT'],
                   allow_headers=['Authorization', 'Content-Type'])
for router in (auth.router, vendors.router, products.router, orders.router, behavior.router, analytics.router,
               inventory.router, catalog.router, customer_analytics.router, recommendations.router):
    app.include_router(router)


@app.get('/health', tags=['System'])
def health():
    return {'status': 'ok', 'environment': settings.environment}


@app.get('/ready', tags=['System'])
def ready(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready'}
