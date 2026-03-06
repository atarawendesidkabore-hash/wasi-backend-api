"""
AfriCredit/MFI — Pydantic request/response schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# ── Client schemas ────────────────────────────────────────────────────────────

class ClientCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=8, max_length=20, description="Phone number (will be hashed)")
    gender: Optional[str] = Field(None, pattern="^[MF]$")
    date_of_birth: Optional[date] = None
    id_type: Optional[str] = Field(None, max_length=30)
    id_number: Optional[str] = Field(None, description="ID number (will be hashed)")
    country_code: str = Field(..., min_length=2, max_length=2)
    city: Optional[str] = Field(None, max_length=100)
    neighborhood: Optional[str] = Field(None, max_length=100)
    business_name: Optional[str] = Field(None, max_length=200)
    sector: Optional[str] = Field(None, max_length=50)
    business_description: Optional[str] = None
    monthly_revenue_xof: Optional[int] = Field(None, ge=0)
    years_in_business: Optional[float] = Field(None, ge=0)


class ClientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    country_code: str
    city: Optional[str]
    sector: Optional[str]
    business_name: Optional[str]
    monthly_revenue_xof: Optional[int]
    years_in_business: Optional[float]
    kyc_level: str
    credit_score: Optional[float]
    is_active: bool


# ── Loan schemas ──────────────────────────────────────────────────────────────

class LoanApplicationRequest(BaseModel):
    client_id: int = Field(..., gt=0)
    product_type: str = Field(..., description="MICRO | SME | AGRICULTURAL | GROUP_SOLIDARITY")
    purpose: Optional[str] = Field(None, max_length=200)
    principal_xof: int = Field(..., gt=0, description="Loan amount in XOF")
    term_months: int = Field(..., ge=1, le=60)
    interest_rate_annual_pct: Optional[float] = Field(None, ge=0, le=50)
    interest_method: str = Field("DECLINING", description="FLAT | DECLINING")
    grace_period_months: int = Field(0, ge=0, le=12)
    repayment_frequency: str = Field("MONTHLY", description="WEEKLY | BIWEEKLY | MONTHLY")
    collateral_type: Optional[str] = Field(None, max_length=50)
    collateral_value_xof: Optional[int] = Field(None, ge=0)
    guarantor_client_id: Optional[int] = None
    disbursement_method: Optional[str] = Field(None, description="MOBILE_MONEY | CASH | ECFA_WALLET")


class LoanDecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVE | REJECT")
    reviewer_name: str = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = None
    rejection_reason: Optional[str] = Field(None, max_length=200)


class RepaymentRequest(BaseModel):
    loan_id: int = Field(..., gt=0)
    amount_xof: int = Field(..., gt=0)
    payment_method: str = Field("CASH", description="MOBILE_MONEY | CASH | ECFA_WALLET")
    reference_number: Optional[str] = Field(None, max_length=50)
    received_by: Optional[str] = Field(None, max_length=100)


class LoanResponse(BaseModel):
    id: int
    loan_number: str
    client_id: int
    product_type: str
    principal_xof: int
    interest_rate_annual_pct: float
    interest_method: str
    term_months: int
    grace_period_months: int
    status: str
    outstanding_balance_xof: int
    days_overdue: int
    disbursement_date: Optional[date]
    maturity_date: Optional[date]
    application_score: Optional[float]


# ── Group schemas ─────────────────────────────────────────────────────────────

class GroupCreateRequest(BaseModel):
    group_name: str = Field(..., min_length=1, max_length=200)
    country_code: str = Field(..., min_length=2, max_length=2)
    city: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=50)


# ── Schedule preview ──────────────────────────────────────────────────────────

class SchedulePreviewRequest(BaseModel):
    principal_xof: int = Field(..., gt=0)
    annual_rate_pct: float = Field(..., ge=0, le=50)
    term_months: int = Field(..., ge=1, le=60)
    grace_months: int = Field(0, ge=0, le=12)
    method: str = Field("DECLINING", description="FLAT | DECLINING")
    frequency: str = Field("MONTHLY", description="WEEKLY | BIWEEKLY | MONTHLY")
