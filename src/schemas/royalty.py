"""Pydantic schemas for Data Marketplace Royalty endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


# ── Individual Royalty Distribution ──────────────────────────────────

class RoyaltyEntryResponse(BaseModel):
    pool_id: int
    period_date: date
    country_code: str
    report_count: int
    avg_confidence: float
    tier_multiplier: float
    quality_weight: float
    share_pct: float
    share_amount_cfa: float
    status: str
    credited_at: Optional[datetime] = None


class RoyaltyHistoryResponse(BaseModel):
    contributor_phone_hash: str
    total_royalties_cfa: float
    entries: List[RoyaltyEntryResponse]


# ── Monthly Breakdown + Summary ─────────────────────────────────────

class MonthlyRoyalty(BaseModel):
    month: str  # "2026-03"
    total_cfa: float
    pools_count: int
    queries_served: int


class RoyaltySummaryResponse(BaseModel):
    contributor_phone_hash: str
    total_royalties_cfa: float
    total_queries_served: int
    avg_share_pct: float
    monthly_breakdown: List[MonthlyRoyalty]


# ── Pool Status ─────────────────────────────────────────────────────

class RoyaltyPoolResponse(BaseModel):
    id: int
    country_code: str
    period_date: date
    total_queries: int
    total_credits_spent: float
    royalty_rate_pct: float
    pool_amount_cfa: float
    contributor_count: int
    distributed: bool
    distributed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class PoolContributorEntry(BaseModel):
    rank: int
    contributor_phone_hash: str
    report_count: int
    avg_confidence: float
    tier_multiplier: float
    quality_weight: float
    share_pct: float
    share_amount_cfa: float


class PoolContributorsResponse(BaseModel):
    pool: RoyaltyPoolResponse
    contributors: List[PoolContributorEntry]


# ── Data Attribution / Lineage ──────────────────────────────────────

class DataAttributionResponse(BaseModel):
    id: int
    query_log_id: Optional[int] = None
    endpoint: str
    consumer_user_id: int
    credits_spent: float
    royalty_contribution: float
    country_code: str
    period_date_start: date
    period_date_end: date
    contributor_count: int
    token_count: int
    avg_confidence: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ── Platform Stats ──────────────────────────────────────────────────

class RoyaltyStatsResponse(BaseModel):
    total_pools: int
    total_distributed_pools: int
    total_pending_pools: int
    total_royalties_distributed_cfa: float
    total_credits_consumed: float
    total_attributions: int
    avg_royalty_per_contributor: float
    unique_contributors: int


# ── Admin Pool List ─────────────────────────────────────────────────

class AdminPoolEntry(BaseModel):
    id: int
    country_code: str
    period_date: date
    pool_amount_cfa: float
    contributor_count: int
    distributed: bool
    distributed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class AdminPoolListResponse(BaseModel):
    pools: List[AdminPoolEntry]
    total_pending_cfa: float
    total_distributed_cfa: float
