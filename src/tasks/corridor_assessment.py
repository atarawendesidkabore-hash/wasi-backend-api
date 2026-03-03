"""
Corridor Assessment Task — reassess all trade corridors every 6 hours.

1. Run CorridorIntelligenceEngine.assess_all_corridors()
2. Log results
"""
import logging
import threading

from src.database.connection import SessionLocal

logger = logging.getLogger(__name__)
_corridor_lock = threading.Lock()


async def run_corridor_assessment():
    """Reassess all ECOWAS trade corridors."""
    if not _corridor_lock.acquire(blocking=False):
        logger.warning("corridor_assessment: previous run still in progress, skipping")
        return

    db = SessionLocal()
    try:
        from src.engines.corridor_engine import CorridorIntelligenceEngine
        engine = CorridorIntelligenceEngine(db)
        result = engine.assess_all_corridors()
        db.commit()
        logger.info(
            "corridor_assessment: assessed=%d corridors",
            result.get("corridors_assessed", 0),
        )
    except Exception as exc:
        logger.error("corridor_assessment failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
        _corridor_lock.release()
