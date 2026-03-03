"""
Trade Corridor database models — corridor registry + periodic assessments.

TradeCorridor:  Static corridor definitions (10 ECOWAS routes).
CorridorAssessment: Periodic composite score snapshots (6 sub-dimensions).
"""
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime

from src.database.models import Base


class TradeCorridor(Base):
    """Static corridor definition — seeded once on bootstrap."""
    __tablename__ = "trade_corridors"

    id = Column(Integer, primary_key=True, index=True)
    corridor_code = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    from_country_code = Column(String(2), nullable=False, index=True)
    to_country_code = Column(String(2), nullable=False, index=True)
    corridor_type = Column(String(20), nullable=False)  # COASTAL|TRANSIT|MINING|SHORT
    distance_km = Column(Float, nullable=True)
    transit_countries = Column(String(50), nullable=True)  # e.g. "BJ,TG"
    key_border_posts = Column(String(200), nullable=True)
    key_ports = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessments = relationship("CorridorAssessment", back_populates="corridor")


class CorridorAssessment(Base):
    """Periodic corridor assessment — one row per corridor per date."""
    __tablename__ = "corridor_assessments"

    id = Column(Integer, primary_key=True, index=True)
    corridor_id = Column(Integer, ForeignKey("trade_corridors.id"), nullable=False, index=True)
    assessment_date = Column(Date, nullable=False, index=True)

    # Sub-scores (0-100, higher = better)
    transport_score = Column(Float, nullable=True)
    fx_score = Column(Float, nullable=True)
    trade_volume_score = Column(Float, nullable=True)
    logistics_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    payment_score = Column(Float, nullable=True)

    # Composite
    corridor_composite = Column(Float, nullable=True)
    trend = Column(String(15), nullable=True)       # IMPROVING|STABLE|DETERIORATING
    bottleneck = Column(String(20), nullable=True)   # weakest sub-score dimension
    confidence = Column(Float, default=0.5)

    # Metadata
    data_sources_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    corridor = relationship("TradeCorridor", back_populates="assessments")

    __table_args__ = (
        UniqueConstraint("corridor_id", "assessment_date", name="uq_corridor_assessment_date"),
    )
