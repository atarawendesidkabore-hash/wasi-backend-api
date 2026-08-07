"""
/api/v3/etf — WASI ETF product catalog and trading.

42 ETF products across 7 categories: Broad, Regional, Sector, Commodity, Equity, Strategy, Country.
NAVs calculated from live WASI data. Trading via eCFA wallet.

Credit costs:
  GET  /api/v3/etf/catalog          — 1 credit
  GET  /api/v3/etf/nav/all          — 2 credits  (triggers NAV recalculation)
  GET  /api/v3/etf/{ticker}         — 1 credit
  GET  /api/v3/etf/{ticker}/history — 1 credit
  POST /api/v3/etf/buy              — 2 credits
  POST /api/v3/etf/sell             — 2 credits
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User
from src.database.etf_models import EtfProduct, EtfNavHistory
from src.database.cbdc_models import CbdcWallet
from src.database.investment_models import InvestmentPortfolio, StockHolding, StockOrder
from src.engines.etf_engine import EtfEngine
from src.schemas.etf import (
    EtfListItem, EtfDetailResponse, EtfBuyRequest, EtfSellRequest,
    EtfOrderResponse, EtfNavHistoryItem,
)
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user

router = APIRouter(prefix="/api/v3/etf", tags=["ETF"])
limiter = Limiter(key_func=get_remote_address)

_engine = EtfEngine()

FEE_RATE = 0.005  # 0.5% trading fee
MIN_ORDER_XOF = 500.0


def _get_wallet(db: Session, user_id: int) -> CbdcWallet:
    wallet = (
        db.query(CbdcWallet)
        .filter(CbdcWallet.user_id == user_id, CbdcWallet.wallet_type == "RETAIL",
                CbdcWallet.status == "active")
        .first()
    )
    if not wallet:
        raise HTTPException(status_code=404, detail="No active eCFA wallet. Create one first.")
    return wallet


def _get_portfolio(db: Session, user_id: int) -> InvestmentPortfolio:
    portfolio = db.query(InvestmentPortfolio).filter(
        InvestmentPortfolio.user_id == user_id
    ).first()
    if not portfolio:
        portfolio = InvestmentPortfolio(user_id=user_id)
        db.add(portfolio)
        db.flush()
    return portfolio


@router.get("/catalog", response_model=list[EtfListItem])
@limiter.limit("30/minute")
async def list_etf_catalog(
    request: Request,
    category: str = Query(None, description="Filter: BROAD|REGIONAL|SECTOR|COMMODITY|EQUITY|STRATEGY|COUNTRY"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all 42 WASI ETF products with current NAVs."""
    deduct_credits(current_user, db, "/api/v3/etf/catalog")
    q = db.query(EtfProduct).filter(EtfProduct.is_active == True)
    if category:
        q = q.filter(EtfProduct.category == category.upper())
    etfs = q.order_by(EtfProduct.category, EtfProduct.ticker).all()
    return [
        EtfListItem(
            ticker=e.ticker, name=e.name, category=e.category,
            nav_xof=e.nav_xof, nav_usd=e.nav_usd,
            change_pct=e.change_pct or 0.0, fee_pct=e.fee_pct,
            description=e.description,
        )
        for e in etfs
    ]


@router.get("/nav/all")
@limiter.limit("10/minute")
async def recalculate_all_navs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recalculate NAV for all 42 ETFs from live data. Returns updated prices."""
    deduct_credits(current_user, db, "/api/v3/etf/nav/all", cost_multiplier=2.0)
    results = _engine.calculate_all_navs(db)
    return {
        "total_products": len(results),
        "products": results,
    }


@router.get("/{ticker}", response_model=EtfDetailResponse)
@limiter.limit("30/minute")
async def get_etf_detail(
    request: Request,
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full details for a specific ETF product."""
    deduct_credits(current_user, db, "/api/v3/etf/detail")
    etf = db.query(EtfProduct).filter(EtfProduct.ticker == ticker.upper()).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {ticker} not found")
    return EtfDetailResponse(
        ticker=etf.ticker, name=etf.name, category=etf.category,
        description=etf.description,
        nav_xof=etf.nav_xof, nav_usd=etf.nav_usd,
        change_pct=etf.change_pct or 0.0, fee_pct=etf.fee_pct,
        currency=etf.currency, underlying_type=etf.underlying_type,
        is_active=etf.is_active,
        nav_updated_at=etf.nav_updated_at.isoformat() if etf.nav_updated_at else None,
    )


@router.get("/{ticker}/history", response_model=list[EtfNavHistoryItem])
@limiter.limit("30/minute")
async def get_etf_nav_history(
    request: Request,
    ticker: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get NAV history for an ETF product."""
    deduct_credits(current_user, db, "/api/v3/etf/history")
    etf = db.query(EtfProduct).filter(EtfProduct.ticker == ticker.upper()).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {ticker} not found")
    rows = (
        db.query(EtfNavHistory)
        .filter(EtfNavHistory.etf_id == etf.id)
        .order_by(EtfNavHistory.nav_date.desc())
        .limit(days)
        .all()
    )
    return [
        EtfNavHistoryItem(
            nav_date=str(r.nav_date), nav_xof=r.nav_xof,
            nav_usd=r.nav_usd, change_pct=r.change_pct,
        )
        for r in rows
    ]


@router.post("/buy", response_model=EtfOrderResponse)
@limiter.limit("10/minute")
async def buy_etf(
    request: Request,
    body: EtfBuyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buy ETF units with XOF from eCFA wallet. Fee: 0.5%, min 500 XOF."""
    deduct_credits(current_user, db, "/api/v3/etf/buy", cost_multiplier=2.0)

    etf = db.query(EtfProduct).filter(
        EtfProduct.ticker == body.ticker.upper(), EtfProduct.is_active == True
    ).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {body.ticker} not found or inactive")
    if etf.nav_xof <= 0:
        raise HTTPException(status_code=400, detail=f"ETF {etf.ticker} has no price yet. Run /nav/all first.")
    if body.amount_xof < MIN_ORDER_XOF:
        raise HTTPException(status_code=400, detail=f"Minimum order: {MIN_ORDER_XOF:,.0f} XOF")

    wallet = _get_wallet(db, current_user.id)
    if wallet.available_balance_ecfa < body.amount_xof:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance: {wallet.available_balance_ecfa:,.2f} XOF available",
        )

    fee = round(body.amount_xof * FEE_RATE, 2)
    net = body.amount_xof - fee
    units = round(net / etf.nav_xof, 6)

    # Deduct wallet
    wallet.balance_ecfa -= body.amount_xof
    wallet.available_balance_ecfa -= body.amount_xof

    # Update portfolio + holding (reuse investment tables with ETF ticker as index_name)
    portfolio = _get_portfolio(db, current_user.id)
    holding = (
        db.query(StockHolding)
        .filter(StockHolding.portfolio_id == portfolio.id,
                StockHolding.exchange_code == "ETF",
                StockHolding.index_name == etf.ticker)
        .first()
    )
    if holding:
        old_cost = holding.total_cost
        holding.units = round(holding.units + units, 6)
        holding.total_cost = old_cost + net
        holding.avg_buy_price = round(holding.total_cost / holding.units, 4) if holding.units > 0 else 0
    else:
        holding = StockHolding(
            portfolio_id=portfolio.id, exchange_code="ETF", index_name=etf.ticker,
            units=units, avg_buy_price=etf.nav_xof, total_cost=net,
        )
        db.add(holding)

    portfolio.total_invested += net

    order = StockOrder(
        portfolio_id=portfolio.id, user_id=current_user.id,
        exchange_code="ETF", index_name=etf.ticker, side="BUY",
        units=units, price_per_unit=etf.nav_xof, total_amount=body.amount_xof,
        wallet_id=wallet.wallet_id, status="EXECUTED",
    )
    db.add(order)
    db.commit()

    return EtfOrderResponse(
        order_id=order.id, side="BUY", ticker=etf.ticker, name=etf.name,
        units=units, nav_per_unit=etf.nav_xof,
        amount_xof=body.amount_xof, fee_xof=fee, net_invested=net,
        status="EXECUTED",
    )


@router.post("/sell", response_model=EtfOrderResponse)
@limiter.limit("10/minute")
async def sell_etf(
    request: Request,
    body: EtfSellRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sell ETF units back for XOF to eCFA wallet. Fee: 0.5%."""
    deduct_credits(current_user, db, "/api/v3/etf/sell", cost_multiplier=2.0)

    etf = db.query(EtfProduct).filter(
        EtfProduct.ticker == body.ticker.upper(), EtfProduct.is_active == True
    ).first()
    if not etf:
        raise HTTPException(status_code=404, detail=f"ETF {body.ticker} not found or inactive")
    if etf.nav_xof <= 0:
        raise HTTPException(status_code=400, detail=f"ETF {etf.ticker} has no price yet.")

    portfolio = _get_portfolio(db, current_user.id)
    holding = (
        db.query(StockHolding)
        .filter(StockHolding.portfolio_id == portfolio.id,
                StockHolding.exchange_code == "ETF",
                StockHolding.index_name == etf.ticker)
        .first()
    )
    if not holding or holding.units < body.units:
        avail = holding.units if holding else 0
        raise HTTPException(status_code=400, detail=f"You own {avail:.6f} units of {etf.ticker}")

    gross = round(body.units * etf.nav_xof, 2)
    fee = round(gross * FEE_RATE, 2)
    net = gross - fee
    cost_basis = round(body.units * holding.avg_buy_price, 2)
    realized_pnl = round(net - cost_basis, 2)

    # Credit wallet
    wallet = _get_wallet(db, current_user.id)
    wallet.balance_ecfa += net
    wallet.available_balance_ecfa += net

    # Update holding
    holding.units = round(holding.units - body.units, 6)
    holding.total_cost = max(0, round(holding.total_cost - cost_basis, 2))

    portfolio.total_withdrawn += net
    portfolio.realized_pnl += realized_pnl

    order = StockOrder(
        portfolio_id=portfolio.id, user_id=current_user.id,
        exchange_code="ETF", index_name=etf.ticker, side="SELL",
        units=body.units, price_per_unit=etf.nav_xof, total_amount=gross,
        wallet_id=wallet.wallet_id, status="EXECUTED",
    )
    db.add(order)
    db.commit()

    return EtfOrderResponse(
        order_id=order.id, side="SELL", ticker=etf.ticker, name=etf.name,
        units=body.units, nav_per_unit=etf.nav_xof,
        gross_amount_xof=gross, fee_xof=fee, net_received=net,
        realized_pnl=realized_pnl, status="EXECUTED",
    )
