"""
Tests for eCFA CBDC Admin endpoints — /api/v3/ecfa/admin/

Covers:
  - Policy management (create, list)
  - Monetary aggregates
  - Settlement (pending, run domestic, run cross-border, COBOL)
  - AML dashboard, alerts, resolve, sweep
  - Auth guards (require_admin, require_cbdc_role)
"""
import uuid
from datetime import timezone, datetime

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import (
    CbdcWallet, CbdcSettlement, CbdcAmlAlert, CbdcPolicy,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────

def _register_and_login(
    username="cbdcadm", email="cbdcadm@test.com",
    password="CbdcPass1", is_admin=False,
):
    """Register, optionally promote to admin, and return auth headers."""
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    if is_admin:
        db = TestingSessionLocal()
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.is_admin = True
            db.commit()
        db.close()
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_cb_wallet(user_id: int, country_id: int, wallet_id: str = None):
    """Create a CENTRAL_BANK wallet for the given user."""
    db = TestingSessionLocal()
    w = CbdcWallet(
        wallet_id=wallet_id or str(uuid.uuid4()),
        user_id=user_id,
        country_id=country_id,
        wallet_type="CENTRAL_BANK",
        institution_code="BCEAO",
        institution_name="BCEAO Treasury",
        kyc_tier=3,
        daily_limit_ecfa=999_999_999_999.0,
        balance_limit_ecfa=999_999_999_999.0,
        balance_ecfa=0.0,
        available_balance_ecfa=0.0,
        status="active",
    )
    db.add(w)
    db.commit()
    wid = w.wallet_id
    db.close()
    return wid


def _create_bank_wallet(user_id: int, country_id: int):
    """Create a COMMERCIAL_BANK wallet for the given user."""
    db = TestingSessionLocal()
    w = CbdcWallet(
        wallet_id=str(uuid.uuid4()),
        user_id=user_id,
        country_id=country_id,
        wallet_type="COMMERCIAL_BANK",
        institution_code="SGBCI",
        institution_name="Societe Generale CI",
        kyc_tier=3,
        daily_limit_ecfa=999_999_999_999.0,
        balance_limit_ecfa=999_999_999_999.0,
        balance_ecfa=0.0,
        available_balance_ecfa=0.0,
        status="active",
    )
    db.add(w)
    db.commit()
    wid = w.wallet_id
    db.close()
    return wid


def _get_user_id(username: str) -> int:
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    uid = user.id
    db.close()
    return uid


def _get_country_id(code: str = "CI") -> int:
    db = TestingSessionLocal()
    c = db.query(Country).filter(Country.code == code).first()
    cid = c.id
    db.close()
    return cid


# ── Auth Guards ────────────────────────────────────────────────────────

def test_policy_create_requires_auth():
    resp = client.post("/api/v3/ecfa/admin/policy/create", json={})
    assert resp.status_code == 401


def test_policy_create_requires_admin():
    headers = _register_and_login("nonadm1", "nonadm1@t.com", "TestPass1")
    resp = client.post(
        "/api/v3/ecfa/admin/policy/create",
        json={
            "policy_name": "Test",
            "policy_type": "SPENDING_RESTRICTION",
            "conditions": "{}",
            "effective_from": "2026-03-01T00:00:00",
            "admin_wallet_id": "cb-001",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_policy_create_requires_cbdc_role():
    """Admin user without a CENTRAL_BANK wallet → 403."""
    headers = _register_and_login("admnocb", "admnocb@t.com", "TestPass1", is_admin=True)
    resp = client.post(
        "/api/v3/ecfa/admin/policy/create",
        json={
            "policy_name": "Test",
            "policy_type": "SPENDING_RESTRICTION",
            "conditions": "{}",
            "effective_from": "2026-03-01T00:00:00",
            "admin_wallet_id": "cb-001",
        },
        headers=headers,
    )
    assert resp.status_code == 403


# ── Policy Management ─────────────────────────────────────────────────

def test_create_policy():
    headers = _register_and_login("cbadm1", "cbadm1@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm1")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.post(
        "/api/v3/ecfa/admin/policy/create",
        json={
            "policy_name": "Food subsidy restriction",
            "policy_type": "SPENDING_RESTRICTION",
            "conditions": '{"category": "FOOD"}',
            "country_codes": "CI,SN",
            "effective_from": "2026-03-01T00:00:00",
            "admin_wallet_id": "cb-001",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy_name"] == "Food subsidy restriction"
    assert data["policy_type"] == "SPENDING_RESTRICTION"
    assert data["is_active"] is True


def test_list_policies():
    headers = _register_and_login("cbadm2", "cbadm2@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm2")
    cid = _get_country_id()
    _create_bank_wallet(uid, cid)  # COMMERCIAL_BANK can list

    resp = client.get("/api/v3/ecfa/admin/policy/list", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_policies_requires_cbdc_role():
    """User with no CBDC wallet at all → 403."""
    headers = _register_and_login("noCbdc1", "nocbdc1@t.com", "TestPass1")
    resp = client.get("/api/v3/ecfa/admin/policy/list", headers=headers)
    assert resp.status_code == 403


# ── Monetary Aggregates ───────────────────────────────────────────────

def test_monetary_aggregates_requires_central_bank():
    headers = _register_and_login("bankusr1", "bankusr1@t.com", "TestPass1")
    uid = _get_user_id("bankusr1")
    cid = _get_country_id()
    _create_bank_wallet(uid, cid)  # COMMERCIAL_BANK, not CENTRAL_BANK

    resp = client.get("/api/v3/ecfa/admin/monetary-aggregates/CI", headers=headers)
    assert resp.status_code == 403


def test_monetary_aggregates_success():
    headers = _register_and_login("cbadm3", "cbadm3@t.com", "TestPass1")
    uid = _get_user_id("cbadm3")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get("/api/v3/ecfa/admin/monetary-aggregates/CI", headers=headers)
    # Returns 200 with aggregates or 404 if no data yet
    assert resp.status_code in (200, 404)


# ── Settlement ────────────────────────────────────────────────────────

def test_pending_settlements():
    headers = _register_and_login("cbadm4", "cbadm4@t.com", "TestPass1")
    uid = _get_user_id("cbadm4")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get("/api/v3/ecfa/admin/settlement/pending", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_run_domestic_settlement():
    headers = _register_and_login("cbadm5", "cbadm5@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm5")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.post("/api/v3/ecfa/admin/settlement/run-domestic", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "settlements" in data
    assert "transactions_netted" in data


def test_run_cross_border_settlement():
    headers = _register_and_login("cbadm6", "cbadm6@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm6")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.post("/api/v3/ecfa/admin/settlement/run-cross-border", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "settlements" in data


def test_settlement_cobol_not_found():
    headers = _register_and_login("cbadm7", "cbadm7@t.com", "TestPass1")
    uid = _get_user_id("cbadm7")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get("/api/v3/ecfa/admin/settlement/nonexistent-id/cobol", headers=headers)
    assert resp.status_code == 404


def test_settlement_cobol_success():
    """Seed a settlement, then fetch its COBOL record."""
    headers = _register_and_login("cbadm8", "cbadm8@t.com", "TestPass1")
    uid = _get_user_id("cbadm8")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    sid = str(uuid.uuid4())
    db = TestingSessionLocal()
    settlement = CbdcSettlement(
        settlement_id=sid,
        settlement_type="DOMESTIC_NET",
        bank_a_code="BOA",
        bank_b_code="SGBCI",
        gross_amount_ecfa=1_000_000.0,
        net_amount_ecfa=250_000.0,
        direction="A_TO_B",
        transaction_count=10,
        country_codes="CI",
        is_cross_border=False,
        status="pending",
        window_start=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 3, 1, 12, 15, tzinfo=timezone.utc),
    )
    db.add(settlement)
    db.commit()
    db.close()

    resp = client.get(f"/api/v3/ecfa/admin/settlement/{sid}/cobol", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["record_length"] == 200
    assert "cobol_record" in data


# ── AML Dashboard ────────────────────────────────────────────────────

def test_aml_dashboard_empty():
    headers = _register_and_login("cbadm9", "cbadm9@t.com", "TestPass1")
    uid = _get_user_id("cbadm9")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get("/api/v3/ecfa/admin/aml/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_alerts"] == 0
    assert data["sars_filed"] == 0


def test_aml_alerts_list():
    headers = _register_and_login("cbadm10", "cbadm10@t.com", "TestPass1")
    uid = _get_user_id("cbadm10")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get("/api/v3/ecfa/admin/aml/alerts", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_aml_alerts_with_severity_filter():
    headers = _register_and_login("cbadm11", "cbadm11@t.com", "TestPass1")
    uid = _get_user_id("cbadm11")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.get(
        "/api/v3/ecfa/admin/aml/alerts?severity=HIGH",
        headers=headers,
    )
    assert resp.status_code == 200


def test_aml_resolve_not_found():
    headers = _register_and_login("cbadm12", "cbadm12@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm12")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.post(
        "/api/v3/ecfa/admin/aml/resolve/nonexistent",
        json={
            "resolution_status": "resolved_clear",
            "resolution_notes": "False alarm, cleared.",
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_aml_resolve_invalid_status():
    """Seed an alert, try to resolve with invalid status."""
    headers = _register_and_login("cbadm13", "cbadm13@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm13")
    cid = _get_country_id()
    wid = _create_cb_wallet(uid, cid)

    alert_id = str(uuid.uuid4())
    db = TestingSessionLocal()
    alert = CbdcAmlAlert(
        alert_id=alert_id,
        wallet_id=wid,
        alert_type="VELOCITY",
        severity="HIGH",
        description="Unusual velocity",
        status="open",
        sar_filed=False,
        reporting_authority="CENTIF-CI",
    )
    db.add(alert)
    db.commit()
    db.close()

    resp = client.post(
        f"/api/v3/ecfa/admin/aml/resolve/{alert_id}",
        json={
            "resolution_status": "invalid_status",
            "resolution_notes": "Testing invalid status",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_aml_resolve_success():
    """Create alert → resolve as false_positive."""
    headers = _register_and_login("cbadm14", "cbadm14@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm14")
    cid = _get_country_id()
    wid = _create_cb_wallet(uid, cid)

    alert_id = str(uuid.uuid4())
    db = TestingSessionLocal()
    alert = CbdcAmlAlert(
        alert_id=alert_id,
        wallet_id=wid,
        alert_type="STRUCTURING",
        severity="MEDIUM",
        description="Structuring pattern detected",
        status="open",
        sar_filed=False,
        reporting_authority="CENTIF-CI",
    )
    db.add(alert)
    db.commit()
    db.close()

    resp = client.post(
        f"/api/v3/ecfa/admin/aml/resolve/{alert_id}",
        json={
            "resolution_status": "false_positive",
            "resolution_notes": "Reviewed — legitimate business pattern.",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "false_positive"


def test_aml_resolve_sar():
    """Resolve as SAR → verify sar_filed is True and reference set."""
    headers = _register_and_login("cbadm15", "cbadm15@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm15")
    cid = _get_country_id()
    wid = _create_cb_wallet(uid, cid)

    alert_id = str(uuid.uuid4())
    db = TestingSessionLocal()
    alert = CbdcAmlAlert(
        alert_id=alert_id,
        wallet_id=wid,
        alert_type="CROSS_BORDER",
        severity="CRITICAL",
        description="Large cross-border movement",
        status="open",
        sar_filed=False,
        reporting_authority="CENTIF-CI",
    )
    db.add(alert)
    db.commit()
    db.close()

    resp = client.post(
        f"/api/v3/ecfa/admin/aml/resolve/{alert_id}",
        json={
            "resolution_status": "resolved_sar",
            "resolution_notes": "SAR filed with CENTIF.",
            "assigned_to": "compliance-team-ci",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sar_filed"] is True
    assert data["status"] == "resolved_sar"


def test_aml_sweep():
    headers = _register_and_login("cbadm16", "cbadm16@t.com", "TestPass1", is_admin=True)
    uid = _get_user_id("cbadm16")
    cid = _get_country_id()
    _create_cb_wallet(uid, cid)

    resp = client.post("/api/v3/ecfa/admin/aml/sweep", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "wallets_scanned" in data
    assert "alerts_generated" in data
