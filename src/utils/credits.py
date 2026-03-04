import uuid
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.database.models import User, X402Transaction, QueryLog
from src.config import settings


def deduct_credits(
    user: User,
    db: Session,
    endpoint: str,
    method: str = "GET",
    cost_multiplier: float = 1.0,
) -> float:
    """
    Deduct x402 credits from a user's balance.
    Writes an X402Transaction and a QueryLog record.
    Returns the cost deducted.

    Free-tier users (query_cost == 0.0) are not charged.

    Uses an atomic UPDATE ... WHERE balance >= cost to prevent
    race conditions on both PostgreSQL and SQLite (where
    SELECT ... FOR UPDATE is silently ignored).
    """
    cost = settings.DEFAULT_QUERY_COST * cost_multiplier

    # Determine effective cost based on tier
    from src.database.models import X402Tier
    tier_record = db.query(X402Tier).filter(X402Tier.tier_name == user.tier).first()
    if tier_record:
        cost = tier_record.query_cost * cost_multiplier

    if cost <= 0:
        # Free tier — just log, don't charge
        _log_query(db, user.id, endpoint, method, 0.0)
        return 0.0

    # Atomic deduction: UPDATE only succeeds if balance is sufficient.
    # This is race-condition safe on both PostgreSQL and SQLite.
    result = db.execute(
        text(
            "UPDATE users SET x402_balance = x402_balance - :cost "
            "WHERE id = :uid AND x402_balance >= :cost"
        ),
        {"cost": cost, "uid": user.id},
    )

    if result.rowcount == 0:
        # Either user doesn't exist or balance is insufficient
        current = db.query(User).filter(User.id == user.id).first()
        if not current:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "Insufficient x402 balance",
                "balance": float(current.x402_balance),
                "cost": cost,
                "topup_url": "/api/payment/topup",
            },
        )

    # Re-read the updated balance for the transaction log
    db.refresh(user)
    balance_after = user.x402_balance
    balance_before = balance_after + cost

    tx = X402Transaction(
        user_id=user.id,
        transaction_type="deduct",
        amount=cost,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_id=f"query-{uuid.uuid4().hex[:16]}",
        description=f"Query: {method} {endpoint}",
        status="completed",
    )
    db.add(tx)
    _log_query(db, user.id, endpoint, method, cost)
    db.commit()
    db.refresh(user)
    return cost


def _log_query(db: Session, user_id: int, endpoint: str, method: str, credits: float):
    log = QueryLog(
        user_id=user_id,
        endpoint=endpoint,
        method=method,
        credits_used=credits,
    )
    db.add(log)
