import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx
from ..config import settings

logger = logging.getLogger("windscope.elexon")

class ElexonAPIError(Exception):
    """Raised when Elexon BMRS API returns a non-transient error or invalid format."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

class ElexonClient:
    """Asynchronous client for Elexon BMRS Insights API v1."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0, max_retries: int = 3):
        self.base_url = (base_url or settings.ELEXON_API_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    async def _get_with_retry(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Executes GET request with bounded exponential backoff for 429 and 5xx."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        params_with_format = dict(params)
        params_with_format["format"] = "json"

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.debug("Requesting Elexon URL: %s with params %s (attempt %d/%d)", url, params_with_format, attempt, self.max_retries)
                    response = await client.get(url, params=params_with_format)

                    if response.status_code == 200:
                        try:
                            return response.json()
                        except Exception as e:
                            raise ElexonAPIError(f"Malformed JSON response from Elexon: {str(e)}")

                    # Retry on 429 Rate Limit or 5xx Server Error
                    if response.status_code in (429, 500, 502, 503, 504):
                        logger.warning("Elexon responded with status %d on attempt %d. Retrying...", response.status_code, attempt)
                        if attempt < self.max_retries:
                            backoff = 1.0 * (2 ** (attempt - 1))
                            await asyncio.sleep(backoff)
                            continue

                    # Non-retryable client error
                    error_msg = f"Elexon API error {response.status_code}: {response.text[:250]}"
                    logger.error(error_msg)
                    raise ElexonAPIError(error_msg, status_code=response.status_code)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                logger.warning("Network/Timeout error calling Elexon on attempt %d: %s", attempt, str(exc))
                if attempt < self.max_retries:
                    backoff = 1.0 * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)
                    continue

        raise ElexonAPIError(f"Failed after {self.max_retries} attempts: {str(last_error)}")

    async def fetch_actuals_fuelhh(self, settlement_date_from: str, settlement_date_to: str) -> List[Dict[str, Any]]:
        """
        Retrieves actual generation records by fuel type (FUELHH).
        Filters strictly to fuelType = WIND.
        """
        params = {
            "settlementDateFrom": settlement_date_from,
            "settlementDateTo": settlement_date_to,
        }
        data = await self._get_with_retry("datasets/FUELHH", params)
        raw_items = data.get("data", [])
        
        # Filter for WIND fuelType
        wind_records = [
            item for item in raw_items
            if str(item.get("fuelType", "")).upper() == "WIND"
        ]
        logger.info("Retrieved %d FUELHH wind records for %s to %s", len(wind_records), settlement_date_from, settlement_date_to)
        return wind_records

    async def fetch_forecasts_windfor(self, publish_datetime_from: str, publish_datetime_to: str) -> List[Dict[str, Any]]:
        """
        Retrieves wind forecast publication stream (WINDFOR).
        Retains all publications within the publish window.
        """
        params = {
            "publishDateTimeFrom": publish_datetime_from,
            "publishDateTimeTo": publish_datetime_to,
        }
        data = await self._get_with_retry("datasets/WINDFOR", params)
        records = data.get("data", [])
        logger.info("Retrieved %d WINDFOR records published between %s and %s", len(records), publish_datetime_from, publish_datetime_to)
        return records
