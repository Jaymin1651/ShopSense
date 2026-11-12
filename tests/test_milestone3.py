"""Milestone 3: revenue analysis, churn, segment picks, snapshots, workflows, MLflow, reports and API."""
import json

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import revenue_analysis as ra
from app.analytics import snapshots
from app.customer_intelligence.churn import score_customers, train_and_evaluate
from app.database import get_db
from app.main import app
from app.models import InventoryMovement, WorkflowRun
from app.recommendations.segment_recommendations import segment_recommendations
from app.scheduler import jobs
from scripts.generate_milestone2_data import build


@pytest.fixture(scope='module')
def synthetic():
    return build(seed=3, n_customers=260)


def sales_frame(t):
    return t['transactions'].merge(t['products'][['product_id', 'category']], on='product_id')


def db_session():
    return next(app.dependency_overrides[get_db]())


# ------------------------------------------------------------------ revenue
def test_revenue_series_growth_and_aov():
    sales = pd.DataFrame({'order_id': [1, 2, 3, 4], 'customer_id': [1, 1, 2, 3], 'product_id': [1, 1, 2, 2],
                          'date': ['2026-01-05', '2026-01-20', '2026-02-03', '2026-02-10'], 'quantity': [1, 1, 1, 1],
                          'amount': [100.0, 100.0, 150.0, 150.0], 'category': ['A', 'A', 'B', 'B']})
    months = ra.revenue_series(sales, 'month')
    assert [m['period'] for m in months] == ['2026-01', '2026-02']
    assert months[1]['gmv'] == 300.0 and months[1]['growth_pct'] == 50.0 and months[1]['aov'] == 150.0
    assert ra.pareto(sales, 'product_id')['top_20_pct_share'] == 60.0


def test_cohorts_leave_unreachable_months_blank(synthetic):
    c = ra.cohort_retention(sales_frame(synthetic), months=6)
    assert c['matrix'][-1][0] == 100.0 and all(v is None for v in c['matrix'][-1][1:])
    assert c['matrix'][0][0] == 100.0 and c['matrix'][0][1] is not None


def test_vendor_benchmark_ranks_and_anonymises(synthetic):
    vendors = synthetic['vendors'].rename(columns={'business_name': 'vendor'})
    bench = ra.vendor_benchmark(sales_frame(synthetic), vendors, synthetic['inventory'])
    ranks = sorted(v['rank'] for v in bench['vendors'])
    assert ranks == list(range(1, len(vendors) + 1))
    top = min(bench['vendors'], key=lambda v: v['rank'])
    assert top['gmv'] == max(v['gmv'] for v in bench['vendors']) and top['gmv_percentile'] == 100
    assert abs(sum(v['share_pct'] for v in bench['vendors']) - 100) < 0.5
    mine = ra.anonymise_benchmark(bench, 3)
    assert mine['you']['vendor_id'] == 3 and 'vendors' not in mine
    assert len(mine['peer_gmv_distribution']) == len(vendors)
    assert all(isinstance(x, float) for x in mine['peer_gmv_distribution'])


# ---------------------------------------------------------- customer intel
def test_churn_model_time_split_and_scores(synthetic):
    sales = synthetic['transactions']
    result = train_and_evaluate(sales, horizon=90)
    m = result['metrics']
    assert m['train_cutoff'] < m['test_cutoff']
    assert 0.5 < m['roc_auc'] <= 1 and 0 <= m['baseline_recency_auc'] <= 1
    scored = score_customers(result['model'], sales)
    assert set(scored['risk']) <= {'Low', 'Medium', 'High'}
    assert scored['churn_probability'].between(0, 1).all() and (scored['expected_value_12m'] >= 0).all()
    personas = scored.merge(synthetic['customers'][['customer_id', 'persona']]).groupby('persona')['churn_probability'].mean()
    assert personas['lapsed'] > personas['frequent']


def test_segment_recommendations_use_lift():
    sales = pd.DataFrame({'customer_id': [1, 2, 3, 4, 5, 6, 1, 2, 3], 'product_id': [10, 10, 10, 20, 20, 20, 20, 20, 20]})
    seg = pd.DataFrame({'customer_id': [1, 2, 3, 4, 5, 6], 'segment': ['A', 'A', 'A', 'B', 'B', 'B']})
    products = pd.DataFrame({'product_id': [10, 20], 'name': ['Laptop', 'Mouse'], 'category': ['x', 'y']})
    out = {r['segment']: r for r in segment_recommendations(sales, seg, products, min_buyers=1)}
    assert out['A']['recommendations'][0]['product'] == 'Laptop' and out['A']['recommendations'][0]['lift'] == 2.0
    assert out['B']['recommendations'][0]['product'] == 'Mouse'


# ---------------------------------------------------------------- snapshots
def test_snapshot_recomputes_only_when_data_changes(client, setup_marketplace):
    s = setup_marketplace
    db = db_session()
    calls = []

    def compute(session):
        calls.append(1)
        return {'orders': len(calls)}
    first = snapshots.serve(db, 'probe', 'all', compute)
    second = snapshots.serve(db, 'probe', 'all', compute)
    assert first['meta']['fresh'] and second['data'] == first['data'] and len(calls) == 1
    client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': s['product_id'], 'quantity': 1}]})
    third = snapshots.serve(db, 'probe', 'all', compute)
    assert len(calls) == 2 and third['meta']['fresh'] and third['meta']['data_version'] == snapshots.data_version(db)


# ---------------------------------------------------------------- workflows
def _factory():
    bind = db_session().get_bind()
    return lambda: Session(bind=bind)


def test_run_job_records_success_retry_and_failure(client, setup_marketplace, monkeypatch):
    factory = _factory()
    ok = jobs.run_job('data_quality', trigger='manual', session_factory=factory, retries=0)
    assert ok['status'] == 'success' and ok['metrics']['issues'] == 0

    attempts = {'n': 0}

    def flaky(db):
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise RuntimeError('database briefly unavailable')
        return {'done': True}
    monkeypatch.setitem(jobs.JOBS, 'flaky', jobs.Job('flaky', 'test', 'interval', {'minutes': 1}, flaky))
    retried = jobs.run_job('flaky', session_factory=factory, retries=2, backoff_seconds=0)
    assert retried['status'] == 'success' and retried['attempts'] == 2

    monkeypatch.setitem(jobs.JOBS, 'broken', jobs.Job('broken', 'test', 'interval', {'minutes': 1},
                                                      lambda db: 1 / 0))
    failed = jobs.run_job('broken', session_factory=factory, retries=1, backoff_seconds=0)
    assert failed['status'] == 'failed' and failed['attempts'] == 2 and 'ZeroDivisionError' in failed['message']

    with factory() as db:
        rows = db.scalars(select(WorkflowRun)).all()
        summary = {x['job']: x for x in jobs.run_summary(db)}
    assert len(rows) == 3 and all(r.finished_at and r.duration_ms is not None for r in rows)
    assert summary['flaky']['success_rate_pct'] == 100.0 and summary['broken']['success_rate_pct'] == 0.0


def test_data_quality_finds_ledger_mismatch(client, setup_marketplace):
    db = db_session()
    db.add(InventoryMovement(product_id=setup_marketplace['product_id'], delta=-3, reason='bad_import'))
    db.commit()
    assert jobs.data_quality(db)['ledger_mismatch'] == 1


def test_scheduler_builds_every_job():
    from app.scheduler.runner import build_scheduler
    scheduler = build_scheduler('background')
    assert {j.id for j in scheduler.get_jobs()} == set(jobs.JOBS)
    assert jobs.describe(jobs.JOBS['retrain_forecast']) == 'daily at 02:00 UTC'
    assert jobs.describe(jobs.JOBS['refresh_snapshots']) == 'every 10 minutes'


# ------------------------------------------------------------------- MLflow
def test_mlflow_registry_champion_challenger(synthetic, tmp_path, monkeypatch):
    from app.mlflow_tracking import tracking
    monkeypatch.setattr(tracking, 'TRACKING_URI', f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    monkeypatch.setattr(tracking, 'ARTIFACT_ROOT', (tmp_path / 'mlruns').as_uri())
    monkeypatch.setattr(tracking, 'ENABLED', True)
    sales = sales_frame(synthetic)
    first = tracking.train_forecast(sales, holdout_weeks=12, n_estimators=30)
    assert first['version'] == 1 and first['decision'] == 'promoted'
    monkeypatch.setitem(tracking.PROMOTION, 'InventoryForecast', ('category_accuracy_pct', -1000))  # demand a big gain
    second = tracking.train_forecast(sales, holdout_weeks=12, n_estimators=30)
    assert second['version'] == 2 and second['decision'] == 'kept_as_challenger'
    overview = tracking.registry_overview()
    model = next(m for m in overview['models'] if m['name'] == 'InventoryForecast')
    assert model['production_version'] == 1
    assert 'challenger' in next(v for v in model['versions'] if v['version'] == 2)['aliases']

    from app.forecasting import service
    monkeypatch.setattr(service, 'tracking', tracking)
    service.reset()
    loaded, label = service.production_forecaster()
    assert loaded is not None and label.startswith('InventoryForecast v1')
    history = pd.Series(np.full(20, 10.0), index=pd.date_range('2026-01-04', periods=20, freq='W-SUN'))
    assert len(loaded.forecast(history, 'x', 3)) == 3
    service.reset()


# --------------------------------------------------------------------- API
def place(client, s, qty=1):
    return client.post('/api/orders', headers=s['customer'], json={'items': [{'product_id': s['product_id'], 'quantity': qty}]})


def test_live_kpis_match_database_immediately(client, setup_marketplace):
    s = setup_marketplace
    before = client.get('/api/live/kpis', headers=s['admin']).json()
    place(client, s, 2)
    after = client.get('/api/live/kpis', headers=s['vendor']).json()
    assert after['orders'] == before['orders'] + 1 and after['units_sold'] == before['units_sold'] + 2
    assert after['gmv'] == before['gmv'] + 100.0 and after['data_version'] != before['data_version']
    assert client.get('/api/live/kpis', headers=s['customer']).status_code == 403


def test_revenue_endpoints_and_vendor_privacy(client, setup_marketplace):
    s = setup_marketplace
    place(client, s)
    overview = client.get('/api/revenue/overview', headers=s['admin']).json()
    assert overview['monthly'][-1]['gmv'] == 50.0 and overview['meta']['fresh']
    assert client.get('/api/revenue/cohorts', headers=s['vendor']).status_code == 200
    full = client.get('/api/revenue/benchmark', headers=s['admin']).json()
    assert full['vendors'][0]['vendor'] == 'North Gadgets'
    mine = client.get('/api/revenue/benchmark', headers=s['vendor']).json()
    assert mine['you']['rank'] == 1 and 'vendors' not in mine
    assert client.get('/api/analytics/revenue', headers=s['vendor']).json()['total_revenue'] == 50.0
    assert len(client.get('/api/analytics/vendor-performance', headers=s['vendor']).json()) == 1
    assert client.get('/api/analytics/customers', headers=s['admin']).json()['customers'] == 1


def test_customer_intelligence_needs_enough_customers(client, setup_marketplace):
    s = setup_marketplace
    place(client, s)
    ci = client.get('/api/customer-intelligence/overview', headers=s['admin']).json()
    assert ci['available'] is False and 'reason' in ci
    assert client.get('/api/customer-intelligence/at-risk', headers=s['vendor']).json() == []


def test_forecast_and_recommend_routes(client, setup_marketplace):
    s = setup_marketplace
    place(client, s)
    summary = client.get('/api/forecast/summary', headers=s['vendor']).json()
    assert summary['weeks'] == 4 and summary['products'][0]['current_stock'] == 6
    assert client.get(f"/api/forecast/{s['product_id']}", headers=s['vendor']).status_code == 200
    assert client.get('/api/forecast/model', headers=s['vendor']).status_code == 403
    assert client.get('/api/forecast/model', headers=s['admin']).json()['registry_enabled'] is False
    me = client.get('/api/auth/me', headers=s['customer']).json()
    recs = client.get(f"/api/recommend/{me['id']}", headers=s['admin'])
    assert recs.status_code == 200 and recs.json()['customer'] == me['id']
    assert client.get(f"/api/recommend/{me['id']}", headers=s['vendor']).status_code == 403
    assert client.get('/api/recommendations/segments', headers=s['admin']).json()['items'] == []


def test_workflow_api_runs_and_reports(client, setup_marketplace):
    s = setup_marketplace
    place(client, s)
    run = client.post('/api/workflows/data_quality/run', params={'wait': True}, headers=s['admin'])
    assert run.status_code == 202 and run.json()['status'] == 'success'
    assert client.post('/api/workflows/nope/run', headers=s['admin']).status_code == 404
    assert client.post('/api/workflows/data_quality/run', headers=s['vendor']).status_code == 403
    runs = client.get('/api/workflows/runs', headers=s['admin']).json()
    assert runs[0]['job'] == 'data_quality' and runs[0]['trigger'] == 'manual'
    summary = {j['job']: j for j in client.get('/api/workflows', headers=s['admin']).json()}
    assert summary['data_quality']['success_rate_pct'] == 100.0 and summary['retrain_forecast']['runs'] == 0
    assert client.get('/api/mlops/models', headers=s['admin']).json() == {'enabled': False, 'models': []}


def test_excel_and_pdf_exports(client, setup_marketplace):
    from io import BytesIO
    from openpyxl import load_workbook
    s = setup_marketplace
    place(client, s)
    xlsx = client.get('/api/reports/business.xlsx', headers=s['vendor'])
    assert xlsx.status_code == 200 and 'vendor' in xlsx.headers['content-disposition']
    wb = load_workbook(BytesIO(xlsx.content))
    assert wb.sheetnames[:3] == ['Summary', 'Monthly revenue', 'Categories']
    assert wb['Summary']['B5'].value == 50.0
    pdf = client.get('/api/reports/business.pdf', headers=s['admin'])
    assert pdf.content[:4] == b'%PDF' and pdf.headers['content-type'] == 'application/pdf'
    assert client.get('/api/reports/business.pdf', headers=s['customer']).status_code == 403


def test_milestone3_evaluation_endpoint(client, setup_marketplace):
    report = client.get('/api/evaluation/milestone3', headers=setup_marketplace['admin']).json()
    assert 'scorecard' in report or report.get('available') is False
    json.dumps(report)
