"""
Legislative Activity Models — laws, bills, and parliamentary sessions
tracked across 16 ECOWAS countries.

Sources: Laws.Africa Content API, IPU Parline API, RSS keyword detection.
Legislative acts with |estimated_magnitude| > 5 create NewsEvent records
that feed into the existing LiveSignal adjustment pipeline.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from datetime import timezone, datetime
from src.database.models import Base


class LegislativeAct(Base):
    """
    Individual law, bill, or regulatory act tracked for WASI impact.

    Categories: TRADE, TARIFF, INVESTMENT, FISCAL, REGULATORY, CUSTOMS,
                LABOR, INFRASTRUCTURE, ENVIRONMENT, OTHER
    Status:     INTRODUCED -> COMMITTEE -> PASSED -> ENACTED -> REPEALED
    Impact:     auto-scored by keyword engine, capped at +/-25 like NewsEvent.
    """
    __tablename__ = "legislative_acts"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    act_number = Column(String(100), nullable=True)
    act_date = Column(Date, nullable=False, index=True)

    category = Column(String(20), nullable=False, default="OTHER")
    status = Column(String(20), nullable=False, default="ENACTED")
    impact_type = Column(String(10), nullable=False, default="NEUTRAL")
    estimated_magnitude = Column(Float, nullable=False, default=0.0)

    source_url = Column(String(500), nullable=True)
    source_name = Column(String(100), nullable=True)
    external_id = Column(String(200), nullable=True, index=True)

    confidence = Column(Float, nullable=True, default=0.70)
    data_quality = Column(String(10), nullable=True, default="medium")
    data_source = Column(String(100), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("country_id", "external_id", name="uq_legislative_act_country_ext"),
    )


class ParliamentarySession(Base):
    """
    Daily/session-level summary of parliamentary activity per country.
    Tracks volume of bills introduced, passed, rejected.
    """
    __tablename__ = "parliamentary_sessions"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    session_date = Column(Date, nullable=False, index=True)

    bills_introduced = Column(Integer, nullable=False, default=0)
    bills_passed = Column(Integer, nullable=False, default=0)
    bills_rejected = Column(Integer, nullable=False, default=0)

    key_topics = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    source_url = Column(String(500), nullable=True)
    data_source = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True, default=0.70)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("country_id", "session_date", name="uq_parliamentary_session"),
    )
