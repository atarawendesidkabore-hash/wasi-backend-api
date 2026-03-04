"""
Data Integrity API — /api/v3/integrity/

8 endpoints for data quality monitoring, anomaly quarantine management,
and data lineage tracing.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.reconciliation_engine import ReconciliationEngine
from src.database.reconciliation_models import DataQuarantine, DataSourceHealth
from src.schemas.reconciliation import QuarantineResolveRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/integrity", tags=["Data Integrity"])
limiter = Limiter(key_func=get_remote_address)


# ── Static routes ─────────────────────────────────────────────────

@router.get("/dashboard")
@limiter.limit("30/minute")
def integrity_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Source health + quality scorecard + freshness overview."""
    deduct_credits(current_user, db, "/api/v3/integrity/dashboard", method="GET", cost_multiplier=3.0)
    engine = ReconciliationEngine(db)
    return engine.get_integrity_dashboard()


@router.get("/sources")
@limiter.limit("30/minute")
def list_sources(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """All data source health statuses."""
    deduct_credits(current_user, db, "/api/v3/integrity/sources", method="GET", cost_multiplier=1.0)
    sources = db.query(DataSourceHealth).order_by(DataSourceHealth.source_name).all()
    return {
        "sources": [
            {
                "source": s.source_name,
                "status": s.status,
                "reliability": round(s.reliability_score, 4),
                "fetch_count": s.fetch_count,
                "error_count": s.error_count,
                "avg_latency_ms": round(s.avg_latency_ms, 1),
                "last_success": str(s.last_success_at) if s.last_success_at else None,
            }
            for s in sources
        ],
        "count": len(sources),
    }


@router.get("/quarantine")
@limiter.limit("30/minute")
def list_quarantine(
    request: Request,
    status: str = Query(default=None, description="Filter: PENDING|APPROVED|REJECTED"),
    severity: str = Query(default=None, description="Filter: LOW|MEDIUM|HIGH|CRITICAL"),
    anomaly_type: str = Query(default=None, description="Filter: Z_SCORE|RATE_OF_CHANGE|CROSS_SOURCE|STALE|MISSING_CRITICAL"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Paginated quarantine queue with filters."""
    deduct_credits(current_user, db, "/api/v3/integrity/quarantine", method="GET", cost_multiplier=2.0)

    query = db.query(DataQuarantine)
    if status:
        query = query.filter(DataQuarantine.status == status.upper())
    if severity:
        query = query.filter(DataQuarantine.severity == severity.upper())
    if anomaly_type:
        query = query.filter(DataQuarantine.anomaly_type == anomaly_type.upper())

    total = query.count()
    items = (
        query.order_by(DataQuarantine.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "items": [
            {
                "id": q.id,
                "table_name": q.table_name,
                "record_id": q.record_id,
                "country_code": q.country_code,
                "anomaly_type": q.anomaly_type,
                "anomaly_detail": q.anomaly_detail,
                "severity": q.severity,
                "status": q.status,
                "created_at": q.created_at.isoformat() + "Z" if q.created_at else None,
            }
            for q in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/anomalies")
@limiter.limit("30/minute")
def recent_anomalies(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recent anomalies within the last N hours."""
    deduct_credits(current_user, db, "/api/v3/integrity/anomalies", method="GET", cost_multiplier=2.0)

    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = (
        db.query(DataQuarantine)
        .filter(DataQuarantine.created_at >= cutoff)
        .order_by(DataQuarantine.id.desc())
        .limit(100)
        .all()
    )

    return {
        "hours": hours,
        "count": len(items),
        "anomalies": [
            {
                "id": q.id,
                "table_name": q.table_name,
                "country_code": q.country_code,
                "anomaly_type": q.anomaly_type,
                "severity": q.severity,
                "status": q.status,
                "created_at": q.created_at.isoformat() + "Z" if q.created_at else None,
            }
            for q in items
        ],
    }


@router.post("/reconcile")
@limiter.limit("5/minute")
def trigger_reconciliation(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Trigger a manual full reconciliation run."""
    deduct_credits(current_user, db, "/api/v3/integrity/reconcile", method="POST", cost_multiplier=10.0)
    engine = ReconciliationEngine(db)
    result = engine.run_full_reconciliation(run_type="MANUAL")
    return result


# ── Dynamic routes ────────────────────────────────────────────────

@router.get("/quarantine/{quarantine_id}")
@limiter.limit("30/minute")
def quarantine_detail(
    quarantine_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Single quarantine record detail."""
    deduct_credits(current_user, db, f"/api/v3/integrity/quarantine/{quarantine_id}", method="GET", cost_multiplier=1.0)
    q = db.query(DataQuarantine).filter(DataQuarantine.id == quarantine_id).first()
    if not q:
        raise HTTPException(404, "Quarantine record not found")

    return {
        "id": q.id,
        "table_name": q.table_name,
        "record_id": q.record_id,
        "country_code": q.country_code,
        "anomaly_type": q.anomaly_type,
        "anomaly_detail": q.anomaly_detail,
        "severity": q.severity,
        "status": q.status,
        "reviewed_by": q.reviewed_by,
        "reviewed_at": q.reviewed_at.isoformat() + "Z" if q.reviewed_at else None,
        "created_at": q.created_at.isoformat() + "Z" if q.created_at else None,
    }


@router.put("/quarantine/{quarantine_id}/resolve")
@limiter.limit("30/minute")
def resolve_quarantine(
    quarantine_id: int,
    body: QuarantineResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Approve or reject a quarantined record."""
    engine = ReconciliationEngine(db)
    result = engine.resolve_quarantine(quarantine_id, body.action, current_user.id)
    if not result:
        raise HTTPException(404, "Quarantine record not found or invalid action")
    return result


@router.get("/lineage/{table_name}/{record_id}")
@limiter.limit("30/minute")
def get_lineage(
    table_name: str,
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Data lineage for a specific record."""
    deduct_credits(current_user, db, f"/api/v3/integrity/lineage/{table_name}/{record_id}", method="GET", cost_multiplier=2.0)
    engine = ReconciliationEngine(db)
    sources = engine.get_lineage(table_name, record_id)
    return {
        "target_table": table_name,
        "target_id": record_id,
        "sources": sources,
        "count": len(sources),
    }
