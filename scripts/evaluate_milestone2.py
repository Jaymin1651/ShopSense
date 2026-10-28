"""Measure the Milestone 2 evaluation targets on held-out data.

Usage:
    python -m scripts.evaluate_milestone2            # synthetic data/ only
    python -m scripts.evaluate_milestone2 --olist    # also real Olist history

Writes ``reports/milestone2_evaluation.json`` (read by the API and dashboard)
and ``reports/MILESTONE2_EVALUATION.md``. Every number is computed here; none
is typed in by hand. Targets from the milestone brief:

* inventory forecasting accuracy >= 80% on held-out sales
* customer segmentation clustering quality >= 0.85 (silhouette)
* recommendation relevance >= 75% on historical interactions
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.metrics import adjusted_rand_score

from app.customer.analytics import customer_stats
from app.customer.segmentation import segment_customers
from app.inventory.inventory_forecasting import evaluate as evaluate_forecast, weekly_series
from app.recommendation.recommendation import build_events, evaluate as evaluate_recommender

ROOT = Path(__file__).resolve().parents[1]
DATA, REPORTS = ROOT / 'data', ROOT / 'reports'
TARGETS = {'forecast_accuracy_pct': 80.0, 'silhouette': 0.85, 'relevance_pct': 75.0}


def synthetic() -> dict:
    tx = pd.read_csv(DATA / 'transactions.csv')
    products = pd.read_csv(DATA / 'products.csv')
    customers = pd.read_csv(DATA / 'customers.csv')
    interactions = pd.read_csv(DATA / 'interactions.csv')
    tx = tx.merge(products[['product_id', 'category', 'parent_category']], on='product_id')

    forecast = {}
    for level, key in (('product', 'product_id'), ('category', 'category'),
                       ('parent_category', 'parent_category'), ('store_total', None)):
        forecast[level] = evaluate_forecast(weekly_series(tx, key), holdout_weeks=12)
        print(f"  forecast {level:<16} accuracy {forecast[level]['model_accuracy_pct']}%")

    stats = customer_stats(tx)
    segmentation = {}
    for label, k in (('k3', 3), ('auto_k', None)):
        result = segment_customers(stats, k=k, stability_runs=10)
        persona = result['assignments'].merge(customers[['customer_id', 'persona']], on='customer_id')
        metrics = dict(result['metrics'])
        metrics['persona_recovery_ari'] = round(float(adjusted_rand_score(persona['persona'], persona['segment'])), 4)
        segmentation[label] = {'k': result['k'], 'metrics': metrics,
                               'profiles': result['profiles'].to_dict('records')}
        print(f"  segments {label:<6} k={result['k']} silhouette {metrics['silhouette']} "
              f"stability {metrics['stability_ari']}")

    events = build_events(interactions, tx)
    recs = {f'k{k}': evaluate_recommender(events, products, k=k, test_days=60) for k in (5, 10)}
    print(f"  recommend HitRate@10 {recs['k10']['relevance_pct']}%")
    return {'dataset': 'synthetic (data/*.csv, seed 42)', 'transactions': int(len(tx)),
            'customers': int(tx['customer_id'].nunique()), 'products': int(tx['product_id'].nunique()),
            'forecasting': forecast, 'segmentation': segmentation, 'recommendation': recs}


def olist() -> dict:
    """Real historical validation on the public Olist dataset (2016-2018)."""
    import sys
    sys.path.insert(0, str(ROOT / 'dashboard'))
    import requests
    from historical_data import MIRROR, build_sales, download_dataset, read_dataset

    folder = Path(os.getenv('OLIST_DATA_DIR', '/tmp/shopsense_olist'))
    download_dataset(folder)
    sales, _ = build_sales(read_dataset(folder))
    customers_file = folder / 'olist_customers_dataset.csv'
    if not customers_file.exists():
        response = requests.get(f'{MIRROR}/olist_customers_dataset.csv', timeout=(15, 120))
        response.raise_for_status()
        customers_file.write_bytes(response.content)
    orders = pd.read_csv(folder / 'olist_orders_dataset.csv', usecols=['order_id', 'customer_id'])
    unique = pd.read_csv(customers_file, usecols=['customer_id', 'customer_unique_id'])
    sales = sales.merge(orders, on='order_id').merge(unique, on='customer_id')
    sales = sales.rename(columns={'purchase_date': 'date', 'units': 'quantity', 'price_brl': 'amount'})
    # Olist's first months are sparse; use the stable period.
    sales = sales.loc[(sales['date'] >= '2017-01-01') & (sales['date'] < '2018-08-27')]

    top = sales['category'].value_counts().head(20).index
    forecast = {
        'top20_categories': evaluate_forecast(weekly_series(sales.loc[sales['category'].isin(top)], 'category'), 12),
        'store_total': evaluate_forecast(weekly_series(sales, None), 12),
    }
    for level, result in forecast.items():
        print(f"  olist forecast {level:<18} accuracy {result['model_accuracy_pct']}%")

    tx = sales.assign(customer_id=sales['customer_unique_id'])
    stats = customer_stats(tx)
    seg = segment_customers(stats, k=3, stability_runs=5)
    print(f"  olist segments silhouette {seg['metrics']['silhouette']}")
    repeat = float((stats['orders'] > 1).mean() * 100)
    return {
        'dataset': 'Olist Brazilian E-Commerce (real, anonymised), delivered orders 2017-01 to 2018-08',
        'item_rows': int(len(sales)), 'customers': int(len(stats)),
        'forecasting': forecast,
        'segmentation': {'k': seg['k'], 'metrics': seg['metrics'], 'profiles': seg['profiles'].to_dict('records')},
        'recommendation': {'evaluated': False,
                           'reason': f'Only {repeat:.1f}% of Olist customers ever order twice, so there is almost '
                                     'no per-customer history to recommend from or to hold out.'},
    }


def scorecard(report: dict) -> list[dict]:
    syn = report['synthetic']
    seg = syn['segmentation']['k3']['metrics']
    rec = syn['recommendation']['k10']
    rows = [
        {'criterion': 'Inventory forecasting accuracy', 'target': '>= 80%',
         'metric': '1 - WAPE, weekly, 12-week holdout, category level',
         'value': syn['forecasting']['category']['model_accuracy_pct'],
         'met': syn['forecasting']['category']['model_accuracy_pct'] >= TARGETS['forecast_accuracy_pct'],
         'context': (f"Store total {syn['forecasting']['store_total']['model_accuracy_pct']}%, "
                     f"single products {syn['forecasting']['product']['model_accuracy_pct']}% "
                     f"(4-week moving average: {syn['forecasting']['product']['methods']['moving_average_4']['accuracy_pct']}%)."
                     ' Individual products sell a few units a week, so week-to-week noise caps product-level accuracy.')},
        {'criterion': 'Customer segmentation quality', 'target': '>= 0.85',
         'metric': 'Silhouette score, K-Means k=3 on log RFM', 'value': seg['silhouette'],
         'met': seg['silhouette'] >= TARGETS['silhouette'],
         'context': (f"Bootstrap stability (adjusted Rand) {seg['stability_ari']}, best silhouette over k=2..6 "
                     f"{max(seg['silhouette_by_k'].values())}. Real purchase behaviour is a continuum, so silhouette "
                     'values of 0.3-0.5 are typical; 0.85 needs almost perfectly separated groups.')},
        {'criterion': 'Recommendation relevance', 'target': '>= 75%',
         'metric': 'HitRate@10 on purchases in the final 60 days', 'value': rec['relevance_pct'],
         'met': rec['relevance_pct'] >= TARGETS['relevance_pct'],
         'context': (f"Popularity baseline {rec['models']['popularity_baseline']['hit_rate_at_10_pct']}%. "
                     f"Precision@10 {rec['models']['hybrid']['precision_at_10_pct']}%, "
                     f"Recall@10 {rec['models']['hybrid']['recall_at_10_pct']}%. "
                     f"The catalogue has {rec['catalogue_size']} products, so 10 picks cover a large share of it.")},
    ]
    if 'olist' in report:
        ol = report['olist']
        rows[0]['context'] += (f" Real Olist data: top-20 categories {ol['forecasting']['top20_categories']['model_accuracy_pct']}%, "
                               f"store total {ol['forecasting']['store_total']['model_accuracy_pct']}%.")
        rows[1]['context'] += f" Real Olist customers: silhouette {ol['segmentation']['metrics']['silhouette']}."
    return rows


def markdown(report: dict) -> str:
    lines = ['# Milestone 2 evaluation', '',
             f"Generated {report['generated_at']} by `python -m scripts.evaluate_milestone2"
             f"{' --olist' if 'olist' in report else ''}`. All figures are computed by the script.", '',
             '| Criterion | Target | Measured | Met? | Metric |', '| --- | --- | --- | --- | --- |']
    for r in report['scorecard']:
        lines.append(f"| {r['criterion']} | {r['target']} | {r['value']} | {'Yes' if r['met'] else 'No'} | {r['metric']} |")
    lines += ['', '## Notes', '']
    for r in report['scorecard']:
        lines.append(f"- **{r['criterion']}.** {r['context']}")
    lines += ['', '## Forecasting detail (synthetic, 1-week-ahead walk-forward, last 12 weeks held out)', '',
              '| Level | Series | Random Forest | Naive | Seasonal naive | 4-week average |', '| --- | --- | --- | --- | --- | --- |']
    for level, res in report['synthetic']['forecasting'].items():
        m = res['methods']
        lines.append(f"| {level} | {res['series']} | {m['random_forest']['accuracy_pct']}% | {m['naive']['accuracy_pct']}% | "
                     f"{m['seasonal_naive']['accuracy_pct']}% | {m['moving_average_4']['accuracy_pct']}% |")
    if 'olist' in report:
        for level, res in report['olist']['forecasting'].items():
            m = res['methods']
            lines.append(f"| Olist {level} | {res['series']} | {m['random_forest']['accuracy_pct']}% | {m['naive']['accuracy_pct']}% | "
                         f"{m['seasonal_naive']['accuracy_pct']}% | {m['moving_average_4']['accuracy_pct']}% |")
    lines += ['', '## Recommendation detail (synthetic)', '', '| Model | K | HitRate | Precision | Recall | NDCG | Coverage |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for key, res in report['synthetic']['recommendation'].items():
        k = res['k']
        for name, m in res['models'].items():
            lines.append(f"| {name} | {k} | {m[f'hit_rate_at_{k}_pct']}% | {m[f'precision_at_{k}_pct']}% | "
                         f"{m[f'recall_at_{k}_pct']}% | {m[f'ndcg_at_{k}']} | {m['catalogue_coverage_pct']}% |")
    lines += ['', '## Segmentation detail (synthetic)', '']
    for key, res in report['synthetic']['segmentation'].items():
        m = res['metrics']
        lines.append(f"- {key} (k={res['k']}): silhouette {m['silhouette']}, Davies-Bouldin {m['davies_bouldin']}, "
                     f"Calinski-Harabasz {m['calinski_harabasz']}, stability {m['stability_ari']}, "
                     f"agreement with simulated personas (ARI) {m['persona_recovery_ari']}.")
    lines += ['', 'The synthetic dataset is simulated; see `scripts/generate_milestone2_data.py`. '
              'Its `persona` column is only used for the persona agreement check above.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Evaluate Milestone 2 targets')
    parser.add_argument('--olist', action='store_true', help='also validate on the real Olist dataset (downloads ~120 MB)')
    args = parser.parse_args()
    print('Synthetic dataset')
    report = {'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'targets': TARGETS,
              'synthetic': synthetic()}
    if args.olist:
        print('Olist dataset')
        report['olist'] = olist()
    report['scorecard'] = scorecard(report)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'milestone2_evaluation.json').write_text(json.dumps(report, indent=2, default=str))
    (REPORTS / 'MILESTONE2_EVALUATION.md').write_text(markdown(report))
    for row in report['scorecard']:
        print(f"{'PASS' if row['met'] else 'MISS'}  {row['criterion']}: {row['value']} (target {row['target']})")


if __name__ == '__main__':
    main()
