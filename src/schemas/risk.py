"""Pydantic response models for the Risk Scoring Engine."""

from pydantic import BaseModel
from typing import Optional


class RiskDimension(BaseModel):
    score: float
    factors: list[str]


class RiskDimensions(BaseModel):
    trade: RiskDimension
    macro: RiskDimension
    political: RiskDimension
    logistics: RiskDimension
    market: RiskDimension


class CountryRiskResponse(BaseModel):
    country_code: str
    country_name: str
    risk_score: float
    risk_rating: str
    dimensions: RiskDimensions
    weights: dict[str, float]
    computed_at: str


class RiskExtreme(BaseModel):
    country: str
    score: float


class RegionalRiskResponse(BaseModel):
    countries: list[CountryRiskResponse]
    regional_risk: float
    regional_rating: str
    highest_risk: RiskExtreme
    lowest_risk: RiskExtreme
    computed_at: str


class Anomaly(BaseModel):
    type: str
    severity: str
    detail: str
    z_score: Optional[float] = None
    pct_change: Optional[float] = None
    net_magnitude: Optional[int] = None
    days_stale: Optional[int] = None


class AnomalyResponse(BaseModel):
    country_code: str
    lookback_days: int
    anomaly_count: int
    anomalies: list[Anomaly]
    computed_at: str


class CorrelationResponse(BaseModel):
    country_a: str
    country_b: str
    correlation: Optional[float]
    data_points: int
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    interpretation: Optional[str] = None
    error: Optional[str] = None
    computed_at: Optional[str] = None
