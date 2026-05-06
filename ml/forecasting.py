from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import sqrt
from statistics import mean
from typing import Callable, Dict, List, Tuple


@dataclass(frozen=True)
class BacktestResult:
    model: str
    mae: float
    rmse: float
    horizon: int
    points: int


def _to_series(history: Dict[str, float]) -> List[Tuple[date, float]]:
    items = [(date.fromisoformat(k), float(v)) for k, v in history.items()]
    items.sort(key=lambda x: x[0])
    if not items:
        return []

    start, end = items[0][0], items[-1][0]
    values = {d: v for d, v in items}
    out: List[Tuple[date, float]] = []
    cur = start
    while cur <= end:
        out.append((cur, float(values.get(cur, 0.0))))
        cur += timedelta(days=1)
    return out


def seasonal_naive_forecast(series: List[Tuple[date, float]], horizon: int, season: int = 7) -> List[Tuple[date, float]]:
    if not series:
        return []
    last_date = series[-1][0]
    vals = [v for _, v in series]
    preds: List[Tuple[date, float]] = []
    for i in range(1, horizon + 1):
        idx = len(vals) - season + ((i - 1) % season)
        pred = vals[idx] if idx >= 0 else vals[-1]
        preds.append((last_date + timedelta(days=i), max(0.0, float(pred))))
    return preds


def moving_average_forecast(series: List[Tuple[date, float]], horizon: int, window: int = 7) -> List[Tuple[date, float]]:
    if not series:
        return []
    last_date = series[-1][0]
    vals = [v for _, v in series]
    base = sum(vals[-window:]) / max(1, min(window, len(vals)))
    return [(last_date + timedelta(days=i), max(0.0, float(base))) for i in range(1, horizon + 1)]


def _linear_trend_forecast(series: List[Tuple[date, float]], horizon: int) -> List[Tuple[date, float]]:
    """
    Simple least-squares linear trend on time index.
    Pure python, no heavy deps.
    """
    if not series:
        return []
    last_date = series[-1][0]
    y = [float(v) for _, v in series]
    n = len(y)
    # x = 0..n-1
    x_mean = (n - 1) / 2.0
    y_mean = mean(y)
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom == 0:
        slope = 0.0
    else:
        slope = sum((i - x_mean) * (y[i] - y_mean) for i in range(n)) / denom
    intercept = y_mean - slope * x_mean

    preds: List[Tuple[date, float]] = []
    for i in range(1, horizon + 1):
        x_f = (n - 1) + i
        v = intercept + slope * x_f
        preds.append((last_date + timedelta(days=i), max(0.0, float(v))))
    return preds


def backtest(history: Dict[str, float], horizon: int = 14, min_train: int = 28) -> List[BacktestResult]:
    series = _to_series(history)
    if len(series) < min_train + horizon:
        return []

    # rolling origin: evaluate on the last few cut points
    candidates: List[Tuple[str, Callable[[List[Tuple[date, float]]], List[Tuple[date, float]]]]] = [
        ("SeasonalNaive(7)", lambda s: seasonal_naive_forecast(s, horizon, 7)),
        ("MovingAvg(7)", lambda s: moving_average_forecast(s, horizon, 7)),
        ("LinearTrend", lambda s: _linear_trend_forecast(s, horizon)),
    ]

    # evaluate at up to 3 origins near the end
    origins = [len(series) - horizon, len(series) - horizon - 7, len(series) - horizon - 14]
    origins = [o for o in origins if o >= min_train]
    if not origins:
        origins = [len(series) - horizon]

    agg: Dict[str, List[Tuple[float, float]]] = {name: [] for name, _ in candidates}
    for origin in origins:
        train = series[:origin]
        test = series[origin:origin + horizon]
        y_true = [v for _, v in test]
        for name, fn in candidates:
            y_pred = [v for _, v in fn(train)]
            mae = sum(abs(a - p) for a, p in zip(y_true, y_pred)) / len(y_true)
            rmse = sqrt(sum((a - p) ** 2 for a, p in zip(y_true, y_pred)) / len(y_true))
            agg[name].append((float(mae), float(rmse)))

    results: List[BacktestResult] = []
    for name, _ in candidates:
        maes = [m for m, _ in agg[name]]
        rmses = [r for _, r in agg[name]]
        results.append(BacktestResult(
            model=name,
            mae=float(mean(maes)) if maes else 0.0,
            rmse=float(mean(rmses)) if rmses else 0.0,
            horizon=horizon,
            points=len(series),
        ))
    results.sort(key=lambda r: r.mae)
    return results


def best_forecast(history: Dict[str, float], horizon: int = 30) -> Dict:
    series = _to_series(history)
    if len(series) < 7:
        return {"error": "Need at least 7 days of history."}

    bt = backtest(history, horizon=min(14, horizon), min_train=28)
    model_name = bt[0].model if bt else "SeasonalNaive(7)"
    mae = bt[0].mae if bt else 0.0
    rmse = bt[0].rmse if bt else 0.0

    if model_name.startswith("MovingAvg"):
        preds = moving_average_forecast(series, horizon, 7)
    elif model_name.startswith("LinearTrend"):
        preds = _linear_trend_forecast(series, horizon)
    else:
        preds = seasonal_naive_forecast(series, horizon, 7)

    # Simple confidence interval using backtest RMSE as sigma proxy
    sigma = float(rmse or 0.0)

    return {
        "model_used": model_name,
        "backtest": [r.__dict__ for r in bt],
        "forecast": [{
            "date": d.isoformat(),
            "predicted_qty": round(v, 2),
            "lower": round(max(0.0, v - 1.96 * sigma), 2),
            "upper": round(v + 1.96 * sigma, 2),
        } for d, v in preds],
        "historical": [{"date": d.isoformat(), "qty": v} for d, v in series[-90:]],
        "accuracy_metrics": {
            "mae": round(float(mae), 2),
            "rmse": round(float(rmse), 2),
            "data_points": int(len(series)),
            "forecast_horizon": int(horizon),
        }
    }

