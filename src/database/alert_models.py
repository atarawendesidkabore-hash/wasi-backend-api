"""
Alert/Webhook database models.

AlertRule — user-defined rules that trigger webhook deliveries.
AlertDelivery — individual webhook delivery attempts with retry tracking.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from src.database.models import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # What to monitor
    event_source = Column(String(30), nullable=False, index=True)
    # WASI_INDEX | COMMODITY_PRICE | NEWS_EVENT | DIVERGENCE |
    # FORECAST_DEVIATION | CONFIDENCE_DROP

    # Filter criteria
    country_code = Column(String(2), nullable=True, index=True)
    commodity_code = Column(String(20), nullable=True)
    event_type_filter = Column(String(30), nullable=True)

    # Threshold
    condition = Column(String(20), nullable=False)
    # DROP_GT | RISE_GT | CHANGE_GT | BELOW | ABOVE | ANY
    threshold_value = Column(Float, nullable=True)

    # Webhook delivery
    webhook_url = Column(String(500), nullable=False)
    webhook_secret = Column(String(128), nullable=False)

    # Billing
    credit_cost_per_delivery = Column(Float, default=1.0)

    # State
    is_active = Column(Boolean, default=True, index=True)
    last_evaluated_at = Column(DateTime, nullable=True)
    last_triggered_at = Column(DateTime, nullable=True)

    # Cooldown: minimum seconds between firings of the same rule
    cooldown_seconds = Column(Integer, default=3600)

    # Metadata
    name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User")
    deliveries = relationship("AlertDelivery", back_populates="rule")


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Payload snapshot
    event_source = Column(String(30), nullable=False)
    payload_json = Column(Text, nullable=False)

    # Delivery state
    status = Column(String(30), default="pending", index=True)
    # pending | delivered | failed | skipped_insufficient_credits
    http_status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True)

    # Credit accounting
    credits_charged = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    delivered_at = Column(DateTime, nullable=True)

    rule = relationship("AlertRule", back_populates="deliveries")
    user = relationship("User")
