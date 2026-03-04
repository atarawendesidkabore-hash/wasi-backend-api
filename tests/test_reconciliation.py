"""
Tests for the Data Reconciliation & Anomaly Detection Engine.

14 engine unit tests + 6 API integration tests = 20 total.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import TestingSessionLocal
from src.main import app
from src.database.models import Country, CountryIndex, MacroIndicator
from src.database.reconciliation_models import (
    DataSourceHealth, DataQuarantine, DataLineage, ReconciliationRun,
)
from src.engines.reconciliation_engine import ReconciliationEngine

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────

def _get_db() -> Session:
    return TestingSessionLocal()


def _get_country(db: Session, code: str = "NG") -> Country:
    return db.query(Country).filter(Country.code == code).first()


def _seed_country_indices(db: Session, country_id: int, values: list[float]):
    """Seed CountryIndex records with given index_values."""
    base_date = date(2025, 1, 1)
    for i, val in enumerate(values):
        db.add(CountryIndex(
            country_id=country_id,
            period_date=base_date + timedelta(days=30 * i),
            index_value=val,
            shipping_score=50.0,
            trade_score=50.0,
            infrastructure_score=50.0,
            economic_score=50.0,
            gdp_growth_pct=3.5 if i < len(values) - 1 else 3.5,
            confidence=0.8,
            data_source="test",
        ))
    db.commit()


def _seed_source_health(db: Session, source_name: str, **kwargs):
    now = datetime.now(timezone.utc)
    sh = DataSourceHealth(
        source_name=source_name,
        last_fetch_at=kwargs.get("last_fetch_at", now),
        last_success_at=kwargs.get("last_success_at", now),
        fetch_count=kwargs.get("fetch_count", 10),
        success_count=kwargs.get("success_count", 10),
        error_count=kwargs.get("error_count", 0),
        avg_latency_ms=kwargs.get("avg_latency_ms", 500.0),
        reliability_score=kwargs.get("reliability_score", 1.0),
        status=kwargs.get("status", "HEALTHY"),
        updated_at=now,
    )
    db.add(sh)
    db.commit()
    return sh


def _register_and_login():
    import time
    ts = str(int(time.time() * 1000))[-8:]
    reg = client.post("/api/auth/register", json={
        "username": f"rec_{ts}",
        "email": f"rec_{ts}@test.com",
        "password": "RecTest1234",
    })
    assert reg.status_code in (200, 201)
    login = client.post("/api/auth/login", data={
        "username": f"rec_{ts}",
        "password": "RecTest1234",
    })
    assert login.status_code == 200
    return login.json()["access_token"]


# ══════════════════════════════════════════════════════════════════
# ENGINE UNIT TESTS
# ══════════════════════════════════════════════════════════════════


class TestReconciliationEngine:

    def test_z_score_flags_outlier(self):
        """An extreme outlier should be quarantined."""
        db = _get_db()
        try:
            country = _get_country(db)
            # 30 normal values around 50 + 1 extreme value at 200
            normal_values = [50.0 + (i % 5) for i in range(30)]
            normal_values.append(200.0)
            _seed_country_indices(db, country.id, normal_values)

            engine = ReconciliationEngine(db)
            flagged = engine.check_z_score_anomalies(
                CountryIndex, "index_value", z_threshold=3.0,
            )
            db.commit()

            assert len(flagged) >= 1
            assert flagged[0]["value"] == 200.0
            assert flagged[0]["z_score"] > 3.0

            # Verify quarantine record created
            q = db.query(DataQuarantine).filter(
                DataQuarantine.anomaly_type == "Z_SCORE"
            ).first()
            assert q is not None
            assert q.severity in ("HIGH", "CRITICAL")
        finally:
            db.close()

    def test_z_score_no_anomaly(self):
        """All values within normal range — nothing quarantined."""
        db = _get_db()
        try:
            country = _get_country(db)
            values = [50.0 + (i % 3) for i in range(20)]
            _seed_country_indices(db, country.id, values)

            engine = ReconciliationEngine(db)
            flagged = engine.check_z_score_anomalies(
                CountryIndex, "index_value", z_threshold=3.0,
            )
            db.commit()

            assert len(flagged) == 0
        finally:
            db.close()

    def test_rate_of_change_spike(self):
        """80% jump should be flagged."""
        db = _get_db()
        try:
            country = _get_country(db)
            _seed_country_indices(db, country.id, [50.0, 90.0])

            engine = ReconciliationEngine(db)
            flagged = engine.check_rate_of_change(
                CountryIndex, "index_value", max_pct_change=50.0,
            )
            db.commit()

            assert len(flagged) >= 1
            assert flagged[0]["pct_change"] == 80.0
        finally:
            db.close()

    def test_rate_of_change_normal(self):
        """10% change — no flag."""
        db = _get_db()
        try:
            country = _get_country(db)
            _seed_country_indices(db, country.id, [50.0, 55.0])

            engine = ReconciliationEngine(db)
            flagged = engine.check_rate_of_change(
                CountryIndex, "index_value", max_pct_change=50.0,
            )
            db.commit()

            assert len(flagged) == 0
        finally:
            db.close()

    def test_cross_validate_gdp_mismatch(self):
        """WB=5.0%, IMF=2.0% should trigger CROSS_SOURCE quarantine."""
        db = _get_db()
        try:
            country = _get_country(db)
            # WB source via CountryIndex
            db.add(CountryIndex(
                country_id=country.id,
                period_date=date(2025, 6, 1),
                index_value=60.0,
                gdp_growth_pct=5.0,
                confidence=0.8,
                data_source="World Bank",
            ))
            # IMF source
            db.add(MacroIndicator(
                country_id=country.id,
                year=2025,
                gdp_growth_pct=2.0,
                is_projection=False,
                data_source="imf_weo",
                confidence=0.85,
            ))
            db.commit()

            engine = ReconciliationEngine(db)
            flagged = engine.cross_validate_gdp(tolerance_pct=20.0)
            db.commit()

            assert len(flagged) >= 1
            assert flagged[0]["country_code"] == "NG"
            assert flagged[0]["divergence_pct"] > 20.0
        finally:
            db.close()

    def test_cross_validate_gdp_match(self):
        """WB=5.0%, IMF=4.5% within 20% tolerance — no flag."""
        db = _get_db()
        try:
            country = _get_country(db)
            db.add(CountryIndex(
                country_id=country.id,
                period_date=date(2025, 6, 1),
                index_value=60.0,
                gdp_growth_pct=5.0,
                confidence=0.8,
                data_source="World Bank",
            ))
            db.add(MacroIndicator(
                country_id=country.id,
                year=2025,
                gdp_growth_pct=4.5,
                is_projection=False,
                data_source="imf_weo",
                confidence=0.85,
            ))
            db.commit()

            engine = ReconciliationEngine(db)
            flagged = engine.cross_validate_gdp(tolerance_pct=20.0)
            db.commit()

            assert len(flagged) == 0
        finally:
            db.close()

    def test_data_freshness_stale(self):
        """Source with last_success_at 45 days ago → DEGRADED."""
        db = _get_db()
        try:
            stale_time = datetime.now(timezone.utc) - timedelta(days=45)
            _seed_source_health(db, "test_stale", last_success_at=stale_time)

            engine = ReconciliationEngine(db)
            flagged = engine.check_data_freshness(max_stale_days=30)
            db.commit()

            assert len(flagged) >= 1
            assert flagged[0]["source"] == "test_stale"
            assert flagged[0]["status"] == "DEGRADED"
        finally:
            db.close()

    def test_data_freshness_fresh(self):
        """Source with last_success_at 1 hour ago → HEALTHY, no flag."""
        db = _get_db()
        try:
            fresh_time = datetime.now(timezone.utc) - timedelta(hours=1)
            _seed_source_health(db, "test_fresh", last_success_at=fresh_time)

            engine = ReconciliationEngine(db)
            flagged = engine.check_data_freshness(max_stale_days=30)
            db.commit()

            assert len(flagged) == 0
        finally:
            db.close()

    def test_missing_critical_fields(self):
        """CountryIndex with NULL shipping_score/trade_score should be quarantined."""
        db = _get_db()
        try:
            country = _get_country(db)
            db.add(CountryIndex(
                country_id=country.id,
                period_date=date(2025, 6, 1),
                index_value=60.0,
                shipping_score=None,
                trade_score=None,
                confidence=0.5,
            ))
            db.commit()

            engine = ReconciliationEngine(db)
            flagged = engine.check_missing_critical_fields()
            db.commit()

            assert len(flagged) >= 1
            assert "shipping_score" in flagged[0]["missing_fields"]
        finally:
            db.close()

    def test_source_health_update_success(self):
        """Successful fetch updates reliability correctly."""
        db = _get_db()
        try:
            _seed_source_health(db, "test_src", fetch_count=0, success_count=0)

            engine = ReconciliationEngine(db)
            engine.update_source_health("test_src", success=True, latency_ms=250.0)
            db.commit()

            src = db.query(DataSourceHealth).filter(
                DataSourceHealth.source_name == "test_src"
            ).first()
            assert src.fetch_count == 1   # was 0, incremented by 1
            assert src.success_count == 1
            assert src.status == "HEALTHY"
        finally:
            db.close()

    def test_source_health_update_failure(self):
        """Failed fetch increments error count."""
        db = _get_db()
        try:
            _seed_source_health(db, "test_fail", fetch_count=10, success_count=5, error_count=5)

            engine = ReconciliationEngine(db)
            engine.update_source_health("test_fail", success=False, latency_ms=5000.0, error_msg="Timeout")
            db.commit()

            src = db.query(DataSourceHealth).filter(
                DataSourceHealth.source_name == "test_fail"
            ).first()
            assert src.fetch_count == 11
            assert src.error_count == 6
            assert src.last_error_message == "Timeout"
        finally:
            db.close()

    def test_lineage_recording(self):
        """Record lineage, query it back."""
        db = _get_db()
        try:
            engine = ReconciliationEngine(db)
            engine.record_lineage("wasi_composite", 1, [
                {"table": "country_index", "id": 10, "weight": 0.28, "value": 65.0},
                {"table": "country_index", "id": 11, "weight": 0.22, "value": 72.0},
            ])
            db.commit()

            lineage = engine.get_lineage("wasi_composite", 1)
            assert len(lineage) == 2
            assert lineage[0]["contribution_weight"] == 0.28
        finally:
            db.close()

    def test_full_reconciliation_run(self):
        """Full run creates ReconciliationRun and returns summary."""
        db = _get_db()
        try:
            country = _get_country(db)
            _seed_country_indices(db, country.id, [50.0, 52.0, 48.0, 51.0, 49.0])

            engine = ReconciliationEngine(db)
            result = engine.run_full_reconciliation(run_type="MANUAL")

            assert result["run_id"] is not None
            assert result["run_type"] == "MANUAL"
            assert "records_checked" in result
            assert "by_type" in result
            assert result["duration_ms"] >= 0

            run = db.query(ReconciliationRun).filter(
                ReconciliationRun.id == result["run_id"]
            ).first()
            assert run is not None
            assert run.completed_at is not None
        finally:
            db.close()

    def test_quarantine_resolve(self):
        """Approve a quarantined record."""
        db = _get_db()
        try:
            q = DataQuarantine(
                table_name="country_index",
                record_id=1,
                country_code="NG",
                anomaly_type="Z_SCORE",
                anomaly_detail="{}",
                severity="HIGH",
                status="PENDING",
            )
            db.add(q)
            db.commit()
            q_id = q.id

            engine = ReconciliationEngine(db)
            result = engine.resolve_quarantine(q_id, "approve", user_id=1)

            assert result["status"] == "APPROVED"
            assert result["reviewed_by"] == 1

            reloaded = db.query(DataQuarantine).filter(DataQuarantine.id == q_id).first()
            assert reloaded.status == "APPROVED"
        finally:
            db.close()


# ══════════════════════════════════════════════════════════════════
# API INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════


def test_unauthenticated_rejected():
    """Integrity endpoints require auth."""
    resp = client.get("/api/v3/integrity/dashboard")
    assert resp.status_code in (401, 403)


def test_dashboard_returns_sources():
    """Dashboard returns source health and quarantine summary."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v3/integrity/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "integrity_score" in data
    assert "sources" in data
    assert "quarantine" in data


def test_sources_endpoint():
    """Sources endpoint returns list of data sources."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v3/integrity/sources", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    assert "count" in data


def test_quarantine_list():
    """Quarantine list with filtering."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v3/integrity/quarantine", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


def test_reconcile_trigger():
    """Manual reconciliation trigger works."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/api/v3/integrity/reconcile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "run_id" in data
    assert "records_checked" in data
    assert "anomalies_found" in data


def test_anomalies_endpoint():
    """Recent anomalies endpoint."""
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v3/integrity/anomalies?hours=24", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "anomalies" in data
    assert "count" in data
