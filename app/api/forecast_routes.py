"""Demand forecasts served from the MLflow production model."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import admin, scope, staff, with_meta
from app.database import get_db
from app.mlflow_tracking import tracking
from app.models import Product, User
from app.services import bi, intelligence

router = APIRouter(prefix='/api/forecast', tags=['Forecasting'])


@router.get('/summary')
def summary(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Next 4 weeks of demand vs stock for every product (projected stock and shortfall)."""
    return with_meta(bi.serve(db, 'forecast_summary', scope(user)))


@router.get('/model')
def model_info(db: Session = Depends(get_db), _: User = Depends(admin)):
    """Which model is serving forecasts, and the InventoryForecast registry versions."""
    intelligence.forecaster(db)
    registry = tracking.registry_overview()
    versions = next((m['versions'] for m in registry.get('models', []) if m['name'] == 'InventoryForecast'), [])
    return {'serving': intelligence.forecast_source(), 'registry_enabled': registry.get('enabled', False),
            'versions': versions}


@router.get('/{product_id}')
def product(product_id: int, weeks: int = Query(default=4, ge=1, le=12), db: Session = Depends(get_db),
            user: User = Depends(staff)):
    item = db.get(Product, product_id)
    if not item:
        raise HTTPException(404, 'Product not found')
    if user.role == 'vendor' and item.vendor_id != user.vendor_id:
        raise HTTPException(403, 'Limited to your own products')
    result = intelligence.product_forecast(db, item, weeks)
    return {**result, 'model_source': intelligence.forecast_source()}
