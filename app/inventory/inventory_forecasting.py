"""Weekly demand forecasting trained on historical sales.

Approach
--------
* Sales are aggregated to weekly units per series (a product, a category or the
  whole store). Weeks end on Sunday.
* One Random Forest is trained across every series ("pooled" model). Each
  series is divided by its own training-period mean so large and small sellers
  share one scale.
* Features only use information known before the forecast week: lags 1-4, 52,
  rolling means of 4/8/13 weeks, and week-of-year seasonality.
* Evaluation is chronological: the last ``holdout_weeks`` are never seen in
  training. The model is compared with naive, seasonal-naive and 4-week moving
  average baselines on the same weeks.

Accuracy is reported as ``1 - WAPE`` where WAPE = sum(|actual - forecast|) /
sum(actual). It is the standard retail "forecast accuracy" figure and stays
defined when single weeks have zero sales (unlike MAPE).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

FEATURES = ['lag_1', 'lag_2', 'lag_3', 'lag_4', 'lag_52', 'roll_4', 'roll_8', 'roll_13',
            'week_sin', 'week_cos', 'nonzero_share_8']
MIN_TRAIN_WEEKS = 12


# --------------------------------------------------------------------------- data

def weekly_series(sales: pd.DataFrame, key: str | None = 'product_id', date_col: str = 'date',
                  qty_col: str = 'quantity', end: pd.Timestamp | None = None,
                  complete_only: bool = True) -> pd.DataFrame:
    """Aggregate sales lines into a complete weekly grid (missing weeks = 0).

    Returns long format: ``series``, ``week`` (week-ending Sunday), ``units``.
    ``key=None`` produces one store-wide series called ``'total'``. With
    ``complete_only`` the partial first and last weeks are dropped so a
    half-finished week is never scored against a full-week forecast.
    """
    frame = sales[[date_col, qty_col] + ([key] if key else [])].copy()
    frame['week'] = pd.to_datetime(frame[date_col]).dt.tz_localize(None).dt.to_period('W-SUN').dt.end_time.dt.normalize()
    frame['series'] = frame[key].astype(str) if key else 'total'
    grouped = frame.groupby(['series', 'week'])[qty_col].sum()
    if grouped.empty:
        return pd.DataFrame(columns=['series', 'week', 'units'])
    last = grouped.index.get_level_values('week').max()
    if end is not None:
        last = max(last, pd.Timestamp(end).to_period('W-SUN').end_time.normalize())
    weeks = pd.date_range(grouped.index.get_level_values('week').min(), last, freq='W-SUN')
    full = pd.MultiIndex.from_product([grouped.index.get_level_values('series').unique(), weeks],
                                      names=['series', 'week'])
    out = grouped.reindex(full, fill_value=0).rename('units').reset_index()
    out['units'] = out['units'].astype(float)
    if complete_only:
        dates = pd.to_datetime(frame[date_col]).dt.tz_localize(None).dt.normalize()
        first_ok = out['week'] - pd.to_timedelta(6, unit='D') >= dates.min()
        last_ok = out['week'] <= (pd.Timestamp(end).normalize() if end is not None else dates.max())
        out = out.loc[first_ok & last_ok].reset_index(drop=True)
    return out


def feature_frame(series: pd.Series, floor: float) -> pd.DataFrame:
    """Features for predicting each week from strictly earlier weeks.

    Every value is divided by ``level`` = the mean of the previous 13 weeks
    (never below ``floor``), so the model learns relative movements and can
    follow a trend that runs above anything seen in training.
    """
    prev = series.shift(1)
    out = pd.DataFrame(index=series.index)
    roll = {k: prev.rolling(k, min_periods=1).mean() for k in (4, 8, 13)}
    level = roll[13].clip(lower=floor)
    for k in (1, 2, 3, 4):
        out[f'lag_{k}'] = series.shift(k) / level
    out['lag_52'] = series.shift(52).fillna(roll[13]) / level
    for k in (4, 8, 13):
        out[f'roll_{k}'] = roll[k] / level
    woy = series.index.isocalendar().week.astype(float).to_numpy()
    out['week_sin'] = np.sin(2 * np.pi * woy / 52.18)
    out['week_cos'] = np.cos(2 * np.pi * woy / 52.18)
    out['nonzero_share_8'] = (prev > 0).astype(float).rolling(8, min_periods=1).mean()
    out['level'] = level
    return out


# ------------------------------------------------------------------------- models

@dataclass
class DemandForecaster:
    """Pooled Random Forest over level-scaled weekly series."""
    n_estimators: int = 300
    random_state: int = 42
    model: RandomForestRegressor | None = None
    floors: dict[str, float] = field(default_factory=dict)
    residual_q: tuple[float, float] = (-0.5, 0.5)

    def _floor(self, name: str, history: pd.Series) -> float:
        return self.floors.get(name) or max(0.1 * float(history.mean() or 0), 0.05)

    def fit(self, weekly: pd.DataFrame) -> 'DemandForecaster':
        frames = []
        for name, grp in weekly.groupby('series'):
            s = grp.set_index('week')['units'].sort_index()
            self.floors[name] = max(0.1 * float(s.mean()), 0.05)
            f = feature_frame(s, self.floors[name]).iloc[4:]
            f['target'] = s.iloc[4:] / f['level']
            frames.append(f)
        rows = pd.concat(frames) if frames else pd.DataFrame()
        if rows.empty:
            raise ValueError('Not enough weekly history to train a forecaster')
        X, y = rows[FEATURES].fillna(0.0), rows['target']
        self.model = RandomForestRegressor(n_estimators=self.n_estimators, min_samples_leaf=5, max_features=0.6,
                                           random_state=self.random_state, n_jobs=-1)
        self.model.fit(X, y)
        resid = y - self.model.predict(X)
        # In-sample residuals understate error; widen them for an honest interval.
        self.residual_q = (float(np.quantile(resid, 0.1)) * 1.8, float(np.quantile(resid, 0.9)) * 1.8)
        return self

    def predict_frame(self, features: pd.DataFrame) -> np.ndarray:
        scaled = self.model.predict(features[FEATURES].fillna(0.0))
        return np.clip(scaled * features['level'].to_numpy(), 0, None)

    def predict_next(self, history: pd.Series, name: str) -> float:
        week = history.index[-1] + pd.to_timedelta(7 * (1), unit='D')
        extended = pd.concat([history, pd.Series([np.nan], index=[week])])
        feats = feature_frame(extended, self._floor(name, history)).iloc[[-1]]
        return float(self.predict_frame(feats)[0])

    def forecast(self, history: pd.Series, name: str, horizon: int) -> pd.DataFrame:
        """Recursive multi-week forecast with an approximate 80% interval."""
        hist = history.astype(float).copy()
        rows = []
        for step in range(1, horizon + 1):
            week = hist.index[-1] + pd.to_timedelta(7 * (1), unit='D')
            extended = pd.concat([hist, pd.Series([np.nan], index=[week])])
            feats = feature_frame(extended, self._floor(name, history)).iloc[[-1]]
            value = float(self.predict_frame(feats)[0])
            level = float(feats['level'].iloc[0])
            widen = np.sqrt(step)
            rows.append({'week': week, 'forecast': round(value, 2),
                         'lower': round(max(0.0, value + self.residual_q[0] * level * widen), 2),
                         'upper': round(value + self.residual_q[1] * level * widen, 2)})
            hist = pd.concat([hist, pd.Series([value], index=[week])])
        return pd.DataFrame(rows)


def baseline_frame(series: pd.Series) -> pd.DataFrame:
    """Naive baselines for each week using only earlier weeks."""
    prev = series.shift(1)
    return pd.DataFrame({
        'naive': prev,
        'seasonal_naive': series.shift(52).fillna(prev.rolling(4, min_periods=1).mean()),
        'moving_average_4': prev.rolling(4, min_periods=1).mean(),
    }, index=series.index).fillna(0.0)


# --------------------------------------------------------------------- evaluation

def forecast_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    total = actual.sum()
    abs_err = np.abs(actual - predicted)
    wape = float(abs_err.sum() / total) if total > 0 else float('nan')
    return {
        'accuracy_pct': round(max(0.0, 1 - wape) * 100, 2) if total > 0 else None,
        'wape_pct': round(wape * 100, 2) if total > 0 else None,
        'mae': round(float(abs_err.mean()), 3),
        'rmse': round(float(np.sqrt(((actual - predicted) ** 2).mean())), 3),
        'bias_pct': round(float((predicted - actual).sum() / total) * 100, 2) if total > 0 else None,
        'actual_units': round(float(total), 1),
    }


def evaluate(weekly: pd.DataFrame, holdout_weeks: int = 12, n_estimators: int = 300) -> dict:
    """Chronological holdout evaluation, 1-week-ahead walk-forward.

    The model is trained once on weeks before the holdout. For each holdout
    week every method sees the true history up to the previous week, which is
    how a weekly replenishment review would use it.
    """
    weeks = np.sort(weekly['week'].unique())
    if len(weeks) < MIN_TRAIN_WEEKS + holdout_weeks:
        raise ValueError(f'Need at least {MIN_TRAIN_WEEKS + holdout_weeks} weeks, found {len(weeks)}')
    cutoff = weeks[-holdout_weeks]
    train = weekly.loc[weekly['week'] < cutoff]
    model = DemandForecaster(n_estimators=n_estimators).fit(train)
    methods = ['random_forest', 'naive', 'seasonal_naive', 'moving_average_4']
    preds = {m: [] for m in methods}
    actual = []
    for name, grp in weekly.groupby('series'):
        s = grp.set_index('week')['units'].sort_index()
        mask = s.index >= cutoff
        feats = feature_frame(s, model._floor(name, s.loc[~mask]))
        actual.extend(s.loc[mask].tolist())
        preds['random_forest'].extend(model.predict_frame(feats.loc[mask]).tolist())
        base = baseline_frame(s).loc[mask]
        for m in methods[1:]:
            preds[m].extend(base[m].tolist())
    results = {m: forecast_metrics(np.array(actual), np.array(p)) for m, p in preds.items()}
    best_baseline = max(methods[1:], key=lambda m: results[m]['accuracy_pct'] or -1)
    return {
        'series': int(weekly['series'].nunique()),
        'train_weeks': int((weeks < cutoff).sum()),
        'holdout_weeks': holdout_weeks,
        'holdout_start': pd.Timestamp(cutoff).date().isoformat(),
        'horizon': '1 week ahead (walk-forward)',
        'methods': results,
        'model_accuracy_pct': results['random_forest']['accuracy_pct'],
        'best_baseline': best_baseline,
        'beats_best_baseline': (results['random_forest']['wape_pct'] or 1e9) < (results[best_baseline]['wape_pct'] or 1e9),
    }


# ------------------------------------------------------------- live single product

def forecast_series(weekly: pd.DataFrame, series_name: str, horizon_weeks: int = 4,
                    model: DemandForecaster | None = None) -> dict:
    """Forecast one series; falls back to a moving average when history is short."""
    grp = weekly.loc[weekly['series'] == str(series_name)]
    history = grp.set_index('week')['units'].sort_index()
    if history.empty:
        return {'method': 'no_history', 'weekly': [], 'history': []}
    hist_out = [{'week': w.date().isoformat(), 'units': float(u)} for w, u in history.tail(26).items()]
    if len(history) < MIN_TRAIN_WEEKS or model is None:
        level = float(history.tail(4).mean())
        rows = [{'week': (history.index[-1] + pd.to_timedelta(7 * (i), unit='D')).date().isoformat(), 'forecast': round(level, 2),
                 'lower': round(level * 0.5, 2), 'upper': round(level * 1.5, 2)} for i in range(1, horizon_weeks + 1)]
        return {'method': 'moving_average_4_weeks', 'weekly': rows, 'history': hist_out,
                'note': f'Fewer than {MIN_TRAIN_WEEKS} weeks of sales; showing a 4-week moving average.'}
    frame = model.forecast(history, str(series_name), horizon_weeks)
    frame['week'] = frame['week'].dt.date.astype(str)
    return {'method': 'random_forest_pooled_weekly', 'weekly': frame.to_dict('records'), 'history': hist_out}
