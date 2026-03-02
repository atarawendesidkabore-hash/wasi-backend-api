"""
eCFA CBDC Settlement Scheduler.

Scheduled tasks:
  - Domestic settlement: every 15 minutes
  - Cross-border settlement: every 4 hours
  - Monetary aggregate snapshot: daily at 23:55 UTC
"""
import logging
from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)


def run_domestic_settlement():
    """Scheduled task: run domestic inter-bank netting every 15 minutes."""
    db = SessionLocal()
    try:
        from src.engines.cbdc_settlement_engine import CbdcSettlementEngine
        engine = CbdcSettlementEngine(db)
        result = engine.run_domestic_settlement(window_minutes=15)
        if result["settlements"] > 0:
            logger.info(
                "eCFA domestic settlement: %d settlements, %d txns netted, ratio=%.2f",
                result["settlements"], result["transactions_netted"],
                result.get("netting_ratio", 0),
            )
    except Exception as exc:
        logger.error("eCFA domestic settlement failed: %s", exc)
    finally:
        db.close()


def run_cross_border_settlement():
    """Scheduled task: run cross-border WAEMU netting every 4 hours."""
    db = SessionLocal()
    try:
        from src.engines.cbdc_settlement_engine import CbdcSettlementEngine
        engine = CbdcSettlementEngine(db)
        result = engine.run_cross_border_settlement()
        if result["settlements"] > 0:
            logger.info(
                "eCFA cross-border settlement: %d settlements, %d txns netted",
                result["settlements"], result["transactions_netted"],
            )
    except Exception as exc:
        logger.error("eCFA cross-border settlement failed: %s", exc)
    finally:
        db.close()


def run_monetary_aggregate_snapshot():
    """Scheduled task: compute daily monetary aggregates for all WAEMU countries."""
    waemu_codes = ["CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW"]
    db = SessionLocal()
    try:
        from src.engines.cbdc_settlement_engine import CbdcSettlementEngine
        engine = CbdcSettlementEngine(db)
        for cc in waemu_codes:
            try:
                engine.compute_monetary_aggregates(cc)
            except Exception as exc:
                logger.warning("Monetary aggregate for %s failed: %s", cc, exc)
        logger.info("eCFA monetary aggregates computed for %d countries", len(waemu_codes))
    except Exception as exc:
        logger.error("eCFA monetary aggregate snapshot failed: %s", exc)
    finally:
        db.close()
