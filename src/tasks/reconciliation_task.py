"""Scheduled reconciliation task — runs every 2 hours."""
import logging
import threading

from src.database.connection import SessionLocal
from src.engines.reconciliation_engine import ReconciliationEngine

logger = logging.getLogger(__name__)
_reconciliation_lock = threading.Lock()


async def run_reconciliation():
    """Run full data reconciliation check."""
    if not _reconciliation_lock.acquire(blocking=False):
        logger.warning("Reconciliation: previous run still in progress, skipping")
        return

    db = SessionLocal()
    try:
        engine = ReconciliationEngine(db)
        result = engine.run_full_reconciliation(run_type="SCHEDULED")
        logger.info(
            "Reconciliation: checked=%d anomalies=%d quarantined=%d duration=%.0fms",
            result["records_checked"],
            result["anomalies_found"],
            result["quarantined"],
            result["duration_ms"],
        )
    except Exception as exc:
        logger.error("Reconciliation failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _reconciliation_lock.release()
