import pytest
from app.schemas import ActualRecordSchema, ForecastRecordSchema
from app.services.matching import match_intervals

def test_matching_performed_by_start_time():
    actuals = [
        ActualRecordSchema(
            startTime="2026-01-15T10:00:00Z",
            generationMw=5000.0,
            settlementDate="2026-01-15",
            settlementPeriod=21
        ),
        ActualRecordSchema(
            startTime="2026-01-15T10:30:00Z",
            generationMw=5500.0,
            settlementDate="2026-01-15",
            settlementPeriod=22
        )
    ]
    forecasts = [
        ForecastRecordSchema(
            startTime="2026-01-15T10:00:00Z",
            publishTime="2026-01-14T11:00:00Z",
            generationMw=5200.0
        ),
        ForecastRecordSchema(
            startTime="2026-01-15T10:30:00Z",
            publishTime="2026-01-14T11:00:00Z",
            generationMw=5300.0
        )
    ]

    matched = match_intervals(actuals, forecasts, cutoff_id="d1-1200")
    assert len(matched) == 2
    assert matched[0].startTime == "2026-01-15T10:00:00Z"
    assert matched[0].actualMw == 5000.0
    assert matched[0].forecastMw == 5200.0
    assert matched[0].errorMw == 200.0  # 5200 - 5000 = +200 MW (overforecast)

    assert matched[1].startTime == "2026-01-15T10:30:00Z"
    assert matched[1].actualMw == 5500.0
    assert matched[1].forecastMw == 5300.0
    assert matched[1].errorMw == -200.0 # 5300 - 5500 = -200 MW (underforecast)

def test_retains_multiple_publications():
    actuals = [
        ActualRecordSchema(
            startTime="2026-01-15T12:00:00Z",
            generationMw=6000.0,
            settlementDate="2026-01-15",
            settlementPeriod=25
        )
    ]
    forecasts = [
        ForecastRecordSchema(startTime="2026-01-15T12:00:00Z", publishTime="2026-01-13T12:00:00Z", generationMw=5000.0),
        ForecastRecordSchema(startTime="2026-01-15T12:00:00Z", publishTime="2026-01-14T09:00:00Z", generationMw=5800.0),
        ForecastRecordSchema(startTime="2026-01-15T12:00:00Z", publishTime="2026-01-14T11:30:00Z", generationMw=6100.0),
        ForecastRecordSchema(startTime="2026-01-15T12:00:00Z", publishTime="2026-01-15T06:00:00Z", generationMw=6300.0), # Intraday
    ]

    matched = match_intervals(actuals, forecasts, cutoff_id="d1-1200")
    assert len(matched) == 1
    assert matched[0].forecastVersionCount == 4
    assert len(matched[0].forecastVersions) == 4
    # Cutoff is D-1 12:00, so latest eligible is 11:30 (6100 MW)
    assert matched[0].forecastMw == 6100.0
    assert matched[0].errorMw == 100.0
