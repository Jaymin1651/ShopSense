"""Train, log and register ShopSense models with MLflow.

Tracking store: ``MLFLOW_TRACKING_URI`` (default ``sqlite:///mlflow.db`` next to
the app, separate from the shop database). Artifacts go to ``./mlruns``.

Registered models and their main metric (higher is better):

=====================  ==================================  =====================
Registered model       What it is                          Promotion metric
=====================  ==================================  =====================
InventoryForecast      Pooled weekly Random Forest         category_accuracy_pct
ChurnRisk              Logistic regression on RFM          roc_auc
=====================  ==================================  =====================

Champion/challenger: a new version gets the ``production`` alias only if its
promotion metric is at least the current production version's metric minus a
small tolerance; otherwise it gets the ``challenger`` alias and production is
left alone. Segmentation and recommendation quality are logged as runs every
time they are evaluated so trends are visible in the MLflow UI.
"""
from __future__ import annotations

import json
import os
import tempfile
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TRACKING_URI = os.getenv('MLFLOW_TRACKING_URI', f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}")
ARTIFACT_ROOT = os.getenv('MLFLOW_ARTIFACT_ROOT', (ROOT / 'mlruns').as_uri())
ENABLED = os.getenv('MLFLOW_ENABLED', '1') == '1'
PROMOTION = {'InventoryForecast': ('category_accuracy_pct', 0.5), 'ChurnRisk': ('roc_auc', 0.005)}
EXPERIMENTS = ['shopsense-forecasting', 'shopsense-churn', 'shopsense-segmentation', 'shopsense-recommendation']


def _mlflow():
    import mlflow
    warnings.filterwarnings('ignore', module='mlflow')
    mlflow.set_tracking_uri(TRACKING_URI)
    return mlflow


def _experiment(mlflow, name: str):
    exp = mlflow.get_experiment_by_name(name)
    if exp is None:
        mlflow.create_experiment(name, artifact_location=f'{ARTIFACT_ROOT}/{name}')
    mlflow.set_experiment(name)


def _promote(client, name: str, version: str, metric_value: float) -> dict:
    """Champion/challenger decision; returns what happened."""
    metric, tolerance = PROMOTION[name]
    try:
        current = client.get_model_version_by_alias(name, 'production')
        current_value = client.get_run(current.run_id).data.metrics.get(metric)
    except Exception:  # no production version yet
        current, current_value = None, None
    if current is None or current_value is None or metric_value >= current_value - tolerance:
        client.set_registered_model_alias(name, 'production', version)
        decision = 'promoted'
    else:
        client.set_registered_model_alias(name, 'challenger', version)
        decision = 'kept_as_challenger'
    client.set_model_version_tag(name, version, 'decision', decision)
    return {'model': name, 'version': int(version), 'decision': decision, metric: metric_value,
            'previous_production_version': int(current.version) if current is not None else None,
            f'previous_{metric}': current_value}


def train_forecast(sales: pd.DataFrame, holdout_weeks: int = 12, n_estimators: int = 300) -> dict:
    """Evaluate at product and category level, fit on all weeks, log and register."""
    from app.inventory.inventory_forecasting import DemandForecaster, evaluate, weekly_series
    from app.mlflow_tracking.models import ForecastModel

    mlflow = _mlflow()
    _experiment(mlflow, 'shopsense-forecasting')
    product_weekly = weekly_series(sales, 'product_id')
    cat_eval = evaluate(weekly_series(sales, 'category'), holdout_weeks, n_estimators)
    prod_eval = evaluate(product_weekly, holdout_weeks, n_estimators)
    model = DemandForecaster(n_estimators=n_estimators).fit(product_weekly)
    with mlflow.start_run(run_name='weekly-random-forest') as run:
        mlflow.log_params({'model': 'RandomForestRegressor', 'n_estimators': n_estimators, 'min_samples_leaf': 5,
                           'max_features': 0.6, 'granularity': 'weekly', 'holdout_weeks': holdout_weeks,
                           'scaling': 'previous 13-week level', 'series': int(product_weekly['series'].nunique()),
                           'train_rows': int(len(product_weekly))})
        mlflow.log_metrics({
            'category_accuracy_pct': cat_eval['model_accuracy_pct'],
            'product_accuracy_pct': prod_eval['model_accuracy_pct'],
            'category_wape_pct': cat_eval['methods']['random_forest']['wape_pct'],
            'category_best_baseline_pct': cat_eval['methods'][cat_eval['best_baseline']]['accuracy_pct'],
            'product_best_baseline_pct': prod_eval['methods'][prod_eval['best_baseline']]['accuracy_pct'],
        })
        _log_json(mlflow, {'category': cat_eval, 'product': prod_eval}, 'evaluation.json')
        info = mlflow.pyfunc.log_model(name='model', python_model=ForecastModel(model),
                                       pip_requirements=['scikit-learn', 'pandas', 'numpy'])
        run_id = run.info.run_id
    version = mlflow.register_model(info.model_uri, 'InventoryForecast')
    result = _promote(mlflow.MlflowClient(), 'InventoryForecast', version.version, cat_eval['model_accuracy_pct'])
    result.update({'run_id': run_id, 'product_accuracy_pct': prod_eval['model_accuracy_pct']})
    return result


def train_churn(sales: pd.DataFrame, horizon: int = 90) -> dict:
    from app.customer_intelligence.churn import FEATURES, train_and_evaluate

    mlflow = _mlflow()
    _experiment(mlflow, 'shopsense-churn')
    out = train_and_evaluate(sales, horizon)
    m = out['metrics']
    with mlflow.start_run(run_name='logistic-regression') as run:
        mlflow.log_params({'model': 'LogisticRegression', 'class_weight': 'balanced', 'features': ','.join(FEATURES),
                           'transform': 'log1p + standardise', 'horizon_days': horizon,
                           'train_cutoff': m['train_cutoff'], 'test_cutoff': m['test_cutoff']})
        mlflow.log_metrics({k: v for k, v in m.items() if isinstance(v, (int, float)) and v is not None})
        info = mlflow.sklearn.log_model(out['model'], name='model')
        run_id = run.info.run_id
    version = mlflow.register_model(info.model_uri, 'ChurnRisk')
    result = _promote(mlflow.MlflowClient(), 'ChurnRisk', version.version, m['roc_auc'])
    result.update({'run_id': run_id, 'baseline_recency_auc': m['baseline_recency_auc']})
    return result


def log_segmentation(metrics: dict, k: int) -> str:
    mlflow = _mlflow()
    _experiment(mlflow, 'shopsense-segmentation')
    with mlflow.start_run(run_name=f'kmeans-k{k}') as run:
        mlflow.log_params({'model': 'KMeans', 'k': k, 'features': 'log recency, frequency, monetary'})
        mlflow.log_metrics({key: float(v) for key, v in metrics.items() if isinstance(v, (int, float)) and v is not None})
        return run.info.run_id


def log_recommender(evaluation: dict) -> str:
    mlflow = _mlflow()
    _experiment(mlflow, 'shopsense-recommendation')
    k = evaluation['k']
    with mlflow.start_run(run_name='hybrid-item-knn') as run:
        mlflow.log_params({'model': 'item-kNN + category + popularity', 'k': k, 'cutoff': evaluation['cutoff'],
                           'blend': '0.70 cf / 0.20 category / 0.10 popularity'})
        for name, metrics in evaluation['models'].items():
            mlflow.log_metrics({f'{name}_{key}': float(v) for key, v in metrics.items()})
        return run.info.run_id


def _log_json(mlflow, obj, filename):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_text(json.dumps(obj, indent=2, default=str))
        mlflow.log_artifact(str(path))


# --------------------------------------------------------------- read side
def registry_overview() -> dict:
    """Registered models with versions, aliases and their run metrics."""
    if not ENABLED:
        return {'enabled': False, 'models': []}
    mlflow = _mlflow()
    client = mlflow.MlflowClient()
    models = []
    for rm in client.search_registered_models():
        aliases = {}
        for alias, ver in (rm.aliases or {}).items():
            aliases.setdefault(str(ver), []).append(alias)
        versions = []
        all_versions = sorted(client.search_model_versions(f"name='{rm.name}'"), key=lambda v: -int(v.version))
        aliased = {str(v) for v in (rm.aliases or {}).values()}
        shown = all_versions[:10] + [v for v in all_versions[10:] if str(v.version) in aliased]
        for mv in shown:
            run = client.get_run(mv.run_id)
            versions.append({'version': int(mv.version), 'aliases': aliases.get(str(mv.version), []),
                             'created': pd.Timestamp(mv.creation_timestamp, unit='ms', tz='UTC').isoformat(timespec='seconds'),
                             'run_id': mv.run_id, 'metrics': {k: round(v, 4) for k, v in run.data.metrics.items()},
                             'decision': (mv.tags or {}).get('decision')})
        production = (rm.aliases or {}).get('production')
        models.append({'name': rm.name, 'versions': versions, 'total_versions': len(all_versions),
                       'production_version': int(production) if production is not None else None})
    store = TRACKING_URI.split(':', 1)[0]  # scheme only; never echo credentials
    return {'enabled': True, 'tracking_store': store, 'models': sorted(models, key=lambda m: m['name'])}


def recent_runs(limit: int = 20) -> list[dict]:
    if not ENABLED:
        return []
    mlflow = _mlflow()
    exps = [e.experiment_id for e in mlflow.search_experiments() if e.name in EXPERIMENTS]
    if not exps:
        return []
    runs = mlflow.search_runs(experiment_ids=exps, max_results=limit, order_by=['start_time DESC'],
                              output_format='list')
    names = {e.experiment_id: e.name for e in mlflow.search_experiments()}
    return [{'run_id': r.info.run_id, 'experiment': names.get(r.info.experiment_id), 'run_name': r.info.run_name,
             'status': r.info.status, 'start': pd.Timestamp(r.info.start_time, unit='ms', tz='UTC').isoformat(timespec='seconds'),
             'metrics': {k: round(v, 4) for k, v in r.data.metrics.items()}, 'params': dict(r.data.params)}
            for r in runs]
