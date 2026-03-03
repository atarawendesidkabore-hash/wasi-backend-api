"""
FX Analytics Models — Daily rates and volatility metrics for ECOWAS currencies.

Two tables:
  - fx_daily_rates:  One row per currency per day (USD, EUR, XOF cross rates)
  - fx_volatility:   Weekly volatility summaries per currency
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Date,
    UniqueConstraint,
)
from datetime import timezone, datetime
from src.database.models import Base


class FxDailyRate(Base):
    """Daily FX rate snapshot — one row per currency per day."""
    __tablename__ = "fx_daily_rates"

    id = Column(Integer, primary_key=True, index=True)
    currency_code = Column(String(5), nullable=False, index=True)
    rate_date = Column(Date, nullable=False, index=True)

    # Cross rates (all derived from USD base)
    rate_to_usd = Column(Numeric(12, 6, asdecimal=False), nullable=False)
    rate_to_eur = Column(Numeric(12, 6, asdecimal=False))
    rate_to_xof = Column(Numeric(12, 6, asdecimal=False))

    # Percentage changes vs USD
    pct_change_1d = Column(Float)
    pct_change_7d = Column(Float)
    pct_change_30d = Column(Float)

    data_source = Column(String(50), default="fawazahmed0")
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("currency_code", "rate_date",
                         name="uq_fx_daily_currency_date"),
    )


class FxVolatility(Base):
    """Weekly volatility metrics per currency — recomputed by scheduler."""
    __tablename__ = "fx_volatility"

    id = Column(Integer, primary_key=True, index=True)
    currency_code = Column(String(5), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False, index=True)

    volatility_7d = Column(Float)
    volatility_30d = Column(Float)
    volatility_90d = Column(Float)
    annualized_vol = Column(Float)

    max_drawdown_pct = Column(Float)
    trend = Column(String(15), default="STABLE")    # APPRECIATING | DEPRECIATING | STABLE
    regime = Column(String(10), default="FLOATING")  # PEGGED | FLOATING | MANAGED

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("currency_code", "period_end",
                         name="uq_fx_vol_currency_period"),
    )
