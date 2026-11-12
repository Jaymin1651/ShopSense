"""MLflow pyfunc wrapper so the demand forecaster can be registered and served."""
from __future__ import annotations

import mlflow
import pandas as pd


class ForecastModel(mlflow.pyfunc.PythonModel):
    """Wraps ``DemandForecaster``.

    Input: long frame with ``series``, ``week``, ``units`` (weekly history).
    Param ``horizon`` (weeks, default 4). Output: one row per series and week.
    """

    def __init__(self, forecaster):
        self.forecaster = forecaster

    def predict(self, context, model_input: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        horizon = int((params or {}).get('horizon', 4))
        frames = []
        for name, grp in model_input.groupby('series'):
            history = grp.assign(week=pd.to_datetime(grp['week'])).set_index('week')['units'].sort_index()
            out = self.forecaster.forecast(history, str(name), horizon)
            frames.append(out.assign(series=str(name)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=['week', 'forecast', 'lower', 'upper', 'series'])
