"""Pydantic schemas for the investment/brokerage endpoints."""
from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class BuyOrderRequest(BaseModel):
    exchange_code: str = Field(..., description="Exchange: NGX | GSE | BRVM")
    index_name: str = Field(..., description="Index name: e.g. NGX All-Share, BRVM Composite")
    amount_xof: float = Field(..., gt=0, description="Amount to invest in XOF (before fees)")


class SellOrderRequest(BaseModel):
    exchange_code: str = Field(..., description="Exchange: NGX | GSE | BRVM")
    index_name: str = Field(..., description="Index name: e.g. NGX All-Share, BRVM Composite")
    units: float = Field(..., gt=0, description="Number of units to sell")


class OrderResponse(BaseModel):
    order_id: int
    side: str
    exchange_code: str
    index_name: str
    units: float
    price_per_unit: float
    status: str
    # BUY fields
    amount_xof: Optional[float] = None
    fee_xof: Optional[float] = None
    net_invested: Optional[float] = None
    # SELL fields
    gross_amount_xof: Optional[float] = None
    net_received: Optional[float] = None
    realized_pnl: Optional[float] = None
    trade_date: Optional[str] = None


class HoldingResponse(BaseModel):
    exchange_code: str
    index_name: str
    units: float
    avg_buy_price: float
    current_price: float
    cost_basis: float
    current_value: float
    unrealized_pnl: float
    pnl_pct: float
    trade_date: str


class PortfolioResponse(BaseModel):
    user_id: int
    currency: str
    total_invested: float
    total_withdrawn: float
    realized_pnl: float
    total_cost_basis: float
    total_current_value: float
    total_unrealized_pnl: float
    holdings: list[HoldingResponse]
    holdings_count: int


class MarketIndexResponse(BaseModel):
    exchange_code: str
    index_name: str
    country_codes: str
    price: float
    change_pct: Optional[float] = None
    trade_date: str
    data_source: Optional[str] = None


class OrderHistoryItem(BaseModel):
    order_id: int
    side: str
    exchange_code: str
    index_name: str
    units: float
    price_per_unit: float
    total_amount: float
    status: str
    created_at: Optional[str] = None
