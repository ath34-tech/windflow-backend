import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..clients.elexon import ElexonClient
from ..schemas import (
    ActualRecordSchema,
    AccuracyMetricsSchema,
    CutoffSensitivityItemSchema,
    DailyAccuracyItemSchema,
    ForecastHistoryItemSchema,
    ForecastHistoryResponseSchema,
    ForecastRecordSchema,
    MatchedIntervalSchema,
)
from .forecast_selection import DECISION_CUTOFF_CONFIGS, calculate_cutoff_timestamp
from .matching import match_intervals
from .metrics import calculate_accuracy_metrics
from .normalization import normalize_fuelhh_list, normalize_windfor_list

logger = logging.getLogger("windscope.data_loader")

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_FILE = CACHE_DIR / "jan2026_cache.json"

class DataLoader:
    """
    Manages in-memory storage, disk persistence, and live Elexon retrieval
    for national wind actuals (FUELHH) and forecasts (WINDFOR) across January 2026.
    """

    def __init__(self):
        self.actuals: List[ActualRecordSchema] = []
        self.forecasts: List[ForecastRecordSchema] = []
        self.is_loaded: bool = False
        self.is_loading: bool = False
        self.last_loaded_at: Optional[str] = None
        self.data_source: str = "Elexon BMRS API v1 (FUELHH & WINDFOR)"

    def get_available_dates(self) -> List[str]:
        """Returns all dates in January 2026 (2026-01-01 to 2026-01-31)."""
        return [f"2026-01-{d:02d}" for d in range(1, 32)]

    async def initialize(self, force_reload: bool = False) -> None:
        """Loads data from local cache or fetches from Elexon."""
        if self.is_loaded and not force_reload:
            return

        if self.is_loading:
            logger.info("Data loading already in progress...")
            return

        self.is_loading = True
        try:
            # 1. Attempt to load from disk cache first for instant cold start
            if not force_reload and CACHE_FILE.exists():
                try:
                    logger.info("Loading January 2026 data from disk cache: %s", CACHE_FILE)
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    
                    self.actuals = [ActualRecordSchema(**item) for item in cached.get("actuals", [])]
                    self.forecasts = [ForecastRecordSchema(**item) for item in cached.get("forecasts", [])]
                    self.last_loaded_at = cached.get("loadedAt", datetime.now(timezone.utc).isoformat())
                    self.is_loaded = True
                    logger.info("Loaded %d actuals and %d forecasts from cache.", len(self.actuals), len(self.forecasts))
                    return
                except Exception as e:
                    logger.warning("Failed to parse disk cache, fetching fresh from Elexon: %s", e)

            # 2. Fetch fresh from Elexon BMRS API
            logger.info("Fetching fresh January 2026 datasets from Elexon BMRS...")
            await self.fetch_and_cache_all()
        finally:
            self.is_loading = False

    async def fetch_and_cache_all(self) -> None:
        """Fetches all January 2026 FUELHH and WINDFOR data in bounded 7-day chunks."""
        client = ElexonClient()

        # 1. Actuals chunks (max 7 days per Elexon validation rule)
        fuel_chunks = [
            ("2026-01-01", "2026-01-07"),
            ("2026-01-08", "2026-01-14"),
            ("2026-01-15", "2026-01-21"),
            ("2026-01-22", "2026-01-28"),
            ("2026-01-29", "2026-01-31"),
        ]
        all_fuel_raw = []
        for d_from, d_to in fuel_chunks:
            try:
                raw = await client.fetch_actuals_fuelhh(d_from, d_to)
                all_fuel_raw.extend(raw)
            except Exception as e:
                logger.error("Error fetching FUELHH chunk %s-%s: %s", d_from, d_to, e)

        normalized_actuals = normalize_fuelhh_list(all_fuel_raw)

        # 2. Forecasts chunks (covers Dec 30 2025 to Jan 31 2026 publications)
        windfor_chunks = [
            ("2025-12-30T00:00:00Z", "2026-01-05T23:59:59Z"),
            ("2026-01-06T00:00:00Z", "2026-01-12T23:59:59Z"),
            ("2026-01-13T00:00:00Z", "2026-01-19T23:59:59Z"),
            ("2026-01-20T00:00:00Z", "2026-01-26T23:59:59Z"),
            ("2026-01-27T00:00:00Z", "2026-01-31T23:59:59Z"),
        ]
        all_windfor_raw = []
        for p_from, p_to in windfor_chunks:
            try:
                raw = await client.fetch_forecasts_windfor(p_from, p_to)
                all_windfor_raw.extend(raw)
            except Exception as e:
                logger.error("Error fetching WINDFOR chunk %s to %s: %s", p_from, p_to, e)

        normalized_forecasts = normalize_windfor_list(all_windfor_raw)

        self.actuals = normalized_actuals
        self.forecasts = normalized_forecasts
        self.last_loaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.is_loaded = True

        # Save to disk cache
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "loadedAt": self.last_loaded_at,
                    "actuals": [a.model_dump() for a in self.actuals],
                    "forecasts": [fc.model_dump() for fc in self.forecasts],
                }, f)
            logger.info("Successfully persisted January 2026 data to %s", CACHE_FILE)
        except Exception as e:
            logger.error("Failed to write disk cache: %s", e)

    def get_data_for_scope(
        self,
        date_str: str,
        scope: str = "day",
        cutoff_id: str = "d1-1200",
        custom_cutoff_hour: Optional[int] = None,
        mode: str = "decision_time"
    ) -> Tuple[List[MatchedIntervalSchema], AccuracyMetricsSchema]:
        """
        Retrieves and matches intervals for selected date and scope ('day', 'week', 'month').
        """
        if scope == "day":
            target_actuals = [a for a in self.actuals if a.settlementDate == date_str]
        elif scope == "week":
            try:
                day_num = int(date_str.split("-")[2])
            except Exception:
                day_num = 15
            end_day = min(31, day_num + 6)
            week_dates = {f"2026-01-{d:02d}" for d in range(day_num, end_day + 1)}
            target_actuals = [a for a in self.actuals if a.settlementDate in week_dates]
        elif scope == "month":
            target_actuals = self.actuals
        else:
            target_actuals = [a for a in self.actuals if a.settlementDate == date_str]

        intervals = match_intervals(
            actuals=target_actuals,
            all_forecasts=self.forecasts,
            cutoff_id=cutoff_id,
            custom_cutoff_hour=custom_cutoff_hour,
            mode=mode
        )
        metrics = calculate_accuracy_metrics(intervals)
        return intervals, metrics

    def get_daily_trends(
        self,
        cutoff_id: str = "d1-1200",
        custom_cutoff_hour: Optional[int] = None,
        mode: str = "decision_time"
    ) -> List[DailyAccuracyItemSchema]:
        """Calculates daily accuracy metrics for each day in January 2026."""
        dates = self.get_available_dates()
        trends: List[DailyAccuracyItemSchema] = []

        for d in dates:
            intervals, metrics = self.get_data_for_scope(
                date_str=d,
                scope="day",
                cutoff_id=cutoff_id,
                custom_cutoff_hour=custom_cutoff_hour,
                mode=mode
            )
            trends.append(
                DailyAccuracyItemSchema(
                    date=d,
                    maeMw=metrics.maeMw,
                    rmseMw=metrics.rmseMw,
                    biasMw=metrics.biasMw,
                    matchedIntervals=metrics.matchedIntervals,
                    avgActualMw=metrics.avgActualMw,
                    avgForecastMw=metrics.avgForecastMw
                )
            )
        return trends

    def get_cutoff_sensitivity(
        self,
        date_str: str,
        scope: str = "day",
        current_cutoff_id: str = "d1-1200",
        custom_cutoff_hour: Optional[int] = None
    ) -> List[CutoffSensitivityItemSchema]:
        """Evaluates MAE and bias across candidate cutoffs from 06:00 to 18:00 on D-1."""
        candidate_hours = [6, 8, 9, 10, 12, 14, 16, 17, 18]
        results: List[CutoffSensitivityItemSchema] = []

        curr_hour = custom_cutoff_hour
        if curr_hour is None:
            curr_hour = DECISION_CUTOFF_CONFIGS.get(current_cutoff_id, {}).get("cutoffHour", 12)

        for h in candidate_hours:
            cutoff_key = f"d1-{h:02d}00"
            intervals, metrics = self.get_data_for_scope(
                date_str=date_str,
                scope=scope,
                cutoff_id=cutoff_key,
                custom_cutoff_hour=h,
                mode="decision_time"
            )
            results.append(
                CutoffSensitivityItemSchema(
                    cutoffHour=h,
                    cutoffLabel=f"D-1 {h:02d}:00 GMT",
                    maeMw=metrics.maeMw,
                    biasMw=metrics.biasMw,
                    matchedIntervals=metrics.matchedIntervals,
                    isCurrent=(h == curr_hour)
                )
            )
        return results

    def get_forecast_history_for_interval(
        self,
        start_time: str,
        cutoff_id: str = "d1-1200",
        custom_cutoff_hour: Optional[int] = None
    ) -> Optional[ForecastHistoryResponseSchema]:
        """Returns all forecast publications for a single delivery interval."""
        actual = next((a for a in self.actuals if a.startTime == start_time), None)
        if not actual:
            return None

        pubs = [fc for fc in self.forecasts if fc.startTime == start_time]
        pubs_sorted = sorted(pubs, key=lambda x: x.publishTime)

        cutoff_iso = calculate_cutoff_timestamp(start_time, cutoff_id, custom_cutoff_hour)
        config = DECISION_CUTOFF_CONFIGS.get(cutoff_id, DECISION_CUTOFF_CONFIGS["d1-1200"])
        cutoff_label = config.get("label", cutoff_id)

        dt_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))

        history_items: List[ForecastHistoryItemSchema] = []
        selected_fc: Optional[ForecastRecordSchema] = None

        for p in pubs_sorted:
            dt_pub = datetime.fromisoformat(p.publishTime.replace("Z", "+00:00"))
            lead_time_hours = round((dt_start - dt_pub).total_seconds() / 3600.0, 1)
            is_elig = p.publishTime <= cutoff_iso
            err = round(p.generationMw - actual.generationMw, 1) if actual.generationMw is not None else None

            history_items.append(
                ForecastHistoryItemSchema(
                    publishTime=p.publishTime,
                    generationMw=p.generationMw,
                    isEligible=is_elig,
                    leadTimeHours=lead_time_hours,
                    errorMw=err
                )
            )
            if is_elig:
                selected_fc = p

        return ForecastHistoryResponseSchema(
            startTime=start_time,
            settlementDate=actual.settlementDate,
            settlementPeriod=actual.settlementPeriod,
            actualMw=actual.generationMw,
            selectedForecast=selected_fc,
            selectedCutoff=cutoff_label,
            publications=history_items
        )

# Global singleton data loader
data_loader = DataLoader()
