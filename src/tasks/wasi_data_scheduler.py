"""
WASI Daily Data Scheduler

Orchestrates the full nightly data pipeline:
  1. Run all country scrapers to collect latest port/trade data
  2. Upsert CountryIndex records (with confidence scores)
  3. Trigger composite index recalculation
  4. Log a pipeline run summary

Runs once per day by default (configurable via SCHEDULER_INTERVAL_HOURS).

Usage:
    from src.tasks.wasi_data_scheduler import start_data_scheduler, stop_data_scheduler
    # Call start_data_scheduler() in app lifespan; stop_data_scheduler() on shutdown.

    # Or trigger manually:
    from src.tasks.wasi_data_scheduler import run_daily_pipeline
    await run_daily_pipeline()
"""
from __future__ import annotations

import logging
from datetime import timezone, date, datetime

from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex
from src.engines.index_calculation import IndexCalculationEngine
from src.tasks.composite_update import update_composite_index
from src.tasks.bceao_ingestion import ingest_bceao_data
from src.tasks.divergence_snapshot import save_divergence_snapshot
from src.pipelines.scrapers.ngx_scraper import fetch_ngx
from src.pipelines.scrapers.gse_scraper import fetch_gse
from src.pipelines.scrapers.brvm_scraper import fetch_brvm
from src.pipelines.scrapers.worldbank_scraper import run_worldbank_scraper
from src.pipelines.scrapers.imf_scraper import run_imf_scraper
from src.pipelines.scrapers.acled_scraper import run_acled_scraper
from src.pipelines.scrapers.comtrade_scraper import run_comtrade_scraper
from src.pipelines.scrapers.commodity_scraper import run_commodity_scraper

# Scraper imports
from src.pipelines.scrapers.ng_scraper import NGScraper
from src.pipelines.scrapers.ci_scraper import CIScraper
from src.pipelines.scrapers.gh_scraper import GHScraper
from src.pipelines.scrapers.sn_scraper import SNScraper
from src.pipelines.scrapers.secondary_scraper import ALL_SECONDARY_SCRAPERS

logger = logging.getLogger(__name__)

# Primary-tier scrapers (in priority order)
_PRIMARY_SCRAPERS = [
    NGScraper(),
    CIScraper(),
    GHScraper(),
    SNScraper(),
]

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    _data_scheduler = AsyncIOScheduler()
    _apscheduler_available = True
except ImportError:
    _data_scheduler = None
    _apscheduler_available = False
    logger.warning("APScheduler not available; daily data pipeline disabled")


# ── Core pipeline ─────────────────────────────────────────────────────────────

async def run_daily_pipeline() -> dict:
    """
    Execute the full data ingestion and index update pipeline.

    Returns a summary dict with counts of successes and failures.
    """
    period_date = date.today().replace(day=1)  # normalise to 1st of month
    logger.info("Daily pipeline starting for period: %s", period_date)

    summary = {
        "period_date":  str(period_date),
        "started_at":   datetime.now(timezone.utc).isoformat(),
        "scraped":      0,
        "upserted":     0,
        "skipped":      0,
        "errors":       0,
        "countries":    [],
    }

    db: Session = SessionLocal()
    try:
        index_engine = IndexCalculationEngine()

        all_scrapers = list(_PRIMARY_SCRAPERS) + list(ALL_SECONDARY_SCRAPERS.values())

        for scraper in all_scrapers:
            code = scraper.COUNTRY_CODE
            result = scraper.run(period_date)

            if result is None:
                logger.warning("Pipeline: scraper for %s returned no data", code)
                summary["errors"] += 1
                continue

            summary["scraped"] += 1

            country = db.query(Country).filter(Country.code == code).first()
            if not country:
                logger.debug("Pipeline: country %s not in DB, skipping", code)
                summary["skipped"] += 1
                continue

            # Check for existing record
            existing = (
                db.query(CountryIndex)
                .filter(
                    CountryIndex.country_id == country.id,
                    CountryIndex.period_date == period_date,
                )
                .first()
            )

            raw = result.to_raw_dict()
            scores = index_engine.calculate_country_index(raw)

            if existing:
                # Update in-place
                for attr, val in raw.items():
                    setattr(existing, attr, val)
                existing.shipping_score        = scores["shipping_score"]
                existing.trade_score           = scores["trade_score"]
                existing.infrastructure_score  = scores["infrastructure_score"]
                existing.economic_score        = scores["economic_score"]
                existing.index_value           = scores["index_value"]
                existing.confidence            = result.confidence
                existing.data_quality          = result.data_quality
                existing.data_source           = result.data_source
            else:
                record = CountryIndex(
                    country_id=country.id,
                    period_date=period_date,
                    ship_arrivals=int(raw["ship_arrivals"]),
                    cargo_tonnage=raw["cargo_tonnage"],
                    container_teu=raw["container_teu"],
                    port_efficiency_score=raw["port_efficiency_score"],
                    dwell_time_days=raw["dwell_time_days"],
                    gdp_growth_pct=raw["gdp_growth_pct"],
                    trade_value_usd=raw["trade_value_usd"],
                    shipping_score=scores["shipping_score"],
                    trade_score=scores["trade_score"],
                    infrastructure_score=scores["infrastructure_score"],
                    economic_score=scores["economic_score"],
                    index_value=scores["index_value"],
                    confidence=result.confidence,
                    data_quality=result.data_quality,
                    data_source=result.data_source,
                )
                db.add(record)

            summary["upserted"] += 1
            summary["countries"].append({"code": code, "confidence": result.confidence})

        db.commit()
        logger.info("Pipeline: upserted %d country records", summary["upserted"])

    except Exception as exc:
        logger.error("Daily pipeline failed: %s", exc, exc_info=True)
        db.rollback()
        summary["errors"] += 1
    finally:
        db.close()

    # Fetch latest stock market data (NGX, GSE, BRVM)
    try:
        from src.database.models import StockMarketData
        stock_inserted = 0
        stock_records = []
        ngx = fetch_ngx()
        if ngx:
            stock_records.append(ngx)
        gse = fetch_gse()
        if gse:
            stock_records.append(gse)
        stock_records.extend(fetch_brvm())

        stock_db = SessionLocal()
        try:
            for rec in stock_records:
                exists = (
                    stock_db.query(StockMarketData)
                    .filter(
                        StockMarketData.exchange_code == rec["exchange_code"],
                        StockMarketData.index_name == rec["index_name"],
                        StockMarketData.trade_date == rec["trade_date"],
                    )
                    .first()
                )
                if not exists:
                    stock_db.add(StockMarketData(**{
                        k: v for k, v in rec.items()
                    }))
                    stock_inserted += 1
            if stock_inserted:
                stock_db.commit()
        finally:
            stock_db.close()

        summary["stock_markets"] = {
            "fetched": len(stock_records),
            "inserted": stock_inserted,
        }
        logger.info("Stock market update: fetched=%d inserted=%d",
                    len(stock_records), stock_inserted)
    except Exception as exc:
        logger.error("Stock market update failed: %s", exc)
        summary["stock_markets"] = {"error": str(exc)}

    # Enrich CI/SN/BJ/TG with BCEAO central-bank data
    try:
        bceao_stats = ingest_bceao_data(db=None)
        summary["bceao"] = bceao_stats
        logger.info("BCEAO enrichment: %s", bceao_stats)
    except Exception as exc:
        logger.error("BCEAO ingestion failed in pipeline: %s", exc)
        summary["bceao"] = {"error": str(exc)}

    # W6: Save divergence snapshots for trend tracking
    try:
        n_snapshots = save_divergence_snapshot()
        summary["divergence_snapshots"] = n_snapshots
        logger.info("DivergenceSnapshot: %d new snapshots written", n_snapshots)
    except Exception as exc:
        logger.error("DivergenceSnapshot failed in pipeline: %s", exc)
        summary["divergence_snapshots"] = 0

    # World Bank Open Data — enrich all 16 countries with real macro indicators
    # Runs synchronously (API calls are sequential with polite delays ~90s total)
    try:
        wb_stats = run_worldbank_scraper(db=None)
        summary["worldbank"] = {
            "updated":   wb_stats["updated"],
            "skipped":   wb_stats["skipped"],
            "errors":    wb_stats["errors"],
            "data_year": wb_stats["data_year"],
        }
        logger.info(
            "World Bank enrichment: updated=%d skipped=%d errors=%d year=%s",
            wb_stats["updated"], wb_stats["skipped"], wb_stats["errors"], wb_stats["data_year"]
        )
    except Exception as exc:
        logger.error("World Bank scraper failed in pipeline: %s", exc)
        summary["worldbank"] = {"error": str(exc)}

    # IMF World Economic Outlook — macro projections (GDP growth, inflation, debt/GDP, CA)
    try:
        imf_stats = run_imf_scraper(db=None)
        summary["imf"] = {
            "updated":   imf_stats["updated"],
            "skipped":   imf_stats["skipped"],
            "errors":    imf_stats["errors"],
            "data_year": imf_stats["data_year"],
        }
        logger.info(
            "IMF WEO enrichment: updated=%d skipped=%d errors=%d year=%s",
            imf_stats["updated"], imf_stats["skipped"], imf_stats["errors"], imf_stats["data_year"],
        )
    except Exception as exc:
        logger.error("IMF scraper failed in pipeline: %s", exc)
        summary["imf"] = {"error": str(exc)}

    # ACLED conflict data — real security signals for corridors / political risk
    try:
        acled_stats = run_acled_scraper(db=None)
        summary["acled"] = {
            "events_created": acled_stats["events_created"],
            "events_skipped": acled_stats["events_skipped"],
            "errors":         acled_stats["errors"],
            "api_used":       acled_stats["api_used"],
        }
        logger.info(
            "ACLED security signals: created=%d skipped=%d errors=%d api=%s",
            acled_stats["events_created"], acled_stats["events_skipped"],
            acled_stats["errors"], acled_stats["api_used"],
        )
    except Exception as exc:
        logger.error("ACLED scraper failed in pipeline: %s", exc)
        summary["acled"] = {"error": str(exc)}

    # UN Comtrade — bilateral trade flows (exports/imports by country)
    try:
        comtrade_stats = run_comtrade_scraper(db=None)
        summary["comtrade"] = {
            "updated":   comtrade_stats["updated"],
            "skipped":   comtrade_stats["skipped"],
            "errors":    comtrade_stats["errors"],
            "data_year": comtrade_stats["data_year"],
        }
        logger.info(
            "UN Comtrade trade flows: updated=%d skipped=%d errors=%d year=%s",
            comtrade_stats["updated"], comtrade_stats["skipped"],
            comtrade_stats["errors"], comtrade_stats["data_year"],
        )
    except Exception as exc:
        logger.error("Comtrade scraper failed in pipeline: %s", exc)
        summary["comtrade"] = {"error": str(exc)}

    # WB Pink Sheet — commodity prices (cocoa, oil, gold, cotton, coffee, iron ore)
    try:
        commodity_stats = run_commodity_scraper(db=None)
        summary["commodities"] = {
            "updated":        commodity_stats["updated"],
            "errors":         commodity_stats["errors"],
            "latest_prices":  commodity_stats["latest_prices"],
        }
        logger.info(
            "Commodity prices updated: %d records — %s",
            commodity_stats["updated"],
            ", ".join(f"{k}=${v:.2f}" for k, v in commodity_stats["latest_prices"].items()),
        )
    except Exception as exc:
        logger.error("Commodity scraper failed in pipeline: %s", exc)
        summary["commodities"] = {"error": str(exc)}

    # Trigger composite recalculation after data update
    try:
        await update_composite_index()
        summary["composite_updated"] = True
    except Exception as exc:
        logger.error("Composite update failed after pipeline: %s", exc)
        summary["composite_updated"] = False

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Daily pipeline complete: %s", summary)
    return summary


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def start_data_scheduler(hour: int = 2, minute: int = 0):
    """
    Start the APScheduler job to run the daily pipeline.

    Default: runs at 02:00 UTC every day.
    """
    if not _apscheduler_available:
        logger.info("Data scheduler: APScheduler not available, skipping")
        return

    _data_scheduler.add_job(
        run_daily_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="wasi_daily_pipeline",
        replace_existing=True,
        misfire_grace_time=600,  # 10 min grace period
    )
    _data_scheduler.start()
    logger.info("Data scheduler started: daily pipeline at %02d:%02d UTC", hour, minute)


def stop_data_scheduler():
    """Stop the data scheduler gracefully."""
    if _apscheduler_available and _data_scheduler and _data_scheduler.running:
        _data_scheduler.shutdown(wait=False)
        logger.info("Data scheduler stopped")
