"""
Investment engine — buy/sell West African stock index units.

Users trade fractional units of stock indices (like ETFs):
  - BUY:  deduct XOF from eCFA wallet → create/increase holding
  - SELL: reduce holding → credit XOF to eCFA wallet

Prices are the latest index_value from StockMarketData.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import StockMarketData
from src.database.cbdc_models import CbdcWallet
from src.database.investment_models import InvestmentPortfolio, StockHolding, StockOrder

logger = logging.getLogger(__name__)

# Supported exchanges and their primary indices
TRADEABLE_INDICES = {
    ("NGX", "NGX All-Share"),
    ("GSE", "GSE Composite"),
    ("BRVM", "BRVM Composite"),
    ("BRVM", "BRVM 10"),
}

# Minimum order in XOF
MIN_ORDER_XOF = 1000.0

# Brokerage fee (0.5%)
FEE_RATE = 0.005


class InvestmentEngine:
    """Stateless engine — all state lives in the DB."""

    def get_or_create_portfolio(self, db: Session, user_id: int) -> InvestmentPortfolio:
        portfolio = db.query(InvestmentPortfolio).filter(
            InvestmentPortfolio.user_id == user_id
        ).first()
        if not portfolio:
            portfolio = InvestmentPortfolio(user_id=user_id)
            db.add(portfolio)
            db.flush()
        return portfolio

    def get_market_price(self, db: Session, exchange_code: str, index_name: str) -> StockMarketData:
        """Get the latest market price for an index. Raises 404 if no data."""
        row = (
            db.query(StockMarketData)
            .filter(
                StockMarketData.exchange_code == exchange_code,
                StockMarketData.index_name == index_name,
            )
            .order_by(StockMarketData.trade_date.desc())
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No market data for {exchange_code} / {index_name}",
            )
        return row

    def get_user_wallet(self, db: Session, user_id: int) -> CbdcWallet:
        """Find the user's retail eCFA wallet. Raises 404 if none."""
        wallet = (
            db.query(CbdcWallet)
            .filter(
                CbdcWallet.user_id == user_id,
                CbdcWallet.wallet_type == "RETAIL",
                CbdcWallet.status == "active",
            )
            .first()
        )
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active eCFA wallet found. Create a wallet first via /api/v3/ecfa/wallet/create",
            )
        return wallet

    def list_market_indices(self, db: Session) -> list[dict]:
        """Return latest price for each tradeable index."""
        results = []
        for exchange_code, index_name in sorted(TRADEABLE_INDICES):
            try:
                row = self.get_market_price(db, exchange_code, index_name)
                results.append({
                    "exchange_code": row.exchange_code,
                    "index_name": row.index_name,
                    "country_codes": row.country_codes,
                    "price": row.index_value,
                    "change_pct": row.change_pct,
                    "trade_date": str(row.trade_date),
                    "data_source": row.data_source,
                })
            except HTTPException:
                continue
        return results

    def buy(
        self, db: Session, user_id: int,
        exchange_code: str, index_name: str,
        amount_xof: float,
    ) -> dict:
        """
        Buy index units with XOF.

        amount_xof: how much to invest (before fees).
        Returns order summary.
        """
        # Validate index
        if (exchange_code, index_name) not in TRADEABLE_INDICES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Index {exchange_code}/{index_name} is not tradeable. "
                       f"Available: {[f'{e}/{n}' for e, n in sorted(TRADEABLE_INDICES)]}",
            )

        if amount_xof < MIN_ORDER_XOF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum order is {MIN_ORDER_XOF:,.0f} XOF",
            )

        # Get market price
        market = self.get_market_price(db, exchange_code, index_name)
        price = market.index_value

        # Calculate fee and net
        fee = round(amount_xof * FEE_RATE, 2)
        net_amount = amount_xof - fee
        units = round(net_amount / price, 6)

        # Check wallet balance
        wallet = self.get_user_wallet(db, user_id)
        if wallet.available_balance_ecfa < amount_xof:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient balance: {wallet.available_balance_ecfa:,.2f} XOF "
                       f"available, need {amount_xof:,.2f} XOF",
            )

        # Deduct from wallet
        wallet.balance_ecfa -= amount_xof
        wallet.available_balance_ecfa -= amount_xof

        # Get or create portfolio + holding
        portfolio = self.get_or_create_portfolio(db, user_id)

        holding = (
            db.query(StockHolding)
            .filter(
                StockHolding.portfolio_id == portfolio.id,
                StockHolding.exchange_code == exchange_code,
                StockHolding.index_name == index_name,
            )
            .first()
        )

        if holding:
            # Update weighted average cost
            old_cost = holding.total_cost
            new_cost = old_cost + net_amount
            old_units = holding.units
            new_units = old_units + units
            holding.units = new_units
            holding.total_cost = new_cost
            holding.avg_buy_price = round(new_cost / new_units, 4) if new_units > 0 else 0
        else:
            holding = StockHolding(
                portfolio_id=portfolio.id,
                exchange_code=exchange_code,
                index_name=index_name,
                units=units,
                avg_buy_price=price,
                total_cost=net_amount,
            )
            db.add(holding)

        portfolio.total_invested += net_amount

        # Record order
        order = StockOrder(
            portfolio_id=portfolio.id,
            user_id=user_id,
            exchange_code=exchange_code,
            index_name=index_name,
            side="BUY",
            units=units,
            price_per_unit=price,
            total_amount=amount_xof,
            wallet_id=wallet.wallet_id,
            status="EXECUTED",
        )
        db.add(order)
        db.commit()

        logger.info(
            "BUY: user=%d %s/%s %.6f units @ %.2f = %.2f XOF (fee=%.2f)",
            user_id, exchange_code, index_name, units, price, amount_xof, fee,
        )

        return {
            "order_id": order.id,
            "side": "BUY",
            "exchange_code": exchange_code,
            "index_name": index_name,
            "units": units,
            "price_per_unit": price,
            "amount_xof": amount_xof,
            "fee_xof": fee,
            "net_invested": net_amount,
            "trade_date": str(market.trade_date),
            "status": "EXECUTED",
        }

    def sell(
        self, db: Session, user_id: int,
        exchange_code: str, index_name: str,
        units: float,
    ) -> dict:
        """
        Sell index units back for XOF.

        units: number of units to sell.
        Returns order summary.
        """
        if (exchange_code, index_name) not in TRADEABLE_INDICES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Index {exchange_code}/{index_name} is not tradeable.",
            )

        if units <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Units must be positive",
            )

        portfolio = self.get_or_create_portfolio(db, user_id)

        holding = (
            db.query(StockHolding)
            .filter(
                StockHolding.portfolio_id == portfolio.id,
                StockHolding.exchange_code == exchange_code,
                StockHolding.index_name == index_name,
            )
            .first()
        )

        if not holding or holding.units < units:
            available = holding.units if holding else 0.0
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient holdings: you own {available:.6f} units, "
                       f"trying to sell {units:.6f}",
            )

        # Get market price
        market = self.get_market_price(db, exchange_code, index_name)
        price = market.index_value

        gross_amount = round(units * price, 2)
        fee = round(gross_amount * FEE_RATE, 2)
        net_amount = gross_amount - fee

        # Calculate realized P&L for these units
        cost_basis = round(units * holding.avg_buy_price, 2)
        realized_pnl = round(net_amount - cost_basis, 2)

        # Credit wallet
        wallet = self.get_user_wallet(db, user_id)
        wallet.balance_ecfa += net_amount
        wallet.available_balance_ecfa += net_amount

        # Update holding
        holding.units = round(holding.units - units, 6)
        holding.total_cost = round(holding.total_cost - cost_basis, 2)
        if holding.total_cost < 0:
            holding.total_cost = 0

        portfolio.total_withdrawn += net_amount
        portfolio.realized_pnl += realized_pnl

        # Record order
        order = StockOrder(
            portfolio_id=portfolio.id,
            user_id=user_id,
            exchange_code=exchange_code,
            index_name=index_name,
            side="SELL",
            units=units,
            price_per_unit=price,
            total_amount=gross_amount,
            wallet_id=wallet.wallet_id,
            status="EXECUTED",
        )
        db.add(order)
        db.commit()

        logger.info(
            "SELL: user=%d %s/%s %.6f units @ %.2f = %.2f XOF (fee=%.2f pnl=%.2f)",
            user_id, exchange_code, index_name, units, price, gross_amount, fee, realized_pnl,
        )

        return {
            "order_id": order.id,
            "side": "SELL",
            "exchange_code": exchange_code,
            "index_name": index_name,
            "units": units,
            "price_per_unit": price,
            "gross_amount_xof": gross_amount,
            "fee_xof": fee,
            "net_received": net_amount,
            "realized_pnl": realized_pnl,
            "trade_date": str(market.trade_date),
            "status": "EXECUTED",
        }

    def get_portfolio(self, db: Session, user_id: int) -> dict:
        """Full portfolio view with current valuations and P&L."""
        portfolio = self.get_or_create_portfolio(db, user_id)

        holdings_out = []
        total_current_value = 0.0
        total_cost_basis = 0.0

        for h in portfolio.holdings:
            if h.units <= 0.0001:
                continue

            try:
                market = self.get_market_price(db, h.exchange_code, h.index_name)
                current_price = market.index_value
                trade_date = str(market.trade_date)
            except HTTPException:
                current_price = h.avg_buy_price
                trade_date = "N/A"

            current_value = round(h.units * current_price, 2)
            cost_basis = float(h.total_cost)
            unrealized_pnl = round(current_value - cost_basis, 2)
            pnl_pct = round((unrealized_pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

            total_current_value += current_value
            total_cost_basis += cost_basis

            holdings_out.append({
                "exchange_code": h.exchange_code,
                "index_name": h.index_name,
                "units": round(h.units, 6),
                "avg_buy_price": h.avg_buy_price,
                "current_price": current_price,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "trade_date": trade_date,
            })

        total_unrealized = round(total_current_value - total_cost_basis, 2)

        return {
            "user_id": user_id,
            "currency": portfolio.currency,
            "total_invested": float(portfolio.total_invested),
            "total_withdrawn": float(portfolio.total_withdrawn),
            "realized_pnl": float(portfolio.realized_pnl),
            "total_cost_basis": total_cost_basis,
            "total_current_value": round(total_current_value, 2),
            "total_unrealized_pnl": total_unrealized,
            "holdings": holdings_out,
            "holdings_count": len(holdings_out),
        }

    def get_order_history(self, db: Session, user_id: int, limit: int = 50) -> list[dict]:
        """Return recent orders for a user."""
        orders = (
            db.query(StockOrder)
            .filter(StockOrder.user_id == user_id)
            .order_by(StockOrder.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "order_id": o.id,
                "side": o.side,
                "exchange_code": o.exchange_code,
                "index_name": o.index_name,
                "units": o.units,
                "price_per_unit": o.price_per_unit,
                "total_amount": float(o.total_amount),
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]
