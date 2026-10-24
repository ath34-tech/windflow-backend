from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import zoneinfo
from ..schemas import ForecastRecordSchema

LONDON_TZ = zoneinfo.ZoneInfo("Europe/London")
UTC_TZ = timezone.utc

DECISION_CUTOFF_CONFIGS = {
    "d1-0900": {"cutoffHour": 9, "label": "D-1 09:00 GMT (Morning Strategy)", "type": "day_ahead_fixed_time"},
    "d1-1200": {"cutoffHour": 12, "label": "D-1 12:00 GMT (Day-Ahead Auction)", "type": "day_ahead_fixed_time"},
    "d1-1400": {"cutoffHour": 14, "label": "D-1 14:00 GMT (Post-Auction Rebalance)", "type": "day_ahead_fixed_time"},
    "d1-1700": {"cutoffHour": 17, "label": "D-1 17:00 GMT (Evening Rebalance)", "type": "day_ahead_fixed_time"},
    "4h-ahead": {"hoursAhead": 4, "label": "Rolling 4h Before Delivery", "type": "hours_ahead"},
    "2h-ahead": {"hoursAhead": 2, "label": "Rolling 2h Before Delivery", "type": "hours_ahead"},
}

def calculate_cutoff_timestamp(
    delivery_start_iso: str,
    cutoff_id: str = "d1-1200",
    custom_cutoff_hour: Optional[int] = None
) -> str:
    """
    Computes canonical ISO 8601 UTC cutoff timestamp for a delivery interval.
    Cutoffs are defined in Europe/London timezone.
    """
    dt_utc = datetime.fromisoformat(delivery_start_iso.replace("Z", "+00:00")).astimezone(UTC_TZ)
    dt_london = dt_utc.astimezone(LONDON_TZ)

    config = DECISION_CUTOFF_CONFIGS.get(cutoff_id, DECISION_CUTOFF_CONFIGS["d1-1200"])
    cutoff_type = config.get("type", "day_ahead_fixed_time")

    if cutoff_type == "hours_ahead":
        hours = config.get("hoursAhead", 4)
        cutoff_dt = dt_utc - timedelta(hours=hours)
        return cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Day-ahead fixed time (D-1 at configured cutoff hour)
    cutoff_hour = custom_cutoff_hour if custom_cutoff_hour is not None else config.get("cutoffHour", 12)
    # Delivery date in London timezone
    delivery_date = dt_london.date()
    d1_date = delivery_date - timedelta(days=1)
    
    # D-1 at cutoff_hour in Europe/London
    d1_london_dt = datetime(d1_date.year, d1_date.month, d1_date.day, cutoff_hour, 0, 0, tzinfo=LONDON_TZ)
    d1_utc_dt = d1_london_dt.astimezone(UTC_TZ)
    return d1_utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def select_forecast_for_interval(
    publications: List[ForecastRecordSchema],
    cutoff_iso: str,
    mode: str = "decision_time"
) -> Tuple[Optional[ForecastRecordSchema], bool]:
    """
    Selects the eligible forecast publication for a single delivery interval.
    
    Returns:
        (selected_forecast, is_eligible_flag)
    """
    if not publications:
        return None, False

    sorted_pubs = sorted(publications, key=lambda x: x.publishTime)

    if mode == "decision_time":
        # Keep only publications with publishTime <= cutoff_iso
        eligible = [p for p in sorted_pubs if p.publishTime <= cutoff_iso]
        if not eligible:
            return None, False
        # Select the latest eligible publication
        return eligible[-1], True

    elif mode == "latest_retrospective":
        # Takes latest overall, but flags whether it complied with decision cutoff
        latest = sorted_pubs[-1]
        is_eligible = latest.publishTime <= cutoff_iso
        return latest, is_eligible

    # Default fallback
    eligible = [p for p in sorted_pubs if p.publishTime <= cutoff_iso]
    if eligible:
        return eligible[-1], True
    return None, False
