"""
Centralized phone hash derivation for contributor identity.

Single source of truth -- all routes MUST use this module instead of
duplicating the HMAC logic.
"""
import hashlib
import hmac

from src.config import settings


def derive_phone_hash(identifier: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        identifier.encode(),
        hashlib.sha256,
    ).hexdigest()


def phone_hash_from_user(user) -> str:
    """Derive contributor phone hash from a User model instance."""
    raw = user.username or user.email or str(user.id)
    return derive_phone_hash(raw)


def truncate_phone_hash(full_hash: str, length: int = 12) -> str:
    """Truncate a phone hash for public-facing responses (leaderboards, etc.)."""
    if len(full_hash) <= length:
        return full_hash
    return full_hash[:length] + "..."
