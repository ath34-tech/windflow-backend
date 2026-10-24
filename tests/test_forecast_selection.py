import pytest
from app.schemas import ForecastRecordSchema
from app.services.forecast_selection import calculate_cutoff_timestamp, select_forecast_for_interval

def test_selects_latest_forecast_at_or_before_cutoff():
    cutoff = "2026-01-14T12:00:00Z"
    pubs = [
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T08:00:00Z", generationMw=7000.0),
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T11:30:00Z", generationMw=7500.0),
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T14:00:00Z", generationMw=8000.0), # After cutoff
    ]

    selected, is_eligible = select_forecast_for_interval(pubs, cutoff, mode="decision_time")
    assert selected is not None
    assert selected.publishTime == "2026-01-14T11:30:00Z"
    assert selected.generationMw == 7500.0
    assert is_eligible is True

def test_excludes_forecast_published_after_cutoff():
    cutoff = "2026-01-14T12:00:00Z"
    pubs = [
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T12:00:01Z", generationMw=8000.0),
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T15:00:00Z", generationMw=8500.0),
    ]

    selected, is_eligible = select_forecast_for_interval(pubs, cutoff, mode="decision_time")
    assert selected is None
    assert is_eligible is False

def test_retrospective_mode_selects_latest_overall_with_eligibility_flag():
    cutoff = "2026-01-14T12:00:00Z"
    pubs = [
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T11:00:00Z", generationMw=7000.0),
        ForecastRecordSchema(startTime="2026-01-15T00:00:00Z", publishTime="2026-01-14T16:00:00Z", generationMw=8200.0), # Intraday revision
    ]

    selected, is_eligible = select_forecast_for_interval(pubs, cutoff, mode="latest_retrospective")
    assert selected is not None
    assert selected.publishTime == "2026-01-14T16:00:00Z"
    assert selected.generationMw == 8200.0
    assert is_eligible is False # Explicitly not decision-valid!

def test_calculate_cutoff_timestamp_london_timezone():
    # 15 Jan 2026 delivery date -> D-1 is 14 Jan 2026 at 12:00 GMT (UTC in Jan)
    cutoff = calculate_cutoff_timestamp("2026-01-15T08:00:00Z", cutoff_id="d1-1200")
    assert cutoff == "2026-01-14T12:00:00Z"

    # Custom cutoff hour: 09:00 GMT
    cutoff_9 = calculate_cutoff_timestamp("2026-01-15T08:00:00Z", custom_cutoff_hour=9)
    assert cutoff_9 == "2026-01-14T09:00:00Z"
