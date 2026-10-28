"""Customer segmentation with K-Means on recency, frequency and monetary value.

Features are ``recency_days``, ``orders`` and ``total_spent`` from
``app.customer.analytics.customer_stats``. They are log-transformed (all three
are heavily right-skewed) and standardised before clustering.

Cluster numbers from K-Means are arbitrary, so segments are named by ranking
each cluster's centroid on a value score (more orders and spend, more recent
= higher), never by a fixed ``{0: 'High value', ...}`` map.

Quality is reported with several metrics so no single number is over-read:
* silhouette (-1..1, internal separation; the milestone target uses this),
* Davies-Bouldin (lower is better) and Calinski-Harabasz (higher is better),
* stability: mean adjusted Rand index between the full-data clustering and
  re-fits on bootstrap samples (1.0 = identical groups every time).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score, davies_bouldin_score,
                             silhouette_score)
from sklearn.preprocessing import StandardScaler

FEATURES = ['recency_days', 'orders', 'total_spent']
NAMES = {
    2: ['High value', 'Low engagement'],
    3: ['High value', 'Regular', 'Dormant'],
    4: ['Champions', 'Loyal', 'Occasional', 'Dormant'],
    5: ['Champions', 'Loyal', 'Promising', 'Needs attention', 'Dormant'],
    6: ['Champions', 'Loyal', 'Promising', 'Needs attention', 'At risk', 'Dormant'],
}
DESCRIPTIONS = {
    'Champions': 'Buy often, spend the most and bought recently.',
    'High value': 'Frequent, high-spending and recently active.',
    'Loyal': 'Steady repeat buyers with solid spend.',
    'Regular': 'Repeat buyers with moderate spend.',
    'Promising': 'Recent buyers who have not yet built a habit.',
    'Occasional': 'Buy now and then with modest spend.',
    'Needs attention': 'Some history but activity is slowing.',
    'At risk': 'Used to buy regularly but have gone quiet.',
    'Low engagement': 'Few orders, low spend or long inactive.',
    'Dormant': 'Long time since the last order.',
}


def prepare(stats: pd.DataFrame) -> tuple[np.ndarray, StandardScaler]:
    X = np.log1p(stats[FEATURES].clip(lower=0).astype(float).to_numpy())
    scaler = StandardScaler().fit(X)
    return scaler.transform(X), scaler


def _fit(X: np.ndarray, k: int, seed: int = 42) -> KMeans:
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)


def choose_k(X: np.ndarray, k_range=range(2, 7), sample: int = 5000, seed: int = 42) -> dict[int, float]:
    """Silhouette for each candidate k (on a sample for large datasets)."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False)
    distinct = len(np.unique(X, axis=0))
    scores = {}
    for k in k_range:
        if k >= len(idx) or k > distinct:
            break
        labels = _fit(X, k, seed).predict(X[idx])
        if len(set(labels)) > 1:
            scores[k] = round(float(silhouette_score(X[idx], labels)), 4)
    return scores


def segment_customers(stats: pd.DataFrame, k: int | None = 3, seed: int = 42,
                      stability_runs: int = 10) -> dict:
    """Cluster customers; ``k=None`` picks the k with the best silhouette."""
    if len(stats) < 10:
        raise ValueError('Need at least 10 customers with purchases to segment')
    X, scaler = prepare(stats)
    distinct = len(np.unique(X, axis=0))
    if distinct < 2:
        raise ValueError('All customers look identical; nothing to segment')
    k_scores = choose_k(X, seed=seed)
    if k is None:
        k = max(k_scores, key=k_scores.get)
    k = min(k, distinct)
    model = _fit(X, k, seed)
    labels = model.labels_

    # Rank clusters by a value score computed from the standardised centroid.
    centroids = model.cluster_centers_
    value = -centroids[:, 0] + centroids[:, 1] + centroids[:, 2]
    order = np.argsort(-value)
    names = NAMES.get(k, [f'Segment {i + 1}' for i in range(k)])
    name_of = {int(cluster): names[rank] for rank, cluster in enumerate(order)}

    result = stats.copy()
    result['cluster'] = labels
    result['segment'] = result['cluster'].map(name_of)
    sample = np.random.default_rng(seed).choice(len(X), size=min(5000, len(X)), replace=False)
    metrics = {
        'silhouette': round(float(silhouette_score(X[sample], labels[sample])), 4),
        'davies_bouldin': round(float(davies_bouldin_score(X, labels)), 4),
        'calinski_harabasz': round(float(calinski_harabasz_score(X, labels)), 1),
        'stability_ari': stability(X, k, labels, runs=stability_runs, seed=seed),
        'silhouette_by_k': k_scores,
    }
    profiles = (result.groupby('segment')
                .agg(customers=('customer_id', 'count'), avg_orders=('orders', 'mean'),
                     avg_spent=('total_spent', 'mean'), avg_recency_days=('recency_days', 'mean'),
                     avg_order_value=('average_order_value', 'mean'))
                .round(1).reset_index())
    profiles['share_pct'] = (profiles['customers'] / len(result) * 100).round(1)
    profiles['description'] = profiles['segment'].map(DESCRIPTIONS).fillna('')
    profiles['rank'] = profiles['segment'].map({names[r]: r for r in range(k)})
    profiles = profiles.sort_values('rank').drop(columns='rank').reset_index(drop=True)
    return {'k': int(k), 'method': 'kmeans_log_rfm_standardised', 'metrics': metrics,
            'profiles': profiles, 'assignments': result}


def stability(X: np.ndarray, k: int, reference: np.ndarray, runs: int = 10, seed: int = 42) -> float | None:
    """Mean adjusted Rand index of bootstrap re-fits versus the reference labels."""
    if runs <= 0:
        return None
    rng = np.random.default_rng(seed)
    scores = []
    for r in range(runs):
        idx = rng.choice(len(X), size=len(X), replace=True)
        refit = KMeans(n_clusters=k, n_init=5, random_state=seed + r + 1).fit(X[idx])
        scores.append(adjusted_rand_score(reference, refit.predict(X)))
    return round(float(np.mean(scores)), 4)
