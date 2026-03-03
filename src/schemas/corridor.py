"""
Pydantic v2 schemas for Trade Corridor Intelligence endpoints.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Sub-components ──────────────────────────────────────────────

class CorridorAssessmentOut(BaseModel):
    corridor_code: str
    name: str
    from_country_code: str
    to_country_code: str
    corridor_type: str
    distance_km: Optional[float] = None
    transit_countries: Optional[str] = None
    key_border_posts: Optional[str] = None
    key_ports: Optional[str] = None
    assessment_date: str
    transport_score: Optional[float] = None
    fx_score: Optional[float] = None
    trade_volume_score: Optional[float] = None
    logistics_score: Optional[float] = None
    risk_score: Optional[float] = None
    payment_score: Optional[float] = None
    corridor_composite: Optional[float] = None
    trend: Optional[str] = None
    bottleneck: Optional[str] = None
    confidence: float = 0.0
    data_sources_used: int = 0


class CorridorListResponse(BaseModel):
    as_of: str
    corridors: list[CorridorAssessmentOut]
    count: int


# ── Ranking ────────────────────────────────────────────────────

class CorridorRankingItem(BaseModel):
    rank: int
    corridor_code: str
    name: str
    from_country_code: str
    to_country_code: str
    corridor_type: str
    corridor_composite: Optional[float] = None
    trend: Optional[str] = None
    bottleneck: Optional[str] = None
    confidence: float = 0.0


class CorridorRankingResponse(BaseModel):
    as_of: str
    rankings: list[CorridorRankingItem]


# ── Comparison ──────────────────────────────────────────────────

class CorridorComparisonResponse(BaseModel):
    corridors: list[CorridorAssessmentOut]
    best_on: dict[str, str]
    count: int


# ── Bottleneck ──────────────────────────────────────────────────

class BottleneckItem(BaseModel):
    dimension: str
    score: float
    weight_pct: float
    recommendation: str


class BottleneckResponse(BaseModel):
    corridor_code: str
    name: str
    bottlenecks: list[BottleneckItem]
    overall_assessment: str
    corridor_composite: Optional[float] = None


# ── History ────────────────────────────────────────────────────

class CorridorHistoryPoint(BaseModel):
    assessment_date: str
    corridor_composite: Optional[float] = None
    transport_score: Optional[float] = None
    fx_score: Optional[float] = None
    trade_volume_score: Optional[float] = None
    logistics_score: Optional[float] = None
    risk_score: Optional[float] = None
    payment_score: Optional[float] = None
    trend: Optional[str] = None
    bottleneck: Optional[str] = None


class CorridorHistoryResponse(BaseModel):
    corridor_code: str
    name: str
    days: int
    history: list[CorridorHistoryPoint]


# ── Dashboard ──────────────────────────────────────────────────

class DashboardCorridorItem(BaseModel):
    corridor_code: str
    name: str
    from_country_code: str
    to_country_code: str
    corridor_type: str
    corridor_composite: Optional[float] = None
    trend: Optional[str] = None
    bottleneck: Optional[str] = None


class CorridorDashboardResponse(BaseModel):
    as_of: str
    total_corridors: int
    avg_corridor_score: Optional[float] = None
    weighted_corridor_health: Optional[float] = None
    best_corridor: Optional[str] = None
    worst_corridor: Optional[str] = None
    most_common_bottleneck: Optional[str] = None
    corridors: list[DashboardCorridorItem]


# ── Refresh ────────────────────────────────────────────────────

class CorridorRefreshResponse(BaseModel):
    corridors_assessed: int
    timestamp: str
