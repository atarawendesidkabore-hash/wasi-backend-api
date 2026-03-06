"""Pydantic schemas for Data Truth + Credit Guardrails module."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class DataMode(str, Enum):
    live = "live"
    cached = "cached"
    historical = "historical"
    estimation = "estimation"
    unavailable = "unavailable"


class FXRateEntry(BaseModel):
    symbol: str = Field(..., description="Target currency code")
    rate: float = Field(..., description="Exchange rate from base")
    inverse: float = Field(..., description="Inverse rate (1/rate)")


class FXResponse(BaseModel):
    base: str
    rates: list[FXRateEntry]
    source: str
    timestamp: str
    data_mode: DataMode
    confidence: float = Field(..., ge=0.0, le=1.0)
    as_of: Optional[str] = None


class LoanType(str, Enum):
    commercial = "commercial"
    infrastructure = "infrastructure"
    trade_finance = "trade_finance"
    dette_souveraine = "dette_souveraine"
    microfinance = "microfinance"


class CreditDecisionRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    loan_type: LoanType
    loan_amount_usd: float = Field(..., gt=0)
    borrower_name: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(..., min_length=1, max_length=500)


class CreditDecisionResponse(BaseModel):
    decision_proposal: str
    score: float
    veto_applied: bool
    veto_reason: Optional[str] = None
    human_review_required: bool = True
    disclaimer: str = "Advisory only. Decision finale = validation humaine"
    country_code: str
    loan_type: str
    risk_factors: list[str]


class FinancialAnalysisRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=2000)
    country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    include_macro: bool = True
    include_trade: bool = True
    include_conflict: bool = True


class Citation(BaseModel):
    source: str
    description: str
    data_mode: DataMode


class FinancialAnalysisResponse(BaseModel):
    analysis: str
    model_used: str
    citations: list[Citation]
    missing_data_flags: list[str]
    disclaimer: str = "Advisory only. Decision finale = validation humaine"
