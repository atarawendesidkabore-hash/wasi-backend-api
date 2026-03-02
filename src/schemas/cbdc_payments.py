"""Pydantic schemas for WASI-Pay cross-border payment operations."""
from datetime import datetime
from pydantic import BaseModel, Field


# ── Quote ──────────────────────────────────────────────────────────────

class CrossBorderQuoteRequest(BaseModel):
    sender_wallet_id: str
    receiver_wallet_id: str | None = None
    receiver_country: str = Field(..., min_length=2, max_length=2)
    amount: float = Field(..., gt=0)
    source_currency: str = Field(default="XOF", max_length=5)
    target_currency: str = Field(..., max_length=5)
    lock_rate: bool = Field(default=True, description="Lock the quoted rate for 30 seconds")


class CrossBorderQuoteResponse(BaseModel):
    quote_id: str | None = None
    rail_type: str
    amount_source: float
    source_currency: str
    amount_target: float
    target_currency: str
    fx_rate: float | None = None
    fx_spread_percent: float | None = None
    platform_fee_ecfa: float
    rail_fee_ecfa: float
    total_cost_ecfa: float
    rate_expires_at: datetime | None = None
    estimated_settlement_sec: int


# ── Payment ────────────────────────────────────────────────────────────

class CrossBorderPaymentRequest(BaseModel):
    sender_wallet_id: str
    receiver_wallet_id: str | None = None
    receiver_country: str = Field(..., min_length=2, max_length=2)
    amount: float = Field(..., gt=0)
    source_currency: str = Field(default="XOF", max_length=5)
    target_currency: str = Field(..., max_length=5)
    quote_id: str | None = None
    pin: str | None = None
    purpose: str | None = Field(None, max_length=100)


class CrossBorderPaymentResponse(BaseModel):
    payment_id: str
    status: str
    rail_type: str
    amount_source: float
    source_currency: str
    amount_target: float | None = None
    target_currency: str
    fx_rate_applied: float | None = None
    platform_fee_ecfa: float = 0.0
    rail_fee_ecfa: float = 0.0
    total_cost_ecfa: float = 0.0
    source_tx_id: str | None = None
    dest_tx_id: str | None = None
    estimated_settlement_sec: int = 0
    failure_reason: str | None = None
    created_at: datetime | None = None


# ── Status & Trace ─────────────────────────────────────────────────────

class PaymentStatusResponse(BaseModel):
    payment_id: str
    status: str
    rail_type: str
    sender_country: str
    receiver_country: str
    amount_source: float
    source_currency: str
    amount_target: float | None = None
    target_currency: str
    compliance_status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    settled_at: datetime | None = None
    failure_reason: str | None = None


class PaymentTraceHop(BaseModel):
    step: int
    hop_type: str
    amount: float | None = None
    currency: str | None = None
    status: str
    timestamp: datetime | None = None
    details: dict | None = None


class PaymentTraceResponse(BaseModel):
    payment_id: str
    status: str
    rail_type: str
    hops: list[PaymentTraceHop]


# ── FX Rates ───────────────────────────────────────────────────────────

class FxRateResponse(BaseModel):
    base: str
    target: str
    rate: float
    inverse_rate: float
    spread_percent: float
    effective_date: str
    staleness_hours: float
    is_stale: bool
    source: str


class FxRateUpdateRequest(BaseModel):
    target_currency: str = Field(..., max_length=5)
    new_rate: float = Field(..., gt=0)
    source: str = Field(default="ADMIN")


# ── Corridors ──────────────────────────────────────────────────────────

class CorridorResponse(BaseModel):
    source_country: str
    dest_country: str
    source_currency: str
    dest_currency: str
    rail_type: str
    requires_fx: bool
    platform_fee_pct: float
    rail_fee_ecfa: float
    estimated_settlement_sec: int
    available: bool
