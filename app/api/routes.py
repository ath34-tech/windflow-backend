import asyncio
from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from ..schemas import (
    AccuracyMetricsSchema,
    CutoffSensitivityItemSchema,
    DailyAccuracyItemSchema,
    ForecastHistoryResponseSchema,
    HealthResponseSchema,
    MatchedIntervalSchema,
    OverviewResponseSchema,
)
from ..services.data_loader import data_loader
from ..services.metrics import calculate_accuracy_metrics

logger = logging.getLogger("windscope.api")
router = APIRouter(prefix="/api", tags=["windscope"])

def validate_january_date(date_str: str) -> None:
    """Rejects dates outside January 1–31, 2026."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if dt.year != 2026 or dt.month != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid delivery date '{date_str}'. WindScope is strictly scoped to January 2026 (2026-01-01 to 2026-01-31)."
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{date_str}'. Expected YYYY-MM-DD."
        )

@router.get("/health", response_model=HealthResponseSchema)
async def get_health():
    """Returns service health, readiness, and dataset verification status."""
    return HealthResponseSchema(
        status="ok",
        version="1.0.0",
        elexonConnected=True,
        dataPreloaded=data_loader.is_loaded,
        actualsCount=len(data_loader.actuals),
        forecastsCount=len(data_loader.forecasts),
        loadedAt=data_loader.last_loaded_at
    )

@router.get("/dates", response_model=List[str])
async def get_available_dates():
    """Returns supported January 2026 delivery dates."""
    return data_loader.get_available_dates()

@router.get("/overview", response_model=OverviewResponseSchema)
async def get_overview(
    date: str = Query("2026-01-15", description="Delivery date (YYYY-MM-DD)"),
    scope: str = Query("day", pattern="^(day|week|month)$", description="Scope: day, week, month"),
    cutoff: str = Query("d1-1200", description="Cutoff ID e.g. d1-1200, d1-0900, d1-1700, 4h-ahead"),
    custom_cutoff_hour: Optional[int] = Query(None, ge=0, le=23, description="Custom cutoff hour on D-1 (0-23)"),
    mode: str = Query("decision_time", pattern="^(decision_time|latest_retrospective)$", description="Forecast mode")
):
    """
    Main overview payload providing intervals, KPIs, metrics, and daily trends
    matching the frontend's primary dashboard views.
    """
    if scope != "month":
        validate_january_date(date)

    if not data_loader.is_loaded:
        await data_loader.initialize()

    intervals, metrics = data_loader.get_data_for_scope(
        date_str=date,
        scope=scope,
        cutoff_id=cutoff,
        custom_cutoff_hour=custom_cutoff_hour,
        mode=mode
    )

    daily_trends = data_loader.get_daily_trends(
        cutoff_id=cutoff,
        custom_cutoff_hour=custom_cutoff_hour,
        mode=mode
    )

    return OverviewResponseSchema(
        selectedDate=date,
        scope=scope,
        cutoffId=cutoff,
        forecastMode=mode,
        intervals=intervals,
        metrics=metrics,
        dailyTrends=daily_trends,
        lastDataFetch=data_loader.last_loaded_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        dataSource="Elexon BMRS (FUELHH & WINDFOR)"
    )

@router.get("/intervals")
async def get_intervals(
    date: str = Query("2026-01-15", description="Delivery date (YYYY-MM-DD)"),
    scope: str = Query("day", pattern="^(day|week|month)$"),
    cutoff: str = Query("d1-1200"),
    custom_cutoff_hour: Optional[int] = Query(None, ge=0, le=23),
    mode: str = Query("decision_time", pattern="^(decision_time|latest_retrospective)$"),
    time_of_day: str = Query("all", description="all, peak, offpeak, morning_ramp, evening_peak"),
    wind_band: str = Query("all", description="all, low, medium, high"),
    day_type: str = Query("all", description="all, weekday, weekend"),
    error_direction: str = Query("all", description="all, over, under"),
    min_error_mw: float = Query(0.0, ge=0.0),
    status_filter: str = Query("all", description="all, matched, missing")
):
    """Returns filtered matched intervals and recomputed subset accuracy metrics."""
    if scope != "month":
        validate_january_date(date)

    if not data_loader.is_loaded:
        await data_loader.initialize()

    intervals, _ = data_loader.get_data_for_scope(
        date_str=date,
        scope=scope,
        cutoff_id=cutoff,
        custom_cutoff_hour=custom_cutoff_hour,
        mode=mode
    )

    # Apply multi-dimensional filters
    filtered: List[MatchedIntervalSchema] = []
    for it in intervals:
        # 1. Time of day
        sp = it.settlementPeriod
        if time_of_day == "peak" and not (15 <= sp <= 38):
            continue
        elif time_of_day == "offpeak" and (15 <= sp <= 38):
            continue
        elif time_of_day == "morning_ramp" and not (11 <= sp <= 18):
            continue
        elif time_of_day == "evening_peak" and not (33 <= sp <= 40):
            continue

        # 2. Wind band
        act = it.actualMw
        if wind_band == "low" and not (act is not None and act < 6000):
            continue
        elif wind_band == "medium" and not (act is not None and 6000 <= act <= 12000):
            continue
        elif wind_band == "high" and not (act is not None and act > 12000):
            continue

        # 3. Day type
        try:
            day_of_week = datetime.strptime(it.settlementDate, "%Y-%m-%d").weekday()
            is_weekend = day_of_week >= 5
            if day_type == "weekday" and is_weekend:
                continue
            elif day_type == "weekend" and not is_weekend:
                continue
        except Exception:
            pass

        # 4. Error direction
        err = it.errorMw
        if error_direction == "over" and not (err is not None and err > 0):
            continue
        elif error_direction == "under" and not (err is not None and err < 0):
            continue

        # 5. Min error threshold
        abs_err = it.absErrorMw
        if min_error_mw > 0 and not (abs_err is not None and abs_err >= min_error_mw):
            continue

        # 6. Status filter
        if status_filter == "matched" and it.status != "Matched":
            continue
        elif status_filter == "missing" and it.status == "Matched":
            continue

        filtered.append(it)

    metrics = calculate_accuracy_metrics(filtered)
    return {"intervals": filtered, "metrics": metrics}

@router.get("/metrics", response_model=AccuracyMetricsSchema)
async def get_metrics(
    date: str = Query("2026-01-15"),
    scope: str = Query("day", pattern="^(day|week|month)$"),
    cutoff: str = Query("d1-1200"),
    custom_cutoff_hour: Optional[int] = Query(None, ge=0, le=23),
    mode: str = Query("decision_time", pattern="^(decision_time|latest_retrospective)$")
):
    """Returns standalone accuracy metrics strictly over matched pairs."""
    if scope != "month":
        validate_january_date(date)

    if not data_loader.is_loaded:
        await data_loader.initialize()

    _, metrics = data_loader.get_data_for_scope(
        date_str=date,
        scope=scope,
        cutoff_id=cutoff,
        custom_cutoff_hour=custom_cutoff_hour,
        mode=mode
    )
    return metrics

@router.get("/cutoff-sensitivity", response_model=List[CutoffSensitivityItemSchema])
async def get_cutoff_sensitivity(
    date: str = Query("2026-01-15"),
    scope: str = Query("day", pattern="^(day|week|month)$"),
    current_cutoff: str = Query("d1-1200"),
    custom_cutoff_hour: Optional[int] = Query(None, ge=0, le=23)
):
    """Evaluates MAE and bias across candidate cutoffs from 06:00 to 18:00 on D-1."""
    if scope != "month":
        validate_january_date(date)

    if not data_loader.is_loaded:
        await data_loader.initialize()

    return data_loader.get_cutoff_sensitivity(
        date_str=date,
        scope=scope,
        current_cutoff_id=current_cutoff,
        custom_cutoff_hour=custom_cutoff_hour
    )

@router.get("/intervals/{start_time}/forecast-history", response_model=ForecastHistoryResponseSchema)
async def get_forecast_history(
    start_time: str,
    cutoff: str = Query("d1-1200"),
    custom_cutoff_hour: Optional[int] = Query(None, ge=0, le=23)
):
    """Returns all forecast publications and cutoff eligibility for a single interval."""
    if not data_loader.is_loaded:
        await data_loader.initialize()

    history = data_loader.get_forecast_history_for_interval(
        start_time=start_time,
        cutoff_id=cutoff,
        custom_cutoff_hour=custom_cutoff_hour
    )
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery interval with startTime '{start_time}' not found in January 2026."
        )
    return history

@router.post("/refresh")
async def trigger_refresh():
    """Triggers a live reload from Elexon BMRS API and updates the local cache."""
    await data_loader.fetch_and_cache_all()
    return {
        "status": "refreshed",
        "loadedAt": data_loader.last_loaded_at,
        "actualsCount": len(data_loader.actuals),
        "forecastsCount": len(data_loader.forecasts)
    }
