"""
Sovereign Veto + Data Truth API routes.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from src.database.connection import get_db
from src.database.models import User, CountryIndex, Country
from src.database.sovereign_models import SovereignVeto, DataTruthAudit
from src.engines.sovereign_veto_engine import (
    check_sovereign_veto, issue_veto, revoke_veto, get_active_vetoes, VETO_TYPES,
)
from src.engines.data_truth_engine import (
    check_cross_source, check_staleness, check_anomaly,
    run_data_truth_check, record_truth_audit, validate_country_data,
)
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits
from src.utils.ml_guardrails import run_guardrails

router = APIRouter(prefix="/api/v1", tags=["Sovereign Veto and Data Truth"])
ADVISORY = "Advisory only. Decision finale = validation humaine."
limiter = Limiter(key_func=get_remote_address)


class VetoIssueRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    veto_type: str = Field(...)
    reason: str = Field(..., min_length=10, max_length=1000)
    issued_by: str = Field(..., min_length=2, max_length=100)
    effective_date: date
    expiry_date: Optional[date] = None
    severity: str = Field(default="FULL_BLOCK")
    max_loan_cap_usd: Optional[float] = Field(None, ge=0)
    reference_number: Optional[str] = None
    legal_basis: Optional[str] = None


class VetoRevokeRequest(BaseModel):
    veto_id: int
    revoked_by: str = Field(..., min_length=2, max_length=100)


class CrossSourceRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    metric_name: str = Field(..., max_length=100)
    source_a: str = Field(..., max_length=50)
    source_b: str = Field(..., max_length=50)
    value_a: float
    value_b: float


@router.get("/sovereign/check/{country_code}")
@limiter.limit("30/minute")
async def check_veto(
    request: Request,
    country_code: str,
    loan_amount_usd: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/api/v1/sovereign/check", cost_multiplier=1.0)
    result = check_sovereign_veto(country_code, db, loan_amount_usd)
    return {"status": "ok", "data": result}


@router.get("/sovereign/list")
@limiter.limit("20/minute")
async def list_all_vetoes(
    request: Request,
    country_code: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/api/v1/sovereign/list", cost_multiplier=1.0)
    if country_code:
        vetoes = get_active_vetoes(country_code, db)
    else:
        today = date.today()
        vetoes = (
            db.query(SovereignVeto)
            .filter(SovereignVeto.is_active.is_(True), SovereignVeto.effective_date <= today)
            .filter((SovereignVeto.expiry_date.is_(None)) | (SovereignVeto.expiry_date >= today))
            .all()
        )
    return {
        "status": "ok",
        "count": len(vetoes),
        "vetoes": [
            {
                "id": v.id, "country_code": v.country_code,
                "veto_type": v.veto_type, "severity": v.severity,
                "reason": v.reason, "issued_by": v.issued_by,
                "effective_date": str(v.effective_date),
                "expiry_date": str(v.expiry_date) if v.expiry_date else None,
            }
            for v in vetoes
        ],
    }


@router.post("/sovereign/issue")
@limiter.limit("5/minute")
async def issue_sovereign_veto(
    request: Request,
    req: VetoIssueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    if req.veto_type not in VETO_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid veto_type. Valid: {sorted(VETO_TYPES)}")
    if req.severity not in ("FULL_BLOCK", "PARTIAL"):
        raise HTTPException(status_code=422, detail="severity must be FULL_BLOCK or PARTIAL.")
    veto = issue_veto(
        db=db, country_code=req.country_code,
        veto_type=req.veto_type, reason=req.reason,
        issued_by=req.issued_by, effective_date=req.effective_date,
        expiry_date=req.expiry_date, severity=req.severity,
        max_loan_cap_usd=req.max_loan_cap_usd, reference_number=req.reference_number,
    )
    return {"status": "ok", "message": f"Sovereign veto issued for {req.country_code.upper()}", "veto_id": veto.id}


@router.post("/sovereign/revoke")
@limiter.limit("5/minute")
async def revoke_sovereign_veto_ep(
    request: Request,
    req: VetoRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    try:
        veto = revoke_veto(db, req.veto_id, req.revoked_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "ok", "message": f"Veto {req.veto_id} revoked for {veto.country_code}"}


@router.get("/data-truth/check/{country_code}")
@limiter.limit("20/minute")
async def data_truth_check(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/api/v1/data-truth/check", cost_multiplier=2.0)
    result = run_data_truth_check(country_code, db)
    return {"status": "ok", "data": result}


@router.post("/data-truth/cross-source")
@limiter.limit("10/minute")
async def cross_source_audit(
    request: Request,
    req: CrossSourceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/api/v1/data-truth/cross-source", cost_multiplier=2.0)
    audit = record_truth_audit(
        db=db, country_code=req.country_code, metric_name=req.metric_name,
        source_a=req.source_a, source_b=req.source_b,
        value_a=req.value_a, value_b=req.value_b,
    )
    return {
        "status": "ok", "audit_id": audit.id,
        "verdict": audit.verdict, "divergence_pct": audit.divergence_pct,
        "confidence_after": audit.confidence_after, "details": audit.details,
    }


@router.get("/data-truth/audits/{country_code}")
@limiter.limit("20/minute")
async def list_truth_audits(
    request: Request,
    country_code: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/api/v1/data-truth/audits", cost_multiplier=1.0)
    audits = (
        db.query(DataTruthAudit)
        .filter(DataTruthAudit.country_code == country_code.upper())
        .order_by(DataTruthAudit.audited_at.desc())
        .limit(min(limit, 100)).all()
    )
    return {
        "status": "ok", "count": len(audits),
        "audits": [
            {
                "id": a.id, "metric_name": a.metric_name,
                "source_a": a.source_a, "source_b": a.source_b,
                "value_a": a.value_a, "value_b": a.value_b,
                "divergence_pct": a.divergence_pct, "verdict": a.verdict,
                "confidence_after": a.confidence_after,
                "audited_at": str(a.audited_at),
            }
            for a in audits
        ],
    }


@router.get("/sovereign/guardrails/{country_code}")
@limiter.limit("15/minute")
async def run_full_guardrails(request: Request, country_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    deduct_credits(current_user, db, "/api/v1/sovereign/guardrails", cost_multiplier=5.0)
    truth_result = validate_country_data(db, country_code)
    if "error" in truth_result:
        raise HTTPException(status_code=404, detail=truth_result["error"])
    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    ml_result = None
    if country:
        latest = db.query(CountryIndex).filter(CountryIndex.country_id == country.id).order_by(CountryIndex.period_date.desc()).first()
        if latest:
            prev = db.query(CountryIndex).filter(CountryIndex.country_id == country.id, CountryIndex.period_date < latest.period_date).order_by(CountryIndex.period_date.desc()).first()
            ml_result = run_guardrails(confidence=latest.confidence or 1.0, index_value=latest.index_value, prev_index_value=prev.index_value if prev else None, shipping_score=latest.shipping_score, trade_score=latest.trade_score, infrastructure_score=latest.infrastructure_score, economic_score=latest.economic_score, context=f"{country_code.upper()} guardrail check")
    veto_result = check_sovereign_veto(country_code, db)
    return {"country_code": country_code.upper(), "ml_guardrails_g1_g4": ml_result, "data_truth_g5_g6_g7": {"overall_truth_score": truth_result.get("overall_truth_score"), "overall_verdict": truth_result.get("overall_verdict"), "checks": truth_result.get("checks", [])}, "sovereign_veto": veto_result, "combined": {"blocked": veto_result["blocked"], "human_review_required": truth_result.get("human_review_required", False) or (ml_result and ml_result.get("human_review", {}).get("required", False)) or veto_result["blocked"] or veto_result["partial"], "overall_confidence": truth_result.get("overall_truth_score", 0.0)}, "advisory": ADVISORY}
