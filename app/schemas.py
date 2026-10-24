from typing import List, Optional, Literal
from pydantic import BaseModel, Field

ForecastSelectionMode = Literal["decision_time", "latest_retrospective"]
AnalysisScope = Literal["day", "week", "month"]
IntervalStatus = Literal["Matched", "No eligible forecast", "Actual unavailable", "Unmatched"]

class ActualRecordSchema(BaseModel):
    startTime: str
    generationMw: Optional[float] = None
    fuelType: str = "WIND"
    settlementDate: str
    settlementPeriod: int
    publishTime: Optional[str] = None

class ForecastRecordSchema(BaseModel):
    startTime: str
    publishTime: str
    generationMw: float

class MatchedIntervalSchema(BaseModel):
    startTime: str
    settlementDate: str
    settlementPeriod: int
    actualMw: Optional[float] = None
    forecastMw: Optional[float] = None
    forecastPublishTime: Optional[str] = None
    errorMw: Optional[float] = None
    absErrorMw: Optional[float] = None
    squaredError: Optional[float] = None
    status: str
    forecastVersionCount: int = 0
    forecastVersions: List[ForecastRecordSchema] = []
    selectedForecast: Optional[ForecastRecordSchema] = None
    isEligibleForecast: bool = True

class AccuracyMetricsSchema(BaseModel):
    maeMw: Optional[float] = None
    rmseMw: Optional[float] = None
    biasMw: Optional[float] = None
    p90AbsErrorMw: Optional[float] = None
    p50AbsErrorMw: Optional[float] = None
    matchedIntervals: int = 0
    totalIntervals: int = 0
    missingForecastIntervals: int = 0
    missingActualIntervals: int = 0
    avgActualMw: Optional[float] = None
    avgForecastMw: Optional[float] = None
    overforecastCount: int = 0
    underforecastCount: int = 0

class DailyAccuracyItemSchema(BaseModel):
    date: str
    maeMw: Optional[float] = None
    rmseMw: Optional[float] = None
    biasMw: Optional[float] = None
    matchedIntervals: int = 0
    avgActualMw: Optional[float] = None
    avgForecastMw: Optional[float] = None

class CutoffSensitivityItemSchema(BaseModel):
    cutoffHour: int
    cutoffLabel: str
    maeMw: Optional[float] = None
    biasMw: Optional[float] = None
    matchedIntervals: int = 0
    isCurrent: bool = False

class ForecastHistoryItemSchema(BaseModel):
    publishTime: str
    generationMw: float
    isEligible: bool
    leadTimeHours: float
    errorMw: Optional[float] = None

class ForecastHistoryResponseSchema(BaseModel):
    startTime: str
    settlementDate: str
    settlementPeriod: int
    actualMw: Optional[float] = None
    selectedForecast: Optional[ForecastRecordSchema] = None
    selectedCutoff: str
    publications: List[ForecastHistoryItemSchema] = []

class OverviewResponseSchema(BaseModel):
    selectedDate: str
    scope: str
    cutoffId: str
    forecastMode: str
    intervals: List[MatchedIntervalSchema]
    metrics: AccuracyMetricsSchema
    dailyTrends: List[DailyAccuracyItemSchema] = []
    lastDataFetch: str
    dataSource: str = "Elexon BMRS (FUELHH & WINDFOR)"

class HealthResponseSchema(BaseModel):
    status: str
    version: str = "1.0.0"
    elexonConnected: bool
    dataPreloaded: bool
    actualsCount: int
    forecastsCount: int
    loadedAt: Optional[str] = None
