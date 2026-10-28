"""Unit tests for the Milestone 2 analytics engines (no database)."""
import numpy as np
import pandas as pd
import pytest

from app.customer.analytics import behaviour_summary, conversion_funnel, customer_stats
from app.customer.segmentation import segment_customers
from app.inventory.inventory_forecasting import DemandForecaster, evaluate, forecast_metrics, weekly_series
from app.inventory.inventory_tracking import inventory_status, reconstruct_stock_levels, turnover_rate, turnover_table
from app.inventory.stock_alert import low_stock_alert, replenishment
from app.recommendation.recommendation import HybridRecommender, build_events, precision_at_k
from scripts.generate_milestone2_data import build


def brief_inventory():
    """The inventory table from the milestone brief (data/inventory.csv example)."""
    return pd.DataFrame({'product_id': [101, 102, 103, 104, 105], 'vendor_id': [1, 1, 2, 2, 3],
                         'current_stock': [150, 15, 90, 10, 5], 'reorder_level': [40, 25, 30, 20, 15]})


def test_inventory_status_matches_brief():
    status = inventory_status(brief_inventory()).set_index('product_id')['status']
    assert status.to_dict() == {101: 'Available', 102: 'Low stock', 103: 'Available',
                                104: 'Low stock', 105: 'Low stock'}
    zero = inventory_status(pd.DataFrame({'product_id': [1], 'current_stock': [0], 'reorder_level': [5]}))
    assert zero['status'].iloc[0] == 'Out of stock'


def test_turnover_rate_brief_example():
    assert turnover_rate(100000, 25000) == 4.0
    with pytest.raises(ValueError):
        turnover_rate(10, 0)


def test_reconstruct_stock_levels_walks_backwards():
    moves = pd.DataFrame({'created_at': pd.to_datetime(['2026-01-01', '2026-01-03', '2026-01-05'], utc=True),
                          'delta': [20, -5, -3]})
    levels = reconstruct_stock_levels(12, moves, pd.Timestamp('2026-01-01'), pd.Timestamp('2026-01-05'))
    assert levels.tolist() == [20, 20, 15, 15, 12]


def test_turnover_table_uses_cost_basis():
    inv = pd.DataFrame({'product_id': [1], 'current_stock': [10], 'reorder_level': [2], 'unit_cost': [4.0]})
    sales = pd.DataFrame({'product_id': [1, 1], 'date': ['2026-01-10', '2026-01-20'], 'quantity': [5, 5]})
    row = turnover_table(inv, sales, days=30, end=pd.Timestamp('2026-01-30')).iloc[0]
    assert row['units_sold'] == 10 and row['basis'] == 'cost' and row['cogs'] == 40.0
    assert row['average_inventory_units'] == 15.0 and row['turnover'] == round(10 / 15, 2)


def test_replenishment_fallback_is_brief_formula():
    plan = replenishment(brief_inventory(), only_needed=False).set_index('product_id')
    assert plan.loc[105, 'reorder_qty'] == 2 * 15 - 5
    assert plan.loc[101, 'reorder_qty'] == 0  # 2*40-150 is negative, clipped to zero
    assert plan.loc[105, 'method'] == 'rule_2x_reorder_level'


def test_replenishment_with_forecast_order_up_to():
    inv = pd.DataFrame({'product_id': [1], 'current_stock': [10], 'reorder_level': [20], 'lead_time_days': [4]})
    demand = pd.DataFrame({'product_id': [1], 'daily_demand': [5.0], 'daily_demand_std': [2.0]})
    row = replenishment(inv, demand, service_level=0.95, review_days=7).iloc[0]
    safety = 1.65 * 2.0 * 2  # z * std * sqrt(4)
    assert row['safety_stock'] == round(safety, 1)
    assert row['reorder_qty'] == int(np.ceil(5 * 11 + safety - 10))


def test_low_stock_alert_severity_and_order():
    inv = pd.DataFrame({'product_id': [1, 2, 3, 4], 'current_stock': [0, 8, 30, 100],
                        'reorder_level': [5, 10, 10, 10], 'lead_time_days': [7, 7, 7, 7]})
    demand = pd.DataFrame({'product_id': [1, 2, 3, 4], 'daily_demand': [1.0, 0.1, 10.0, 1.0]})
    alerts = low_stock_alert(inv, demand)
    assert alerts['product_id'].tolist() == [1, 3, 2]  # stock-out and run-out-in-lead-time are critical
    assert alerts['severity'].tolist() == ['critical', 'critical', 'warning']
    assert 'day' in alerts.loc[alerts['product_id'] == 3, 'message'].iloc[0]


def test_weekly_series_fills_gaps_and_drops_partial_weeks():
    sales = pd.DataFrame({'date': ['2026-01-07', '2026-01-14', '2026-01-28', '2026-02-02'],
                          'product_id': [1, 1, 1, 1], 'quantity': [2, 3, 4, 9]})
    weekly = weekly_series(sales)
    # The first week (starting 5 Jan) began before the first sale; the week of 2 Feb is unfinished.
    assert weekly['week'].dt.strftime('%m-%d').tolist() == ['01-18', '01-25', '02-01']
    assert weekly['units'].tolist() == [3.0, 0.0, 4.0]


def test_forecast_metrics_wape():
    m = forecast_metrics(np.array([10, 10, 0]), np.array([8, 12, 1]))
    assert m['wape_pct'] == 25.0 and m['accuracy_pct'] == 75.0 and m['bias_pct'] == 5.0


def test_forecaster_learns_seasonal_series_and_beats_naive():
    rng = np.random.default_rng(0)
    weeks = pd.date_range('2023-01-01', periods=130, freq='W-SUN')
    rows = []
    for s, base in enumerate([20, 60, 120]):
        season = 1 + 0.4 * np.sin(2 * np.pi * np.arange(130) / 52)
        units = rng.poisson(base * season)
        rows += [{'series': str(s), 'week': w, 'units': float(u)} for w, u in zip(weeks, units)]
    result = evaluate(pd.DataFrame(rows), holdout_weeks=12, n_estimators=80)
    assert result['train_weeks'] + result['holdout_weeks'] == 130
    assert result['model_accuracy_pct'] > result['methods']['naive']['accuracy_pct']
    model = DemandForecaster(n_estimators=50).fit(pd.DataFrame(rows))
    history = pd.DataFrame(rows).query("series == '2'").set_index('week')['units']
    future = model.forecast(history, '2', 4)
    assert len(future) == 4 and (future['lower'] <= future['forecast']).all() and (future['forecast'] <= future['upper']).all()


def make_rfm(n_each=40, seed=0):
    rng = np.random.default_rng(seed)
    groups = [(5, 30, 6000), (60, 8, 1500), (400, 2, 200)]  # (recency, orders, spend)
    rows = []
    for g, (r, o, m) in enumerate(groups):
        for _ in range(n_each):
            rows.append({'customer_id': len(rows) + 1, 'recency_days': max(1, rng.normal(r, r * .15)),
                         'orders': max(1, round(rng.normal(o, o * .15))), 'total_spent': max(10, rng.normal(m, m * .15)),
                         'average_order_value': 100.0, 'truth': g})
    return pd.DataFrame(rows)


def test_segmentation_names_clusters_by_value_not_index():
    stats = make_rfm()
    result = segment_customers(stats, k=3, stability_runs=3)
    named = result['assignments'].groupby('truth')['segment'].agg(lambda s: s.mode().iloc[0]).to_dict()
    assert named == {0: 'High value', 1: 'Regular', 2: 'Dormant'}
    assert result['metrics']['silhouette'] > 0.5 and result['metrics']['stability_ari'] > 0.9
    assert list(result['profiles']['segment']) == ['High value', 'Regular', 'Dormant']
    assert segment_customers(stats, k=None, stability_runs=0)['k'] in range(2, 7)


def test_customer_stats_and_summary():
    tx = pd.DataFrame({'customer_id': [1, 1, 2], 'order_id': [10, 11, 12], 'product_id': [5, 6, 5],
                       'date': ['2026-01-01', '2026-01-11', '2026-01-05'], 'amount': [100.0, 50.0, 30.0],
                       'quantity': [1, 1, 1]})
    stats = customer_stats(tx, as_of=pd.Timestamp('2026-01-21')).set_index('customer_id')
    assert stats.loc[1, 'orders'] == 2 and stats.loc[1, 'average_order_value'] == 75.0
    assert stats.loc[1, 'recency_days'] == 10 and stats.loc[2, 'recency_days'] == 16
    summary = behaviour_summary(stats.reset_index())
    assert summary['average_order_value'] == 60.0 and summary['repeat_rate_pct'] == 50.0
    funnel = conversion_funnel(pd.DataFrame({'customer_id': [1, 1, 2], 'product_id': [5, 5, 6],
                                             'event_type': ['view', 'cart', 'view']}), tx)
    assert funnel['view_to_cart_pct'] == 50.0 and funnel['cart_to_purchase_pct'] == 100.0


def co_purchase_events():
    """Customers who buy 1 also buy 2; customers who buy 3 also buy 4."""
    rows = []
    for c in range(1, 9):
        pair = (1, 2) if c <= 4 else (3, 4)
        rows += [{'customer_id': c, 'product_id': pair[0]}, {'customer_id': c, 'product_id': pair[1]}]
    rows += [{'customer_id': 9, 'product_id': 1}, {'customer_id': 10, 'product_id': 4}]
    tx = pd.DataFrame(rows).assign(date='2026-01-01')
    return build_events(None, tx)


def test_recommender_follows_co_purchases_and_excludes_owned():
    products = pd.DataFrame({'product_id': [1, 2, 3, 4, 5], 'name': list('ABCDE'), 'category': ['x', 'x', 'y', 'y', 'z']})
    model = HybridRecommender().fit(co_purchase_events(), products)
    first = model.recommend(9, k=2)
    assert first[0]['product_id'] == 2 and 'A' in first[0]['reason']
    assert all(r['product_id'] != 1 for r in first)
    assert model.recommend(10, k=1)[0]['product_id'] == 3
    cold = model.recommend(999, k=3)
    assert [r['reason'] for r in cold] == ['Popular with other shoppers'] * 3
    assert model.recommend(9, k=5, candidates={5})[0]['product_id'] == 5


def test_precision_at_k():
    assert precision_at_k([1, 2, 3, 4], {2, 4, 9}, 4) == 0.5
    assert precision_at_k([1], {1}, 0) == 0.0


def test_dataset_generator_is_deterministic():
    a, b = build(seed=7, n_customers=40), build(seed=7, n_customers=40)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])
    assert set(a['transactions'].columns) >= {'transaction_id', 'customer_id', 'product_id', 'amount', 'date'}
    assert (a['inventory']['reorder_level'] >= 5).all()
