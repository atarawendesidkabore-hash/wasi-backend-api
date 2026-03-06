"""Pydantic schemas for Sovereign Veto + Data Truth endpoints."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from enum import Enum


class VetoType(str, Enum):
    SANCTIONS = "SANCTIONS"
    DEBT_CEILING = "DEBT_CEILING"
    MONETARY_POLICY = "MONETARY_POLICY"
    POLITICAL_CRISIS = "POLITICAL_CRISIS"
    AML_CFT = "AML_CFT"


class Severity(str, Enum):
    FULL_BLOCK = "FULL_BLOCK"
    PARTIAL = "PARTIAL"


class VetoCreateRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    veto_type: VetoType
    severity: Severity = Severity.FULL_BLOCK
    reason: str = Field(..., min_length=10, max_length=2000)
    issued_by: str = Field(..., min_length=2, max_length=100)
    legal_basis: Optional[str] = Field(None, max_length=200)
    reference_number: Optional[str] = Field(None, max_length=100)
    effective_date: date
    expiry_date: Optional[date] = None
    max_loan_cap_usd: Optional[float] = Field(None, gt=0)


class VetoRevokeRequest(BaseModel):
    revoked_by: str = Field(..., min_length=2, max_length=100)
    revocation_reason: Optional[str] = Field(None, max_length=2000)


class VetoResponse(BaseModel):
    id: int
    country_code: str
    veto_type: str
    severity: str
    reason: str
    issued_by: str
    legal_basis: Optional[str] = None
    reference_number: Optional[str] = None
    effective_date: str
    expiry_date: Optional[str] = None
    is_active: bool
    max_loan_cap_usd: Optional[float] = None
    human_review_required: bool = True
    created_at: str
    revoked_at: Optional[str] = None
    revoked_by: Optional[str] = None
    revocation_reason: Optional[str] = None


class VetoCheckResponse(BaseModel):
    blocked: bool
    partial: bool
    max_loan_cap_usd: Optional[float] = None
    vetoes: list[dict]
    message: str
    human_review_required: bool = True
    advisory: str = "Advisory only. Decision finale = validation humaine."


class VetoListResponse(BaseModel):
    country_code: Optional[str] = None
    active_count: int
    vetoes: list[VetoResponse]


class DataTruthResponse(BaseModel):
    country_code: str
    country_name: Optional[str] = None
    overall_truth_score: float
    overall_verdict: str
    active_vetoes: int
    veto_details: list[dict] = []
    checks: list[dict]
    human_review_required: bool
    advisory: str = "Advisory only. Decision finale = validation humaine."


class CrossSourceAuditRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    metric_name: str = Field(..., min_length=1, max_length=100)
    source_a: str = Field(..., min_length=1, max_length=100)
    source_b: str = Field(..., min_length=1, max_length=100)
    value_a: float
    value_b: float


class CrossSourceAuditResponse(BaseModel):
    id: int
    country_code: str
    metric_name: str
    source_a: str
    source_b: str
    value_a: float
    value_b: float
    divergence_pct: float
    verdict: str
    confidence_after: Optional[float] = None
    details: Optional[str] = None
    audited_at: str
