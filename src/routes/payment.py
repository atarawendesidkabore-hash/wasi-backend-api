from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db
from src.database.models import User, X402Transaction
from src.schemas.payment import TopupRequest, PaymentStatusResponse, TransactionResponse
from src.utils.security import get_current_user, require_admin

router = APIRouter(prefix="/api/payment", tags=["Payment"])

limiter = Limiter(key_func=get_remote_address)


@router.post("/topup", response_model=PaymentStatusResponse)
@limiter.limit("20/minute")
async def topup_credits(
    request: Request,
    payload: TopupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Add x402 credits to a user's balance. ADMIN ONLY.
    The reference_id must be unique (prevents double-spend / idempotency guard).
    """
    if db.query(X402Transaction).filter(
        X402Transaction.reference_id == payload.reference_id
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Transaction reference_id already used",
        )

    balance_before = current_user.x402_balance
    current_user.x402_balance += payload.amount

    tx = X402Transaction(
        user_id=current_user.id,
        transaction_type="topup",
        amount=payload.amount,
        balance_before=balance_before,
        balance_after=current_user.x402_balance,
        reference_id=payload.reference_id,
        description=f"Manual top-up of {payload.amount} credits",
        status="completed",
    )
    db.add(tx)
    db.commit()
    db.refresh(current_user)

    return _build_status(current_user, db)


@router.get("/status", response_model=PaymentStatusResponse)
@limiter.limit("30/minute")
async def get_payment_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current x402 balance and the 10 most recent transactions."""
    return _build_status(current_user, db)


def _build_status(user: User, db: Session) -> PaymentStatusResponse:
    recent = (
        db.query(X402Transaction)
        .filter(X402Transaction.user_id == user.id)
        .order_by(X402Transaction.created_at.desc())
        .limit(10)
        .all()
    )
    return PaymentStatusResponse(
        user_id=user.id,
        balance=user.x402_balance,
        tier=user.tier,
        recent_transactions=[TransactionResponse.model_validate(t) for t in recent],
    )
