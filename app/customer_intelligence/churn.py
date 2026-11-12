"""Churn risk: which customers are unlikely to order in the next 90 days.

Label: a customer "churns" if they place no order in the ``horizon`` days after
a cutoff date. Features use only orders before the cutoff:
recency, frequency, spend, average order value, tenure, orders and spend in
the last 90 days, and the average gap between orders.

Evaluation is time-based. The model is trained at cutoff T - horizon (labels
from the window that ends at T) and tested at cutoff T (labels from the final
``horizon`` days), so it never sees the period it is scored on. It is
compared with a recency-only baseline (longer since last order = more risk).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

FEATURES = ['recency_days', 'orders', 'total_spent', 'aov', 'tenure_days', 'orders_90d', 'spend_90d',
            'avg_gap_days']


def features_at(sales: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """One row per customer with at least one order before ``cutoff``."""
    tx = sales.loc[pd.to_datetime(sales['date']).dt.tz_localize(None) < cutoff].copy()
    if tx.empty:
        return pd.DataFrame(columns=['customer_id'] + FEATURES)
    tx['date'] = pd.to_datetime(tx['date']).dt.tz_localize(None).dt.normalize()
    orders = tx.groupby(['customer_id', 'order_id']).agg(date=('date', 'min'), amount=('amount', 'sum')).reset_index()
    g = orders.groupby('customer_id')
    out = pd.DataFrame({'orders': g['order_id'].count(), 'total_spent': g['amount'].sum(),
                        'first': g['date'].min(), 'last': g['date'].max()})
    recent = orders.loc[orders['date'] >= cutoff - pd.to_timedelta(90, unit='D')].groupby('customer_id')
    out['orders_90d'] = recent['order_id'].count()
    out['spend_90d'] = recent['amount'].sum()
    out = out.fillna({'orders_90d': 0, 'spend_90d': 0})
    out['recency_days'] = (cutoff - out['last']).dt.days
    out['tenure_days'] = (cutoff - out['first']).dt.days
    out['aov'] = out['total_spent'] / out['orders']
    out['avg_gap_days'] = np.where(out['orders'] > 1, (out['last'] - out['first']).dt.days / (out['orders'] - 1),
                                   out['tenure_days'])
    return out.drop(columns=['first', 'last']).reset_index()


def labels_after(sales: pd.DataFrame, cutoff: pd.Timestamp, horizon: int) -> set:
    """Customers who DID order in (cutoff, cutoff + horizon]."""
    dates = pd.to_datetime(sales['date']).dt.tz_localize(None)
    window = sales.loc[(dates >= cutoff) & (dates < cutoff + pd.to_timedelta(horizon, unit='D'))]
    return set(window['customer_id'])


def _dataset(sales, cutoff, horizon):
    X = features_at(sales, cutoff)
    active = labels_after(sales, cutoff, horizon)
    y = (~X['customer_id'].isin(active)).astype(int)
    return X, y


def make_model():
    return make_pipeline(FunctionTransformer(np.log1p, feature_names_out='one-to-one'), StandardScaler(),
                         LogisticRegression(class_weight='balanced', max_iter=500))


def train_and_evaluate(sales: pd.DataFrame, horizon: int = 90, as_of: pd.Timestamp | None = None) -> dict:
    """Fit on the earlier window, score on the latest complete window."""
    end = (pd.Timestamp(as_of) if as_of is not None
           else pd.to_datetime(sales['date']).dt.tz_localize(None).max()).normalize() + pd.to_timedelta(1, unit='D')
    test_cut = end - pd.to_timedelta(horizon, unit='D')
    train_cut = test_cut - pd.to_timedelta(horizon, unit='D')
    X_tr, y_tr = _dataset(sales, train_cut, horizon)
    X_te, y_te = _dataset(sales, test_cut, horizon)
    if len(X_tr) < 20 or y_tr.nunique() < 2 or len(X_te) < 20 or y_te.nunique() < 2:
        raise ValueError('Not enough customer history for a time-based churn evaluation')
    model = make_model().fit(X_tr[FEATURES].clip(lower=0), y_tr)
    prob = model.predict_proba(X_te[FEATURES].clip(lower=0))[:, 1]
    pred = (prob >= 0.5).astype(int)
    top = np.argsort(-prob)[: max(1, len(prob) // 10)]
    base_rate = float(y_te.mean())
    metrics = {
        'roc_auc': round(float(roc_auc_score(y_te, prob)), 4),
        'baseline_recency_auc': round(float(roc_auc_score(y_te, X_te['recency_days'])), 4),
        'precision': round(float(precision_score(y_te, pred, zero_division=0)), 4),
        'recall': round(float(recall_score(y_te, pred, zero_division=0)), 4),
        'top_decile_lift': round(float(y_te.iloc[top].mean() / base_rate), 2) if base_rate else None,
        'churn_rate': round(base_rate, 4), 'train_customers': int(len(X_tr)), 'test_customers': int(len(X_te)),
        'train_cutoff': train_cut.date().isoformat(), 'test_cutoff': test_cut.date().isoformat(),
        'horizon_days': horizon,
    }
    # For live scoring, refit on the most recent labelled window.
    final = make_model().fit(X_te[FEATURES].clip(lower=0), y_te)
    return {'model': final, 'metrics': metrics, 'as_of': end}


def score_customers(model, sales: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Churn probability, risk band and a simple 12-month value for every customer."""
    end = (pd.Timestamp(as_of) if as_of is not None
           else pd.to_datetime(sales['date']).dt.tz_localize(None).max()).normalize() + pd.to_timedelta(1, unit='D')
    X = features_at(sales, end)
    if X.empty:
        return X.assign(churn_probability=[], risk=[], expected_value_12m=[])
    X['churn_probability'] = model.predict_proba(X[FEATURES].clip(lower=0))[:, 1].round(4)
    X['risk'] = pd.cut(X['churn_probability'], [-0.01, 0.4, 0.7, 1.0], labels=['Low', 'Medium', 'High']).astype(str)
    X['expected_value_12m'] = clv_12m(X)
    return X


def clv_12m(frame: pd.DataFrame) -> pd.Series:
    """Heuristic customer value for the next 12 months.

    expected orders = recent monthly order rate x 12 x (1 - churn probability)
    value           = expected orders x average order value
    Recent rate uses the last 90 days, falling back to the lifetime rate.
    """
    lifetime_rate = frame['orders'] / (frame['tenure_days'].clip(lower=30) / 30.44)
    recent_rate = frame['orders_90d'] / (90 / 30.44)
    rate = np.where(frame['orders_90d'] > 0, recent_rate, lifetime_rate)
    return (rate * 12 * (1 - frame['churn_probability']) * frame['aov']).round(2)
