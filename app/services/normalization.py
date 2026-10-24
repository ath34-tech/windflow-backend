from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import zoneinfo
from ..schemas import ActualRecordSchema, ForecastRecordSchema

LONDON_TZ = zoneinfo.ZoneInfo("Europe/London")
UTC_TZ = timezone.utc

def parse_iso_utc(ts_str: Optional[str]) -> Optional[str]:
    """Ensures timestamp is a canonical ISO 8601 UTC string ending in 'Z'."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC_TZ)
        else:
            dt = dt.astimezone(UTC_TZ)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ts_str

def to_london_datetime(ts_str: str) -> datetime:
    """Converts a UTC ISO timestamp to a Europe/London datetime."""
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(LONDON_TZ)

def normalize_fuelhh_record(raw: Dict[str, Any]) -> Optional[ActualRecordSchema]:
    """Validates and converts a raw FUELHH item into an ActualRecordSchema."""
    start_time = parse_iso_utc(raw.get("startTime"))
    if not start_time:
        return None

    fuel_type = str(raw.get("fuelType", "")).upper()
    if fuel_type != "WIND":
        return None

    raw_gen = raw.get("generation")
    generation_mw: Optional[float] = None
    if raw_gen is not None:
        try:
            generation_mw = float(raw_gen)
        except (ValueError, TypeError):
            generation_mw = None

    settlement_date = str(raw.get("settlementDate", ""))
    if not settlement_date and start_time:
        settlement_date = start_time[:10]

    period = raw.get("settlementPeriod")
    try:
        settlement_period = int(period) if period is not None else 1
    except (ValueError, TypeError):
        settlement_period = 1

    publish_time = parse_iso_utc(raw.get("publishTime"))

    return ActualRecordSchema(
        startTime=start_time,
        generationMw=generation_mw,
        fuelType="WIND",
        settlementDate=settlement_date,
        settlementPeriod=settlement_period,
        publishTime=publish_time
    )

def normalize_fuelhh_list(raw_list: List[Dict[str, Any]]) -> List[ActualRecordSchema]:
    """Deduplicates and sorts actual wind records by startTime."""
    record_map: Dict[str, ActualRecordSchema] = {}
    for item in raw_list:
        rec = normalize_fuelhh_record(item)
        if not rec:
            continue
        # Deduplicate on startTime; if already present, prefer one with later publishTime
        if rec.startTime not in record_map:
            record_map[rec.startTime] = rec
        else:
            existing = record_map[rec.startTime]
            if rec.publishTime and existing.publishTime and rec.publishTime > existing.publishTime:
                record_map[rec.startTime] = rec

    records = list(record_map.values())
    records.sort(key=lambda x: x.startTime)
    return records

def normalize_windfor_record(raw: Dict[str, Any]) -> Optional[ForecastRecordSchema]:
    """Validates and converts a raw WINDFOR item into a ForecastRecordSchema."""
    start_time = parse_iso_utc(raw.get("startTime"))
    publish_time = parse_iso_utc(raw.get("publishTime"))
    if not start_time or not publish_time:
        return None

    raw_gen = raw.get("generation")
    if raw_gen is None:
        return None
    try:
        generation_mw = float(raw_gen)
    except (ValueError, TypeError):
        return None

    return ForecastRecordSchema(
        startTime=start_time,
        publishTime=publish_time,
        generationMw=generation_mw
    )

def normalize_windfor_list(raw_list: List[Dict[str, Any]]) -> List[ForecastRecordSchema]:
    """Deduplicates on exact (startTime, publishTime) pair and preserves distinct publications."""
    seen = set()
    records: List[ForecastRecordSchema] = []
    for item in raw_list:
        rec = normalize_windfor_record(item)
        if not rec:
            continue
        key = (rec.startTime, rec.publishTime)
        if key not in seen:
            seen.add(key)
            records.append(rec)

    records.sort(key=lambda x: (x.startTime, x.publishTime))
    return records
