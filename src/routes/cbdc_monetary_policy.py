"""
eCFA CBDC Monetary Policy Routes — /api/v3/ecfa/monetary-policy/

BCEAO central bank monetary policy operations:
  - Policy rate management (taux directeur, corridor rates)
  - Reserve requirement monitoring and enforcement
  - Standing facility operations (lending/deposit windows)
  - Interest accrual and demurrage control
  - M0/M1/M2 money supply dashboard
  - Monetary Policy Committee decision recording
  - Collateral framework management

Credit costs:
  GET  /rates/current                — 1 credit
  POST /rates/set                    — 20 credits
  GET  /rates/history/{type}         — 2 credits
  GET  /reserves/status              — 5 credits
  POST /reserves/set-ratio           — 20 credits
  POST /facility/lending/open        — 10 credits
  POST /facility/deposit/open        — 10 credits
  POST /facility/mature              — 10 credits
  POST /interest/apply-daily         — 10 credits
  GET  /money-supply                 — 3 credits
  GET  /money-supply/{cc}            — 3 credits
  GET  /aggregates/{cc}              — 5 credits
  POST /decision/record              — 20 credits
  GET  /decision/history             — 3 credits
  POST /collateral/register          — 5 credits
  GET  /collateral/list              — 2 credits
"""
import uuid
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.cbdc_models import CbdcEligibleCollateral
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.cbdc_monetary_policy_engine import CbdcMonetaryPolicyEngine
from src.schemas.cbdc_monetary_policy import (
    SetPolicyRateRequest, SetPolicyRateResponse,
    RateHistoryResponse,
    SetReserveRatioRequest, ReserveRequirementResponse,
    OpenLendingRequest, OpenDepositRequest,
    FacilityResponse, FacilityMaturityResponse,
    DailyInterestResponse,
    MoneySupplyResponse, EnhancedAggregateResponse,
    PolicyDecisionRequest, PolicyDecisionResponse, PolicyDecisionHistoryItem,
    RegisterCollateralRequest, CollateralResponse,
)

router = APIRouter(prefix="/api/v3/ecfa/monetary-policy", tags=["eCFA Monetary Policy"])
limiter = Limiter(key_func=get_remote_address)


# ── Policy Rates ─────────────────────────────────────────────────────

@router.get("/rates/current")
@limiter.limit("30/minute")
async def get_current_rates(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all current BCEAO policy rates (taux directeur, corridor, reserves)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/rates/current", "GET", 1.0)
    engine = CbdcMonetaryPolicyEngine(db)
    return engine.get_current_rates()


@router.post("/rates/set", response_model=SetPolicyRateResponse)
@limiter.limit("5/minute")
async def set_policy_rate(
    request: Request,
    body: SetPolicyRateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set a new BCEAO policy rate.

    When taux_directeur changes, corridor rates auto-adjust (±200bp).
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/rates/set", "POST", 20.0)
    engine = CbdcMonetaryPolicyEngine(db)
    try:
        result = engine.set_policy_rate(
            rate_type=body.rate_type,
            new_rate_percent=body.new_rate_percent,
            rationale=body.rationale,
            effective_date=body.effective_date,
        )
        return SetPolicyRateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/rates/history/{rate_type}", response_model=RateHistoryResponse)
@limiter.limit("20/minute")
async def get_rate_history(
    request: Request,
    rate_type: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get historical changes for a specific rate type."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/rates/history", "GET", 2.0)
    engine = CbdcMonetaryPolicyEngine(db)
    history = engine.get_rate_history(rate_type.upper(), limit)
    return RateHistoryResponse(rate_type=rate_type.upper(), history=history)


# ── Reserve Requirements ─────────────────────────────────────────────

@router.get("/reserves/status", response_model=ReserveRequirementResponse)
@limiter.limit("10/minute")
async def get_reserve_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute and return reserve requirement compliance for all banks."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/reserves/status", "GET", 5.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.compute_reserve_requirements()
    return ReserveRequirementResponse(**result)


@router.post("/reserves/set-ratio")
@limiter.limit("3/minute")
async def set_reserve_ratio(
    request: Request,
    body: SetReserveRatioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set a new reserve requirement ratio for all commercial banks."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/reserves/set-ratio", "POST", 20.0)
    engine = CbdcMonetaryPolicyEngine(db)
    return engine.set_reserve_ratio(body.new_ratio_percent)


# ── Standing Facilities ──────────────────────────────────────────────

@router.post("/facility/lending/open", response_model=FacilityResponse)
@limiter.limit("10/minute")
async def open_lending_facility(
    request: Request,
    body: OpenLendingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bank borrows from BCEAO at taux de prêt marginal."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/facility/lending", "POST", 10.0)
    engine = CbdcMonetaryPolicyEngine(db)
    try:
        result = engine.open_lending_facility(
            bank_wallet_id=body.bank_wallet_id,
            amount_ecfa=body.amount_ecfa,
            maturity=body.maturity,
            collateral_id=body.collateral_id,
        )
        return FacilityResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/facility/deposit/open", response_model=FacilityResponse)
@limiter.limit("10/minute")
async def open_deposit_facility(
    request: Request,
    body: OpenDepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bank deposits excess liquidity at BCEAO at taux de dépôt."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/facility/deposit", "POST", 10.0)
    engine = CbdcMonetaryPolicyEngine(db)
    try:
        result = engine.open_deposit_facility(
            bank_wallet_id=body.bank_wallet_id,
            amount_ecfa=body.amount_ecfa,
        )
        return FacilityResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/facility/mature", response_model=FacilityMaturityResponse)
@limiter.limit("5/minute")
async def mature_facilities(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process all matured standing facilities (repay lending, return deposits)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/facility/mature", "POST", 10.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.mature_facilities()
    return FacilityMaturityResponse(**result)


# ── Interest & Demurrage ─────────────────────────────────────────────

@router.post("/interest/apply-daily", response_model=DailyInterestResponse)
@limiter.limit("2/minute")
async def apply_daily_interest(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply daily interest accrual and demurrage across all wallets."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/interest/apply-daily", "POST", 10.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.apply_daily_interest()
    return DailyInterestResponse(**result)


# ── Money Supply Dashboard ───────────────────────────────────────────

@router.get("/money-supply", response_model=MoneySupplyResponse)
@limiter.limit("20/minute")
async def get_money_supply_all(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get WAEMU-wide M0/M1/M2 money supply."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/money-supply", "GET", 3.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.compute_money_supply()
    return MoneySupplyResponse(**result)


@router.get("/money-supply/{country_code}", response_model=MoneySupplyResponse)
@limiter.limit("20/minute")
async def get_money_supply_country(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get M0/M1/M2 money supply for a specific WAEMU country."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/money-supply/cc", "GET", 3.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.compute_money_supply(country_code.upper())
    return MoneySupplyResponse(**result)


@router.get("/aggregates/{country_code}", response_model=EnhancedAggregateResponse)
@limiter.limit("10/minute")
async def get_enhanced_aggregates(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full monetary aggregates: M0/M1/M2 + policy rates + reserves + facilities."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/aggregates", "GET", 5.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.compute_enhanced_monetary_aggregates(country_code.upper())
    return EnhancedAggregateResponse(**result)


# ── Monetary Policy Decisions ────────────────────────────────────────

@router.post("/decision/record", response_model=PolicyDecisionResponse)
@limiter.limit("3/minute")
async def record_policy_decision(
    request: Request,
    body: PolicyDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a Comité de Politique Monétaire decision and apply rate changes."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/decision/record", "POST", 20.0)
    engine = CbdcMonetaryPolicyEngine(db)
    result = engine.record_policy_decision(
        meeting_date=body.meeting_date,
        decision_summary=body.decision_summary,
        rationale=body.rationale,
        taux_directeur=body.taux_directeur,
        taux_pret_marginal=body.taux_pret_marginal,
        taux_depot=body.taux_depot,
        reserve_ratio=body.reserve_ratio,
        meeting_type=body.meeting_type,
        inflation_rate=body.inflation_rate,
        gdp_growth=body.gdp_growth,
        votes_for=body.votes_for,
        votes_against=body.votes_against,
        votes_abstain=body.votes_abstain,
        effective_date=body.effective_date,
    )
    return PolicyDecisionResponse(**result)


@router.get("/decision/history", response_model=list[PolicyDecisionHistoryItem])
@limiter.limit("20/minute")
async def get_decision_history(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get history of monetary policy committee decisions."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/decision/history", "GET", 3.0)
    engine = CbdcMonetaryPolicyEngine(db)
    history = engine.get_decision_history(limit)
    return [PolicyDecisionHistoryItem(**item) for item in history]


# ── Collateral Framework ─────────────────────────────────────────────

@router.post("/collateral/register", response_model=CollateralResponse)
@limiter.limit("10/minute")
async def register_collateral(
    request: Request,
    body: RegisterCollateralRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register an eligible collateral asset for lending facility operations."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/collateral/register", "POST", 5.0)

    collateral_value = body.market_value_ecfa * (1.0 - body.haircut_percent / 100.0)

    coll = CbdcEligibleCollateral(
        collateral_id=str(uuid.uuid4()),
        asset_class=body.asset_class,
        asset_description=body.asset_description,
        issuer=body.issuer,
        issuer_country=body.issuer_country,
        face_value_ecfa=body.face_value_ecfa,
        market_value_ecfa=body.market_value_ecfa,
        haircut_percent=body.haircut_percent,
        collateral_value_ecfa=round(collateral_value, 2),
        min_credit_rating=body.min_credit_rating,
        maturity_date=body.maturity_date,
        owner_wallet_id=body.owner_wallet_id,
        effective_date=date.today(),
    )
    db.add(coll)
    db.commit()
    db.refresh(coll)

    return CollateralResponse(
        collateral_id=coll.collateral_id,
        asset_class=coll.asset_class,
        asset_description=coll.asset_description,
        face_value_ecfa=coll.face_value_ecfa,
        market_value_ecfa=coll.market_value_ecfa,
        haircut_percent=coll.haircut_percent,
        collateral_value_ecfa=coll.collateral_value_ecfa,
        is_pledged=coll.is_pledged,
        is_eligible=coll.is_eligible,
    )


@router.get("/collateral/list", response_model=list[CollateralResponse])
@limiter.limit("20/minute")
async def list_collateral(
    request: Request,
    eligible_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List eligible collateral assets."""
    deduct_credits(current_user, db, "/api/v3/ecfa/monetary-policy/collateral/list", "GET", 2.0)

    query = db.query(CbdcEligibleCollateral)
    if eligible_only:
        query = query.filter(CbdcEligibleCollateral.is_eligible == True)

    items = query.order_by(CbdcEligibleCollateral.created_at.desc()).limit(100).all()

    return [CollateralResponse(
        collateral_id=c.collateral_id,
        asset_class=c.asset_class,
        asset_description=c.asset_description,
        face_value_ecfa=c.face_value_ecfa,
        market_value_ecfa=c.market_value_ecfa,
        haircut_percent=c.haircut_percent,
        collateral_value_ecfa=c.collateral_value_ecfa,
        is_pledged=c.is_pledged,
        is_eligible=c.is_eligible,
    ) for c in items]
