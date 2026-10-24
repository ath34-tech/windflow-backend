from typing import Dict, List, Optional
from ..schemas import ActualRecordSchema, ForecastRecordSchema, MatchedIntervalSchema
from .forecast_selection import calculate_cutoff_timestamp, select_forecast_for_interval

def match_intervals(
    actuals: List[ActualRecordSchema],
    all_forecasts: List[ForecastRecordSchema],
    cutoff_id: str = "d1-1200",
    custom_cutoff_hour: Optional[int] = None,
    mode: str = "decision_time"
) -> List[MatchedIntervalSchema]:
    """
    Joins actual generation records with forecast publications strictly by delivery startTime.
    Never collapses the raw forecast history.
    """
    # Group forecasts by delivery interval startTime
    forecast_map: Dict[str, List[ForecastRecordSchema]] = {}
    for fc in all_forecasts:
        forecast_map.setdefault(fc.startTime, []).append(fc)

    matched: List[MatchedIntervalSchema] = []

    for actual in actuals:
        start_time = actual.startTime
        pubs = forecast_map.get(start_time, [])
        pubs_sorted = sorted(pubs, key=lambda x: x.publishTime)

        cutoff_iso = calculate_cutoff_timestamp(start_time, cutoff_id, custom_cutoff_hour)
        selected_fc, is_eligible = select_forecast_for_interval(pubs_sorted, cutoff_iso, mode)

        actual_mw = actual.generationMw
        fc_mw = selected_fc.generationMw if selected_fc else None

        if actual_mw is not None and fc_mw is not None:
            status = "Matched"
            err = round(fc_mw - actual_mw, 1)
            abs_err = round(abs(err), 1)
            sq_err = round((fc_mw - actual_mw) ** 2, 1)
        elif fc_mw is None:
            status = "No eligible forecast"
            err = None
            abs_err = None
            sq_err = None
        else:
            status = "Actual unavailable"
            err = None
            abs_err = None
            sq_err = None

        matched.append(
            MatchedIntervalSchema(
                startTime=start_time,
                settlementDate=actual.settlementDate,
                settlementPeriod=actual.settlementPeriod,
                actualMw=actual_mw,
                forecastMw=fc_mw,
                forecastPublishTime=selected_fc.publishTime if selected_fc else None,
                errorMw=err,
                absErrorMw=abs_err,
                squaredError=sq_err,
                status=status,
                forecastVersionCount=len(pubs_sorted),
                forecastVersions=pubs_sorted,
                selectedForecast=selected_fc,
                isEligibleForecast=is_eligible
            )
        )

    matched.sort(key=lambda x: x.startTime)
    return matched
