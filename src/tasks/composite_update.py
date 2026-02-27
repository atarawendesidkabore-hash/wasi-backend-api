import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from src.database.connection import SessionLocal
from src.database.models import CountryIndex, WASIComposite, Country
from src.engines.composite_engine import CompositeEngine
from src.config import settings

logger = logging.getLogger(__name__)

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
            existing.calculated_at = datetime.utcnow()
        else:
            record = WASIComposite(
                period_date=period_date,
                calculated_at=datetime.utcnow(),
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
    from src.tasks.ussd_aggregation import run_ussd_aggregation
    _scheduler.add_job(
        run_ussd_aggregation,
        trigger=IntervalTrigger(hours=4),
        id="ussd_aggregation",
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: composite update every %dh, news sweep every 1h, USSD aggregation every 4h",
        settings.COMPOSITE_UPDATE_INTERVAL_HOURS,
    )


def stop_scheduler():
    if _apscheduler_available and _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
