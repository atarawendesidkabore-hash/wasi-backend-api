"""
eCFA CBDC Central Bank Admin — /api/v3/ecfa/admin/

Endpoints for BCEAO central bank operations: policy management,
monetary aggregates, settlement oversight, and AML dashboard.

Credit costs:
  POST /policy/create              — 10 credits
  GET  /policy/list                — 1 credit
  GET  /monetary-aggregates/{cc}   — 3 credits
  GET  /settlement/pending         — 2 credits
  POST /settlement/run-domestic    — 10 credits
  POST /settlement/run-cross-border — 10 credits
  GET  /aml/dashboard              — 3 credits
  POST /aml/resolve/{alert_id}     — 5 credits
  GET  /aml/alerts                 — 2 credits
"""
import uuid
from datetime import timezone, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.cbdc_models import (
    CbdcPolicy, CbdcSettlement, CbdcAmlAlert, CbdcMonetaryAggregate,
)
from src.utils.security import get_current_user, require_cbdc_role, require_admin
from src.utils.credits import deduct_credits
from src.engines.cbdc_settlement_engine import CbdcSettlementEngine
from src.engines.cbdc_compliance_engine import CbdcComplianceEngine
from src.utils.cbdc_cobol import format_settlement_cobol
from src.schemas.cbdc_admin import (
    PolicyCreateRequest, PolicyResponse,
    MonetaryAggregateResponse, SettlementResponse, SettlementRunResponse,
    AmlAlertResponse, AmlResolveRequest, ComplianceSweepResponse,
)

router = APIRouter(prefix="/api/v3/ecfa/admin", tags=["eCFA Admin"])
limiter = Limiter(key_func=get_remote_address)


# ── Policy Management ─────────────────────────────────────────────────

@router.post("/policy/create", response_model=PolicyResponse)
@limiter.limit("5/minute")
async def create_policy(
    request: Request,
    body: PolicyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Create a programmable money policy (Central Bank only)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/policy/create", "POST", 10.0)

    policy = CbdcPolicy(
        policy_id=str(uuid.uuid4()),
        policy_name=body.policy_name,
        policy_type=body.policy_type,
        conditions=body.conditions,
        country_codes=body.country_codes,
        wallet_types=body.wallet_types,
        effective_from=body.effective_from,
        effective_until=body.effective_until,
        created_by=body.admin_wallet_id,
        cobol_policy_code=body.cobol_policy_code,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)

    return PolicyResponse.model_validate(policy)


@router.get("/policy/list", response_model=list[PolicyResponse])
@limiter.limit("20/minute")
async def list_policies(
    request: Request,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK", "COMMERCIAL_BANK"])),
):
    """List programmable money policies."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/policy/list", "GET", 1.0)

    query = db.query(CbdcPolicy)
    if active_only:
        query = query.filter(CbdcPolicy.is_active == True)
    policies = query.order_by(CbdcPolicy.created_at.desc()).all()

    return [PolicyResponse.model_validate(p) for p in policies]


# ── Monetary Aggregates ───────────────────────────────────────────────

@router.get("/monetary-aggregates/{country_code}", response_model=MonetaryAggregateResponse)
@limiter.limit("20/minute")
async def get_monetary_aggregates(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Get daily monetary aggregates for a WAEMU country."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/monetary-aggregates", "GET", 3.0)

    engine = CbdcSettlementEngine(db)
    result = engine.compute_monetary_aggregates(country_code.upper())

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return MonetaryAggregateResponse(**result)


# ── Settlement ────────────────────────────────────────────────────────

@router.get("/settlement/pending", response_model=list[SettlementResponse])
@limiter.limit("20/minute")
async def get_pending_settlements(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """View pending settlements awaiting RTGS confirmation."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/settlement/pending", "GET", 2.0)

    settlements = db.query(CbdcSettlement).filter(
        CbdcSettlement.status == "pending"
    ).order_by(CbdcSettlement.created_at.desc()).limit(50).all()

    return [SettlementResponse.model_validate(s) for s in settlements]


@router.post("/settlement/run-domestic", response_model=SettlementRunResponse)
@limiter.limit("4/minute")
async def run_domestic_settlement(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Trigger domestic inter-bank netting settlement."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/settlement/run-domestic", "POST", 10.0)

    engine = CbdcSettlementEngine(db)
    result = engine.run_domestic_settlement()
    return SettlementRunResponse(**result)


@router.post("/settlement/run-cross-border", response_model=SettlementRunResponse)
@limiter.limit("4/minute")
async def run_cross_border_settlement(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Trigger cross-border WAEMU netting settlement."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/settlement/run-cross-border", "POST", 10.0)

    engine = CbdcSettlementEngine(db)
    result = engine.run_cross_border_settlement()
    return SettlementRunResponse(**result)


@router.get("/settlement/{settlement_id}/cobol")
@limiter.limit("20/minute")
async def get_settlement_cobol(
    request: Request,
    settlement_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Get COBOL-formatted settlement record for STAR-UEMOA."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/settlement/cobol", "GET", 2.0)

    settlement = db.query(CbdcSettlement).filter(
        CbdcSettlement.settlement_id == settlement_id
    ).first()
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")

    cobol_record = format_settlement_cobol({
        "settlement_id": settlement.settlement_id[:10],
        "settlement_type": settlement.settlement_type,
        "bank_a_code": settlement.bank_a_code,
        "bank_b_code": settlement.bank_b_code,
        "gross_amount_ecfa": settlement.gross_amount_ecfa,
        "net_amount_ecfa": settlement.net_amount_ecfa,
        "direction": settlement.direction,
        "transaction_count": settlement.transaction_count,
        "country_codes": settlement.country_codes,
        "window_start": settlement.window_start,
        "window_end": settlement.window_end,
        "status": settlement.status,
        "star_uemoa_ref": settlement.star_uemoa_ref or "",
    })

    return {
        "settlement_id": settlement.settlement_id,
        "cobol_record": cobol_record,
        "record_length": len(cobol_record),
        "format": "STAR-UEMOA fixed-width 200 chars",
    }


# ── AML Dashboard ────────────────────────────────────────────────────

@router.get("/aml/dashboard")
@limiter.limit("20/minute")
async def aml_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK", "COMMERCIAL_BANK"])),
):
    """AML alert dashboard summary."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/aml/dashboard", "GET", 3.0)

    from sqlalchemy import func

    # Count by status
    status_counts = db.query(
        CbdcAmlAlert.status, func.count(CbdcAmlAlert.id)
    ).group_by(CbdcAmlAlert.status).all()

    # Count by type
    type_counts = db.query(
        CbdcAmlAlert.alert_type, func.count(CbdcAmlAlert.id)
    ).group_by(CbdcAmlAlert.alert_type).all()

    # Count by severity
    severity_counts = db.query(
        CbdcAmlAlert.severity, func.count(CbdcAmlAlert.id)
    ).group_by(CbdcAmlAlert.severity).all()

    # SARs filed
    sars = db.query(CbdcAmlAlert).filter(CbdcAmlAlert.sar_filed == True).count()

    return {
        "by_status": {s: c for s, c in status_counts},
        "by_type": {t: c for t, c in type_counts},
        "by_severity": {s: c for s, c in severity_counts},
        "sars_filed": sars,
        "total_alerts": sum(c for _, c in status_counts),
    }


@router.get("/aml/alerts", response_model=list[AmlAlertResponse])
@limiter.limit("20/minute")
async def list_aml_alerts(
    request: Request,
    status: str = Query("open", description="open | under_review | escalated"),
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK", "COMMERCIAL_BANK"])),
):
    """List AML alerts filtered by status and severity."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/aml/alerts", "GET", 2.0)

    query = db.query(CbdcAmlAlert).filter(CbdcAmlAlert.status == status)
    if severity:
        query = query.filter(CbdcAmlAlert.severity == severity)

    alerts = query.order_by(CbdcAmlAlert.created_at.desc()).limit(limit).all()
    return [AmlAlertResponse.model_validate(a) for a in alerts]


@router.post("/aml/resolve/{alert_id}", response_model=AmlAlertResponse)
@limiter.limit("10/minute")
async def resolve_aml_alert(
    request: Request,
    alert_id: str,
    body: AmlResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Resolve an AML alert."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/aml/resolve", "POST", 5.0)

    alert = db.query(CbdcAmlAlert).filter(CbdcAmlAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    valid_resolutions = {"resolved_clear", "resolved_sar", "false_positive"}
    if body.resolution_status not in valid_resolutions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resolution. Must be one of: {', '.join(valid_resolutions)}",
        )

    alert.status = body.resolution_status
    alert.resolution_notes = body.resolution_notes
    alert.assigned_to = body.assigned_to
    alert.resolved_at = datetime.now(timezone.utc)

    if body.resolution_status == "resolved_sar":
        alert.sar_filed = True
        alert.sar_reference = f"SAR-{alert_id[:8].upper()}"

    db.commit()
    db.refresh(alert)

    return AmlAlertResponse.model_validate(alert)


@router.post("/aml/sweep", response_model=ComplianceSweepResponse)
@limiter.limit("2/minute")
async def run_compliance_sweep(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Trigger manual AML compliance sweep across all wallets with recent activity."""
    deduct_credits(current_user, db, "/api/v3/ecfa/admin/aml/sweep", "POST", 10.0)

    engine = CbdcComplianceEngine(db)
    result = engine.run_full_sweep()
    return ComplianceSweepResponse(**result)
