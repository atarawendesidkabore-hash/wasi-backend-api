"""
/api/v3/invest — West African stock exchange investment endpoints.

Simulated brokerage: buy/sell units of NGX, GSE, BRVM indices (like ETFs).
Settlement via eCFA wallet.

Credit costs:
  GET  /api/v3/invest/markets       — 1 credit
  GET  /api/v3/invest/portfolio     — 1 credit
  POST /api/v3/invest/buy           — 2 credits
  POST /api/v3/invest/sell          — 2 credits
  GET  /api/v3/invest/orders        — 1 credit
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User
from src.engines.investment_engine import InvestmentEngine
from src.schemas.investment import (
    BuyOrderRequest, SellOrderRequest, OrderResponse,
    PortfolioResponse, MarketIndexResponse, OrderHistoryItem,
)
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user

router = APIRouter(prefix="/api/v3/invest", tags=["Investment"])
limiter = Limiter(key_func=get_remote_address)

_engine = InvestmentEngine()


@router.get("/markets", response_model=list[MarketIndexResponse])
@limiter.limit("30/minute")
async def list_tradeable_markets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all tradeable West African stock indices with latest prices."""
    deduct_credits(current_user, db, "/api/v3/invest/markets")
    return _engine.list_market_indices(db)


@router.get("/portfolio", response_model=PortfolioResponse)
@limiter.limit("30/minute")
async def get_portfolio(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """View your investment portfolio: holdings, current values, P&L."""
    deduct_credits(current_user, db, "/api/v3/invest/portfolio")
    return _engine.get_portfolio(db, current_user.id)


@router.post("/buy", response_model=OrderResponse)
@limiter.limit("10/minute")
async def buy_index(
    request: Request,
    body: BuyOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Buy units of a stock index with XOF from your eCFA wallet.

    Fee: 0.5% of order amount. Minimum order: 1,000 XOF.
    """
    deduct_credits(current_user, db, "/api/v3/invest/buy", cost_multiplier=2.0)
    return _engine.buy(
        db, current_user.id,
        body.exchange_code.upper(), body.index_name, body.amount_xof,
    )


@router.post("/sell", response_model=OrderResponse)
@limiter.limit("10/minute")
async def sell_index(
    request: Request,
    body: SellOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sell units of a stock index back for XOF to your eCFA wallet.

    Fee: 0.5% of sale amount. Proceeds credited after fee deduction.
    """
    deduct_credits(current_user, db, "/api/v3/invest/sell", cost_multiplier=2.0)
    return _engine.sell(
        db, current_user.id,
        body.exchange_code.upper(), body.index_name, body.units,
    )


@router.get("/orders", response_model=list[OrderHistoryItem])
@limiter.limit("30/minute")
async def get_order_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """View your recent investment orders (buy/sell history)."""
    deduct_credits(current_user, db, "/api/v3/invest/orders")
    return _engine.get_order_history(db, current_user.id, limit=limit)
