"""
Data Tokenization Routes — 3 pillars across 16 ECOWAS countries.

Endpoints:
  GET  /api/v3/tokenization/status                    — Dashboard overview
  GET  /api/v3/tokenization/tokens/{cc}               — Tokens by country
  GET  /api/v3/tokenization/activities/{cc}            — Citizen activities
  POST /api/v3/tokenization/business/submit            — Business data submission
  GET  /api/v3/tokenization/business/{cc}/credits      — Tax credit summary
  GET  /api/v3/tokenization/contracts/{cc}             — Contract milestones
  POST /api/v3/tokenization/contracts/{id}/verify      — Citizen verification (FREE)
  GET  /api/v3/tokenization/workers/{cc}               — Faso Meabo workers
  GET  /api/v3/tokenization/payments/{cc}              — Disbursement history
  POST /api/v3/tokenization/aggregate/calculate        — Trigger aggregation
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.connection import get_db
from src.database.models import User, Country
from src.database.tokenization_models import (
    DataToken, DailyActivityDeclaration, BusinessDataSubmission,
    TaxCreditLedger, ContractMilestone, MilestoneVerification,
    FasoMeaboWorker, WorkerCheckIn, PaymentDisbursement,
    TokenizationDailyAggregate,
)
from src.schemas.tokenization import (
    CitizenActivityRequest, BusinessSubmissionRequest,
    MilestoneVerificationRequest, WorkerCheckInRequest,
    DataTokenResponse, CitizenActivityResponse,
    BusinessCreditResponse, ContractMilestoneResponse,
    WorkerResponse, DisbursementResponse,
    TokenizationStatusResponse, TokenizationAggregateResponse,
)
from src.engines.tokenization_engine import (
    TokenizationEngine, CrossValidationEngine,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/tokenization", tags=["Data Tokenization"])


# ── Helper ────────────────────────────────────────────────────────────

def _get_country(db: Session, cc: str) -> Country:
    country = db.query(Country).filter(Country.code == cc.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {cc} not found")
    return country


# ── 1. Dashboard ──────────────────────────────────────────────────────

@router.get("/status", response_model=TokenizationStatusResponse)
async def tokenization_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tokenization dashboard overview. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/status", cost_multiplier=1.0)

    total = db.query(func.count(DataToken.id)).scalar() or 0

    # By pillar
    pillar_rows = (
        db.query(DataToken.pillar, func.count(DataToken.id))
        .group_by(DataToken.pillar)
        .all()
    )
    tokens_by_pillar = {r[0]: r[1] for r in pillar_rows}

    # By country
    country_rows = (
        db.query(Country.code, func.count(DataToken.id))
        .join(Country, DataToken.country_id == Country.id)
        .group_by(Country.code)
        .all()
    )
    tokens_by_country = {r[0]: r[1] for r in country_rows}

    # Totals
    total_paid = (
        db.query(func.coalesce(func.sum(PaymentDisbursement.amount_cfa), 0.0))
        .filter(PaymentDisbursement.status == "completed")
        .scalar()
    ) or 0.0

    total_credits = (
        db.query(func.coalesce(func.sum(TaxCreditLedger.amount_cfa), 0.0))
        .filter(TaxCreditLedger.credit_type == "EARNED")
        .scalar()
    ) or 0.0

    countries_active = len(tokens_by_country)

    latest_agg = (
        db.query(func.max(TokenizationDailyAggregate.period_date)).scalar()
    )

    return TokenizationStatusResponse(
        total_tokens=total,
        tokens_by_pillar=tokens_by_pillar,
        tokens_by_country=tokens_by_country,
        total_paid_cfa=total_paid,
        total_tax_credits_cfa=total_credits,
        countries_active=countries_active,
        latest_aggregate_date=latest_agg,
    )


# ── 2. Tokens by country ─────────────────────────────────────────────

@router.get("/tokens/{country_code}", response_model=list[DataTokenResponse])
async def get_tokens(
    country_code: str = Path(..., min_length=2, max_length=2),
    days: int = Query(default=30, ge=1, le=365),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides days."),
    pillar: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tokens by country. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/tokens", cost_multiplier=1.0)
    country = _get_country(db, country_code)

    q = db.query(DataToken).filter(DataToken.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        q = q.filter(DataToken.period_date.between(q_start, q_end))
    else:
        cutoff = date.today() - timedelta(days=days)
        q = q.filter(DataToken.period_date >= cutoff)

    if pillar:
        q = q.filter(DataToken.pillar == pillar.upper())

    tokens = q.order_by(DataToken.period_date.desc()).limit(500).all()
    return tokens


# ── 3. Citizen activities ─────────────────────────────────────────────

@router.get("/activities/{country_code}", response_model=list[CitizenActivityResponse])
async def get_activities(
    country_code: str = Path(..., min_length=2, max_length=2),
    days: int = Query(default=7, ge=1, le=90),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides days."),
    activity_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Citizen activity declarations. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/activities", cost_multiplier=1.0)
    country = _get_country(db, country_code)

    q = db.query(DailyActivityDeclaration).filter(DailyActivityDeclaration.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        q = q.filter(DailyActivityDeclaration.period_date.between(q_start, q_end))
    else:
        cutoff = date.today() - timedelta(days=days)
        q = q.filter(DailyActivityDeclaration.period_date >= cutoff)

    if activity_type:
        q = q.filter(DailyActivityDeclaration.activity_type == activity_type.upper())

    return q.order_by(DailyActivityDeclaration.period_date.desc()).limit(500).all()


# ── 4. Business submission ────────────────────────────────────────────

@router.post("/business/submit")
async def submit_business_data(
    req: BusinessSubmissionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit business data for tax credits. Costs 2 credits."""
    deduct_credits(current_user, db, "/api/v3/tokenization/business/submit", cost_multiplier=2.0)

    engine = TokenizationEngine(db)
    phone_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), current_user.username.encode("utf-8"), hashlib.sha256).hexdigest()

    result = engine.create_business_token(
        country_code=req.country_code.upper(),
        business_phone_hash=phone_hash,
        business_type=req.business_type.upper(),
        metric_type=req.metric_type.upper(),
        metrics_json=req.metrics,
        period_date=req.period_date,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── 5. Tax credits by country ────────────────────────────────────────

@router.get("/business/{country_code}/credits")
async def get_business_credits(
    country_code: str = Path(..., min_length=2, max_length=2),
    fiscal_year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tax credit summary per business. Costs 2 credits."""
    deduct_credits(current_user, db, "/api/v3/tokenization/business/credits", cost_multiplier=2.0)
    country = _get_country(db, country_code)

    year = fiscal_year or date.today().year

    # Aggregate per business
    rows = (
        db.query(
            TaxCreditLedger.business_phone_hash,
            TaxCreditLedger.tier,
            func.sum(TaxCreditLedger.amount_cfa).label("total"),
        )
        .filter(
            TaxCreditLedger.country_id == country.id,
            TaxCreditLedger.fiscal_year == year,
            TaxCreditLedger.credit_type == "EARNED",
        )
        .group_by(TaxCreditLedger.business_phone_hash, TaxCreditLedger.tier)
        .all()
    )

    # Build per-business summaries
    from collections import defaultdict
    biz_map = defaultdict(lambda: {"A": 0.0, "B": 0.0, "C": 0.0})
    for r in rows:
        biz_map[r.business_phone_hash][r.tier] += r.total

    cap = 5_000_000.0
    result = []
    for phone_hash, tiers in biz_map.items():
        earned = sum(tiers.values())
        # Get used credits
        used = (
            db.query(func.coalesce(func.sum(TaxCreditLedger.amount_cfa), 0.0))
            .filter(
                TaxCreditLedger.business_phone_hash == phone_hash,
                TaxCreditLedger.fiscal_year == year,
                TaxCreditLedger.credit_type == "USED",
            )
            .scalar()
        ) or 0.0

        result.append(BusinessCreditResponse(
            business_phone_hash=phone_hash,
            fiscal_year=year,
            cumulative_earned_cfa=earned,
            cumulative_used_cfa=used,
            remaining_cfa=max(0, earned - used),
            cap_absolute_cfa=cap,
            tier_breakdown=tiers,
        ))

    return result


# ── 6. Contract milestones ────────────────────────────────────────────

@router.get("/contracts/{country_code}", response_model=list[ContractMilestoneResponse])
async def get_contracts(
    country_code: str = Path(..., min_length=2, max_length=2),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contract milestones by country. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/contracts", cost_multiplier=1.0)
    country = _get_country(db, country_code)

    q = db.query(ContractMilestone).filter(ContractMilestone.country_id == country.id)
    if status:
        q = q.filter(ContractMilestone.status == status.lower())

    return q.order_by(ContractMilestone.contract_id, ContractMilestone.milestone_number).all()


# ── 7. Milestone verification (FREE) ─────────────────────────────────

@router.post("/contracts/{contract_id}/verify")
async def verify_milestone(
    contract_id: str,
    req: MilestoneVerificationRequest,
    milestone_number: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Citizen milestone verification. FREE (0 credits) to encourage participation."""
    # No credit deduction — civic duty is free

    milestone = (
        db.query(ContractMilestone)
        .filter(
            ContractMilestone.contract_id == contract_id,
            ContractMilestone.milestone_number == milestone_number,
        )
        .first()
    )
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    engine = TokenizationEngine(db)
    phone_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), current_user.username.encode("utf-8"), hashlib.sha256).hexdigest()

    result = engine.submit_milestone_verification(
        milestone_id=milestone.id,
        verifier_phone_hash=phone_hash,
        verifier_type=req.verifier_type.upper(),
        vote=req.vote.upper(),
        completion_pct=req.completion_pct,
        evidence_json=req.evidence,
        location_lat=req.location_lat,
        location_lon=req.location_lon,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── 8. Faso Meabo workers ─────────────────────────────────────────────

@router.get("/workers/{country_code}", response_model=list[WorkerResponse])
async def get_workers(
    country_code: str = Path(..., min_length=2, max_length=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Faso Meabo workers by country. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/workers", cost_multiplier=1.0)
    country = _get_country(db, country_code)

    return (
        db.query(FasoMeaboWorker)
        .filter(FasoMeaboWorker.country_id == country.id)
        .order_by(FasoMeaboWorker.total_days_worked.desc())
        .limit(500)
        .all()
    )


# ── 9. Disbursement history ──────────────────────────────────────────

@router.get("/payments/{country_code}", response_model=list[DisbursementResponse])
async def get_payments(
    country_code: str = Path(..., min_length=2, max_length=2),
    days: int = Query(default=30, ge=1, le=365),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides days."),
    payment_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Payment disbursement history. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/tokenization/payments", cost_multiplier=1.0)
    country = _get_country(db, country_code)

    q = db.query(PaymentDisbursement).filter(PaymentDisbursement.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        q = q.filter(PaymentDisbursement.queued_at >= q_start, PaymentDisbursement.queued_at <= q_end)
    else:
        cutoff = date.today() - timedelta(days=days)
        q = q.filter(PaymentDisbursement.queued_at >= cutoff)

    if payment_type:
        q = q.filter(PaymentDisbursement.payment_type == payment_type.upper())

    return q.order_by(PaymentDisbursement.queued_at.desc()).limit(500).all()


# ── 10. Trigger aggregation ──────────────────────────────────────────

@router.post("/aggregate/calculate")
async def calculate_aggregation(
    period_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger tokenization aggregation. Costs 5 credits."""
    deduct_credits(
        current_user, db, "/api/v3/tokenization/aggregate/calculate", cost_multiplier=5.0
    )

    from src.tasks.tokenization_aggregation import run_tokenization_aggregation
    result = run_tokenization_aggregation(db)
    return result
