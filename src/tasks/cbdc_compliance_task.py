"""
eCFA CBDC Compliance Scheduler.

Scheduled task: hourly AML/CFT sweep across all wallets with recent activity.
"""
import logging
import threading
from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)
_aml_lock = threading.Lock()


def run_aml_sweep():
    """Scheduled task: hourly AML compliance sweep."""
    if not _aml_lock.acquire(blocking=False):
        logger.info("eCFA AML sweep: previous run still in progress, skipping")
        return
    db = SessionLocal()
    try:
        from src.engines.cbdc_compliance_engine import CbdcComplianceEngine
        engine = CbdcComplianceEngine(db)
        result = engine.run_full_sweep()
        logger.info(
            "eCFA AML sweep: scanned=%d wallets, alerts=%d",
            result["wallets_scanned"], result["alerts_generated"],
        )
    except Exception as exc:
        logger.error("eCFA AML sweep failed: %s", exc)
    finally:
        db.close()
        _aml_lock.release()
