import jwt
import secrets
import hashlib
import uuid
import threading
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from src.config import settings
from src.database.connection import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Token Blacklist (in-memory) ──────────────────────────────────────────
# Process-local set of revoked access token JTIs. On restart, revoked refresh
# tokens are still checked in the DB; a stolen access token can only survive
# until its 60-min natural expiry after a restart (acceptable vs Redis).

_blacklisted_jtis: set[str] = set()
_blacklist_lock = threading.Lock()
_blacklist_expiry: dict[str, float] = {}  # jti → unix timestamp of token exp


def blacklist_jti(jti: str, exp_timestamp: float) -> None:
    with _blacklist_lock:
        _blacklisted_jtis.add(jti)
        _blacklist_expiry[jti] = exp_timestamp


def is_jti_blacklisted(jti: str) -> bool:
    with _blacklist_lock:
        return jti in _blacklisted_jtis


def cleanup_blacklist() -> int:
    now = datetime.now(timezone.utc).timestamp()
    with _blacklist_lock:
        expired = [jti for jti, exp in _blacklist_expiry.items() if exp < now]
        for jti in expired:
            _blacklisted_jtis.discard(jti)
            del _blacklist_expiry[jti]
    return len(expired)


# ── Password Hashing ────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Access Token (JWT) ──────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    jti = str(uuid.uuid4())
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc), "jti": jti})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Refresh Token ───────────────────────────────────────────────────────

def create_refresh_token() -> tuple[str, str]:
    """Generate a random refresh token. Returns (raw_token, sha256_hash)."""
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# ── Auth Dependencies ───────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Blacklist check (backward compat: old tokens without jti skip this)
    jti = payload.get("jti")
    if jti and is_jti_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from src.database.models import User
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def require_admin(
    current_user=Depends(get_current_user),
):
    """Reject non-admin users with 403."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_cbdc_role(allowed_wallet_types: list[str]):
    """FastAPI dependency that checks the user owns a CBDC wallet of the required type.

    Usage:
        @router.post("/admin/mint")
        async def mint(
            ...,
            _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
        ):
    """
    async def _check_role(
        current_user=Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        from src.database.cbdc_models import CbdcWallet
        wallet = db.query(CbdcWallet).filter(
            CbdcWallet.user_id == current_user.id,
            CbdcWallet.wallet_type.in_(allowed_wallet_types),
            CbdcWallet.status == "active",
        ).first()
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return wallet
    return _check_role
