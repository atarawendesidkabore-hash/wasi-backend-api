"""
ETF models — 42 WASI exchange-traded fund products.

Each ETF tracks an underlying WASI data source (composite index, country score,
commodity price, equity index, or strategy). NAV is recalculated from live data.
"""
from datetime import datetime, timezone, date

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, Boolean, Text, Numeric,
    ForeignKey, UniqueConstraint,
)
from src.database.models import Base


class EtfProduct(Base):
    """Registry of all WASI ETF products."""
    __tablename__ = "etf_products"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(30), nullable=False, index=True)
    # Categories: BROAD, REGIONAL, SECTOR, COMMODITY, EQUITY, STRATEGY, COUNTRY
    description = Column(Text, nullable=True)

    # Pricing
    nav_xof = Column(Float, default=0.0, nullable=False)          # current NAV in XOF
    nav_usd = Column(Float, default=0.0, nullable=False)          # current NAV in USD
    change_pct = Column(Float, default=0.0)                        # daily change %
    inception_nav = Column(Float, default=10000.0, nullable=False) # base NAV at launch

    # Composition
    underlying_type = Column(String(30), nullable=False)
    # Types: composite, country_group, sub_index, commodity, equity, strategy
    underlying_config = Column(Text, nullable=True)  # JSON config for NAV calculation

    # Metadata
    currency = Column(String(5), default="XOF", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    fee_pct = Column(Float, default=0.50, nullable=False)  # management fee %
    nav_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class EtfNavHistory(Base):
    """Daily NAV snapshots for each ETF product."""
    __tablename__ = "etf_nav_history"
    __table_args__ = (
        UniqueConstraint("etf_id", "nav_date", name="uq_etf_nav_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    etf_id = Column(Integer, ForeignKey("etf_products.id"), nullable=False, index=True)
    nav_date = Column(Date, nullable=False, index=True)
    nav_xof = Column(Float, nullable=False)
    nav_usd = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
