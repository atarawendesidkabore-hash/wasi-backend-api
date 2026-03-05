"""Pydantic schemas for Personalized Data Intelligence endpoints."""
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel


# ── Profile Card ─────────────────────────────────────────────────────

class ReputationComponent(BaseModel):
    current: float
    max: float
    label: str


class WeakestFactor(BaseModel):
    factor: str
    current: float
    max: float
    gap: float
    advice_en: str
    advice_fr: str


class TierProgress(BaseModel):
    current_tier: str
    next_tier: Optional[str] = None
    points_to_next: float
    estimated_days_to_advance: Optional[int] = None


class ProfileCardResponse(BaseModel):
    contributor_phone_hash: str
    country_code: str
    reputation_score: float
    tier: str
    tier_progress: TierProgress
    reputation_breakdown: dict[str, ReputationComponent]
    weakest_factor: WeakestFactor


# ── Data Specialization ──────────────────────────────────────────────

class PillarDistribution(BaseModel):
    count: int
    pct: float


class TokenTypeEntry(BaseModel):
    token_type: str
    count: int
    pct: float


class CountryComparison(BaseModel):
    avg_token_types: float
    your_token_types: int
    specialization_score: float


class SpecializationResponse(BaseModel):
    contributor_phone_hash: str
    total_tokens: int
    primary_pillar: str
    pillar_distribution: dict[str, PillarDistribution]
    token_type_distribution: List[TokenTypeEntry]
    expertise_label_en: str
    expertise_label_fr: str
    country_comparison: CountryComparison


# ── Quality Trends ───────────────────────────────────────────────────

class MonthlyTrend(BaseModel):
    month: str
    avg_confidence: float
    cross_validation_rate: float
    reports_count: int


class QualityTrendsResponse(BaseModel):
    contributor_phone_hash: str
    monthly_trends: List[MonthlyTrend]
    confidence_direction: str
    confidence_change_pct: float
    country_percentile: float
    country_avg_confidence: float


# ── Earning Projection ───────────────────────────────────────────────

class WhatIfScenario(BaseModel):
    scenario: str
    description_en: str
    description_fr: str
    projected_monthly_cfa: float
    uplift_pct: float


class EarningProjectionResponse(BaseModel):
    contributor_phone_hash: str
    lifetime_earnings_cfa: float
    current_monthly_rate_cfa: float
    projected_next_month_cfa: float
    royalty_earnings_cfa: float
    token_earnings_cfa: float
    what_if_scenarios: List[WhatIfScenario]


# ── Coverage Opportunities ───────────────────────────────────────────

class UnderservedTokenType(BaseModel):
    token_type: str
    reporters_count: int
    country_avg_reporters: float
    potential_royalty_uplift_pct: float


class GeographicGap(BaseModel):
    region: str
    reporters_count: int
    opportunity_level: str


class MatchingChallenge(BaseModel):
    challenge_id: int
    title_fr: str
    goal_metric: str
    progress_pct: float
    match_reason_fr: str


class CoverageOpportunitiesResponse(BaseModel):
    contributor_phone_hash: str
    country_code: str
    underserved_token_types: List[UnderservedTokenType]
    geographic_gaps: List[GeographicGap]
    matching_challenges: List[MatchingChallenge]


# ── Nudges ────────────────────────────────────────────────────────────

class NudgeResponse(BaseModel):
    type: str
    priority: int
    message_en: str
    message_fr: str
    action_hint: str


# ── Wrapped Summary ──────────────────────────────────────────────────

class TokenTypeSummary(BaseModel):
    token_type: str
    count: int


class BadgeEarned(BaseModel):
    badge_code: str
    name_fr: str
    earned_at: str


class BestMonth(BaseModel):
    month: str
    reports: int


class ImpactSummary(BaseModel):
    formal_surveys_equivalent: int
    estimated_value_usd: float


class WrappedSummaryResponse(BaseModel):
    contributor_phone_hash: str
    year: int
    total_reports: int
    total_earned_cfa: float
    streak_record: int
    top_token_types: List[TokenTypeSummary]
    top_region: Optional[str] = None
    peer_percentile: float
    data_citations: int
    regions_helped: int
    badges_earned_this_year: List[BadgeEarned]
    months_active: int
    best_month: Optional[BestMonth] = None
    impact_summary: ImpactSummary
