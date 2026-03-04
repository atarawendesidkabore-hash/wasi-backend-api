import os
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import timezone, datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db

router = APIRouter(tags=["Health"])
limiter = Limiter(key_func=get_remote_address)

_BOOT_TIME = time.monotonic()


@router.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """Health check endpoint. Returns database connectivity status."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/health/detailed")
@limiter.limit("10/minute")
async def health_detailed(request: Request, db: Session = Depends(get_db)):
    """Detailed health check: DB, scheduler, data freshness, memory."""
    now = datetime.now(timezone.utc)

    # ── Database ──────────────────────────────────────────────────
    db_ok = True
    db_latency_ms = None
    try:
        t0 = time.monotonic()
        db.execute(text("SELECT 1"))
        db_latency_ms = round((time.monotonic() - t0) * 1000, 2)
    except Exception:
        db_ok = False

    # ── Table row counts (key tables only) ────────────────────────
    table_counts = {}
    try:
        from src.database.models import Country, CountryIndex, WASIComposite, User
        table_counts["countries"] = db.query(func.count(Country.id)).scalar()
        table_counts["country_indices"] = db.query(func.count(CountryIndex.id)).scalar()
        table_counts["composites"] = db.query(func.count(WASIComposite.id)).scalar()
        table_counts["users"] = db.query(func.count(User.id)).scalar()
    except Exception:
        pass

    # ── Data freshness ────────────────────────────────────────────
    freshness = {}
    try:
        from src.database.models import WASIComposite, CountryIndex
        latest_composite = db.query(func.max(WASIComposite.period_date)).scalar()
        latest_index = db.query(func.max(CountryIndex.period_date)).scalar()
        freshness["latest_composite_date"] = str(latest_composite) if latest_composite else None
        freshness["latest_index_date"] = str(latest_index) if latest_index else None
    except Exception:
        pass

    # ── Scheduler status ──────────────────────────────────────────
    scheduler_info = {"enabled": False, "running": False, "jobs": 0}
    try:
        from src.tasks.composite_update import (
            _scheduler, _apscheduler_available, get_scheduler_heartbeat,
        )
        from src.config import settings as cfg
        scheduler_info["enabled"] = _apscheduler_available and cfg.SCHEDULER_ENABLED
        if _scheduler and _apscheduler_available:
            scheduler_info["running"] = _scheduler.running
            scheduler_info["jobs"] = len(_scheduler.get_jobs())
            scheduler_info["job_names"] = [j.name for j in _scheduler.get_jobs()]
        scheduler_info["heartbeat"] = get_scheduler_heartbeat()
    except Exception:
        pass

    # ── Process info ──────────────────────────────────────────────
    uptime_seconds = round(time.monotonic() - _BOOT_TIME, 1)

    overall = "healthy" if db_ok else "degraded"

    return {
        "status": overall,
        "version": "3.0.0",
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime_seconds,
        "database": {
            "connected": db_ok,
            "latency_ms": db_latency_ms,
            "table_counts": table_counts,
        },
        "data_freshness": freshness,
        "scheduler": scheduler_info,
        "environment": {
            "debug": os.environ.get("DEBUG", "false").lower() == "true",
            "light_startup": os.environ.get("LIGHT_STARTUP", "false").lower() == "true",
        },
        "api_versions": {
            "/api/": "core - stable",
            "/api/v2/": "extended - stable",
            "/api/v3/": "financial - stable",
            "/api/v4/": "advanced - experimental",
        },
    }
