import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import ActualRecordSchema, ForecastRecordSchema
from app.services.data_loader import data_loader

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_dummy_data():
    """Populates data_loader with deterministic dummy data for route testing."""
    data_loader.actuals = [
        ActualRecordSchema(
            startTime="2026-01-15T12:00:00Z",
            generationMw=8000.0,
            settlementDate="2026-01-15",
            settlementPeriod=25,
            fuelType="WIND"
        ),
        ActualRecordSchema(
            startTime="2026-01-15T12:30:00Z",
            generationMw=8200.0,
            settlementDate="2026-01-15",
            settlementPeriod=26,
            fuelType="WIND"
        )
    ]
    data_loader.forecasts = [
        ForecastRecordSchema(
            startTime="2026-01-15T12:00:00Z",
            publishTime="2026-01-14T11:00:00Z",
            generationMw=8500.0
        ),
        ForecastRecordSchema(
            startTime="2026-01-15T12:30:00Z",
            publishTime="2026-01-14T11:00:00Z",
            generationMw=8100.0
        )
    ]
    data_loader.is_loaded = True

def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"
    assert data["dataPreloaded"] is True

def test_dates_endpoint():
    res = client.get("/api/dates")
    assert res.status_code == 200
    dates = res.json()
    assert len(dates) == 31
    assert "2026-01-01" in dates
    assert "2026-01-31" in dates

def test_overview_endpoint():
    res = client.get("/api/overview?date=2026-01-15&scope=day&cutoff=d1-1200&mode=decision_time")
    assert res.status_code == 200
    data = res.json()
    assert data["selectedDate"] == "2026-01-15"
    assert len(data["intervals"]) == 2
    assert data["metrics"]["matchedIntervals"] == 2
    # Errors: [500, -100] -> MAE = 300, Bias = 200
    assert data["metrics"]["maeMw"] == 300.0
    assert data["metrics"]["biasMw"] == 200.0

def test_rejects_dates_outside_january_2026():
    # February 2026 -> 400 Bad Request
    res = client.get("/api/overview?date=2026-02-01&scope=day")
    assert res.status_code == 400
    assert "strictly scoped to January 2026" in res.json()["detail"]

    # Invalid date string -> 400 Bad Request
    res2 = client.get("/api/overview?date=invalid-date&scope=day")
    assert res2.status_code == 400

def test_cutoff_sensitivity_endpoint():
    res = client.get("/api/cutoff-sensitivity?date=2026-01-15&scope=day")
    assert res.status_code == 200
    items = res.json()
    assert len(items) > 0
    assert any(i["cutoffHour"] == 12 for i in items)

def test_forecast_history_endpoint():
    res = client.get("/api/intervals/2026-01-15T12:00:00Z/forecast-history?cutoff=d1-1200")
    assert res.status_code == 200
    data = res.json()
    assert data["startTime"] == "2026-01-15T12:00:00Z"
    assert len(data["publications"]) == 1
    assert data["publications"][0]["isEligible"] is True
