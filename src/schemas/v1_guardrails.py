from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataMode(str, Enum):
    live = "live"
    historique = "historique"
    estimation = "estimation"


class FXRateRow(BaseModel):
    symbol: str
    rate: float


class FXMarketResponse(BaseModel):
    base: str
    rates: list[FXRateRow]
    source: str
    timestamp: str
    data_mode: DataMode
    confidence: float = Field(..., ge=0.0, le=1.0)
    as_of: str | None = None
    message: str | None = None


class CreditDecisionComponents(BaseModel):
    pays: float = Field(..., ge=0, le=100)
    politique: float = Field(..., ge=0, le=100)
    sectoriel: float = Field(..., ge=0, le=100)
    flux: float = Field(..., ge=0, le=100)
    corridor: float = Field(..., ge=0, le=100)
    emprunteur: float = Field(..., ge=0, le=100)
    change: float = Field(..., ge=0, le=100)


class CreditDecisionRequest(BaseModel):
    country: str = Field(..., min_length=2, max_length=2)
    loan_type: str
    components: CreditDecisionComponents
    borrower_profile: str | None = None
    corridor: str | None = None


class CreditDecisionResponse(BaseModel):
    decision_proposal: str
    score: float
    veto_applied: bool
    veto_reason: str | None = None
    human_review_required: bool
    disclaimer: str


class FinancialAnalysisRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=3000)
    context_data: Any = None
    confidentiality_mode: str = Field(default="cloud")


class FinancialAnalysisResponse(BaseModel):
    analysis: str
    model_used: str
    citations: list[str]
    missing_data_flags: list[str]
    human_review_required: bool
    disclaimer: str
