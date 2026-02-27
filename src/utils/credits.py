import uuid
from fastapi import HTTPException, status
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

    if user.x402_balance < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient x402 balance. Required: {cost}, Available: {user.x402_balance}",
        )

    balance_before = user.x402_balance
    user.x402_balance -= cost

    tx = X402Transaction(
        user_id=user.id,
        transaction_type="deduct",
        amount=cost,
        balance_before=balance_before,
        balance_after=user.x402_balance,
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
