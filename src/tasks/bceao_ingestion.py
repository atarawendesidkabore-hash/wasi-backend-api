"""
BCEAO data ingestion task.

Fetches BCEAO monthly records (CI, SN, BJ, TG) and enriches CountryIndex rows:
  - If a matching (country_id, period_date) record exists → update economic fields
  - If no record exists → create a new one with port fields zeroed

After enrichment the index scores are recalculated via IndexCalculationEngine
with confidence = 0.95 and data_source = "bceao".

Called at startup (after CSV ingestion) and daily by the WASI data scheduler.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex
from src.engines.index_calculation import IndexCalculationEngine
from src.pipelines.scrapers.bceao_scraper import fetch_bceao_records
from src.pipelines.parsers.bceao_parser import BCEAORecord

logger = logging.getLogger(__name__)

_engine = IndexCalculationEngine()


def _upsert_from_record(record: BCEAORecord, db: Session) -> bool:
    """
    Upsert a single BCEAORecord into CountryIndex.
    Returns True if a DB change was made.
    """
    country = db.query(Country).filter(Country.code == record.country_code).first()
    if not country:
        logger.debug("BCEAO: unknown country code %s — skipped", record.country_code)
        return False

    existing: CountryIndex | None = (
        db.query(CountryIndex)
        .filter(
            CountryIndex.country_id == country.id,
            CountryIndex.period_date == record.period_date,
        )
        .first()
    )

    if existing:
        # Only enrich if our source has higher or equal confidence
        if (existing.confidence or 0.0) > record.confidence:
            logger.debug(
                "BCEAO: skipping %s %s — existing confidence %.2f > BCEAO %.2f",
                record.country_code,
                record.period_date,
                existing.confidence,
                record.confidence,
            )
            return False

        # Patch economic fields
        if record.gdp_growth_pct is not None:
            existing.gdp_growth_pct = record.gdp_growth_pct
        if record.trade_value_usd is not None:
            existing.trade_value_usd = record.trade_value_usd

        # Recalculate scores with enriched data
        raw = {
            "ship_arrivals":         existing.ship_arrivals or 0,
            "cargo_tonnage":         existing.cargo_tonnage or 0,
            "container_teu":         existing.container_teu or 0,
            "port_efficiency_score": existing.port_efficiency_score or 50,
            "dwell_time_days":       existing.dwell_time_days or 15,
            "gdp_growth_pct":        existing.gdp_growth_pct or 0,
            "trade_value_usd":       existing.trade_value_usd or 0,
        }
        scores = _engine.calculate_country_index(raw)
        existing.shipping_score       = scores["shipping_score"]
        existing.trade_score          = scores["trade_score"]
        existing.infrastructure_score = scores["infrastructure_score"]
        existing.economic_score       = scores["economic_score"]
        existing.index_value          = scores["index_value"]
        existing.confidence           = record.confidence
        existing.data_quality         = record.data_quality
        existing.data_source          = record.data_source
        return True

    else:
        # Create new record — port fields default to 0 / sensible defaults
        raw = {
            "ship_arrivals":         0,
            "cargo_tonnage":         0,
            "container_teu":         0,
            "port_efficiency_score": 50,
            "dwell_time_days":       15,
            "gdp_growth_pct":        record.gdp_growth_pct or 0,
            "trade_value_usd":       record.trade_value_usd or 0,
        }
        scores = _engine.calculate_country_index(raw)
        new_row = CountryIndex(
            country_id=country.id,
            period_date=record.period_date,
            ship_arrivals=None,
            cargo_tonnage=None,
            container_teu=None,
            port_efficiency_score=None,
            dwell_time_days=None,
            gdp_growth_pct=record.gdp_growth_pct,
            trade_value_usd=record.trade_value_usd,
            shipping_score=scores["shipping_score"],
            trade_score=scores["trade_score"],
            infrastructure_score=scores["infrastructure_score"],
            economic_score=scores["economic_score"],
            index_value=scores["index_value"],
            confidence=record.confidence,
            data_quality=record.data_quality,
            data_source=record.data_source,
        )
        db.add(new_row)
        return True


def ingest_bceao_data(db: Session | None = None) -> dict:
    """
    Main entry point.  Fetch BCEAO records, upsert into CountryIndex.

    Parameters
    ----------
    db : optional Session — if None, a new SessionLocal() is created and closed.

    Returns
    -------
    dict with keys: records_fetched, updated, inserted, skipped
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()

    stats = {"records_fetched": 0, "updated": 0, "inserted": 0, "skipped": 0}

    try:
        records = fetch_bceao_records()
        stats["records_fetched"] = len(records)

        if not records:
            logger.info("BCEAO ingestion: no records fetched — nothing to do")
            return stats

        # Track what was in DB before to distinguish updates vs inserts
        for rec in records:
            country = db.query(Country).filter(Country.code == rec.country_code).first()
            if not country:
                stats["skipped"] += 1
                continue

            had_existing = (
                db.query(CountryIndex)
                .filter(
                    CountryIndex.country_id == country.id,
                    CountryIndex.period_date == rec.period_date,
                )
                .first()
            ) is not None

            changed = _upsert_from_record(rec, db)
            if changed:
                if had_existing:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1
            else:
                stats["skipped"] += 1

        db.commit()
        logger.info(
            "BCEAO ingestion complete: fetched=%d updated=%d inserted=%d skipped=%d",
            stats["records_fetched"],
            stats["updated"],
            stats["inserted"],
            stats["skipped"],
        )

    except Exception as exc:
        logger.error("BCEAO ingestion failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        if close_db:
            db.close()

    return stats
