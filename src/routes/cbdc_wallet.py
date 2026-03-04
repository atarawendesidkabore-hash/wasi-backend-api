"""
eCFA CBDC Wallet Management — /api/v3/ecfa/wallet/

Endpoints for creating, querying, freezing, and closing eCFA wallets.

Credit costs:
  POST /create      — 2 credits
  GET  /balance/{id} — 1 credit
  GET  /info/{id}   — 1 credit
  POST /set-pin     — 0 credits (free)
  POST /freeze      — 5 credits (admin)
  POST /unfreeze    — 5 credits (admin)
  POST /close       — 0 credits
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet, KYC_TIER_LIMITS
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits
from src.utils.cbdc_crypto import generate_wallet_id, hash_pin, hash_phone
from src.utils.cbdc_audit import log_wallet_created
from src.schemas.cbdc_wallet import (
    WalletCreateRequest, WalletCreateResponse,
    WalletBalanceResponse, WalletFreezeRequest, WalletFreezeResponse,
    WalletInfoResponse, SetPinRequest, SetPinResponse,
)
from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

router = APIRouter(prefix="/api/v3/ecfa/wallet", tags=["eCFA Wallet"])
limiter = Limiter(key_func=get_remote_address)

VALID_WALLET_TYPES = {"CENTRAL_BANK", "COMMERCIAL_BANK", "AGENT", "MERCHANT", "RETAIL"}


@router.post("/create", response_model=WalletCreateResponse)
@limiter.limit("10/minute")
async def create_wallet(
    request: Request,
    body: WalletCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new eCFA wallet. Auto-assigns KYC Tier 0 (or Tier 3 for institutions)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/create", method="POST", cost_multiplier=2.0)

    # Validate country
    country = db.query(Country).filter(
        Country.code == body.country_code.upper(),
        Country.is_active == True,
    ).first()
    if not country:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Country '{body.country_code}' not found or inactive",
        )

    # Validate wallet type
    wtype = body.wallet_type.upper()
    if wtype not in VALID_WALLET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid wallet type. Must be one of: {', '.join(sorted(VALID_WALLET_TYPES))}",
        )

    # Institutional wallet types require is_admin flag on user account
    if wtype in ("CENTRAL_BANK", "COMMERCIAL_BANK"):
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to create institutional wallets",
            )
        kyc_tier = 3
    else:
        kyc_tier = 0

    limits = KYC_TIER_LIMITS[kyc_tier]

    wallet_id = generate_wallet_id()

    wallet = CbdcWallet(
        wallet_id=wallet_id,
        user_id=current_user.id,
        country_id=country.id,
        phone_hash=body.phone_hash,
        wallet_type=wtype,
        institution_code=body.institution_code,
        institution_name=body.institution_name,
        kyc_tier=kyc_tier,
        daily_limit_ecfa=limits["daily"] if limits["daily"] != float("inf") else 999_999_999_999.0,
        balance_limit_ecfa=limits["balance"] if limits["balance"] != float("inf") else 999_999_999_999.0,
        pin_hash=hash_pin(body.pin) if body.pin else None,
        status="active",
    )
    db.add(wallet)

    log_wallet_created(
        db, wallet_id, wtype, body.country_code.upper(),
        actor_ip=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(wallet)

    return WalletCreateResponse(
        wallet_id=wallet.wallet_id,
        wallet_type=wallet.wallet_type,
        country_code=body.country_code.upper(),
        kyc_tier=wallet.kyc_tier,
        daily_limit_ecfa=wallet.daily_limit_ecfa,
        balance_limit_ecfa=wallet.balance_limit_ecfa,
        status=wallet.status,
        created_at=wallet.created_at,
    )


@router.get("/balance/{wallet_id}", response_model=WalletBalanceResponse)
@limiter.limit("30/minute")
async def get_balance(
    request: Request,
    wallet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get wallet balance with ledger verification."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/balance", method="GET", cost_multiplier=1.0)

    # IDOR protection: verify the wallet belongs to the current user
    wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == wallet_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if wallet.user_id is not None and wallet.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this wallet")

    engine = CbdcLedgerEngine(db)
    result = engine.get_balance(wallet_id)
    return WalletBalanceResponse(**result)


@router.get("/info/{wallet_id}", response_model=WalletInfoResponse)
@limiter.limit("30/minute")
async def get_wallet_info(
    request: Request,
    wallet_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get wallet metadata and status."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/info", method="GET", cost_multiplier=1.0)

    wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == wallet_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    # IDOR protection: verify the wallet belongs to the current user
    if wallet.user_id is not None and wallet.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied to this wallet")

    country = db.query(Country).filter(Country.id == wallet.country_id).first()

    return WalletInfoResponse(
        wallet_id=wallet.wallet_id,
        wallet_type=wallet.wallet_type,
        country_code=country.code if country else "XX",
        kyc_tier=wallet.kyc_tier,
        balance_ecfa=wallet.balance_ecfa,
        available_balance_ecfa=wallet.available_balance_ecfa,
        status=wallet.status,
        daily_limit_ecfa=wallet.daily_limit_ecfa,
        balance_limit_ecfa=wallet.balance_limit_ecfa,
        has_pin=wallet.pin_hash is not None,
        has_public_key=wallet.public_key_hex is not None,
        created_at=wallet.created_at,
        last_activity_at=wallet.last_activity_at,
    )


@router.post("/set-pin", response_model=SetPinResponse)
@limiter.limit("5/minute")
async def set_pin(
    request: Request,
    body: SetPinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set or update wallet PIN for USSD transactions.

    If the wallet already has a PIN, the current_pin field is required.
    """
    wallet = db.query(CbdcWallet).filter(
        CbdcWallet.wallet_id == body.wallet_id,
        CbdcWallet.user_id == current_user.id,
    ).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found or not owned by you")

    # If wallet already has a PIN, verify current PIN before allowing change
    if wallet.pin_hash is not None:
        if not body.current_pin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current PIN is required to change an existing PIN",
            )
        from src.utils.cbdc_crypto import verify_pin
        if not verify_pin(body.current_pin, wallet.pin_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current PIN is incorrect",
            )

    from src.utils.cbdc_audit import log_pin_changed
    wallet.pin_hash = hash_pin(body.new_pin)
    log_pin_changed(db, wallet.wallet_id)
    db.commit()

    return SetPinResponse(wallet_id=wallet.wallet_id, message="PIN set successfully")


@router.post("/freeze", response_model=WalletFreezeResponse)
@limiter.limit("10/minute")
async def freeze_wallet(
    request: Request,
    body: WalletFreezeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Freeze a wallet (admin only)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/freeze", method="POST", cost_multiplier=5.0)

    # Ownership check: verify admin_wallet_id belongs to current_user
    admin_wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == body.admin_wallet_id).first()
    if not admin_wallet:
        raise HTTPException(status_code=404, detail="Admin wallet not found")
    if admin_wallet.user_id is not None and admin_wallet.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Admin wallet does not belong to you")

    engine = CbdcLedgerEngine(db)
    result = engine.freeze_wallet(
        body.admin_wallet_id, body.target_wallet_id, body.reason,
        actor_ip=request.client.host if request.client else None,
    )
    return WalletFreezeResponse(**result)


@router.post("/unfreeze", response_model=WalletFreezeResponse)
@limiter.limit("10/minute")
async def unfreeze_wallet(
    request: Request,
    body: WalletFreezeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Unfreeze a previously frozen wallet (admin only)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/unfreeze", method="POST", cost_multiplier=5.0)

    # Ownership check: verify admin_wallet_id belongs to current_user
    admin_wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == body.admin_wallet_id).first()
    if not admin_wallet:
        raise HTTPException(status_code=404, detail="Admin wallet not found")
    if admin_wallet.user_id is not None and admin_wallet.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Admin wallet does not belong to you")

    engine = CbdcLedgerEngine(db)
    result = engine.unfreeze_wallet(
        body.admin_wallet_id, body.target_wallet_id,
        actor_ip=request.client.host if request.client else None,
    )
    return WalletFreezeResponse(**result)
