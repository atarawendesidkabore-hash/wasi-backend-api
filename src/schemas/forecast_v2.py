"""
Pydantic schemas for Forecast v4 API responses.

Extends v3 schemas with fan chart, regime info, multivariate adjustment,
backtesting, scenario analysis, model zoo, and accuracy reporting.
"""
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.schemas.forecast import ForecastPeriod, ForecastResponse


# ── v2 extension models ───────────────────────────────────────────

class FanChartBand(BaseModel):
    period_offset: int
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class RegimeInfo(BaseModel):
    change_point_detected: bool
    regime_start_index: int
    effective_data_points: int
    change_points: list[int] = []


class MultivariateAdjustment(BaseModel):
    applied: bool
    indicators_used: list[dict] = []
    total_adjustment: list[float] = []


class DataProfile(BaseModel):
    n: int
    mean: float
    std: float
    trend_strength: float
    seasonality_strength: float
    autocorrelation_lag1: float
    zero_fraction: float
    stationarity_score: float
    series_class: str
    recommended_methods: list[str] = []
    regime_change_detected: bool
    last_change_point: Optional[int] = None


class ForecastV4Period(ForecastPeriod):
    """Extends v3 ForecastPeriod with fan chart percentiles."""
    p10: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    p90: Optional[float] = None


class ForecastV4Response(BaseModel):
    """Full v4 forecast response with diagnostics."""
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
    periods: list[ForecastV4Period]
    method_forecasts: dict[str, list[float]]
    calculated_at: Optional[datetime] = None
    error: Optional[str] = None

    # v2 extensions
    engine_version: str = "2.0"
    data_profile: Optional[DataProfile] = None
    fan_chart: Optional[list[FanChartBand]] = None
    regime_info: Optional[RegimeInfo] = None
    multivariate_adjustment: Optional[MultivariateAdjustment] = None
    backtesting_summary: Optional[dict] = None
    method_params: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


# ── Scenario models ───────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    scenario_type: str
    target_code: Optional[str] = None
    custom_shocks: Optional[dict] = None
    horizon_months: int = 12


class ScenarioResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_type: str
    description: str = ""
    baseline_periods: list[dict]
    scenario_periods: list[dict]
    impact_delta: list[float]
    impact_summary: dict
    error: Optional[str] = None


# ── Backtesting models ────────────────────────────────────────────

class BacktestMethodResult(BaseModel):
    method: str
    n_splits: int
    window_type: str
    avg_rmse: Optional[float] = None
    avg_mae: Optional[float] = None
    avg_mape: Optional[float] = None
    avg_directional_accuracy: Optional[float] = None
    avg_coverage_68: Optional[float] = None
    avg_coverage_95: Optional[float] = None
    error: Optional[str] = None


class BacktestResponse(BaseModel):
    target_type: str
    target_code: str
    methods: list[BacktestMethodResult]
    best_method: Optional[str] = None
    ranking: list[dict] = []
    computed_at: Optional[datetime] = None


# ── Model Zoo ─────────────────────────────────────────────────────

class ModelZooEntry(BaseModel):
    method: str
    target: str
    weight: float
    data_points: Optional[int] = None
    trend_strength: Optional[float] = None
    seasonality_strength: Optional[float] = None
    rmse: Optional[float] = None
    fitted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ModelZooResponse(BaseModel):
    models: list[ModelZooEntry]
    total_models: int
    best_overall_method: Optional[str] = None


# ── Accuracy ──────────────────────────────────────────────────────

class AccuracyResponse(BaseModel):
    target_type: Optional[str] = None
    target_code: Optional[str] = None
    overall_rmse: Optional[float] = None
    overall_mae: Optional[float] = None
    overall_mape: Optional[float] = None
    directional_accuracy: Optional[float] = None
    band_coverage_68: Optional[float] = None
    band_coverage_95: Optional[float] = None
    by_horizon: dict = {}
    sample_size: int = 0


# ── VAR Big 4 ─────────────────────────────────────────────────────

class VARCountryForecast(BaseModel):
    country_code: str
    last_value: float
    forecast: list[float]


class VARResponse(BaseModel):
    countries: list[VARCountryForecast]
    horizon: int
    model: str = "VAR(1)"
    interdependencies: Optional[dict] = None
