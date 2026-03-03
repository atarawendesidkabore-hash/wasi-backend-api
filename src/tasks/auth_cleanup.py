"""Periodic cleanup of expired refresh tokens."""
import logging
from datetime import datetime, timezone, timedelta
from src.database.connection import SessionLocal
from src.database.models import RefreshToken

logger = logging.getLogger(__name__)


async def cleanup_expired_refresh_tokens():
    """Mark expired tokens as revoked, delete tokens revoked >30 days ago."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Mark expired tokens as revoked
        expired_count = db.query(RefreshToken).filter(
            RefreshToken.expires_at < now,
            RefreshToken.is_revoked == False,
        ).update({"is_revoked": True, "revoked_at": now})

        # Delete tokens revoked more than 30 days ago
        cutoff = now - timedelta(days=30)
        deleted_count = db.query(RefreshToken).filter(
            RefreshToken.is_revoked == True,
            RefreshToken.revoked_at < cutoff,
        ).delete()

        db.commit()
        if expired_count or deleted_count:
            logger.info(
                "auth_cleanup: marked_expired=%d deleted_old=%d",
                expired_count, deleted_count,
            )
    except Exception as exc:
        logger.error("auth_cleanup failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        db.close()
