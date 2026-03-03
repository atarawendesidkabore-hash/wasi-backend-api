"""
eCFA CBDC Transaction Operations — /api/v3/ecfa/tx/

Endpoints for sending, receiving, and querying eCFA transactions.

Credit costs:
  POST /send           — 2 credits
  POST /merchant-pay   — 2 credits
  POST /cash-in        — 1 credit
  POST /cash-out       — 1 credit
  GET  /status/{id}    — 1 credit
  GET  /history/{id}   — 1 credit
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.cbdc_models import CbdcTransaction, CbdcWallet
from src.utils.security import get_current_user, require_cbdc_role, require_admin
from src.utils.credits import deduct_credits
from src.engines.cbdc_ledger_engine import CbdcLedgerEngine


from src.schemas.cbdc_transaction import (
    TransferRequest, TransferResponse,
    MintRequest, MintResponse,
    BurnRequest, BurnResponse,
    TransactionStatusResponse,
    TransactionHistoryItem, TransactionHistoryResponse,
)

def _verify_wallet_ownership(db, wallet_id: str, user_id: int) -> None:
    """Verify that the given wallet belongs to the authenticated user."""
    wallet = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == wallet_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    if wallet.user_id is not None and wallet.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this wallet")


router = APIRouter(prefix="/api/v3/ecfa/tx", tags=["eCFA Transactions"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/send", response_model=TransferResponse)
@limiter.limit("30/minute")
async def send_ecfa(
    request: Request,
    body: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send eCFA between wallets (P2P, P2B, or any transfer type)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/send", "POST", 2.0)
    _verify_wallet_ownership(db, body.sender_wallet_id, current_user.id)

    engine = CbdcLedgerEngine(db)
    result = engine.transfer(
        sender_wallet_id=body.sender_wallet_id,
        receiver_wallet_id=body.receiver_wallet_id,
        amount_ecfa=body.amount_ecfa,
        tx_type=body.tx_type,
        channel=body.channel,
        pin=body.pin,
        signature=body.signature,
        nonce=body.nonce,
        policy_id=body.policy_id,
        spending_category=body.spending_category,
        memo=body.memo,
        fee_ecfa=body.fee_ecfa,
    )
    return TransferResponse(**result)


@router.post("/merchant-pay", response_model=TransferResponse)
@limiter.limit("30/minute")
async def merchant_payment(
    request: Request,
    body: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pay a merchant with eCFA. Enforces spending category restrictions."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/merchant-pay", "POST", 2.0)
    _verify_wallet_ownership(db, body.sender_wallet_id, current_user.id)

    engine = CbdcLedgerEngine(db)
    result = engine.transfer(
        sender_wallet_id=body.sender_wallet_id,
        receiver_wallet_id=body.receiver_wallet_id,
        amount_ecfa=body.amount_ecfa,
        tx_type="MERCHANT_PAYMENT",
        channel=body.channel,
        pin=body.pin,
        signature=body.signature,
        nonce=body.nonce,
        policy_id=body.policy_id,
        spending_category=body.spending_category,
        memo=body.memo,
        fee_ecfa=body.fee_ecfa,
    )
    return TransferResponse(**result)


@router.post("/cash-in", response_model=TransferResponse)
@limiter.limit("20/minute")
async def cash_in(
    request: Request,
    body: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Agent cash-in: convert physical CFA to eCFA."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/cash-in", "POST", 1.0)
    _verify_wallet_ownership(db, body.sender_wallet_id, current_user.id)

    engine = CbdcLedgerEngine(db)
    result = engine.transfer(
        sender_wallet_id=body.sender_wallet_id,  # agent wallet
        receiver_wallet_id=body.receiver_wallet_id,  # user wallet
        amount_ecfa=body.amount_ecfa,
        tx_type="CASH_IN",
        channel=body.channel,
        pin=body.pin,
        memo=body.memo,
    )
    return TransferResponse(**result)


@router.post("/cash-out", response_model=TransferResponse)
@limiter.limit("20/minute")
async def cash_out(
    request: Request,
    body: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Agent cash-out: convert eCFA to physical CFA."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/cash-out", "POST", 1.0)
    _verify_wallet_ownership(db, body.sender_wallet_id, current_user.id)

    engine = CbdcLedgerEngine(db)
    result = engine.transfer(
        sender_wallet_id=body.sender_wallet_id,  # user wallet
        receiver_wallet_id=body.receiver_wallet_id,  # agent wallet
        amount_ecfa=body.amount_ecfa,
        tx_type="CASH_OUT",
        channel=body.channel,
        pin=body.pin,
        memo=body.memo,
    )
    return TransferResponse(**result)


@router.post("/mint", response_model=MintResponse)
@limiter.limit("5/minute")
async def mint_ecfa(
    request: Request,
    body: MintRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Mint new eCFA (Central Bank only)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/mint", "POST", 10.0)

    engine = CbdcLedgerEngine(db)
    result = engine.mint(
        central_bank_wallet_id=body.central_bank_wallet_id,
        target_wallet_id=body.target_wallet_id,
        amount_ecfa=body.amount_ecfa,
        reference=body.reference,
        memo=body.memo,
        actor_ip=request.client.host if request.client else None,
    )
    return MintResponse(**result)


@router.post("/burn", response_model=BurnResponse)
@limiter.limit("5/minute")
async def burn_ecfa(
    request: Request,
    body: BurnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    _role=Depends(require_cbdc_role(["CENTRAL_BANK"])),
):
    """Burn eCFA (Central Bank only)."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/burn", "POST", 10.0)

    engine = CbdcLedgerEngine(db)
    result = engine.burn(
        central_bank_wallet_id=body.central_bank_wallet_id,
        source_wallet_id=body.source_wallet_id,
        amount_ecfa=body.amount_ecfa,
        reference=body.reference,
        actor_ip=request.client.host if request.client else None,
    )
    return BurnResponse(**result)


@router.get("/status/{transaction_id}", response_model=TransactionStatusResponse)
@limiter.limit("30/minute")
async def get_transaction_status(
    request: Request,
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get transaction status by ID."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/status", "GET", 1.0)

    tx = db.query(CbdcTransaction).filter(
        CbdcTransaction.transaction_id == transaction_id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # IDOR protection: user must own sender or receiver wallet
    user_wallets = {w.wallet_id for w in db.query(CbdcWallet.wallet_id).filter(
        CbdcWallet.user_id == current_user.id
    ).all()}
    if tx.sender_wallet_id not in user_wallets and tx.receiver_wallet_id not in user_wallets:
        raise HTTPException(status_code=403, detail="Access denied to this transaction")

    return TransactionStatusResponse.model_validate(tx)


@router.get("/history/{wallet_id}", response_model=TransactionHistoryResponse)
@limiter.limit("20/minute")
async def get_transaction_history(
    request: Request,
    wallet_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get paginated transaction history for a wallet."""
    deduct_credits(current_user, db, "/api/v3/ecfa/tx/history", "GET", 1.0)
    _verify_wallet_ownership(db, wallet_id, current_user.id)

    # Count total
    total = db.query(CbdcTransaction).filter(
        (CbdcTransaction.sender_wallet_id == wallet_id) |
        (CbdcTransaction.receiver_wallet_id == wallet_id)
    ).count()

    # Fetch page
    offset = (page - 1) * page_size
    txs = db.query(CbdcTransaction).filter(
        (CbdcTransaction.sender_wallet_id == wallet_id) |
        (CbdcTransaction.receiver_wallet_id == wallet_id)
    ).order_by(CbdcTransaction.initiated_at.desc()).offset(offset).limit(page_size).all()

    items = []
    for tx in txs:
        direction = "SENT" if tx.sender_wallet_id == wallet_id else "RECEIVED"
        counterparty = (
            tx.receiver_wallet_id if direction == "SENT" else tx.sender_wallet_id
        )
        items.append(TransactionHistoryItem(
            transaction_id=tx.transaction_id,
            tx_type=tx.tx_type,
            status=tx.status,
            amount_ecfa=tx.amount_ecfa,
            fee_ecfa=tx.fee_ecfa,
            counterparty_wallet_id=counterparty,
            direction=direction,
            channel=tx.channel,
            initiated_at=tx.initiated_at,
        ))

    return TransactionHistoryResponse(
        wallet_id=wallet_id,
        transactions=items,
        total_count=total,
        page=page,
        page_size=page_size,
    )
