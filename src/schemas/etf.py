"""Pydantic schemas for ETF endpoints."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class EtfListItem(BaseModel):
    ticker: str
    name: str
    category: str
    nav_xof: float
    nav_usd: float
    change_pct: float
    fee_pct: float
    description: Optional[str] = None


class EtfDetailResponse(BaseModel):
    ticker: str
    name: str
    category: str
    description: Optional[str] = None
    nav_xof: float
    nav_usd: float
    change_pct: float
    fee_pct: float
    currency: str
    underlying_type: str
    is_active: bool
    nav_updated_at: Optional[str] = None


class EtfBuyRequest(BaseModel):
    ticker: str = Field(..., description="ETF ticker (e.g. WASI-COMP)")
    amount_xof: float = Field(..., gt=0, description="Amount to invest in XOF")


class EtfSellRequest(BaseModel):
    ticker: str = Field(..., description="ETF ticker (e.g. WASI-COMP)")
    units: float = Field(..., gt=0, description="Number of units to sell")


class EtfOrderResponse(BaseModel):
    order_id: int
    side: str
    ticker: str
    name: str
    units: float
    nav_per_unit: float
    amount_xof: Optional[float] = None
    fee_xof: Optional[float] = None
    net_invested: Optional[float] = None
    gross_amount_xof: Optional[float] = None
    net_received: Optional[float] = None
    realized_pnl: Optional[float] = None
    status: str


class EtfNavHistoryItem(BaseModel):
    nav_date: str
    nav_xof: float
    nav_usd: Optional[float] = None
    change_pct: Optional[float] = None
