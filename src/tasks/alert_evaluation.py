"""
Alert Evaluation — Scheduled task (every 5 minutes).

Phase 1: Evaluate all active alert rules and queue deliveries.
Phase 2: Send pending webhook deliveries (with retry).
"""
import logging
import threading

from src.database.connection import SessionLocal
from src.engines.alert_engine import deliver_pending_webhooks, evaluate_all_rules

logger = logging.getLogger(__name__)

_alert_lock = threading.Lock()


async def run_alert_evaluation():
    """Evaluate alert rules and deliver pending webhooks."""
    if not _alert_lock.acquire(blocking=False):
        logger.warning("alert_evaluation: previous run still in progress, skipping")
        return

    db = SessionLocal()
    try:
        # Phase 1: evaluate rules → queue deliveries
        eval_result = evaluate_all_rules(db)
        logger.info(
            "alert_evaluation: evaluated=%d triggered=%d queued=%d",
            eval_result["rules_evaluated"],
            eval_result["alerts_triggered"],
            eval_result["deliveries_queued"],
        )

        # Phase 2: deliver pending webhooks
        delivery_result = deliver_pending_webhooks(db)
        logger.info(
            "alert_delivery: delivered=%d failed=%d retrying=%d",
            delivery_result["delivered"],
            delivery_result["failed"],
            delivery_result["retrying"],
        )

    except Exception as exc:
        logger.error("alert_evaluation failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _alert_lock.release()
