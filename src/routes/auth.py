import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db
from src.database.models import User, RefreshToken
from src.schemas.auth import (
    UserRegister, TokenResponse, TokenResponseWithRefresh,
    RefreshRequest, LogoutRequest, UserResponse, UserSessionsResponse,
    DeleteAccountRequest,
)
from src.utils.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    get_current_user, require_admin, oauth2_scheme,
    create_refresh_token, hash_refresh_token, blacklist_jti,
)
from src.config import settings

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user. Initial x402 balance is set from FREE_TIER_BALANCE."""
    # Generic message prevents user enumeration (H1)
    if db.query(User).filter(
        or_(User.username == payload.username, User.email == payload.email)
    ).first():
        raise HTTPException(status_code=409, detail="Registration failed. Username or email may already be in use.")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        x402_balance=settings.FREE_TIER_BALANCE,
        tier="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponseWithRefresh)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2 password flow. Returns a JWT access token + refresh token.
    Supply username (not email) in the 'username' field.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    # Create refresh token — store hash in DB
    raw_refresh, refresh_hash = create_refresh_token()
    refresh_jti = str(uuid.uuid4())
    refresh_expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        jti=refresh_jti,
        expires_at=refresh_expires,
    ))
    db.commit()

    return TokenResponseWithRefresh(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponseWithRefresh)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    payload: RefreshRequest,
    db: Session = Depends(get_db),
):
    """Exchange a valid refresh token for a new access+refresh pair.

    The old refresh token is revoked (rotation). If a revoked refresh token
    is presented, ALL of that user's tokens are revoked (replay detection).
    """
    token_hash = hash_refresh_token(payload.refresh_token)

    db_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
    ).first()

    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Replay detection: revoked token reuse → revoke ALL user sessions
    # Use naive UTC for SQLite compatibility (SQLite strips tzinfo on storage)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if db_token.is_revoked:
        db.query(RefreshToken).filter(
            RefreshToken.user_id == db_token.user_id,
            RefreshToken.is_revoked == False,
        ).update({"is_revoked": True, "revoked_at": now})
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Refresh token reuse detected — all sessions revoked",
        )

    # Check expiry
    if db_token.expires_at < now:
        db_token.is_revoked = True
        db_token.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    # Verify user still active
    user = db.query(User).filter(User.id == db_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Revoke old refresh token (rotation)
    db_token.is_revoked = True
    db_token.revoked_at = now

    # Issue new pair
    new_access = create_access_token(data={"sub": str(user.id)})
    raw_refresh, refresh_hash = create_refresh_token()
    new_jti = str(uuid.uuid4())
    refresh_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        jti=new_jti,
        expires_at=refresh_expires,
    ))
    db.commit()

    return TokenResponseWithRefresh(
        access_token=new_access,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout")
async def logout(
    payload: LogoutRequest = None,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Blacklist the current access token and optionally revoke the refresh token."""
    decoded = decode_access_token(token)
    jti = decoded.get("jti")
    if jti:
        exp = decoded.get("exp", 0)
        blacklist_jti(jti, exp)

    # Revoke refresh token if provided
    if payload and payload.refresh_token:
        token_hash = hash_refresh_token(payload.refresh_token)
        db_token = db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,
        ).first()
        if db_token:
            db_token.is_revoked = True
            db_token.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()

    return {"detail": "Successfully logged out"}


@router.post("/admin/revoke-sessions/{user_id}", response_model=UserSessionsResponse)
async def admin_revoke_user_sessions(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: revoke all active refresh tokens for a user."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active_tokens = db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_revoked == False,
        RefreshToken.expires_at > now,
    ).all()

    revoked_count = 0
    for t in active_tokens:
        t.is_revoked = True
        t.revoked_at = now
        revoked_count += 1

    db.commit()

    return UserSessionsResponse(
        user_id=user_id,
        active_sessions=0,
        revoked_count=revoked_count,
        sessions=[],
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


@router.delete("/me", status_code=200)
async def delete_account(
    payload: DeleteAccountRequest,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR right-to-erasure: permanently delete the authenticated user's account
    and all associated data. Requires password re-confirmation. This action is
    irreversible.
    """
    # Verify password before destructive action
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Incorrect password — account deletion denied",
        )

    uid = current_user.id

    # ── Cascade delete all user-owned records (leaf → root order) ──

    # 1. Alerts (deliveries reference rules, so delete deliveries first)
    from src.database.alert_models import AlertRule, AlertDelivery
    db.query(AlertDelivery).filter(AlertDelivery.user_id == uid).delete()
    db.query(AlertRule).filter(AlertRule.user_id == uid).delete()

    # 2. Auth tokens
    db.query(RefreshToken).filter(RefreshToken.user_id == uid).delete()

    # 3. Financial logs
    from src.database.models import X402Transaction, QueryLog, BankDossierScore
    db.query(X402Transaction).filter(X402Transaction.user_id == uid).delete()
    db.query(QueryLog).filter(QueryLog.user_id == uid).delete()
    db.query(BankDossierScore).filter(BankDossierScore.user_id == uid).delete()

    # 4. Forecast scenarios
    from src.database.forecast_v2_models import ForecastScenario
    db.query(ForecastScenario).filter(ForecastScenario.user_id == uid).delete()

    # 5. Valuation (results reference targets)
    from src.database.valuation_models import ValuationTarget, ValuationResult
    db.query(ValuationResult).filter(ValuationResult.user_id == uid).delete()
    db.query(ValuationTarget).filter(ValuationTarget.user_id == uid).delete()

    # 6. Reconciliation audit trail — SET NULL (not owned, just reviewer ref)
    from src.database.reconciliation_models import DataQuarantine
    db.query(DataQuarantine).filter(
        DataQuarantine.reviewed_by == uid
    ).update({DataQuarantine.reviewed_by: None})

    # 7. CBDC wallets and their downstream records
    from src.database.cbdc_models import (
        CbdcWallet, CbdcLedgerEntry, CbdcKycRecord, CbdcAmlAlert,
        CbdcMerchant, CbdcReserveRequirement, CbdcStandingFacility,
        CbdcEligibleCollateral,
    )
    from src.database.cbdc_payment_models import CbdcCrossBorderPayment

    wallet_ids = [
        w.wallet_id for w in
        db.query(CbdcWallet.wallet_id).filter(CbdcWallet.user_id == uid).all()
    ]
    if wallet_ids:
        # Delete wallet children first
        db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcKycRecord).filter(
            CbdcKycRecord.wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcAmlAlert).filter(
            CbdcAmlAlert.wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcMerchant).filter(
            CbdcMerchant.wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcReserveRequirement).filter(
            CbdcReserveRequirement.bank_wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcStandingFacility).filter(
            CbdcStandingFacility.bank_wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcEligibleCollateral).filter(
            CbdcEligibleCollateral.owner_wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        db.query(CbdcCrossBorderPayment).filter(
            CbdcCrossBorderPayment.sender_wallet_id.in_(wallet_ids)
        ).delete(synchronize_session=False)
        # Delete wallets
        db.query(CbdcWallet).filter(CbdcWallet.user_id == uid).delete()

    # 8. Delete the user
    db.query(User).filter(User.id == uid).delete()
    db.commit()

    # Blacklist the current access token so it can't be reused
    decoded = decode_access_token(token)
    jti = decoded.get("jti")
    if jti:
        blacklist_jti(jti, decoded.get("exp", 0))

    return {"detail": "Account and all associated data permanently deleted"}


@router.get("/me/export")
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR data portability: export all data associated with the authenticated user."""
    uid = current_user.id

    from src.database.models import X402Transaction, QueryLog, BankDossierScore

    transactions = [
        {"id": t.id, "type": t.transaction_type, "amount": float(t.amount),
         "balance_before": float(t.balance_before), "balance_after": float(t.balance_after),
         "description": t.description, "status": t.status, "created_at": str(t.created_at)}
        for t in db.query(X402Transaction).filter(X402Transaction.user_id == uid).all()
    ]

    query_logs = [
        {"id": q.id, "endpoint": q.endpoint, "method": q.method,
         "credits_used": float(q.credits_used), "created_at": str(q.created_at)}
        for q in db.query(QueryLog).filter(QueryLog.user_id == uid).all()
    ]

    # CBDC wallets
    from src.database.cbdc_models import CbdcWallet
    wallets = [
        {"wallet_id": w.wallet_id, "wallet_type": w.wallet_type,
         "country_code": w.country_code, "status": w.status,
         "balance_ecfa": float(w.balance_ecfa) if w.balance_ecfa else 0.0,
         "created_at": str(w.created_at)}
        for w in db.query(CbdcWallet).filter(CbdcWallet.user_id == uid).all()
    ]

    return {
        "profile": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "tier": current_user.tier,
            "x402_balance": float(current_user.x402_balance),
            "is_active": current_user.is_active,
            "created_at": str(current_user.created_at),
        },
        "transactions": transactions,
        "query_logs": query_logs,
        "cbdc_wallets": wallets,
        "exported_at": str(datetime.now(timezone.utc)),
    }
