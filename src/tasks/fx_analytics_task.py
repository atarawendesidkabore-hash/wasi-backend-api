"""
FX Analytics Update Task — Fetches rates and recomputes volatility every 6 hours.

1. Run FX scraper (Fawazahmed0 / ExchangeRate-API / fallback)
2. Recompute volatility for all 9 currencies
3. Log results
"""
import logging
import threading

from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)
_fx_analytics_lock = threading.Lock()


async def run_fx_analytics_update():
    """Fetch rates and recompute volatility."""
    if not _fx_analytics_lock.acquire(blocking=False):
        logger.warning("fx_analytics_update: previous run still in progress, skipping")
        return

    db = SessionLocal()
    try:
        from src.pipelines.scrapers.fx_scraper import run_fx_scraper
        scrape_result = run_fx_scraper(db=db)

        from src.engines.fx_analytics_engine import FxAnalyticsEngine
        engine = FxAnalyticsEngine(db)
        vol_result = engine.recompute_all_volatility()

        db.commit()
        logger.info(
            "fx_analytics_update: scraped=%d vol_recomputed=%d errors=%d",
            scrape_result.get("updated", 0),
            vol_result.get("currencies_computed", 0),
            scrape_result.get("errors", 0),
        )
    except Exception as exc:
        logger.error("fx_analytics_update failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _fx_analytics_lock.release()
