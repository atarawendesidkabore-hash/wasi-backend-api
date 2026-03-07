"""
Data Truth API — /api/v3/data-truth/

G5: Cross-source validation (2+ sources must converge within tolerance).
G6: Staleness detection (data age thresholds).
G7: Statistical anomaly detection (z-score rejection).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.data_truth_engine import (
    run_data_truth_check,
    validate_country_data,
    record_truth_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/data-truth", tags=["Data Truth"])
limiter = Limiter(key_func=get_remote_address)


# ── Schemas ──────────────────────────────────────────────────────────────────

class AuditRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    metric_name: str = Field(..., min_length=1, max_length=100)
    source_a: str = Field(..., min_length=1, max_length=100)
    source_b: str = Field(..., min_length=1, max_length=100)
    value_a: float
    value_b: float


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{country_code}")
@limiter.limit("30/minute")
def get_country_truth(
    country_code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Full data truth assessment: G5+G6+G7 checks, macro cross-reference, active vetoes."""
    code = country_code.strip().upper()
    deduct_credits(current_user, db, f"/api/v3/data-truth/{code}", method="GET", cost_multiplier=2.0)
    result = validate_country_data(db, code)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/{country_code}/quick")
@limiter.limit("30/minute")
def get_country_truth_quick(
    country_code: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Quick G6+G7 truth check (staleness + anomaly only, no macro cross-reference)."""
    code = country_code.strip().upper()
    deduct_credits(current_user, db, f"/api/v3/data-truth/{code}/quick", method="GET", cost_multiplier=1.0)
    result = run_data_truth_check(code, db)
    if not result.get("checks") and result.get("overall_confidence_penalty", 0) >= 1.0:
        raise HTTPException(404, result.get("message", f"Country {code} not found"))
    return result


@router.post("/audit")
@limiter.limit("10/minute")
def create_truth_audit(
    request: Request,
    payload: AuditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """G5 cross-source validation audit: compare two data sources and persist result."""
    deduct_credits(current_user, db, "/api/v3/data-truth/audit", method="POST", cost_multiplier=3.0)
    audit = record_truth_audit(
        db=db,
        country_code=payload.country_code,
        metric_name=payload.metric_name,
        source_a=payload.source_a,
        source_b=payload.source_b,
        value_a=payload.value_a,
        value_b=payload.value_b,
    )
    return {
        "audit_id": audit.id,
        "country_code": audit.country_code,
        "metric_name": audit.metric_name,
        "verdict": audit.verdict,
        "divergence_pct": audit.divergence_pct,
        "confidence_after": audit.confidence_after,
        "details": audit.details,
    }
