import pytest
import httpx
from app.clients.elexon import ElexonClient, ElexonAPIError
from app.services.normalization import normalize_fuelhh_list, normalize_windfor_list

@pytest.mark.asyncio
async def test_elexon_client_retries_and_parses(monkeypatch):
    """Verifies that ElexonClient handles responses and extracts data."""
    sample_fuelhh_response = {
        "data": [
            {
                "dataset": "FUELHH",
                "publishTime": "2026-01-16T00:00:00Z",
                "startTime": "2026-01-15T23:30:00Z",
                "settlementDate": "2026-01-15",
                "settlementPeriod": 48,
                "fuelType": "WIND",
                "generation": 7500
            },
            {
                "dataset": "FUELHH",
                "publishTime": "2026-01-16T00:00:00Z",
                "startTime": "2026-01-15T23:30:00Z",
                "settlementDate": "2026-01-15",
                "settlementPeriod": 48,
                "fuelType": "GAS",
                "generation": 12000
            }
        ]
    }

    class MockResponse:
        status_code = 200
        def json(self):
            return sample_fuelhh_response

    async def mock_get(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = ElexonClient(max_retries=1)
    wind_items = await client.fetch_actuals_fuelhh("2026-01-15", "2026-01-15")

    # Only WIND should be returned
    assert len(wind_items) == 1
    assert wind_items[0]["fuelType"] == "WIND"
    assert wind_items[0]["generation"] == 7500

    normalized = normalize_fuelhh_list(wind_items)
    assert len(normalized) == 1
    assert normalized[0].generationMw == 7500.0

@pytest.mark.asyncio
async def test_elexon_client_handles_empty_response(monkeypatch):
    class MockEmptyResponse:
        status_code = 200
        def json(self):
            return {"data": []}

    async def mock_get(*args, **kwargs):
        return MockEmptyResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = ElexonClient(max_retries=1)
    items = await client.fetch_forecasts_windfor("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
    assert items == []
    normalized = normalize_windfor_list(items)
    assert normalized == []

@pytest.mark.asyncio
async def test_elexon_client_raises_on_500_after_retries(monkeypatch):
    class Mock500Response:
        status_code = 500
        text = "Internal Server Error"

    async def mock_get(*args, **kwargs):
        return Mock500Response()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = ElexonClient(max_retries=2)
    with pytest.raises(ElexonAPIError):
        await client.fetch_actuals_fuelhh("2026-01-01", "2026-01-02")
