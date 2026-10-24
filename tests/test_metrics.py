import pytest
from app.schemas import MatchedIntervalSchema
from app.services.metrics import calculate_accuracy_metrics, compute_metrics_from_values

def test_hand_calculated_metric_example():
    """
    PRD & must.md explicit requirement:
    Forecasts: [110, 90] MW, Actuals: [100, 100] MW
    Errors: [10, -10] MW
    Expected: MAE = 10 MW, RMSE = 10 MW, Bias = 0 MW, n = 2
    """
    res = compute_metrics_from_values(forecasts=[110, 90], actuals=[100, 100])
    assert res["mae"] == 10.0
    assert res["rmse"] == 10.0
    assert res["bias"] == 0.0
    assert res["n"] == 2

def test_positive_bias_convention():
    """Positive bias means wind was over-forecasted (forecast > actual)."""
    res = compute_metrics_from_values(forecasts=[1100, 1200], actuals=[1000, 1000])
    assert res["bias"] == 150.0
    assert res["bias"] > 0
    assert res["mae"] == 150.0

def test_negative_bias_convention():
    """Negative bias means wind was under-forecasted (forecast < actual)."""
    res = compute_metrics_from_values(forecasts=[900, 850], actuals=[1000, 1000])
    assert res["bias"] == -125.0
    assert res["bias"] < 0
    assert res["mae"] == 125.0

def test_missing_data_excluded_from_metrics():
    """Missing actuals or forecasts are never converted to zero and are excluded from metrics."""
    intervals = [
        MatchedIntervalSchema(
            startTime="2026-01-15T00:00:00Z",
            settlementDate="2026-01-15",
            settlementPeriod=1,
            actualMw=1000.0,
            forecastMw=1100.0,
            errorMw=100.0,
            absErrorMw=100.0,
            squaredError=10000.0,
            status="Matched"
        ),
        MatchedIntervalSchema(
            startTime="2026-01-15T00:30:00Z",
            settlementDate="2026-01-15",
            settlementPeriod=2,
            actualMw=None,  # Missing actual!
            forecastMw=1200.0,
            errorMw=None,
            absErrorMw=None,
            squaredError=None,
            status="Actual unavailable"
        ),
        MatchedIntervalSchema(
            startTime="2026-01-15T01:00:00Z",
            settlementDate="2026-01-15",
            settlementPeriod=3,
            actualMw=800.0,
            forecastMw=None,  # Missing forecast!
            errorMw=None,
            absErrorMw=None,
            squaredError=None,
            status="No eligible forecast"
        )
    ]
    metrics = calculate_accuracy_metrics(intervals)
    assert metrics.matchedIntervals == 1
    assert metrics.totalIntervals == 3
    assert metrics.missingActualIntervals == 1
    assert metrics.missingForecastIntervals == 1
    assert metrics.maeMw == 100.0
    assert metrics.biasMw == 100.0

def test_empty_intervals_return_null_metrics():
    """Zero matched intervals returns None for metrics, never 0."""
    metrics = calculate_accuracy_metrics([])
    assert metrics.matchedIntervals == 0
    assert metrics.maeMw is None
    assert metrics.rmseMw is None
    assert metrics.biasMw is None
