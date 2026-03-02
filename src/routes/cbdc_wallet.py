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
from src.utils.security import get_current_user
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
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/create", "POST", 2.0)

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

    # Determine KYC tier
    if wtype in ("CENTRAL_BANK", "COMMERCIAL_BANK"):
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
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/balance", "GET", 1.0)

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
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/info", "GET", 1.0)

    wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == wallet_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

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
    """Set or update wallet PIN for USSD transactions."""
    wallet = db.query(CbdcWallet).filter(
        CbdcWallet.wallet_id == body.wallet_id,
        CbdcWallet.user_id == current_user.id,
    ).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found or not owned by you")

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
    current_user: User = Depends(get_current_user),
):
    """Freeze a wallet (admin/compliance action)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/freeze", "POST", 5.0)

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
    current_user: User = Depends(get_current_user),
):
    """Unfreeze a previously frozen wallet."""
    deduct_credits(current_user, db, "/api/v3/ecfa/wallet/unfreeze", "POST", 5.0)

    engine = CbdcLedgerEngine(db)
    result = engine.unfreeze_wallet(
        body.admin_wallet_id, body.target_wallet_id,
        actor_ip=request.client.host if request.client else None,
    )
    return WalletFreezeResponse(**result)
