"""
Data Reconciliation & Integrity models — anomaly detection, quarantine, lineage.

DataSourceHealth:    Scraper/source reliability tracking.
DataQuarantine:      Suspicious records pending review.
DataLineage:         Trace any score back to source records.
ReconciliationRun:   Audit trail of reconciliation runs.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey,
)
from datetime import datetime, timezone

from src.database.models import Base


class DataSourceHealth(Base):
    __tablename__ = "data_source_health"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(50), unique=True, index=True, nullable=False)
    last_fetch_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    fetch_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    avg_latency_ms = Column(Float, default=0.0)
    reliability_score = Column(Float, default=1.0)
    status = Column(String(15), default="UNKNOWN", nullable=False)
    last_error_message = Column(Text, nullable=True)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DataQuarantine(Base):
    __tablename__ = "data_quarantine"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(50), index=True, nullable=False)
    record_id = Column(Integer, index=True, nullable=False)
    country_code = Column(String(2), index=True, nullable=True)
    anomaly_type = Column(String(30), index=True, nullable=False)
    anomaly_detail = Column(Text, nullable=False)
    severity = Column(String(10), nullable=False)
    status = Column(String(15), default="PENDING", index=True, nullable=False)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class DataLineage(Base):
    __tablename__ = "data_lineage"

    id = Column(Integer, primary_key=True, index=True)
    target_table = Column(String(50), index=True, nullable=False)
    target_id = Column(Integer, index=True, nullable=False)
    source_table = Column(String(50), nullable=False)
    source_id = Column(Integer, nullable=False)
    contribution_weight = Column(Float, nullable=False)
    snapshot_value = Column(Float, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False,
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_type = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    records_checked = Column(Integer, default=0)
    anomalies_found = Column(Integer, default=0)
    quarantined = Column(Integer, default=0)
    auto_resolved = Column(Integer, default=0)
    summary_json = Column(Text, nullable=True)
