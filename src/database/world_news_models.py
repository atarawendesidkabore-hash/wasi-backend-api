"""
World News Intelligence database models.

WorldNewsEvent:       Raw global news events from worldwide RSS feeds.
NewsImpactAssessment: Per-country impact mapping for a global event.
DailyNewsBriefing:    Cached daily intelligence digest.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, UniqueConstraint,
)
from src.database.models import Base


class WorldNewsEvent(Base):
    """
    A worldwide news event detected from global RSS feeds.
    Not country-specific initially -- country impact is assessed separately
    in NewsImpactAssessment and may spawn country-specific NewsEvent rows.
    """
    __tablename__ = "world_news_events"

    id = Column(Integer, primary_key=True, index=True)

    # Classification
    event_type = Column(String(40), nullable=False, index=True)
    # GLOBAL_COMMODITY_SHOCK | GLOBAL_TRADE_POLICY | GLOBAL_SHIPPING_DISRUPTION
    # GLOBAL_CLIMATE_EVENT | GLOBAL_FINANCIAL_CRISIS | GLOBAL_HEALTH_EMERGENCY
    # GLOBAL_SUPPLY_CHAIN

    # Content
    headline = Column(String(500), nullable=False)
    summary = Column(Text, default="")
    source_url = Column(String(500))
    source_name = Column(String(100))
    source_region = Column(String(50))  # EUROPE, ASIA, AMERICAS, MIDDLE_EAST, GLOBAL

    # Relevance to West Africa (computed by engine)
    relevance_score = Column(Float, nullable=False, default=0.0)       # 0.0-1.0
    relevance_layer1_keyword = Column(Float, default=0.0)              # 0.0-1.0
    relevance_layer2_supply_chain = Column(Float, default=0.0)         # 0.0-1.0
    relevance_layer3_transmission = Column(Float, default=0.0)         # 0.0-1.0

    # Keywords matched (JSON list)
    keywords_matched = Column(Text, default="[]")

    # Global magnitude (-25 to +25, same scale as NewsEvent)
    global_magnitude = Column(Float, nullable=False, default=0.0)

    # Lifecycle
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)

    # Whether this event has been cascaded into country-specific NewsEvent rows
    cascaded = Column(Boolean, default=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            "headline", "source_name", "detected_at",
            name="uq_world_news_dedup",
        ),
    )


class NewsImpactAssessment(Base):
    """
    Per-country impact assessment for a WorldNewsEvent.
    One row per (world_news_event_id, country_code) pair.

    Three impact channels, each scored 0.0-1.0:
      direct_impact:   commodity price / trade volume effect
      indirect_impact: freight cost / supply chain effect
      systemic_impact: GDP growth / demand contraction effect
    """
    __tablename__ = "news_impact_assessments"

    id = Column(Integer, primary_key=True, index=True)
    world_news_event_id = Column(Integer, nullable=False, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # Impact channels (0.0-1.0 each)
    direct_impact = Column(Float, default=0.0)
    indirect_impact = Column(Float, default=0.0)
    systemic_impact = Column(Float, default=0.0)

    # Computed country-level magnitude (-25 to +25)
    country_magnitude = Column(Float, nullable=False, default=0.0)

    # Transmission explanation
    transmission_channel = Column(String(100))  # e.g. "oil_import_dependency"
    explanation = Column(Text, default="")

    # Whether this assessment generated a country-specific NewsEvent
    news_event_created = Column(Boolean, default=False)
    news_event_id = Column(Integer, nullable=True)

    assessed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "world_news_event_id", "country_code",
            name="uq_impact_event_country",
        ),
    )


class DailyNewsBriefing(Base):
    """
    Cached daily intelligence briefing summarizing global events
    and their impact on ECOWAS countries.
    Generated once daily; TTL 24 hours.
    """
    __tablename__ = "daily_news_briefings"

    id = Column(Integer, primary_key=True, index=True)
    briefing_date = Column(Date, nullable=False, unique=True, index=True)

    # Summary counts
    total_global_events = Column(Integer, default=0)
    high_relevance_events = Column(Integer, default=0)    # relevance >= 0.60
    countries_affected = Column(Integer, default=0)

    # JSON content
    top_events_json = Column(Text, default="[]")           # top 10 events
    country_exposure_json = Column(Text, default="{}")      # per-country impact
    trend_indicators_json = Column(Text, default="{}")      # improving/worsening
    watchlist_json = Column(Text, default="[]")             # items needing attention

    # Metadata
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    engine_version = Column(String(10), default="1.0")
