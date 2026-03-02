"""
FX Rate Update Task — Refreshes ECOWAS currency rates every 6 hours.

Phase 1: Re-seeds from default rates (placeholder for BCEAO API).
Phase 2: Will connect to BCEAO/IMF rate feeds.
"""
import logging
import threading
from datetime import date

from src.database.connection import SessionLocal
from src.database.cbdc_models import CbdcFxRate

logger = logging.getLogger(__name__)

_fx_lock = threading.Lock()

# Default seed rates (XOF per 1 unit of target)
DEFAULT_FX_RATES = {
    "NGN": 2.54,   "GHS": 0.041,  "GNF": 14.10,
    "SLE": 0.036,  "LRD": 0.315,  "GMD": 0.115,
    "MRU": 0.066,  "CVE": 0.167,
}


async def run_fx_rate_update():
    """Refresh FX rates from seed defaults (Phase 1 placeholder)."""
    if not _fx_lock.acquire(blocking=False):
        logger.warning("fx_rate_update: previous run still in progress, skipping")
        return

    db = SessionLocal()
    try:
        today = date.today()
        updated = 0

        for currency, rate in DEFAULT_FX_RATES.items():
            existing = db.query(CbdcFxRate).filter(
                CbdcFxRate.target_currency == currency,
                CbdcFxRate.effective_date == today,
            ).first()

            inverse = round(1.0 / rate, 6) if rate else 0

            if existing:
                # Rate already exists for today — skip (don't overwrite admin updates)
                continue
            else:
                db.add(CbdcFxRate(
                    base_currency="XOF",
                    target_currency=currency,
                    rate=rate,
                    inverse_rate=inverse,
                    effective_date=today,
                    source="FX_SCHEDULER",
                ))
                updated += 1

        db.commit()
        logger.info("fx_rate_update: date=%s updated=%d currencies", today, updated)

    except Exception as exc:
        logger.error("fx_rate_update failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _fx_lock.release()
