import os
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from datetime import timezone, datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db
from src.utils.security import get_current_user

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
async def health_detailed(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
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

    # ── Data freshness (core + scraper sources) ─────────────────
    freshness = {}
    try:
        from src.database.models import (
            WASIComposite, CountryIndex, MacroIndicator, NewsEvent, CommodityPrice,
        )
        from datetime import timedelta
        stale_threshold = now - timedelta(hours=48)

        latest_composite = db.query(func.max(WASIComposite.period_date)).scalar()
        latest_index = db.query(func.max(CountryIndex.period_date)).scalar()
        freshness["latest_composite_date"] = str(latest_composite) if latest_composite else None
        freshness["latest_index_date"] = str(latest_index) if latest_index else None

        # World Bank → CountryIndex
        wb_latest = db.query(func.max(CountryIndex.period_date)).filter(
            CountryIndex.data_source == "World Bank Open Data API"
        ).scalar()
        freshness["worldbank_latest"] = str(wb_latest) if wb_latest else None
        freshness["worldbank_stale"] = wb_latest is None

        # IMF → MacroIndicator (year-based)
        imf_latest_year = db.query(func.max(MacroIndicator.year)).filter(
            MacroIndicator.data_source == "imf_weo"
        ).scalar()
        freshness["imf_latest_year"] = imf_latest_year
        freshness["imf_stale"] = imf_latest_year is None or imf_latest_year < (now.year - 1)

        # ACLED → NewsEvent
        acled_latest = db.query(func.max(NewsEvent.detected_at)).scalar()
        freshness["acled_latest"] = acled_latest.isoformat() if acled_latest else None
        freshness["acled_stale"] = acled_latest is None or acled_latest < stale_threshold

        # Commodity prices
        commodity_latest = db.query(func.max(CommodityPrice.period_date)).scalar()
        freshness["commodity_latest"] = str(commodity_latest) if commodity_latest else None
        freshness["commodity_stale"] = commodity_latest is None
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

    # ── Alembic migration status ─────────────────────────────────
    alembic_info = {}
    try:
        result = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        row = result.fetchone()
        current_rev = row[0] if row else None

        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory
        alembic_cfg = AlembicConfig("alembic.ini")
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script_dir.get_current_head()

        alembic_info["current_revision"] = current_rev
        alembic_info["head_revision"] = head_rev
        alembic_info["up_to_date"] = current_rev == head_rev
    except Exception:
        alembic_info["available"] = False

    # ── Scraper circuit breaker status ─────────────────────────────
    scraper_circuits = {}
    try:
        from src.pipelines.scrapers.resilience import get_circuit_status
        scraper_circuits = get_circuit_status()
    except Exception:
        pass

    overall = "healthy" if db_ok else "degraded"
    # Degrade if any scraper data is stale
    if freshness.get("worldbank_stale") or freshness.get("acled_stale") or freshness.get("commodity_stale"):
        overall = "degraded" if db_ok else overall
    # Degrade if any scraper circuit is open
    if any(s.get("circuit_open") for s in scraper_circuits.values()):
        overall = "degraded" if overall != "unhealthy" else overall

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
        "scrapers": scraper_circuits,
        "alembic": alembic_info,
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
