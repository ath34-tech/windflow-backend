import math
from typing import Dict, List, Optional
from ..schemas import AccuracyMetricsSchema, MatchedIntervalSchema

def calculate_percentile(sorted_values: List[float], percentile: float) -> Optional[float]:
    """Calculates percentile using standard linear interpolation."""
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[int(f)] * (c - k)
    d1 = sorted_values[int(c)] * (k - f)
    return round(d0 + d1, 1)

def compute_metrics_from_values(forecasts: List[float], actuals: List[float]) -> Dict[str, Optional[float]]:
    """
    Direct formula computation used for unit testing against known hand-calculated values.
    Example: Forecasts [110, 90], Actuals [100, 100] -> MAE 10, RMSE 10, Bias 0, n 2
    """
    if len(forecasts) != len(actuals) or not forecasts:
        return {"mae": None, "rmse": None, "bias": None, "n": 0}

    n = len(forecasts)
    errors = [f - a for f, a in zip(forecasts, actuals)]
    abs_errors = [abs(e) for e in errors]
    squared_errors = [e ** 2 for e in errors]

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(squared_errors) / n)
    bias = sum(errors) / n

    return {
        "mae": round(mae, 1),
        "rmse": round(rmse, 1),
        "bias": round(bias, 1),
        "n": n
    }

def calculate_accuracy_metrics(intervals: List[MatchedIntervalSchema]) -> AccuracyMetricsSchema:
    """
    Computes summary accuracy metrics strictly over valid matched intervals.
    Missing intervals are excluded and never treated as zero.
    """
    total = len(intervals)
    matched_pairs = [
        it for it in intervals
        if it.actualMw is not None and it.forecastMw is not None and it.errorMw is not None
    ]
    n = len(matched_pairs)

    missing_forecast = sum(1 for it in intervals if it.forecastMw is None)
    missing_actual = sum(1 for it in intervals if it.actualMw is None)

    if n == 0:
        return AccuracyMetricsSchema(
            maeMw=None,
            rmseMw=None,
            biasMw=None,
            p90AbsErrorMw=None,
            p50AbsErrorMw=None,
            matchedIntervals=0,
            totalIntervals=total,
            missingForecastIntervals=missing_forecast,
            missingActualIntervals=missing_actual,
            avgActualMw=None,
            avgForecastMw=None,
            overforecastCount=0,
            underforecastCount=0
        )

    errors = [it.errorMw for it in matched_pairs]
    abs_errors = sorted([abs(e) for e in errors])
    squared_errors = [e ** 2 for e in errors]

    actuals = [it.actualMw for it in matched_pairs]
    forecasts = [it.forecastMw for it in matched_pairs]

    mae = round(sum(abs_errors) / n, 1)
    rmse = round(math.sqrt(sum(squared_errors) / n), 1)
    bias = round(sum(errors) / n, 1)

    p90 = calculate_percentile(abs_errors, 0.90)
    p50 = calculate_percentile(abs_errors, 0.50)

    avg_act = round(sum(actuals) / n, 1)
    avg_fc = round(sum(forecasts) / n, 1)

    over_count = sum(1 for e in errors if e > 0)
    under_count = sum(1 for e in errors if e < 0)

    return AccuracyMetricsSchema(
        maeMw=mae,
        rmseMw=rmse,
        biasMw=bias,
        p90AbsErrorMw=p90,
        p50AbsErrorMw=p50,
        matchedIntervals=n,
        totalIntervals=total,
        missingForecastIntervals=missing_forecast,
        missingActualIntervals=missing_actual,
        avgActualMw=avg_act,
        avgForecastMw=avg_fc,
        overforecastCount=over_count,
        underforecastCount=under_count
    )
