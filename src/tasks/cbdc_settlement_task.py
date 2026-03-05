"""
eCFA CBDC Settlement Scheduler.

Scheduled tasks:
  - Domestic settlement: every 15 minutes
  - Cross-border settlement: every 4 hours
  - Daily limit reset: daily at 00:01 UTC
  - Monetary aggregate snapshot: daily at 23:55 UTC
"""
import logging
import threading
from datetime import date

from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)
_settlement_lock = threading.Lock()
_cross_border_lock = threading.Lock()
_daily_limit_lock = threading.Lock()
_auto_unfreeze_lock = threading.Lock()
_monetary_agg_lock = threading.Lock()


def run_domestic_settlement():
    """Scheduled task: run domestic inter-bank netting every 15 minutes."""
    if not _settlement_lock.acquire(blocking=False):
        logger.warning("eCFA settlement: previous run still in progress, skipping")
        return
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
        _settlement_lock.release()


def run_cross_border_settlement():
    """Scheduled task: run cross-border WAEMU netting every 4 hours."""
    if not _cross_border_lock.acquire(blocking=False):
        logger.info("eCFA cross-border settlement: previous run still in progress, skipping")
        return
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
        _cross_border_lock.release()


def run_daily_limit_reset():
    """Scheduled task: reset daily spending counters for all eCFA wallets (00:01 UTC)."""
    if not _daily_limit_lock.acquire(blocking=False):
        logger.info("eCFA daily limit reset: previous run still in progress, skipping")
        return
    db = SessionLocal()
    try:
        from src.database.cbdc_models import CbdcWallet
        today = date.today()
        count = (
            db.query(CbdcWallet)
            .filter(CbdcWallet.daily_reset_date < today)
            .update({
                CbdcWallet.daily_spent_ecfa: 0.0,
                CbdcWallet.daily_reset_date: today,
            })
        )
        db.commit()
        if count > 0:
            logger.info("eCFA daily limit reset: %d wallets", count)
    except Exception as exc:
        logger.error("eCFA daily limit reset failed: %s", exc)
        db.rollback()
    finally:
        db.close()
        _daily_limit_lock.release()


def run_auto_unfreeze():
    """Scheduled task: auto-unfreeze wallets past their auto_unfreeze_date (00:02 UTC).

    Wallets frozen for > 30 days with no compliance action are unfrozen automatically.
    This prevents indefinite account lockout (psychological safety).
    """
    if not _auto_unfreeze_lock.acquire(blocking=False):
        logger.info("eCFA auto-unfreeze: previous run still in progress, skipping")
        return
    db = SessionLocal()
    try:
        from src.database.cbdc_models import CbdcWallet
        today = date.today()
        count = (
            db.query(CbdcWallet)
            .filter(
                CbdcWallet.status == "frozen",
                CbdcWallet.auto_unfreeze_date != None,
                CbdcWallet.auto_unfreeze_date <= today,
                # Only unfreeze if appeal is NOT actively denied
                CbdcWallet.appeal_status != "DENIED",
            )
            .update({
                CbdcWallet.status: "active",
                CbdcWallet.freeze_reason: None,
                CbdcWallet.frozen_at: None,
                CbdcWallet.frozen_by: None,
                CbdcWallet.auto_unfreeze_date: None,
                CbdcWallet.appeal_status: "APPROVED",
            })
        )
        db.commit()
        if count > 0:
            logger.info("eCFA auto-unfreeze: %d wallets unfrozen", count)
    except Exception as exc:
        logger.error("eCFA auto-unfreeze failed: %s", exc)
        db.rollback()
    finally:
        db.close()
        _auto_unfreeze_lock.release()


def run_monetary_aggregate_snapshot():
    """Scheduled task: compute daily monetary aggregates for all WAEMU countries."""
    if not _monetary_agg_lock.acquire(blocking=False):
        logger.info("eCFA monetary aggregates: previous run still in progress, skipping")
        return
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
        _monetary_agg_lock.release()
