"""
Investment models — simulated brokerage for West African stock exchanges.

Users buy/sell units of stock indices (like ETFs tracking NGX, GSE, BRVM).
Prices come from StockMarketData table. Settlements via eCFA wallet.

Exchanges:
  NGX  — Nigerian Exchange Group        (NG)
  GSE  — Ghana Stock Exchange           (GH)
  BRVM — Bourse Régionale des Valeurs   (CI/SN/BJ/TG)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Numeric, Text,
)
from sqlalchemy.orm import relationship

from src.database.models import Base


class InvestmentPortfolio(Base):
    """One portfolio per user — tracks total invested, current value, P&L."""
    __tablename__ = "investment_portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    currency = Column(String(5), default="XOF", nullable=False)

    total_invested = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)
    total_withdrawn = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)
    realized_pnl = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    holdings = relationship("StockHolding", back_populates="portfolio", lazy="selectin")
    orders = relationship("StockOrder", back_populates="portfolio", lazy="selectin")


class StockHolding(Base):
    """Current position in a specific stock index (exchange + index_name)."""
    __tablename__ = "stock_holdings"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("investment_portfolios.id"), nullable=False, index=True)

    exchange_code = Column(String(10), nullable=False, index=True)   # NGX | GSE | BRVM
    index_name = Column(String(50), nullable=False)                  # e.g. "NGX All-Share"

    units = Column(Float, default=0.0, nullable=False)               # fractional units allowed
    avg_buy_price = Column(Float, default=0.0, nullable=False)       # weighted average cost
    total_cost = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    portfolio = relationship("InvestmentPortfolio", back_populates="holdings")


class StockOrder(Base):
    """Buy or sell order for a stock index."""
    __tablename__ = "stock_orders"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("investment_portfolios.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # What
    exchange_code = Column(String(10), nullable=False, index=True)
    index_name = Column(String(50), nullable=False)
    side = Column(String(4), nullable=False)       # BUY | SELL
    order_type = Column(String(10), default="MARKET", nullable=False)  # MARKET only for now

    # Quantity
    units = Column(Float, nullable=False)
    price_per_unit = Column(Float, nullable=False)  # execution price (index value at time of order)
    total_amount = Column(Numeric(18, 2, asdecimal=False), nullable=False)  # units * price

    # Settlement
    currency = Column(String(5), default="XOF", nullable=False)
    wallet_id = Column(String(36), nullable=True)   # eCFA wallet used for settlement
    settlement_status = Column(String(20), default="SETTLED", nullable=False)

    # Status
    status = Column(String(20), default="EXECUTED", nullable=False)  # EXECUTED | CANCELLED | FAILED
    failure_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    portfolio = relationship("InvestmentPortfolio", back_populates="orders")
