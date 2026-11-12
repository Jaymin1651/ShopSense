"""Which demand forecaster the API uses.

Order of preference:
1. ``models:/InventoryForecast@production`` from the MLflow registry
   (loaded once, re-checked every ``CHECK_SECONDS`` for a newer production version);
2. a model trained in-process from the current orders (Milestone 2 behaviour).
"""
from __future__ import annotations

import threading
import time

from app.mlflow_tracking import tracking

CHECK_SECONDS = 60
_STATE = {'checked': 0.0, 'version': None, 'model': None}
_LOCK = threading.Lock()


def production_forecaster():
    """Return ``(DemandForecaster, 'InventoryForecast v3')`` or ``(None, None)``."""
    if not tracking.ENABLED:
        return None, None
    with _LOCK:
        if time.time() - _STATE['checked'] < CHECK_SECONDS:
            return _STATE['model'], _label(_STATE['version'])
    try:
        mlflow = tracking._mlflow()
        client = mlflow.MlflowClient()
        version = client.get_model_version_by_alias('InventoryForecast', 'production').version
        if version != _STATE['version']:
            loaded = mlflow.pyfunc.load_model(f'models:/InventoryForecast/{version}')
            model = loaded.unwrap_python_model().forecaster
            model.model.set_params(n_jobs=1)  # single-row predictions: avoid thread start-up per call
        else:
            model = _STATE['model']
    except Exception:  # registry empty, MLflow not configured, or model missing
        version, model = None, None
    with _LOCK:
        _STATE.update(checked=time.time(), version=version, model=model)
    return model, _label(version)


def _label(version):
    return f'InventoryForecast v{version} (MLflow production)' if version else None


def reset():
    with _LOCK:
        _STATE.update(checked=0.0, version=None, model=None)
