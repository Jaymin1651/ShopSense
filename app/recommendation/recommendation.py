"""Hybrid product recommendations: item-based collaborative filtering blended
with category affinity and popularity, plus offline evaluation.

Signals are implicit: each event adds weight to a customer-product cell
(view 1, wishlist 2, cart 3, purchase 5), then ``log1p`` dampens heavy repeats.
Item-item cosine similarity on that matrix answers "people who engaged with
X also engaged with Y". The final score blends:

    0.70 * collaborative score (normalised per customer)
    0.20 * share of the customer's activity in the product's category
    0.10 * overall product popularity

Customers with no history get the popularity ranking ("cold start").

Evaluation (``evaluate``) uses a time split: everything before a cutoff date
trains the model, and the products each customer *newly* buys after the
cutoff are the relevant items. Metrics: HitRate@K (share of customers with at
least one relevant item in their top K; reported as "recommendation
relevance"), Precision@K, Recall@K, NDCG@K and catalogue coverage, each next
to the popularity baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

EVENT_WEIGHTS = {'view': 1.0, 'wishlist': 2.0, 'cart': 3.0, 'purchase': 5.0}
BLEND = {'cf': 0.70, 'category': 0.20, 'popularity': 0.10}


def build_events(interactions: pd.DataFrame | None, transactions: pd.DataFrame | None) -> pd.DataFrame:
    """Combine interaction rows and purchases into one weighted event table."""
    frames = []
    if interactions is not None and not interactions.empty:
        frames.append(interactions.loc[interactions['event_type'].isin(EVENT_WEIGHTS),
                                       ['customer_id', 'product_id', 'event_type', 'timestamp']])
    if transactions is not None and not transactions.empty:
        ts = transactions['timestamp'] if 'timestamp' in transactions else transactions['date']
        frames.append(pd.DataFrame({'customer_id': transactions['customer_id'], 'product_id': transactions['product_id'],
                                    'event_type': 'purchase', 'timestamp': ts}))
    if not frames:
        return pd.DataFrame(columns=['customer_id', 'product_id', 'event_type', 'timestamp', 'weight'])
    events = pd.concat(frames, ignore_index=True)
    events['timestamp'] = pd.to_datetime(events['timestamp'], utc=True, format='mixed').dt.tz_localize(None)
    events['weight'] = events['event_type'].map(EVENT_WEIGHTS)
    return events


@dataclass
class HybridRecommender:
    blend: dict = field(default_factory=lambda: dict(BLEND))
    users: pd.Index | None = None
    items: pd.Index | None = None
    matrix: sparse.csr_matrix | None = None
    similarity: np.ndarray | None = None
    popularity: pd.Series | None = None
    item_category: pd.Series | None = None
    purchased: dict = field(default_factory=dict)
    seen: dict = field(default_factory=dict)
    item_names: dict = field(default_factory=dict)

    def fit(self, events: pd.DataFrame, products: pd.DataFrame | None = None) -> 'HybridRecommender':
        cells = events.groupby(['customer_id', 'product_id'])['weight'].sum().apply(np.log1p)
        self.users = pd.Index(cells.index.get_level_values(0).unique())
        catalogue = set(cells.index.get_level_values(1))
        if products is not None:
            catalogue |= set(products['product_id'])
        self.items = pd.Index(sorted(catalogue))
        rows = self.users.get_indexer(cells.index.get_level_values(0))
        cols = self.items.get_indexer(cells.index.get_level_values(1))
        self.matrix = sparse.csr_matrix((cells.to_numpy(), (rows, cols)), shape=(len(self.users), len(self.items)))
        sim = cosine_similarity(self.matrix.T, dense_output=True)
        np.fill_diagonal(sim, 0.0)
        self.similarity = sim
        buyers = events.loc[events['event_type'] == 'purchase'].groupby('product_id')['customer_id'].nunique()
        pop = buyers.reindex(self.items, fill_value=0).astype(float)
        self.popularity = pop / pop.max() if pop.max() > 0 else pop
        if products is not None and 'category' in products:
            self.item_category = products.set_index('product_id')['category'].reindex(self.items)
            if 'name' in products:
                self.item_names = products.set_index('product_id')['name'].to_dict()
            elif 'product_name' in products:
                self.item_names = products.set_index('product_id')['product_name'].to_dict()
        purchases = events.loc[events['event_type'] == 'purchase']
        self.purchased = purchases.groupby('customer_id')['product_id'].agg(set).to_dict()
        self.seen = events.groupby('customer_id')['product_id'].agg(set).to_dict()
        return self

    def _scores(self, customer_id) -> tuple[np.ndarray, np.ndarray | None]:
        pop = self.popularity.to_numpy()
        if customer_id not in self.users:
            return pop.copy(), None
        row = self.matrix[self.users.get_loc(customer_id)].toarray().ravel()
        cf = row @ self.similarity
        cf = cf / cf.max() if cf.max() > 0 else cf
        cat = np.zeros_like(cf)
        if self.item_category is not None and row.sum() > 0:
            weights = pd.Series(row, index=self.items).groupby(self.item_category.values).sum()
            share = weights / weights.sum()
            cat = self.item_category.map(share).fillna(0).to_numpy()
            cat = cat / cat.max() if cat.max() > 0 else cat
        b = self.blend
        return b['cf'] * cf + b['category'] * cat + b['popularity'] * pop, row

    def recommend(self, customer_id, k: int = 10, exclude: str = 'purchased',
                  candidates: set | None = None) -> list[dict]:
        """Top-k products. ``exclude``: 'purchased', 'seen' (any interaction) or 'none'."""
        scores, row = self._scores(customer_id)
        blocked = set()
        if exclude == 'purchased':
            blocked = self.purchased.get(customer_id, set())
        elif exclude == 'seen':
            blocked = self.seen.get(customer_id, set())
        order = np.argsort(-scores, kind='stable')
        out = []
        for idx in order:
            pid = self.items[idx]
            if pid in blocked or (candidates is not None and pid not in candidates):
                continue
            out.append({'product_id': int(pid), 'score': round(float(scores[idx]), 4),
                        'reason': self._reason(idx, row)})
            if len(out) >= k:
                break
        return out

    def _reason(self, idx: int, row: np.ndarray | None) -> str:
        if row is None or row.sum() == 0:
            return 'Popular with other shoppers'
        # Credit the most similar product this shopper engaged with (not simply their heaviest one).
        contrib = np.where(row > 0, self.similarity[:, idx], 0.0)
        if contrib.max() > 0:
            source = self.items[int(np.argmax(contrib))]
            name = self.item_names.get(source, f'product #{source}')
            return f'Shoppers who liked {name} also chose this'
        if self.item_category is not None and pd.notna(self.item_category.iloc[idx]):
            return f'Matches your interest in {self.item_category.iloc[idx]}'
        return 'Popular with other shoppers'


class PopularityRecommender(HybridRecommender):
    """Baseline: everyone gets the most-purchased products they haven't bought."""

    def _scores(self, customer_id):
        return self.popularity.to_numpy().copy(), None


# --------------------------------------------------------------------- evaluation

def precision_at_k(recommended: list, relevant: set, k: int) -> float:
    """Share of the top-k recommendations that are relevant."""
    if k <= 0:
        return 0.0
    return len([p for p in recommended[:k] if p in relevant]) / k


def _ndcg(recommended: list, relevant: set, k: int) -> float:
    gains = [1 / np.log2(i + 2) for i, p in enumerate(recommended[:k]) if p in relevant]
    ideal = sum(1 / np.log2(i + 2) for i in range(min(len(relevant), k)))
    return sum(gains) / ideal if ideal else 0.0


def evaluate(events: pd.DataFrame, products: pd.DataFrame | None = None, k: int = 10,
             test_days: int = 60, cutoff: pd.Timestamp | None = None) -> dict:
    """Time-split offline evaluation of the hybrid model and popularity baseline."""
    events = events.copy()
    cutoff = pd.Timestamp(cutoff) if cutoff is not None else events['timestamp'].max() - pd.to_timedelta(test_days, unit='D')
    train = events.loc[events['timestamp'] < cutoff]
    test = events.loc[(events['timestamp'] >= cutoff) & (events['event_type'] == 'purchase')]
    bought_before = train.loc[train['event_type'] == 'purchase'].groupby('customer_id')['product_id'].agg(set)
    relevant = {}
    for cid, grp in test.groupby('customer_id'):
        new_items = set(grp['product_id']) - bought_before.get(cid, set())
        if new_items and cid in set(train['customer_id']):
            relevant[cid] = new_items
    if not relevant:
        raise ValueError('No customers with new purchases after the cutoff to evaluate')
    results = {}
    for name, model in (('hybrid', HybridRecommender()), ('popularity_baseline', PopularityRecommender())):
        model.fit(train, products)
        hits, precisions, recalls, ndcgs, shown = [], [], [], [], set()
        for cid, rel in relevant.items():
            recs = [r['product_id'] for r in model.recommend(cid, k, exclude='purchased')]
            shown.update(recs)
            found = len(set(recs) & rel)
            hits.append(found > 0)
            precisions.append(precision_at_k(recs, rel, k))
            recalls.append(found / len(rel))
            ndcgs.append(_ndcg(recs, rel, k))
        results[name] = {
            f'hit_rate_at_{k}_pct': round(float(np.mean(hits)) * 100, 2),
            f'precision_at_{k}_pct': round(float(np.mean(precisions)) * 100, 2),
            f'recall_at_{k}_pct': round(float(np.mean(recalls)) * 100, 2),
            f'ndcg_at_{k}': round(float(np.mean(ndcgs)), 4),
            'catalogue_coverage_pct': round(len(shown) / max(len(model.items), 1) * 100, 1),
        }
    return {
        'k': k, 'cutoff': cutoff.date().isoformat(), 'test_customers': len(relevant),
        'catalogue_size': int(events['product_id'].nunique()),
        'relevance_definition': f'HitRate@{k}: share of customers whose top {k} contains a product they newly bought after the cutoff',
        'models': results,
        'relevance_pct': results['hybrid'][f'hit_rate_at_{k}_pct'],
        'beats_baseline': results['hybrid'][f'hit_rate_at_{k}_pct'] > results['popularity_baseline'][f'hit_rate_at_{k}_pct'],
    }
