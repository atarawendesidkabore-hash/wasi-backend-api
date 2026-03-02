"""Pydantic schemas for eCFA CBDC admin and compliance operations."""
from datetime import datetime, date
from pydantic import BaseModel, Field


class PolicyCreateRequest(BaseModel):
    policy_name: str = Field(..., min_length=3)
    policy_type: str = Field(..., description="SPENDING_RESTRICTION | EXPIRY | DEMURRAGE | INTEREST | ESCROW | VELOCITY_CAP")
    conditions: str = Field(..., description="JSON conditions object")
    country_codes: str | None = Field(None, description="Comma-separated ISO-2 codes (null = all WAEMU)")
    wallet_types: str | None = Field(None, description="Comma-separated wallet types")
    effective_from: datetime
    effective_until: datetime | None = None
    admin_wallet_id: str = Field(..., description="Central bank wallet ID of creator")
    cobol_policy_code: str | None = Field(None, max_length=10)


class PolicyResponse(BaseModel):
    id: int
    policy_id: str
    policy_name: str
    policy_type: str
    conditions: str
    country_codes: str | None
    is_active: bool
    effective_from: datetime
    effective_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MonetaryAggregateResponse(BaseModel):
    snapshot_date: date
    country_code: str
    total_ecfa_circulation: float
    retail_balance_ecfa: float
    merchant_balance_ecfa: float
    bank_balance_ecfa: float
    agent_balance_ecfa: float
    total_minted_ecfa: float
    total_burned_ecfa: float
    total_p2p_volume_ecfa: float
    total_merchant_volume_ecfa: float
    total_cross_border_volume_ecfa: float
    active_wallets: int
    new_wallets: int
    total_transactions: int
    # Money supply breakdown
    m0_base_money_ecfa: float = 0.0
    m1_narrow_money_ecfa: float = 0.0
    m2_broad_money_ecfa: float = 0.0
    # Reserve position
    total_required_reserves_ecfa: float = 0.0
    total_held_reserves_ecfa: float = 0.0
    reserve_compliance_ratio: float = 0.0
    # Facility usage
    total_lending_facility_ecfa: float = 0.0
    total_deposit_facility_ecfa: float = 0.0
    # Policy rates snapshot
    taux_directeur_percent: float | None = None
    taux_pret_marginal_percent: float | None = None
    taux_depot_percent: float | None = None
    velocity: float
    # Interest/demurrage
    total_interest_paid_ecfa: float = 0.0
    total_demurrage_collected_ecfa: float = 0.0
    total_reserve_penalties_ecfa: float = 0.0


class SettlementResponse(BaseModel):
    settlement_id: str
    settlement_type: str
    bank_a_code: str
    bank_b_code: str | None
    gross_amount_ecfa: float
    net_amount_ecfa: float
    direction: str
    transaction_count: int
    country_codes: str
    is_cross_border: bool
    status: str
    star_uemoa_ref: str | None
    window_start: datetime
    window_end: datetime
    settled_at: datetime | None

    model_config = {"from_attributes": True}


class SettlementRunResponse(BaseModel):
    settlements: int
    transactions_netted: int
    netting_ratio: float | None = None
    window: str | None = None


class AmlAlertResponse(BaseModel):
    alert_id: str
    wallet_id: str
    transaction_id: str | None
    alert_type: str
    severity: str
    description: str
    evidence: str | None
    status: str
    assigned_to: str | None
    sar_filed: bool
    reporting_authority: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class AmlResolveRequest(BaseModel):
    resolution_status: str = Field(..., description="resolved_clear | resolved_sar | false_positive")
    resolution_notes: str = Field(..., min_length=5)
    assigned_to: str | None = None


class KycSubmitRequest(BaseModel):
    wallet_id: str
    tier_requested: int = Field(..., ge=1, le=3)
    id_type: str | None = Field(None, description="PHONE_OTP | NATIONAL_ID | PASSPORT | ECOWAS_CARD | VOTER_ID")
    id_number: str | None = Field(None, description="Raw ID number (will be hashed)")
    id_country: str | None = None
    full_name: str | None = Field(None, description="Full legal name (will be encrypted)")
    date_of_birth: str | None = Field(None, description="YYYY-MM-DD")


class KycStatusResponse(BaseModel):
    wallet_id: str
    current_tier: int
    pending_requests: list[dict]


class ComplianceSweepResponse(BaseModel):
    wallets_scanned: int
    alerts_generated: int
    sweep_time: str
