"""
eCFA CBDC Monetary Policy Scheduled Tasks.

  - Daily interest accrual + demurrage (00:05 UTC)
  - Reserve requirement compliance check (06:00 UTC)
  - Standing facility maturation (hourly)
"""
import logging
from src.database.connection import SessionLocal
from src.engines.cbdc_monetary_policy_engine import CbdcMonetaryPolicyEngine

logger = logging.getLogger(__name__)


async def run_daily_interest_accrual():
    """Apply interest and demurrage across all wallets."""
    db = SessionLocal()
    try:
        engine = CbdcMonetaryPolicyEngine(db)
        result = engine.apply_daily_interest()
        logger.info(
            "Daily interest: paid=%.2f demurrage=%.2f wallets=%d",
            result["total_interest_paid_ecfa"],
            result["total_demurrage_collected_ecfa"],
            result["wallets_affected"],
        )
    except Exception as exc:
        logger.error("Daily interest accrual failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()


async def run_reserve_requirement_check():
    """Check reserve compliance for all commercial banks."""
    db = SessionLocal()
    try:
        engine = CbdcMonetaryPolicyEngine(db)
        result = engine.compute_reserve_requirements()
        logger.info(
            "Reserve check: banks=%d non_compliant=%d required=%.0f held=%.0f",
            result["banks_assessed"],
            result["banks_non_compliant"],
            result["total_required_ecfa"],
            result["total_held_ecfa"],
        )
    except Exception as exc:
        logger.error("Reserve requirement check failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()


async def run_facility_maturation():
    """Process matured standing facilities."""
    db = SessionLocal()
    try:
        engine = CbdcMonetaryPolicyEngine(db)
        result = engine.mature_facilities()
        if result["facilities_matured"] > 0:
            logger.info(
                "Facility maturation: matured=%d interest=%.2f",
                result["facilities_matured"],
                result["total_interest_ecfa"],
            )
    except Exception as exc:
        logger.error("Facility maturation failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
