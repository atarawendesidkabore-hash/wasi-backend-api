"""Pydantic schemas for forecast API responses."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, computed_field

from src.utils.periods import quarter_label


class ForecastPeriod(BaseModel):
    period_offset: int
    period_date: Optional[date] = None
    forecast_value: float
    lower_1sigma: float
    upper_1sigma: float
    lower_2sigma: float
    upper_2sigma: float

    @computed_field
    @property
    def quarter(self) -> Optional[str]:
        """Quarter label derived from period_date, e.g. 'Q3-2026'."""
        return quarter_label(self.period_date) if self.period_date else None


class ForecastResponse(BaseModel):
    target_type: str
    target_code: str
    horizon: int
    last_actual_date: Optional[str] = None
    last_actual_value: Optional[float] = None
    data_points_used: int
    methods_used: list[str]
    ensemble_weights: dict[str, float]
    residual_std: Optional[float] = None
    confidence_score: float
    periods: list[ForecastPeriod]
    method_forecasts: dict[str, list[float]]
    calculated_at: Optional[datetime] = None
    error: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ForecastSummaryItem(BaseModel):
    country_code: str
    country_name: str
    current_value: Optional[float] = None
    forecast_3m: Optional[float] = None
    forecast_6m: Optional[float] = None
    forecast_12m: Optional[float] = None
    trend: str = "flat"
    confidence: float = 0.0
    data_quality: str = "grey"


class ForecastSummaryResponse(BaseModel):
    composite_forecast: Optional[ForecastResponse] = None
    countries: list[ForecastSummaryItem]
    total_countries: int
    generated_at: datetime


class ForecastRefreshResponse(BaseModel):
    status: str
    country_forecasts_computed: int
    composite_computed: bool
    commodities_computed: int
    macro_computed: int
    duration_seconds: float
    computed_at: datetime
