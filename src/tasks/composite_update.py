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

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
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


def start_scheduler():
    if not _apscheduler_available or not settings.SCHEDULER_ENABLED:
        logger.info(
            "Scheduler disabled (APScheduler available=%s, SCHEDULER_ENABLED=%s)",
            _apscheduler_available,
            settings.SCHEDULER_ENABLED,
        )
        return

    _scheduler.add_job(
        update_composite_index,
        trigger=IntervalTrigger(hours=settings.COMPOSITE_UPDATE_INTERVAL_HOURS),
        id="composite_update",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # News sweep runs hourly
    from src.tasks.news_sweep import run_news_sweep
    _scheduler.add_job(
        run_news_sweep,
        trigger=IntervalTrigger(hours=1),
        id="news_sweep",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # USSD data aggregation runs every 4 hours
    from src.tasks.ussd_aggregation import run_ussd_aggregation, bridge_route_to_road_corridors
    _scheduler.add_job(
        run_ussd_aggregation,
        trigger=IntervalTrigger(hours=4),
        id="ussd_aggregation",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Route-to-corridor bridge runs every 4 hours (after USSD aggregation)
    _scheduler.add_job(
        bridge_route_to_road_corridors,
        trigger=IntervalTrigger(hours=4),
        id="route_corridor_bridge",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # eCFA CBDC: domestic settlement every 15 minutes
    from src.tasks.cbdc_settlement_task import (
        run_domestic_settlement, run_cross_border_settlement,
        run_monetary_aggregate_snapshot,
    )
    _scheduler.add_job(
        run_domestic_settlement,
        trigger=IntervalTrigger(minutes=15),
        id="ecfa_domestic_settlement",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # eCFA CBDC: cross-border settlement every 4 hours
    _scheduler.add_job(
        run_cross_border_settlement,
        trigger=IntervalTrigger(hours=4),
        id="ecfa_cross_border_settlement",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # eCFA CBDC: AML compliance sweep every hour
    from src.tasks.cbdc_compliance_task import run_aml_sweep
    _scheduler.add_job(
        run_aml_sweep,
        trigger=IntervalTrigger(hours=1),
        id="ecfa_aml_sweep",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # eCFA CBDC: monetary aggregate snapshot daily at 23:55 UTC
    from apscheduler.triggers.cron import CronTrigger
    _scheduler.add_job(
        run_monetary_aggregate_snapshot,
        trigger=CronTrigger(hour=23, minute=55),
        id="ecfa_monetary_aggregates",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # eCFA CBDC: daily interest accrual & demurrage at 00:05 UTC
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
    )

    # eCFA CBDC: reserve requirement check daily at 06:00 UTC
    _scheduler.add_job(
        run_reserve_requirement_check,
        trigger=CronTrigger(hour=6, minute=0),
        id="ecfa_reserve_check",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # eCFA CBDC: mature standing facilities every hour
    _scheduler.add_job(
        run_facility_maturation,
        trigger=IntervalTrigger(hours=1),
        id="ecfa_facility_maturation",
        replace_existing=True,
        misfire_grace_time=120,
    )

    # Forecast engine: daily at 04:00 UTC
    from src.tasks.forecast_task import run_forecast_update
    _scheduler.add_job(
        run_forecast_update,
        trigger=CronTrigger(hour=4, minute=0),
        id="forecast_update",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # WASI-Pay: FX rate refresh every 6 hours
    from src.tasks.fx_rate_update import run_fx_rate_update
    _scheduler.add_job(
        run_fx_rate_update,
        trigger=IntervalTrigger(hours=6),
        id="fx_rate_update",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Tokenization: aggregation every 4 hours
    from src.tasks.tokenization_aggregation import run_tokenization_aggregation
    _scheduler.add_job(
        run_tokenization_aggregation,
        trigger=IntervalTrigger(hours=4),
        id="tokenization_aggregation",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Tokenization: payment disbursement daily at 20:00 UTC
    from src.tasks.tokenization_aggregation import run_payment_disbursement
    _scheduler.add_job(
        run_payment_disbursement,
        trigger=CronTrigger(hour=20, minute=0),
        id="tokenization_disbursement",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Legislative monitoring: sweep every 6 hours
    from src.tasks.legislative_sweep import run_legislative_sweep
    _scheduler.add_job(
        run_legislative_sweep,
        trigger=IntervalTrigger(hours=6),
        id="legislative_sweep",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # FX Analytics: rate scrape + volatility recomputation every 6 hours
    from src.tasks.fx_analytics_task import run_fx_analytics_update
    _scheduler.add_job(
        run_fx_analytics_update,
        trigger=IntervalTrigger(hours=6),
        id="fx_analytics_update",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Corridor Intelligence: reassess all trade corridors every 6 hours
    from src.tasks.corridor_assessment import run_corridor_assessment
    _scheduler.add_job(
        run_corridor_assessment,
        trigger=IntervalTrigger(hours=6),
        id="corridor_assessment",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Alert evaluation: every 5 minutes
    from src.tasks.alert_evaluation import run_alert_evaluation
    _scheduler.add_job(
        run_alert_evaluation,
        trigger=IntervalTrigger(minutes=5),
        id="alert_evaluation",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # Data reconciliation every 2 hours
    from src.tasks.reconciliation_task import run_reconciliation
    _scheduler.add_job(
        run_reconciliation,
        trigger=IntervalTrigger(hours=2),
        id="run_reconciliation",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # World News Intelligence: daily at 05:00 UTC
    from src.tasks.world_news_sweep import run_world_news_sweep
    _scheduler.add_job(
        run_world_news_sweep,
        trigger=CronTrigger(hour=5, minute=0),
        id="world_news_sweep",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Token blacklist cleanup every 30 minutes
    from src.utils.security import cleanup_blacklist
    _scheduler.add_job(
        cleanup_blacklist,
        trigger=IntervalTrigger(minutes=settings.BLACKLIST_CLEANUP_INTERVAL_MINUTES),
        id="token_blacklist_cleanup",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # Expired refresh token cleanup daily at 03:00 UTC
    from src.tasks.auth_cleanup import cleanup_expired_refresh_tokens
    _scheduler.add_job(
        cleanup_expired_refresh_tokens,
        trigger=CronTrigger(hour=3, minute=0),
        id="refresh_token_cleanup",
        replace_existing=True,
        misfire_grace_time=600,
    )

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
