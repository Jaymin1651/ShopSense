"""Business-intelligence results shared by the API, workflows and reports.

Each ``compute_*`` function takes a session and a vendor scope (None = whole
marketplace) and returns JSON-ready data. API routes serve them through
``app.analytics.snapshots.serve`` and the ``refresh_snapshots`` workflow
pre-computes them, so the dashboard, scheduled reports and API always agree.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import revenue_analysis as ra
from app.customer_intelligence.churn import score_customers, train_and_evaluate
from app.models import Category, Product, Vendor
from app.recommendations.segment_recommendations import segment_recommendations
from app.services import intelligence as intel


def _parents(db: Session) -> dict[str, str]:
    cats = db.scalars(select(Category)).all()
    by_id = {c.id: c.name for c in cats}
    return {c.name: by_id.get(c.parent_id, c.name) for c in cats}


def _vendors(db: Session) -> pd.DataFrame:
    rows = db.execute(select(Vendor.id, Vendor.business_name).where(Vendor.status == 'approved')).all()
    return pd.DataFrame(rows, columns=['vendor_id', 'vendor'])


def compute_revenue_overview(db: Session, vendor_id: int | None) -> dict:
    sales = intel.load_sales(db, vendor_id)
    now = intel._now()
    return {
        'growth': ra.growth_summary(sales, as_of=now),
        'monthly': ra.revenue_series(sales, 'month', 18),
        'weekly': ra.revenue_series(sales, 'week', 26),
        'daily': ra.revenue_series(sales, 'day', 60),
        'categories': ra.category_mix(sales, _parents(db), 90, as_of=now),
        'pareto_products': {k: v for k, v in ra.pareto(sales, 'product_id').items()},
    }


def compute_cohorts(db: Session, vendor_id: int | None) -> dict:
    return ra.cohort_retention(intel.load_sales(db, vendor_id), 12)


def compute_benchmark(db: Session, vendor_id: int | None = None) -> dict:
    """Full table (admin). Vendors get ``anonymise_benchmark`` of this."""
    sales = intel.load_sales(db)
    inventory = intel.load_inventory(db)
    return ra.vendor_benchmark(sales, _vendors(db), inventory, 90, as_of=intel._now())


def compute_customer_intelligence(db: Session, vendor_id: int | None) -> dict:
    sales = intel.load_sales(db, vendor_id)
    if sales.empty or sales['customer_id'].nunique() < 20:
        return {'available': False, 'reason': 'Churn scoring needs at least 20 customers with orders.'}
    try:
        trained = train_and_evaluate(sales, 90, as_of=intel._now())
    except ValueError as exc:
        return {'available': False, 'reason': str(exc)}
    scored = score_customers(trained['model'], sales, as_of=intel._now())
    segments = intel.segment_assignments(db, vendor_id)
    scored = scored.merge(segments, on='customer_id', how='left')
    risk = scored['risk'].value_counts().reindex(['High', 'Medium', 'Low'], fill_value=0)
    by_segment = (scored.groupby('segment').agg(customers=('customer_id', 'count'),
                                                avg_churn=('churn_probability', 'mean'),
                                                value_12m=('expected_value_12m', 'sum'))
                  .round(3).reset_index().to_dict('records')) if 'segment' in scored and scored['segment'].notna().any() else []
    at_risk = scored.sort_values(['churn_probability', 'total_spent'], ascending=[False, False])
    at_risk = at_risk.loc[at_risk['risk'] == 'High'].sort_values('total_spent', ascending=False).head(50)
    return {
        'available': True, 'model_metrics': trained['metrics'],
        'customers': int(len(scored)),
        'risk_counts': {k: int(v) for k, v in risk.items()},
        'expected_value_12m_total': round(float(scored['expected_value_12m'].sum()), 2),
        'value_at_risk_12m': round(float(scored.loc[scored['risk'] == 'High', 'total_spent'].sum()), 2),
        'by_segment': by_segment,
        'high_risk_customers': intel._clean(at_risk, ['customer_id', 'segment', 'orders', 'total_spent', 'recency_days',
                                                      'churn_probability', 'expected_value_12m']),
    }


def compute_segment_recommendations(db: Session, vendor_id: int | None) -> list[dict]:
    sales = intel.load_sales(db, vendor_id)
    products = pd.DataFrame(db.execute(select(Product.id, Product.name, Product.category)).all(),
                            columns=['product_id', 'name', 'category'])
    return segment_recommendations(sales, intel.segment_assignments(db, vendor_id), products)


def compute_forecast_summary(db: Session, vendor_id: int | None, weeks: int = 4) -> dict:
    """Next ``weeks`` of demand per product vs stock: the mockup's 'Predicted stock' panel."""
    inv = intel.load_inventory(db, vendor_id)
    if inv.empty:
        return {'products': [], 'source': None, 'weeks': weeks}
    inv = inv.loc[inv['is_active']]
    demand = intel.demand_table(db, inv['product_id'].tolist())
    frame = inv.merge(demand[['product_id', 'daily_demand']], on='product_id', how='left')
    frame['daily_demand'] = frame['daily_demand'].fillna(0)
    frame['forecast_units'] = (frame['daily_demand'] * 7 * weeks).round(1)
    frame['projected_stock'] = (frame['current_stock'] - frame['forecast_units']).round(1)
    frame['shortfall'] = (-frame['projected_stock']).clip(lower=0).round(1)
    frame = frame.sort_values('projected_stock')
    return {'weeks': weeks, 'source': intel.forecast_source() or '8-week average',
            'products': intel._clean(frame, ['product_id', 'name', 'vendor', 'current_stock', 'forecast_units',
                                             'projected_stock', 'shortfall', 'reorder_level'])}


def compute_inventory_overview(db: Session, vendor_id: int | None) -> dict:
    return intel.inventory_overview(db, vendor_id)


def compute_customer_overview(db: Session, vendor_id: int | None) -> dict:
    return intel.customer_overview(db, vendor_id)


# name -> (compute function, also computed per vendor?)
SNAPSHOTS = {
    'revenue_overview': (compute_revenue_overview, True),
    'cohorts': (compute_cohorts, True),
    'benchmark': (compute_benchmark, False),
    'customer_intelligence': (compute_customer_intelligence, True),
    'segment_recommendations': (compute_segment_recommendations, True),
    'forecast_summary': (compute_forecast_summary, True),
    'inventory_overview': (compute_inventory_overview, True),
    'customer_overview': (compute_customer_overview, True),
}


def scope_key(vendor_id: int | None) -> str:
    return 'all' if vendor_id is None else f'vendor:{vendor_id}'


def serve(db: Session, name: str, vendor_id: int | None) -> dict:
    """Snapshot-backed result for one scope ({'data', 'meta'})."""
    from app.analytics import snapshots
    compute, _ = SNAPSHOTS[name]
    return snapshots.serve(db, name, scope_key(vendor_id), lambda s: compute(s, vendor_id))
