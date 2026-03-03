"""
Wallet routes — extends payment with full transaction history, tier info, and upgrade.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import timezone, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from src.database.connection import get_db
from src.database.models import User, X402Transaction, X402Tier, QueryLog
from src.utils.security import get_current_user

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


# ── Response schemas ──────────────────────────────────────────────────────────

class TierInfo(BaseModel):
    tier_name: str
    query_cost: float
    monthly_limit: Optional[int] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionDetail(BaseModel):
    id: int
    transaction_type: str
    amount: float
    balance_before: float
    balance_after: float
    reference_id: Optional[str] = None
    description: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WalletOverview(BaseModel):
    user_id: int
    username: str
    email: str
    balance: float
    tier: str
    tier_info: Optional[TierInfo] = None
    total_spent: float
    total_topped_up: float
    transaction_count: int


class UsageStats(BaseModel):
    user_id: int
    total_queries: int
    total_credits_used: float
    most_used_endpoint: Optional[str] = None
    queries_last_30_days: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/overview", response_model=WalletOverview)
async def get_wallet_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full wallet overview: balance, tier info, totals spent and topped up.
    No credit cost.
    """
    tier_record = (
        db.query(X402Tier)
        .filter(X402Tier.tier_name == current_user.tier)
        .first()
    )

    transactions = (
        db.query(X402Transaction)
        .filter(X402Transaction.user_id == current_user.id)
        .all()
    )

    total_spent = sum(t.amount for t in transactions if t.transaction_type == "deduct")
    total_topped_up = sum(t.amount for t in transactions if t.transaction_type == "topup")

    return WalletOverview(
        user_id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        balance=current_user.x402_balance,
        tier=current_user.tier,
        tier_info=TierInfo.model_validate(tier_record) if tier_record else None,
        total_spent=round(total_spent, 4),
        total_topped_up=round(total_topped_up, 4),
        transaction_count=len(transactions),
    )


@router.get("/transactions", response_model=list[TransactionDetail])
async def get_transaction_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    transaction_type: Optional[str] = Query(default=None, description="topup | deduct | refund"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full paginated transaction history. Filter by type (topup/deduct/refund).
    No credit cost.
    """
    query = (
        db.query(X402Transaction)
        .filter(X402Transaction.user_id == current_user.id)
    )
    if transaction_type:
        query = query.filter(X402Transaction.transaction_type == transaction_type)

    records = (
        query
        .order_by(X402Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [TransactionDetail.model_validate(r) for r in records]


@router.get("/tiers", response_model=list[TierInfo])
async def list_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all available subscription tiers and their costs.
    No credit cost.
    """
    tiers = db.query(X402Tier).filter(X402Tier.is_active.is_(True)).all()
    return [TierInfo.model_validate(t) for t in tiers]


@router.post("/upgrade", response_model=WalletOverview)
async def upgrade_tier(
    tier_name: str = Query(description="Target tier: free | pro | enterprise"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upgrade (or change) the user's subscription tier.
    No credit cost — tier change is free in this phase.
    """
    valid_tiers = {"free", "pro", "enterprise"}
    if tier_name not in valid_tiers:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{tier_name}'. Choose from: {sorted(valid_tiers)}",
        )

    if current_user.tier == tier_name:
        raise HTTPException(
            status_code=409,
            detail=f"User is already on the '{tier_name}' tier.",
        )

    current_user.tier = tier_name
    db.commit()
    db.refresh(current_user)

    tier_record = db.query(X402Tier).filter(X402Tier.tier_name == tier_name).first()
    transactions = db.query(X402Transaction).filter(X402Transaction.user_id == current_user.id).all()
    total_spent = sum(t.amount for t in transactions if t.transaction_type == "deduct")
    total_topped_up = sum(t.amount for t in transactions if t.transaction_type == "topup")

    return WalletOverview(
        user_id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        balance=current_user.x402_balance,
        tier=current_user.tier,
        tier_info=TierInfo.model_validate(tier_record) if tier_record else None,
        total_spent=round(total_spent, 4),
        total_topped_up=round(total_topped_up, 4),
        transaction_count=len(transactions),
    )


@router.get("/usage", response_model=UsageStats)
async def get_usage_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    API usage statistics: total queries, credits used, most-used endpoint.
    No credit cost.
    """
    from datetime import timedelta
    from sqlalchemy import func as sqlfunc

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    logs = db.query(QueryLog).filter(QueryLog.user_id == current_user.id).all()
    total_credits = sum(l.credits_used or 0 for l in logs)

    recent_count = (
        db.query(sqlfunc.count(QueryLog.id))
        .filter(
            QueryLog.user_id == current_user.id,
            QueryLog.created_at >= thirty_days_ago,
        )
        .scalar() or 0
    )

    # Find most-used endpoint
    endpoint_counts: dict[str, int] = {}
    for log in logs:
        endpoint_counts[log.endpoint] = endpoint_counts.get(log.endpoint, 0) + 1
    top_endpoint = max(endpoint_counts, key=endpoint_counts.get) if endpoint_counts else None

    return UsageStats(
        user_id=current_user.id,
        total_queries=len(logs),
        total_credits_used=round(total_credits, 4),
        most_used_endpoint=top_endpoint,
        queries_last_30_days=recent_count,
    )
