"""
Data Marketplace Royalty Models — Revenue flows backwards.

3 models:
  RoyaltyPool          — daily per-country royalty accumulator
  RoyaltyDistribution  — individual payout to a contributor
  DataAttribution      — per-query data lineage record
"""

from datetime import timezone, datetime
from sqlalchemy import (
    Column, Integer, Numeric, String, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint,
)
from src.database.models import Base


class RoyaltyPool(Base):
    """One pool per country per day. Accumulates royalties from API queries."""
    __tablename__ = "royalty_pools"

    id = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Accumulation
    total_queries = Column(Integer, default=0, nullable=False)
    total_credits_spent = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)
    royalty_rate_pct = Column(Numeric(5, 2, asdecimal=False), default=15, nullable=False)
    pool_amount_cfa = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)

    # Distribution
    contributor_count = Column(Integer, default=0, nullable=False)
    distributed = Column(Boolean, default=False, nullable=False)
    distributed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("country_code", "period_date", name="uq_royalty_pool_country_date"),
    )


class RoyaltyDistribution(Base):
    """Individual royalty payout to a contributor from a pool."""
    __tablename__ = "royalty_distributions"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("royalty_pools.id"), nullable=False, index=True)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)
    country_code = Column(String(2), nullable=False)

    # Share calculation
    report_count = Column(Integer, default=0, nullable=False)
    avg_confidence = Column(Numeric(4, 2, asdecimal=False), default=0, nullable=False)
    tier_multiplier = Column(Numeric(3, 2, asdecimal=False), default=1.0, nullable=False)
    quality_weight = Column(Numeric(12, 4, asdecimal=False), default=0, nullable=False)
    share_pct = Column(Numeric(8, 4, asdecimal=False), default=0, nullable=False)
    share_amount_cfa = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)

    # Status: pending → credited → failed
    status = Column(String(12), default="pending", nullable=False)
    credited_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("pool_id", "contributor_phone_hash",
                         name="uq_royalty_dist_pool_contributor"),
    )


class DataAttribution(Base):
    """Per-query attribution — traces which country's data was consumed."""
    __tablename__ = "data_attributions"

    id = Column(Integer, primary_key=True, index=True)
    query_log_id = Column(Integer, nullable=True, index=True)
    endpoint = Column(String(255), nullable=False)
    consumer_user_id = Column(Integer, nullable=False, index=True)
    credits_spent = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)
    royalty_contribution = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)

    # Attribution scope
    country_code = Column(String(2), nullable=False, index=True)
    period_date_start = Column(Date, nullable=False)
    period_date_end = Column(Date, nullable=False)

    # Data metrics at query time
    contributor_count = Column(Integer, default=0, nullable=False)
    token_count = Column(Integer, default=0, nullable=False)
    avg_confidence = Column(Numeric(4, 2, asdecimal=False), default=0, nullable=False)

    # Timestamp
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
