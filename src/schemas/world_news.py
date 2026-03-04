"""
Pydantic schemas for World News Intelligence endpoints.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class WorldNewsEventResponse(BaseModel):
    id: int
    event_type: str
    headline: str
    summary: str
    source_url: Optional[str] = None
    source_name: str
    source_region: str
    relevance_score: float
    relevance_layer1_keyword: float
    relevance_layer2_supply_chain: float
    relevance_layer3_transmission: float
    keywords_matched: list
    global_magnitude: float
    detected_at: datetime
    expires_at: datetime
    is_active: bool
    cascaded: bool

    model_config = ConfigDict(from_attributes=True)


class ImpactAssessmentResponse(BaseModel):
    id: int
    world_news_event_id: int
    country_code: str
    direct_impact: float
    indirect_impact: float
    systemic_impact: float
    country_magnitude: float
    transmission_channel: Optional[str] = None
    explanation: str
    news_event_created: bool
    assessed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImpactCascadeResponse(BaseModel):
    world_event: WorldNewsEventResponse
    assessments: list[ImpactAssessmentResponse]
    countries_affected: int
    most_affected_country: Optional[str] = None
    total_cascaded_events: int


class CountryExposureItem(BaseModel):
    event_id: int
    event_type: str
    headline: str
    country_magnitude: float
    transmission_channel: Optional[str] = None
    detected_at: datetime


class CountryExposureResponse(BaseModel):
    country_code: str
    country_name: str
    total_active_global_events: int
    net_global_adjustment: float
    exposure_items: list[CountryExposureItem]


class DailyBriefingTopEvent(BaseModel):
    event_id: int
    event_type: str
    headline: str
    relevance_score: float
    global_magnitude: float
    countries_affected: int
    most_affected: Optional[str] = None


class DailyBriefingCountryImpact(BaseModel):
    country_code: str
    net_global_impact: float
    active_global_events: int
    trend: str  # "improving" | "worsening" | "stable"


class DailyBriefingResponse(BaseModel):
    briefing_date: date
    total_global_events: int
    high_relevance_events: int
    countries_affected: int
    top_events: list[DailyBriefingTopEvent]
    country_impacts: list[DailyBriefingCountryImpact]
    watchlist: list[str]
    generated_at: datetime


class WorldNewsSweepResponse(BaseModel):
    status: str
    global_events_detected: int
    high_relevance_events: int
    country_events_cascaded: int
    assessments_created: int
    briefing_generated: bool
    swept_at: datetime
