import asyncio
import logging
import threading
from datetime import timezone, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from src.database.connection import SessionLocal
from src.database.models import CountryIndex, WASIComposite, Country
from src.engines.composite_engine import CompositeEngine
from src.config import settings

logger = logging.getLogger(__name__)

# Re-entrance guard: prevents concurrent execution of the same scheduled task
_composite_lock = threading.Lock()

# Scheduler heartbeat: updated every time any job executes
_last_heartbeat: datetime | None = None
_heartbeat_lock = threading.Lock()

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    _scheduler = AsyncIOScheduler()
    _apscheduler_available = True
except ImportError:
    _scheduler = None
    _apscheduler_available = False
    logger.warning("APScheduler not installed; background scheduling disabled")


async def update_composite_index():
    """
    Fetch the latest country index per country, calculate the WASI composite,
    and upsert the result into the wasi_composites table.
    """
    if not _composite_lock.acquire(blocking=False):
        logger.warning("composite_update: previous run still in progress, skipping")
        return

    db: Session = SessionLocal()
    try:
        engine = CompositeEngine()

        subq = (
            db.query(
                CountryIndex.country_id,
                func.max(CountryIndex.period_date).label("max_date"),
            )
            .group_by(CountryIndex.country_id)
            .subquery()
        )

        rows = (
            db.query(CountryIndex, Country)
            .join(
                subq,
                and_(
                    CountryIndex.country_id == subq.c.country_id,
                    CountryIndex.period_date == subq.c.max_date,
                ),
            )
            .join(Country, Country.id == CountryIndex.country_id)
            .all()
        )

        if not rows:
            logger.warning("composite_update: no country index data found; skipping")
            return

        country_indices = {r.Country.code: r.CountryIndex.index_value for r in rows}
        period_date = max(r.CountryIndex.period_date for r in rows)

        history_records = (
            db.query(WASIComposite)
            .order_by(WASIComposite.period_date.asc())
            .all()
        )
        history_values = [r.composite_value for r in history_records]

        result = engine.calculate_composite(country_indices, period_date, history_values)

        exclude_keys = {"period_date", "country_contributions"}
        existing = (
            db.query(WASIComposite)
            .filter(WASIComposite.period_date == period_date)
            .first()
        )

        if existing:
            for k, v in result.items():
                if k not in exclude_keys:
                    setattr(existing, k, v)
            existing.calculated_at = datetime.now(timezone.utc)
        else:
            record = WASIComposite(
                period_date=period_date,
                calculated_at=datetime.now(timezone.utc),
                **{k: v for k, v in result.items() if k not in exclude_keys},
            )
            db.add(record)

        db.commit()
        logger.info(
            "composite_update: period=%s value=%.4f countries=%d",
            period_date,
            result["composite_value"],
            result["countries_included"],
        )

    except Exception as exc:
        logger.error("composite_update failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _composite_lock.release()


def _update_heartbeat(event):
    """APScheduler listener: record timestamp on every job execution."""
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = datetime.now(timezone.utc)


def get_scheduler_heartbeat() -> dict:
    """Return heartbeat info for /api/health/detailed."""
    with _heartbeat_lock:
        hb = _last_heartbeat
    if hb is None:
        return {"last_heartbeat": None, "stale": False}
    age_seconds = (datetime.now(timezone.utc) - hb).total_seconds()
    # Stale if no job ran in 15 minutes (shortest interval is 5m for alerts)
    return {
        "last_heartbeat": hb.isoformat(),
        "seconds_since_heartbeat": round(age_seconds, 1),
        "stale": age_seconds > 900,
    }


def _threaded(sync_fn):
    """Wrap a sync function to run in asyncio.to_thread(), preventing event-loop blocking."""
    async def _wrapper(*args, **kwargs):
        return await asyncio.to_thread(sync_fn, *args, **kwargs)
    _wrapper.__name__ = sync_fn.__name__
    _wrapper.__qualname__ = sync_fn.__qualname__
    return _wrapper


def start_scheduler():
    if not _apscheduler_available or not settings.SCHEDULER_ENABLED:
        logger.info(
            "Scheduler disabled (APScheduler available=%s, SCHEDULER_ENABLED=%s)",
            _apscheduler_available,
            settings.SCHEDULER_ENABLED,
        )
        return

    # ── Composite index (already async) ───────────────────────────
    _scheduler.add_job(
        update_composite_index,
        trigger=IntervalTrigger(hours=settings.COMPOSITE_UPDATE_INTERVAL_HOURS),
        id="composite_update",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=120,
    )

    # ── News sweep (sync → threaded) ─────────────────────────────
    from src.tasks.news_sweep import run_news_sweep
    _scheduler.add_job(
        _threaded(run_news_sweep),
        trigger=IntervalTrigger(hours=1),
        id="news_sweep",
        replace_existing=True,
        misfire_grace_time=120,
        max_instances=1,
        jitter=120,
    )

    # ── USSD aggregation (sync → threaded) ───────────────────────
    from src.tasks.ussd_aggregation import run_ussd_aggregation, bridge_route_to_road_corridors
    _scheduler.add_job(
        _threaded(run_ussd_aggregation),
        trigger=IntervalTrigger(hours=4),
        id="ussd_aggregation",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    _scheduler.add_job(
        _threaded(bridge_route_to_road_corridors),
        trigger=IntervalTrigger(hours=4),
        id="route_corridor_bridge",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    # ── eCFA CBDC settlement (sync → threaded) ───────────────────
    from src.tasks.cbdc_settlement_task import (
        run_domestic_settlement, run_cross_border_settlement,
        run_monetary_aggregate_snapshot, run_daily_limit_reset,
        run_auto_unfreeze,
    )
    _scheduler.add_job(
        _threaded(run_domestic_settlement),
        trigger=IntervalTrigger(minutes=15),
        id="ecfa_domestic_settlement",
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1,
        jitter=30,
    )

    _scheduler.add_job(
        _threaded(run_cross_border_settlement),
        trigger=IntervalTrigger(hours=4),
        id="ecfa_cross_border_settlement",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    _scheduler.add_job(
        _threaded(run_daily_limit_reset),
        trigger=CronTrigger(hour=0, minute=1),
        id="ecfa_daily_limit_reset",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
    )

    _scheduler.add_job(
        _threaded(run_auto_unfreeze),
        trigger=CronTrigger(hour=0, minute=2),
        id="ecfa_auto_unfreeze",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
    )

    # ── eCFA AML sweep (sync → threaded) ─────────────────────────
    from src.tasks.cbdc_compliance_task import run_aml_sweep
    _scheduler.add_job(
        _threaded(run_aml_sweep),
        trigger=IntervalTrigger(hours=1),
        id="ecfa_aml_sweep",
        replace_existing=True,
        misfire_grace_time=120,
        max_instances=1,
        jitter=120,
    )

    _scheduler.add_job(
        _threaded(run_monetary_aggregate_snapshot),
        trigger=CronTrigger(hour=23, minute=55),
        id="ecfa_monetary_aggregates",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # ── eCFA monetary policy (already async) ─────────────────────
    from src.tasks.cbdc_monetary_policy_task import (
        run_daily_interest_accrual,
        run_reserve_requirement_check,
        run_facility_maturation,
    )
    _scheduler.add_job(
        run_daily_interest_accrual,
        trigger=CronTrigger(hour=0, minute=5),
        id="ecfa_daily_interest",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    _scheduler.add_job(
        run_reserve_requirement_check,
        trigger=CronTrigger(hour=6, minute=0),
        id="ecfa_reserve_check",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    _scheduler.add_job(
        run_facility_maturation,
        trigger=IntervalTrigger(hours=1),
        id="ecfa_facility_maturation",
        replace_existing=True,
        misfire_grace_time=120,
        max_instances=1,
        jitter=120,
    )

    # ── Forecast v1 (already async) ──────────────────────────────
    from src.tasks.forecast_task import run_forecast_update
    _scheduler.add_job(
        run_forecast_update,
        trigger=CronTrigger(hour=4, minute=0),
        id="forecast_update",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # ── Forecast v2 (sync → threaded) ────────────────────────────
    if settings.FORECAST_ENGINE_VERSION >= 2:
        from src.tasks.forecast_v2_task import run_forecast_v2_update_sync
        _scheduler.add_job(
            _threaded(run_forecast_v2_update_sync),
            trigger=CronTrigger(hour=4, minute=30),
            id="forecast_v2_update",
            replace_existing=True,
            misfire_grace_time=600,
            max_instances=1,
        )

    # ── FX rate refresh (already async) ──────────────────────────
    from src.tasks.fx_rate_update import run_fx_rate_update
    _scheduler.add_job(
        run_fx_rate_update,
        trigger=IntervalTrigger(hours=6),
        id="fx_rate_update",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    # ── Tokenization (sync → threaded) ───────────────────────────
    from src.tasks.tokenization_aggregation import run_tokenization_aggregation
    _scheduler.add_job(
        _threaded(run_tokenization_aggregation),
        trigger=IntervalTrigger(hours=4),
        id="tokenization_aggregation",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    from src.tasks.tokenization_aggregation import run_payment_disbursement
    _scheduler.add_job(
        _threaded(run_payment_disbursement),
        trigger=CronTrigger(hour=20, minute=0),
        id="tokenization_disbursement",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # ── Legislative sweep (already async) ────────────────────────
    from src.tasks.legislative_sweep import run_legislative_sweep
    _scheduler.add_job(
        run_legislative_sweep,
        trigger=IntervalTrigger(hours=6),
        id="legislative_sweep",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
        jitter=180,
    )

    # ── FX Analytics (already async) ─────────────────────────────
    from src.tasks.fx_analytics_task import run_fx_analytics_update
    _scheduler.add_job(
        run_fx_analytics_update,
        trigger=IntervalTrigger(hours=6),
        id="fx_analytics_update",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    # ── Corridor assessment (already async) ──────────────────────
    from src.tasks.corridor_assessment import run_corridor_assessment
    _scheduler.add_job(
        run_corridor_assessment,
        trigger=IntervalTrigger(hours=6),
        id="corridor_assessment",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    # ── Alert evaluation (already async) ─────────────────────────
    from src.tasks.alert_evaluation import run_alert_evaluation
    _scheduler.add_job(
        run_alert_evaluation,
        trigger=IntervalTrigger(minutes=5),
        id="alert_evaluation",
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1,
        jitter=15,
    )

    # ── Reconciliation (already async) ───────────────────────────
    from src.tasks.reconciliation_task import run_reconciliation
    _scheduler.add_job(
        run_reconciliation,
        trigger=IntervalTrigger(hours=2),
        id="run_reconciliation",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
    )

    # ── World News (sync → threaded) ─────────────────────────────
    from src.tasks.world_news_sweep import run_world_news_sweep
    _scheduler.add_job(
        _threaded(run_world_news_sweep),
        trigger=CronTrigger(hour=5, minute=0),
        id="world_news_sweep",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # ── Token/session cleanup ────────────────────────────────────
    from src.utils.security import cleanup_blacklist
    _scheduler.add_job(
        cleanup_blacklist,
        trigger=IntervalTrigger(minutes=settings.BLACKLIST_CLEANUP_INTERVAL_MINUTES),
        id="token_blacklist_cleanup",
        replace_existing=True,
        misfire_grace_time=60,
        max_instances=1,
    )

    from src.tasks.auth_cleanup import cleanup_expired_refresh_tokens
    _scheduler.add_job(
        cleanup_expired_refresh_tokens,
        trigger=CronTrigger(hour=3, minute=0),
        id="refresh_token_cleanup",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # ── Engagement (Walk15-style) ────────────────────────────────
    from src.tasks.engagement_task import (
        run_nightly_streaks, run_badge_check,
        run_challenge_lifecycle, run_monthly_impact,
    )
    _scheduler.add_job(
        run_nightly_streaks,
        trigger=CronTrigger(hour=0, minute=30),
        id="engagement_nightly_streaks",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    _scheduler.add_job(
        run_badge_check,
        trigger=IntervalTrigger(hours=4),
        id="engagement_badge_check",
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
        jitter=180,
    )

    _scheduler.add_job(
        run_challenge_lifecycle,
        trigger=IntervalTrigger(hours=1),
        id="engagement_challenge_lifecycle",
        replace_existing=True,
        misfire_grace_time=120,
        max_instances=1,
        jitter=120,
    )

    _scheduler.add_job(
        run_monthly_impact,
        trigger=CronTrigger(day=1, hour=3, minute=0),
        id="engagement_monthly_impact",
        replace_existing=True,
        misfire_grace_time=3600,
        max_instances=1,
    )

    # ── Royalty distribution (sync → threaded) ───────────────────
    from src.engines.royalty_engine import RoyaltyEngine
    def _run_royalty_distribution():
        db = SessionLocal()
        try:
            result = RoyaltyEngine.distribute_all_pending(db)
            db.commit()
            logger.info("Royalty distribution: %s", result)
            return result
        except Exception as exc:
            db.rollback()
            logger.error("Royalty distribution failed: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}
        finally:
            db.close()

    _scheduler.add_job(
        _threaded(_run_royalty_distribution),
        trigger=CronTrigger(hour=21, minute=0),
        id="royalty_distribution",
        replace_existing=True,
        misfire_grace_time=600,
        max_instances=1,
    )

    # Wire heartbeat listener so health endpoint can detect stale scheduler
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
    _scheduler.add_listener(_update_heartbeat, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    _scheduler.start()
    logger.info(
        "Scheduler started: composite %dh, news 1h, USSD 4h, eCFA settlement 15m/4h, "
        "AML 1h, interest daily, reserves daily, facilities 1h, forecast daily 04:00, "
        "FX rates 6h, tokenization 4h, disbursement daily 20:00, legislative 6h, "
        "FX analytics 6h, corridor assessment 6h, alerts 5m, reconciliation 2h, "
        "world news daily 05:00, blacklist cleanup 30m, refresh cleanup daily",
        settings.COMPOSITE_UPDATE_INTERVAL_HOURS,
    )


def stop_scheduler():
    if _apscheduler_available and _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
