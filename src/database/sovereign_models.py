"""
Sovereign Credit Veto + Data Truth Audit models.

SovereignVeto: BCEAO/sovereign authority can block credit for a country.
    Veto types: SANCTIONS, DEBT_CEILING, MONETARY_POLICY, POLITICAL_CRISIS, AML_CFT.
    Severity: FULL_BLOCK (reject all credit) or PARTIAL (cap loan size, advisory only).

DataTruthAudit: Cross-source verification log for data integrity.
    Records when data from multiple sources agrees/diverges.
    Tracks staleness, outlier z-scores, and adjusted confidence.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime

from src.database.models import Base


# Valid enumerations
VETO_TYPES = {"SANCTIONS", "DEBT_CEILING", "MONETARY_POLICY", "POLITICAL_CRISIS", "AML_CFT"}
SEVERITY_LEVELS = {"FULL_BLOCK", "PARTIAL"}
TRUTH_VERDICTS = {"AGREE", "DIVERGE", "STALE", "ANOMALY", "VETOED"}


class SovereignVeto(Base):
    """
    BCEAO sovereign veto on credit operations for a country.
    When active with severity=FULL_BLOCK, ALL bank credit endpoints must reject scoring.
    When severity=PARTIAL, loan amounts are capped at max_loan_cap_usd.

    human_review_required is always True -- sovereign decisions demand validation chain.
    """
    __tablename__ = "sovereign_vetoes"

    id = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # Veto classification
    veto_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="FULL_BLOCK", nullable=False)

    # Authority
    issued_by = Column(String(100), nullable=False)
    issued_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reference_number = Column(String(100), nullable=True)
    legal_basis = Column(String(200), nullable=True)

    # Veto scope
    reason = Column(Text, nullable=False)
    max_loan_cap_usd = Column(Float, nullable=True)

    # Lifecycle
    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Revocation
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(String(100), nullable=True)
    revoked_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    revocation_reason = Column(Text, nullable=True)

    # Always true
    human_review_required = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    issued_by_user = relationship("User", foreign_keys=[issued_by_user_id])
    revoked_by_user = relationship("User", foreign_keys=[revoked_by_user_id])

    __table_args__ = (
        UniqueConstraint("country_code", "veto_type", "effective_date",
                         name="uq_veto_country_type_date"),
    )


class DataTruthAudit(Base):
    """
    Cross-source data verification audit log.

    Verdicts:
      AGREE    -- sources within 5% divergence
      DIVERGE  -- sources differ > 15%
      STALE    -- primary source older than staleness window
      ANOMALY  -- z-score > 2.5 from historical mean
      VETOED   -- data point is under sovereign veto
    """
    __tablename__ = "data_truth_audits"

    id = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # What is being verified
    metric_name = Column(String(100), nullable=False, index=True)
    record_table = Column(String(50), nullable=True)
    record_id = Column(Integer, nullable=True)
    field_name = Column(String(50), nullable=True)

    # Source comparison
    source_a = Column(String(100), nullable=False)
    source_b = Column(String(100), nullable=False)
    value_a = Column(Float, nullable=False)
    value_b = Column(Float, nullable=False)
    divergence_pct = Column(Float, nullable=False)

    # Statistical analysis
    z_score = Column(Float, nullable=True)
    historical_mean = Column(Float, nullable=True)
    historical_std = Column(Float, nullable=True)

    # Freshness
    source_a_date = Column(DateTime, nullable=True)
    source_b_date = Column(DateTime, nullable=True)
    staleness_hours = Column(Float, nullable=True)
    is_stale = Column(Boolean, default=False)

    # Verdict
    verdict = Column(String(20), nullable=False)
    confidence_before = Column(Float, nullable=True)
    confidence_after = Column(Float, nullable=True)
    truth_score = Column(Float, default=1.0)

    # Veto linkage
    veto_id = Column(Integer, ForeignKey("sovereign_vetoes.id"), nullable=True, index=True)

    details = Column(Text, nullable=True)
    audited_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    veto = relationship("SovereignVeto")

    __table_args__ = (
        UniqueConstraint("country_code", "metric_name", "audited_at",
                         name="uq_truth_audit"),
    )
