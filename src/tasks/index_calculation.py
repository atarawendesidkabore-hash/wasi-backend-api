import logging
from sqlalchemy.orm import Session
from src.database.models import CountryIndex
from src.engines.index_calculation import IndexCalculationEngine

logger = logging.getLogger(__name__)


def recalculate_all_country_indices(db: Session) -> dict:
    """
    Recalculate sub-scores and index_value for CountryIndex records
    that have raw data but null sub-scores (e.g. after changing normalization).
    Returns {"updated": N}.
    """
    engine = IndexCalculationEngine()

    stale_records = (
        db.query(CountryIndex)
        .filter(CountryIndex.shipping_score.is_(None))
        .all()
    )

    updated = 0
    for record in stale_records:
        raw = {
            "ship_arrivals":          record.ship_arrivals or 0,
            "cargo_tonnage":          record.cargo_tonnage or 0,
            "container_teu":          record.container_teu or 0,
            "port_efficiency_score":  record.port_efficiency_score or 50,
            "dwell_time_days":        record.dwell_time_days or 15,
            "gdp_growth_pct":         record.gdp_growth_pct or 0,
            "trade_value_usd":        record.trade_value_usd or 0,
        }
        scores = engine.calculate_country_index(raw)
        record.shipping_score = scores["shipping_score"]
        record.trade_score = scores["trade_score"]
        record.infrastructure_score = scores["infrastructure_score"]
        record.economic_score = scores["economic_score"]
        record.index_value = scores["index_value"]
        updated += 1

    if updated:
        db.commit()
        logger.info("Recalculated scores for %d CountryIndex records", updated)

    return {"updated": updated}
