"""
WASI-Pay Cross-Border Payment Models.

Three models for the payment interoperability layer:
  1. CbdcCrossBorderPayment — Full lifecycle of a cross-border payment
  2. CbdcRateLock — Short-lived FX rate guarantee (30-120 seconds)
  3. CbdcFxPosition — Net exposure tracking per currency
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Boolean, Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime
from src.database.models import Base


# ---------------------------------------------------------------------------
# 1. CbdcCrossBorderPayment — Cross-border payment lifecycle
# ---------------------------------------------------------------------------
# Status state machine:
#   INITIATED → COMPLIANCE_CHECK → FX_LOCKED → SOURCE_DEBITED
#   → FX_CONVERTED → DEST_CREDITED → SETTLED
#   Any state can → FAILED
#   SETTLED can → REVERSED

class CbdcCrossBorderPayment(Base):
    __tablename__ = "cbdc_cross_border_payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String(36), unique=True, nullable=False, index=True)

    # Sender
    sender_wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id"),
                              nullable=False, index=True)
    sender_country = Column(String(2), nullable=False, index=True)

    # Receiver
    receiver_wallet_id = Column(String(36), nullable=True, index=True)
    receiver_phone_hash = Column(String(64), nullable=True)
    receiver_institution_code = Column(String(20), nullable=True)
    receiver_country = Column(String(2), nullable=False, index=True)

    # Amounts
    amount_source = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    source_currency = Column(String(5), nullable=False)
    amount_target = Column(Numeric(18, 2, asdecimal=False), nullable=True)
    target_currency = Column(String(5), nullable=False)

    # FX details
    fx_rate_applied = Column(Numeric(12, 6, asdecimal=False), nullable=True)
    fx_spread_applied = Column(Float, nullable=True)

    # Fees
    platform_fee_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    rail_fee_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_cost_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Status
    status = Column(String(20), nullable=False, default="INITIATED", index=True)
    # INITIATED | COMPLIANCE_CHECK | FX_LOCKED | SOURCE_DEBITED
    # | FX_CONVERTED | DEST_CREDITED | SETTLED | FAILED | REVERSED

    # Routing
    rail_type = Column(String(30), nullable=False)
    # ECFA_INTERNAL | ECFA_TO_EXTERNAL | EXTERNAL_TO_ECFA | EXTERNAL_BRIDGE

    # Linked transactions
    source_tx_id = Column(String(36), nullable=True)
    dest_tx_id = Column(String(36), nullable=True)

    # Rate lock
    rate_lock_id = Column(String(36), nullable=True)
    rate_lock_expires_at = Column(DateTime, nullable=True)

    # Compliance
    compliance_status = Column(String(20), default="pending")
    compliance_alert_id = Column(String(36), nullable=True)

    # Purpose
    purpose = Column(String(100), nullable=True)

    # External references
    iso_message_ref = Column(String(50), nullable=True)
    star_uemoa_ref = Column(String(50), nullable=True)
    external_bridge_ref = Column(String(100), nullable=True)

    # Failure
    failure_reason = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    settled_at = Column(DateTime, nullable=True)

    sender_wallet = relationship("CbdcWallet", foreign_keys=[sender_wallet_id])


# ---------------------------------------------------------------------------
# 2. CbdcRateLock — Short-lived FX rate guarantee
# ---------------------------------------------------------------------------
class CbdcRateLock(Base):
    __tablename__ = "cbdc_rate_locks"

    id = Column(Integer, primary_key=True, index=True)
    lock_id = Column(String(36), unique=True, nullable=False, index=True)

    base_currency = Column(String(5), nullable=False, default="XOF")
    target_currency = Column(String(5), nullable=False, index=True)
    rate = Column(Numeric(12, 6, asdecimal=False), nullable=False)
    inverse_rate = Column(Numeric(12, 6, asdecimal=False), nullable=False)
    spread_percent = Column(Float, nullable=False)

    locked_amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    payment_id = Column(String(36), nullable=True, index=True)

    expires_at = Column(DateTime, nullable=False, index=True)
    consumed = Column(Boolean, default=False)
    consumed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 3. CbdcFxPosition — Net exposure tracking per currency
# ---------------------------------------------------------------------------
class CbdcFxPosition(Base):
    __tablename__ = "cbdc_fx_positions"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(String(5), unique=True, nullable=False, index=True)

    net_position_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    position_limit_ecfa = Column(Numeric(18, 2, asdecimal=False), default=50_000_000.0)

    total_bought_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_sold_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
