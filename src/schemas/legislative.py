"""Pydantic schemas for legislative monitoring API responses."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class LegislativeActResponse(BaseModel):
    id: int
    country_code: str = ""
    country_name: str = ""
    title: str
    description: Optional[str] = None
    act_number: Optional[str] = None
    act_date: Optional[date] = None
    category: str
    status: str
    impact_type: str
    estimated_magnitude: float
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    confidence: Optional[float] = None
    data_quality: Optional[str] = None
    data_source: Optional[str] = None
    is_active: bool = True
    detected_at: Optional[datetime] = None
    confidence_indicator: str = "grey"

    model_config = ConfigDict(from_attributes=True)


class CountryLegislativeResponse(BaseModel):
    country_code: str
    country_name: str
    total_active_acts: int
    positive_count: int
    negative_count: int
    neutral_count: int
    net_magnitude: float
    categories: dict[str, int]
    recent_acts: list[dict]
    assessment: str
    timestamp: str


class LegislativeImpactResponse(BaseModel):
    country_code: str
    country_name: str
    total_active_acts: int
    positive_count: int
    negative_count: int
    neutral_count: int
    net_magnitude: float
    categories: dict[str, int]
    recent_acts: list[dict]
    assessment: str
    timestamp: str


class CountrySummaryItem(BaseModel):
    country_code: str
    country_name: str
    wasi_weight: float
    total_acts: int
    positive: int
    negative: int
    net_magnitude: float
    weighted_impact: float


class ECOWASLegislativeSummary(BaseModel):
    total_acts_tracked: int
    total_positive: int
    total_negative: int
    ecowas_weighted_impact: float
    ecowas_assessment: str
    countries: list[CountrySummaryItem]
    timestamp: str


class LegislativeRefreshResponse(BaseModel):
    acts_found: int
    sessions_found: int
    errors: int
    countries_covered: list[str]
    sources_used: list[str]
