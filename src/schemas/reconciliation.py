"""Pydantic schemas for Data Reconciliation & Integrity API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class QuarantineResolveRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


class SourceHealthOut(BaseModel):
    source: str
    status: str
    reliability: float
    fetch_count: int
    error_count: int
    avg_latency_ms: float
    last_success: Optional[str] = None


class QuarantineSummary(BaseModel):
    pending: int
    by_severity: dict
    by_type: dict


class LastRunOut(BaseModel):
    run_id: Optional[int] = None
    completed_at: Optional[str] = None
    anomalies_found: int = 0


class IntegrityDashboardResponse(BaseModel):
    as_of: str
    integrity_score: float
    sources: list[SourceHealthOut]
    quarantine: QuarantineSummary
    last_reconciliation: LastRunOut


class QuarantineItemOut(BaseModel):
    id: int
    table_name: str
    record_id: int
    country_code: Optional[str] = None
    anomaly_type: str
    anomaly_detail: str
    severity: str
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None
    created_at: str


class LineageItemOut(BaseModel):
    source_table: str
    source_id: int
    contribution_weight: float
    snapshot_value: Optional[float] = None
    created_at: Optional[str] = None


class ReconciliationRunResponse(BaseModel):
    run_id: int
    run_type: str
    records_checked: int
    anomalies_found: int
    quarantined: int
    by_type: dict
    duration_ms: float
