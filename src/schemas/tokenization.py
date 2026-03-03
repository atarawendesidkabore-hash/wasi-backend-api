"""Pydantic schemas for Data Tokenization endpoints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, ConfigDict


# ── Request Models ────────────────────────────────────────────────────

class CitizenActivityRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    activity_type: str = Field(
        ...,
        description="FARM_WORK | MARKET_PRICE | CROP_YIELD | ROAD_CONDITION | "
                    "WEATHER | WATER_ACCESS | HEALTH_FACILITY | SCHOOL_STATUS",
    )
    location_name: str = Field(..., min_length=2, max_length=200)
    location_region: Optional[str] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    price_local: Optional[float] = None
    details: Optional[str] = None


class BusinessSubmissionRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    business_type: str = Field(
        ...,
        description="AGRICULTURE | TRADING | TRANSPORT | MANUFACTURING | "
                    "SERVICES | MINING | RETAIL",
    )
    metric_type: str = Field(
        ...,
        description="CUSTOMS_DECLARATION | BANK_STATEMENT | SALES_VOLUME | "
                    "INVENTORY_LEVEL | SUPPLIER_COUNT | TRADE_VOLUME | "
                    "EMPLOYEE_COUNT | ACTIVITY_REPORT",
    )
    metrics: str = Field(..., description="JSON string of business metrics")
    period_date: date


class MilestoneVerificationRequest(BaseModel):
    verifier_type: str = Field(
        ..., description="CITIZEN | INSPECTOR | CONTRACTOR"
    )
    vote: str = Field(..., description="APPROVE | REJECT | PARTIAL")
    completion_pct: Optional[float] = Field(None, ge=0, le=100)
    evidence: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None


class WorkerCheckInRequest(BaseModel):
    contract_id: str
    location_name: Optional[str] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None


# ── Response Models ───────────────────────────────────────────────────

class DataTokenResponse(BaseModel):
    token_id: str
    pillar: str
    token_type: str
    token_value_cfa: float
    token_value_usd: Optional[float] = None
    status: str
    validation_count: int
    confidence: float
    period_date: date
    location_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CitizenActivityResponse(BaseModel):
    id: int
    activity_type: str
    location_name: Optional[str] = None
    location_region: Optional[str] = None
    quantity_value: Optional[float] = None
    payment_amount_cfa: float
    payment_status: str
    validation_count: int
    confidence: float
    is_cross_validated: bool
    period_date: date
    model_config = ConfigDict(from_attributes=True)


class BusinessCreditResponse(BaseModel):
    business_phone_hash: str
    fiscal_year: int
    cumulative_earned_cfa: float
    cumulative_used_cfa: float
    remaining_cfa: float
    cap_absolute_cfa: float
    tier_breakdown: Dict[str, float]


class ContractMilestoneResponse(BaseModel):
    id: int
    contract_id: str
    contract_name: str
    milestone_number: int
    description: str
    value_cfa: float
    status: str
    verification_count: int
    verification_required: int
    confidence: float
    location_name: Optional[str] = None
    expected_end_date: Optional[date] = None
    model_config = ConfigDict(from_attributes=True)


class WorkerResponse(BaseModel):
    id: int
    country_code: str
    skill_type: str
    daily_rate_cfa: float
    is_active: bool
    total_days_worked: int
    total_earned_cfa: float
    current_contract_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class DisbursementResponse(BaseModel):
    disbursement_id: str
    amount_cfa: float
    amount_usd: Optional[float] = None
    payment_type: str
    pillar: str
    status: str
    mobile_money_provider: Optional[str] = None
    queued_at: datetime
    completed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class TokenizationStatusResponse(BaseModel):
    total_tokens: int
    tokens_by_pillar: Dict[str, int]
    tokens_by_country: Dict[str, int]
    total_paid_cfa: float
    total_tax_credits_cfa: float
    countries_active: int
    latest_aggregate_date: Optional[date] = None


class TokenizationAggregateResponse(BaseModel):
    country_code: str
    period_date: date
    citizen_data_score: Optional[float] = None
    business_data_score: Optional[float] = None
    contract_score: Optional[float] = None
    tokenization_composite_score: Optional[float] = None
    citizen_reports_count: int
    business_submissions_count: int
    workers_checked_in: int
    avg_confidence: float
    cross_validated_pct: float
    model_config = ConfigDict(from_attributes=True)
