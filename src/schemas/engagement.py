"""Pydantic schemas for Walk15-style Engagement endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ── Request Models ────────────────────────────────────────────────────

class ChallengeCreateRequest(BaseModel):
    challenge_code: str = Field(..., min_length=3, max_length=40)
    title_en: str = Field(..., min_length=3, max_length=200)
    title_fr: str = Field(..., min_length=3, max_length=200)
    description_en: Optional[str] = None
    description_fr: Optional[str] = None
    scope: Literal["REGIONAL", "COUNTRY", "GLOBAL"]
    target_country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    target_region: Optional[str] = None
    goal_metric: Literal[
        "citizen_reports", "cross_validated", "unique_reporters",
        "business_submissions", "worker_checkins",
    ]
    goal_target: int = Field(..., gt=0)
    start_date: datetime
    end_date: datetime
    reward_multiplier: float = Field(1.50, ge=1.0, le=3.0)
    bonus_cfa: float = Field(0, ge=0)


class RewardCreateRequest(BaseModel):
    reward_code: str = Field(..., min_length=3, max_length=40)
    name_en: str = Field(..., min_length=3, max_length=100)
    name_fr: str = Field(..., min_length=3, max_length=100)
    description_en: Optional[str] = None
    description_fr: Optional[str] = None
    reward_type: Literal["AIRTIME", "DATA_BUNDLE", "ECFA_BONUS", "PARTNER_DISCOUNT"]
    cost_cfa: float = Field(..., gt=0)
    min_tier: Literal["BRONZE", "SILVER", "GOLD", "PLATINUM"] = "BRONZE"
    partner_name: Optional[str] = None


# ── Response Models ───────────────────────────────────────────────────

class DataWalletResponse(BaseModel):
    contributor_phone_hash: str
    country_code: str
    total_reports: int
    total_earned_cfa: float
    total_redeemed_cfa: float = 0
    available_balance_cfa: float = 0
    total_cross_validated: int
    current_streak: int
    longest_streak: int
    last_report_date: Optional[date] = None
    streak_grace_used: bool
    reputation_score: float
    tier: str
    current_multiplier: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def compute_available_balance(self):
        self.available_balance_cfa = round(
            (self.total_earned_cfa or 0) - (self.total_redeemed_cfa or 0), 2
        )
        return self


class StreakResponse(BaseModel):
    current_streak: int
    longest_streak: int
    last_report_date: Optional[date] = None
    streak_grace_used: bool
    current_multiplier: float
    next_milestone: int  # days to next streak tier (0 = max reached)
    next_multiplier: float


class TierResponse(BaseModel):
    current_tier: str
    reputation_score: float
    next_tier: Optional[str] = None
    points_to_next: float
    multiplier_bonus: float
    perks: List[str]


class BadgeDefinitionResponse(BaseModel):
    id: int
    badge_code: str
    name_en: str
    name_fr: str
    description_en: Optional[str] = None
    description_fr: Optional[str] = None
    category: str
    rarity: str
    icon_emoji: Optional[str] = None
    pillar: Optional[str] = None
    sort_order: int
    model_config = ConfigDict(from_attributes=True)


class UserBadgeResponse(BaseModel):
    badge_code: str
    name_en: str
    name_fr: str
    category: str
    rarity: str
    icon_emoji: Optional[str] = None
    earned_at: Optional[datetime] = None
    earned: bool
    progress_current: int
    progress_target: int
    progress_pct: float


class ChallengeResponse(BaseModel):
    id: int
    challenge_code: str
    title_en: str
    title_fr: str
    description_en: Optional[str] = None
    description_fr: Optional[str] = None
    scope: str
    target_country_code: Optional[str] = None
    target_region: Optional[str] = None
    goal_metric: str
    goal_target: int
    current_progress: int
    progress_pct: float
    start_date: datetime
    end_date: datetime
    status: str
    reward_multiplier: float
    bonus_cfa: float
    participant_count: int
    model_config = ConfigDict(from_attributes=True)


class ChallengeDetailResponse(ChallengeResponse):
    leaderboard: List[LeaderboardEntry]


class LeaderboardEntry(BaseModel):
    rank: int
    contributor_phone_hash: str
    country_code: str
    contribution_count: int
    reputation_score: Optional[float] = None


# Forward ref fix — ChallengeDetailResponse references LeaderboardEntry
ChallengeDetailResponse.model_rebuild()


class ImpactResponse(BaseModel):
    period_month: str
    country_code: str
    reports_submitted: int
    cross_validated_count: int
    regions_covered: int
    countries_helped: int
    data_quality_avg: float
    formal_surveys_equivalent: int
    estimated_value_usd: float
    model_config = ConfigDict(from_attributes=True)


class ImpactDashboardResponse(BaseModel):
    wallet: DataWalletResponse
    current_streak: StreakResponse
    badges_earned: int
    badges_total: int
    active_challenges: int
    lifetime_impact: LifetimeImpact


class LifetimeImpact(BaseModel):
    total_reports: int
    total_cross_validated: int
    total_regions: int
    total_countries_helped: int
    total_formal_surveys_equivalent: int
    total_value_usd: float


# Forward ref fix
ImpactDashboardResponse.model_rebuild()


class RewardCatalogResponse(BaseModel):
    id: int
    reward_code: str
    name_en: str
    name_fr: str
    description_en: Optional[str] = None
    description_fr: Optional[str] = None
    reward_type: str
    cost_cfa: float
    min_tier: str
    is_active: bool
    partner_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class RewardRedeemResponse(BaseModel):
    status: str
    reward_code: str
    reward_name: str
    cost_cfa: float
    payment_reference: Optional[str] = None
    remaining_balance_cfa: float


class CountryEngagementResponse(BaseModel):
    country_code: str
    total_reporters: int
    active_reporters_30d: int
    avg_reputation: float
    avg_streak: float
    top_tier_distribution: dict  # {"BRONZE": N, "SILVER": N, ...}
    top_badges: List[str]  # most common badge codes
    active_challenges: int


class EngagementSummaryResponse(BaseModel):
    total_wallets: int
    total_reports_all: int
    total_earned_cfa_all: float
    avg_reputation: float
    avg_streak: float
    tier_distribution: dict
    badges_awarded_total: int
    active_challenges: int
    countries_with_data: int
