"""Pydantic schemas for eCFA CBDC monetary policy operations."""
from datetime import datetime, date
from pydantic import BaseModel, Field


# ── Policy Rate Schemas ──────────────────────────────────────────────

class PolicyRateResponse(BaseModel):
    rate_type: str
    rate_percent: float
    effective_date: str
    decided_by: str | None = None
    rate_id: str | None = None


class AllRatesResponse(BaseModel):
    TAUX_DIRECTEUR: PolicyRateResponse
    TAUX_PRET_MARGINAL: PolicyRateResponse
    TAUX_DEPOT: PolicyRateResponse


class SetPolicyRateRequest(BaseModel):
    rate_type: str = Field(..., description="TAUX_DIRECTEUR | TAUX_PRET_MARGINAL | TAUX_DEPOT | TAUX_RESERVE")
    new_rate_percent: float = Field(..., ge=0.0, le=50.0)
    rationale: str | None = None
    effective_date: date | None = None


class SetPolicyRateResponse(BaseModel):
    rates_updated: list[dict]
    effective_date: str
    decided_by: str


class RateHistoryResponse(BaseModel):
    rate_type: str
    history: list[dict]


# ── Reserve Requirement Schemas ──────────────────────────────────────

class SetReserveRatioRequest(BaseModel):
    new_ratio_percent: float = Field(..., ge=0.0, le=25.0, description="e.g. 3.0 = 3%")


class ReserveRequirementResponse(BaseModel):
    reserve_ratio_percent: float
    banks_assessed: int
    banks_non_compliant: int
    total_required_ecfa: float
    total_held_ecfa: float
    system_surplus_ecfa: float
    computation_date: str
    bank_details: list[dict]


# ── Standing Facility Schemas ────────────────────────────────────────

class OpenLendingRequest(BaseModel):
    bank_wallet_id: str
    amount_ecfa: float = Field(..., gt=0)
    maturity: str = Field("OVERNIGHT", description="OVERNIGHT | 7_DAY | 28_DAY")
    collateral_id: str | None = None


class OpenDepositRequest(BaseModel):
    bank_wallet_id: str
    amount_ecfa: float = Field(..., gt=0)


class FacilityResponse(BaseModel):
    facility_id: str
    facility_type: str
    amount_ecfa: float
    rate_percent: float
    interest_ecfa: float
    maturity: str | None = None
    matures_at: str
    bank_new_balance: float


class FacilityMaturityResponse(BaseModel):
    facilities_matured: int
    total_interest_ecfa: float


# ── Interest & Demurrage ─────────────────────────────────────────────

class DailyInterestResponse(BaseModel):
    date: str
    wallets_affected: int
    total_interest_paid_ecfa: float
    total_demurrage_collected_ecfa: float
    net_ecfa: float


# ── Money Supply ─────────────────────────────────────────────────────

class MoneySupplyResponse(BaseModel):
    country_code: str
    date: str
    m0_base_money_ecfa: float
    m1_narrow_money_ecfa: float
    m2_broad_money_ecfa: float
    reserve_multiplier: float
    breakdown: dict
    daily_volume_ecfa: float
    velocity: float
    total_wallets: int


class EnhancedAggregateResponse(BaseModel):
    country_code: str
    date: str
    m0_base_money_ecfa: float
    m1_narrow_money_ecfa: float
    m2_broad_money_ecfa: float
    reserve_multiplier: float
    breakdown: dict
    daily_volume_ecfa: float
    velocity: float
    total_wallets: int
    policy_rates: dict
    reserve_position: dict
    facility_usage: dict


# ── Monetary Policy Decision Schemas ─────────────────────────────────

class PolicyDecisionRequest(BaseModel):
    meeting_date: date
    meeting_type: str = Field("QUARTERLY", description="QUARTERLY | EXTRAORDINARY | EMERGENCY")
    decision_summary: str = Field(..., min_length=10)
    rationale: str = Field(..., min_length=10)
    taux_directeur: float = Field(..., ge=0.0, le=50.0)
    taux_pret_marginal: float = Field(..., ge=0.0, le=50.0)
    taux_depot: float = Field(..., ge=0.0, le=50.0)
    reserve_ratio: float = Field(..., ge=0.0, le=25.0)
    inflation_rate: float | None = None
    gdp_growth: float | None = None
    votes_for: int | None = None
    votes_against: int | None = None
    votes_abstain: int | None = None
    effective_date: date | None = None


class PolicyDecisionResponse(BaseModel):
    decision_id: str
    meeting_date: str
    effective_date: str
    rates: dict
    changes: dict
    status: str


class PolicyDecisionHistoryItem(BaseModel):
    decision_id: str
    meeting_date: str
    meeting_type: str
    decision_summary: str
    taux_directeur: float
    taux_pret_marginal: float
    taux_depot: float
    reserve_ratio_percent: float
    inflation_rate_percent: float | None
    status: str
    effective_date: str


# ── Collateral Schemas ───────────────────────────────────────────────

class RegisterCollateralRequest(BaseModel):
    asset_class: str = Field(..., description="ECFA_TREASURY_BILL | BCEAO_BOND | GOVT_BOND | CORPORATE_BOND | BANK_DEPOSIT")
    asset_description: str
    issuer: str | None = None
    issuer_country: str | None = None
    face_value_ecfa: float = Field(..., gt=0)
    market_value_ecfa: float = Field(..., gt=0)
    haircut_percent: float = Field(..., ge=0.0, le=100.0)
    min_credit_rating: str | None = None
    maturity_date: date | None = None
    owner_wallet_id: str | None = None


class CollateralResponse(BaseModel):
    collateral_id: str
    asset_class: str
    asset_description: str
    face_value_ecfa: float
    market_value_ecfa: float
    haircut_percent: float
    collateral_value_ecfa: float
    is_pledged: bool
    is_eligible: bool
