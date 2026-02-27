import os
import logging
import pandas as pd
from sqlalchemy.orm import Session
from src.database.models import Country, CountryIndex
from src.engines.index_calculation import IndexCalculationEngine

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def ingest_csv_file(filepath: str, db: Session) -> int:
    """
    Read a CSV port data file and insert CountryIndex records.

    Expected columns:
        date, country_code, ship_arrivals, cargo_tonnage, container_teu,
        port_efficiency_score, dwell_time_days, gdp_growth_pct, trade_value_usd

    Rows for unknown country codes or duplicate (country, period) are skipped.
    Returns the number of new rows inserted.
    """
    engine = IndexCalculationEngine()

    try:
        df = pd.read_csv(filepath, parse_dates=["date"])
    except Exception as exc:
        logger.error("Failed to read CSV %s: %s", filepath, exc)
        return 0

    inserted = 0
    for _, row in df.iterrows():
        country_code = str(row.get("country_code", "")).strip().upper()
        country = db.query(Country).filter(Country.code == country_code).first()
        if not country:
            logger.warning("Skipping unknown country code: %s", country_code)
            continue

        period_date = row["date"].date().replace(day=1)

        exists = db.query(CountryIndex).filter(
            CountryIndex.country_id == country.id,
            CountryIndex.period_date == period_date,
        ).first()
        if exists:
            continue

        raw = {
            "ship_arrivals":          float(row.get("ship_arrivals") or 0),
            "cargo_tonnage":          float(row.get("cargo_tonnage") or 0),
            "container_teu":          float(row.get("container_teu") or 0),
            "port_efficiency_score":  float(row.get("port_efficiency_score") or 50),
            "dwell_time_days":        float(row.get("dwell_time_days") or 15),
            "gdp_growth_pct":         float(row.get("gdp_growth_pct") or 0),
            "trade_value_usd":        float(row.get("trade_value_usd") or 0),
        }

        scores = engine.calculate_country_index(raw)

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
            confidence=0.90,        # curated CSV = high confidence
            data_quality="high",
            data_source="csv_import",
        )
        db.add(record)
        inserted += 1

    if inserted:
        db.commit()
        logger.info("Ingested %d rows from %s", inserted, os.path.basename(filepath))

    return inserted


def ingest_all_csv_files(db: Session) -> dict:
    """
    Scan the data/ directory and ingest all *.csv files.
    Returns {filename: rows_inserted}.
    """
    results = {}
    if not os.path.isdir(DATA_DIR):
        logger.warning("Data directory not found: %s", DATA_DIR)
        return results

    for filename in sorted(os.listdir(DATA_DIR)):
        if filename.lower().endswith(".csv"):
            filepath = os.path.join(DATA_DIR, filename)
            count = ingest_csv_file(filepath, db)
            results[filename] = count

    return results
