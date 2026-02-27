"""Pydantic schemas for USSD integration endpoints."""
from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional


# ── USSD Gateway Callback (Africa's Talking / Infobip format) ─────────

class USSDCallbackRequest(BaseModel):
    """Incoming USSD callback from MNO gateway."""
    sessionId: str = Field(..., description="Unique session ID from MNO")
    serviceCode: str = Field(..., description="USSD short code (e.g. *384*123#)")
    phoneNumber: str = Field(..., description="MSISDN in E.164 format (e.g. +22507XXXXXXX)")
    text: str = Field(default="", description="Concatenated user input (e.g. '1*2*500000')")


class USSDCallbackResponse(BaseModel):
    """Response to MNO gateway — plain text prefixed with CON or END."""
    response: str
    session_type: str


# ── Provider management ───────────────────────────────────────────────

class USSDProviderCreate(BaseModel):
    provider_code: str = Field(..., min_length=2, max_length=20)
    provider_name: str = Field(..., min_length=2, max_length=100)
    gateway_url: Optional[str] = None
    country_codes: str = Field(..., description="Comma-separated ISO-2 codes")
    ussd_shortcode: Optional[str] = None


class USSDProviderResponse(BaseModel):
    id: int
    provider_code: str
    provider_name: str
    country_codes: str
    ussd_shortcode: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Mobile Money Flow ─────────────────────────────────────────────────

class MobileMoneyFlowCreate(BaseModel):
    """Bulk push from MNO partner — daily aggregated mobile money stats."""
    country_code: str = Field(..., pattern="^[A-Z]{2}$")
    provider_code: str
    period_date: date
    transaction_count: int = Field(ge=0)
    total_value_local: float = Field(ge=0)
    local_currency: str = Field(..., max_length=5)
    fx_rate_usd: float = Field(gt=0)
    p2p_count: Optional[int] = 0
    merchant_count: Optional[int] = 0
    bill_pay_count: Optional[int] = 0
    cash_in_count: Optional[int] = 0
    cash_out_count: Optional[int] = 0
    cross_border_count: Optional[int] = 0


class MobileMoneyFlowResponse(BaseModel):
    id: int
    country_id: int
    provider_code: str
    period_date: date
    transaction_count: int
    total_value_local: float
    total_value_usd: float
    avg_transaction_usd: float
    local_currency: Optional[str]
    p2p_count: int
    merchant_count: int
    cross_border_count: int
    confidence: float

    model_config = {"from_attributes": True}


# ── Commodity Report ──────────────────────────────────────────────────

class CommodityReportResponse(BaseModel):
    id: int
    country_id: int
    period_date: date
    market_name: str
    commodity_code: str
    commodity_name: str
    price_local: float
    price_usd: Optional[float]
    local_currency: Optional[str]
    pct_change_week: Optional[float]
    pct_change_month: Optional[float]
    report_count: int
    confidence: float

    model_config = {"from_attributes": True}


# ── Trade Declaration ─────────────────────────────────────────────────

class TradeDeclarationResponse(BaseModel):
    id: int
    country_id: int
    period_date: date
    border_post: str
    origin_country: str
    destination_country: str
    direction: str
    commodity_category: str
    declared_value_local: Optional[float]
    declared_value_usd: Optional[float]
    declaration_count: int
    confidence: float

    model_config = {"from_attributes": True}


# ── Port Clearance ────────────────────────────────────────────────────

class PortClearanceResponse(BaseModel):
    id: int
    country_id: int
    period_date: date
    port_name: str
    port_code: Optional[str]
    containers_cleared: int
    containers_pending: int
    avg_clearance_hours: Optional[float]
    congestion_level: Optional[str]
    customs_delay_hours: float
    reporter_count: int
    confidence: float

    model_config = {"from_attributes": True}


# ── Daily Aggregate ───────────────────────────────────────────────────

class USSDDailyAggregateResponse(BaseModel):
    country_code: str
    period_date: date
    mobile_money_score: Optional[float]
    commodity_price_score: Optional[float]
    informal_trade_score: Optional[float]
    port_efficiency_score: Optional[float]
    ussd_composite_score: Optional[float]
    data_points: int
    providers_reporting: int
    confidence: float


# ── USSD Status Overview ─────────────────────────────────────────────

class USSDStatusResponse(BaseModel):
    """Overview of USSD data pipeline status."""
    total_providers: int
    active_providers: int
    total_sessions_today: int
    total_sessions_all: int
    countries_with_data: int
    data_sources: dict  # {mobile_money: N, commodity: N, trade: N, port: N}
    latest_aggregate_date: Optional[date]
