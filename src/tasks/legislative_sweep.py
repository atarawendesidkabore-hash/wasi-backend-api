"""
Legislative Sweep — scheduled task that fetches new legislation,
scores impact, and emits NewsEvent records for high-impact laws.

Runs every 6 hours via APScheduler (registered in composite_update.py).
"""
import logging
import threading

from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.legislative_models import LegislativeAct

logger = logging.getLogger(__name__)

_legislative_lock = threading.Lock()


async def run_legislative_sweep():
    """
    1. Run legislative scraper (Laws.Africa + IPU + fallback).
    2. Score all unscored acts via LegislativeImpactEngine.
    3. Emit NewsEvent records for acts with |magnitude| > 5.
    """
    if not _legislative_lock.acquire(blocking=False):
        logger.warning("legislative_sweep: previous run still in progress, skipping")
        return

    db: Session = SessionLocal()
    try:
        # Step 1: Fetch new legislation
        from src.pipelines.scrapers.legislative_scraper import run_legislative_scraper
        scraper_result = run_legislative_scraper(db)
        logger.info(
            "Legislative scraper: acts=%d sessions=%d errors=%d",
            scraper_result["acts_found"],
            scraper_result["sessions_found"],
            scraper_result["errors"],
        )

        # Step 2: Score any acts that haven't been scored yet (magnitude == 0.0 and not OTHER)
        from src.engines.legislative_engine import LegislativeImpactEngine
        engine = LegislativeImpactEngine(db)

        unscored = (
            db.query(LegislativeAct)
            .filter(
                LegislativeAct.estimated_magnitude == 0.0,
                LegislativeAct.is_active == True,
            )
            .all()
        )

        scored_count = 0
        events_emitted = 0

        for act in unscored:
            try:
                result = engine.score_and_update_act(act)
                scored_count += 1

                # Step 3: Emit NewsEvent for high-impact acts
                if abs(act.estimated_magnitude) > 5.0:
                    event = engine.emit_news_event(act)
                    if event:
                        events_emitted += 1
            except Exception as exc:
                logger.warning("Error scoring act %d: %s", act.id, exc)

        logger.info(
            "Legislative sweep complete: new_acts=%d scored=%d events_emitted=%d",
            scraper_result["acts_found"], scored_count, events_emitted,
        )

    except Exception as exc:
        logger.error("legislative_sweep failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _legislative_lock.release()
