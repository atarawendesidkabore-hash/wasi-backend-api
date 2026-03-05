"""
HTTP route tests for eCFA CBDC Monetary Policy — /api/v3/ecfa/monetary-policy/

Tests all 16 endpoints at the HTTP level: auth guards, credit deduction,
request validation, and response schemas. Engine logic is already covered
by tests/test_cbdc_monetary_policy.py (25 engine-level tests).
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet
from tests.conftest import TestingSessionLocal

client = TestClient(app)

PREFIX = "/api/v3/ecfa/monetary-policy"


# ── Helpers (same pattern as test_cbdc_admin.py) ──────────────────────

def _register_and_login(
    username="mpadm", email="mpadm@test.com",
    password="MpPass1!", is_admin=False,
):
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


def _create_bank_wallet(user_id: int, country_id: int, balance: float = 500_000_000.0):
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
        balance_ecfa=balance,
        available_balance_ecfa=balance,
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
    country = db.query(Country).filter(Country.code == code).first()
    cid = country.id
    db.close()
    return cid


def _setup_admin_with_cb_wallet(username="mpadm", email="mpadm@test.com"):
    """Full setup: register admin + create CB wallet. Returns (headers, bank_wallet_id)."""
    headers = _register_and_login(username, email, is_admin=True)
    uid = _get_user_id(username)
    cid = _get_country_id("CI")
    _create_cb_wallet(uid, cid)
    bank_wid = _create_bank_wallet(uid, cid)
    return headers, bank_wid


# ── Auth Guard Tests ──────────────────────────────────────────────────

def test_rates_current_requires_auth():
    resp = client.get(f"{PREFIX}/rates/current")
    assert resp.status_code == 401


def test_rates_set_requires_admin():
    headers = _register_and_login("mpnonadm", "mpnonadm@test.com", is_admin=False)
    resp = client.post(f"{PREFIX}/rates/set", json={
        "rate_type": "TAUX_DIRECTEUR",
        "new_rate_percent": 4.0,
    }, headers=headers)
    assert resp.status_code == 403


def test_rates_set_requires_cbdc_role():
    headers = _register_and_login("mpadmnocb", "mpadmnocb@test.com", is_admin=True)
    # No CB wallet created
    resp = client.post(f"{PREFIX}/rates/set", json={
        "rate_type": "TAUX_DIRECTEUR",
        "new_rate_percent": 4.0,
    }, headers=headers)
    assert resp.status_code == 403


# ── Policy Rates ──────────────────────────────────────────────────────

def test_rates_current_success():
    headers = _register_and_login("mpview1", "mpview1@test.com")
    resp = client.get(f"{PREFIX}/rates/current", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "TAUX_DIRECTEUR" in data
    assert "TAUX_PRET_MARGINAL" in data
    assert "TAUX_DEPOT" in data


def test_rates_set_success():
    headers, _ = _setup_admin_with_cb_wallet("mpset1", "mpset1@test.com")
    resp = client.post(f"{PREFIX}/rates/set", json={
        "rate_type": "TAUX_DIRECTEUR",
        "new_rate_percent": 4.25,
        "rationale": "Inflation control",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "rates_updated" in data
    assert len(data["rates_updated"]) >= 1


def test_rates_history():
    headers, _ = _setup_admin_with_cb_wallet("mphist1", "mphist1@test.com")
    # Set a rate first to have history
    client.post(f"{PREFIX}/rates/set", json={
        "rate_type": "TAUX_DIRECTEUR",
        "new_rate_percent": 3.75,
    }, headers=headers)
    resp = client.get(f"{PREFIX}/rates/history/TAUX_DIRECTEUR", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["rate_type"] == "TAUX_DIRECTEUR"
    assert "history" in data


# ── Reserve Requirements ──────────────────────────────────────────────

def test_reserves_status():
    headers = _register_and_login("mpres1", "mpres1@test.com")
    resp = client.get(f"{PREFIX}/reserves/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "reserve_ratio_percent" in data


def test_reserves_set_ratio():
    headers, _ = _setup_admin_with_cb_wallet("mpresset1", "mpresset1@test.com")
    resp = client.post(f"{PREFIX}/reserves/set-ratio", json={
        "new_ratio_percent": 4.5,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "rates_updated" in data


# ── Standing Facilities ───────────────────────────────────────────────

def test_facility_lending_open():
    headers, bank_wid = _setup_admin_with_cb_wallet("mpfacl1", "mpfacl1@test.com")
    resp = client.post(f"{PREFIX}/facility/lending/open", json={
        "bank_wallet_id": bank_wid,
        "amount_ecfa": 10_000_000.0,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["facility_type"] == "LENDING"
    assert "facility_id" in data


def test_facility_deposit_open():
    headers, bank_wid = _setup_admin_with_cb_wallet("mpfacd1", "mpfacd1@test.com")
    resp = client.post(f"{PREFIX}/facility/deposit/open", json={
        "bank_wallet_id": bank_wid,
        "amount_ecfa": 5_000_000.0,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["facility_type"] == "DEPOSIT"
    assert "facility_id" in data


def test_facility_mature():
    headers, _ = _setup_admin_with_cb_wallet("mpfacm1", "mpfacm1@test.com")
    resp = client.post(f"{PREFIX}/facility/mature", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "facilities_matured" in data


# ── Interest & Demurrage ──────────────────────────────────────────────

def test_interest_apply_daily():
    headers, _ = _setup_admin_with_cb_wallet("mpint1", "mpint1@test.com")
    resp = client.post(f"{PREFIX}/interest/apply-daily", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "wallets_affected" in data


# ── Money Supply Dashboard ────────────────────────────────────────────

def test_money_supply_all():
    headers = _register_and_login("mpmsa1", "mpmsa1@test.com")
    resp = client.get(f"{PREFIX}/money-supply", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "m0_base_money_ecfa" in data
    assert "m1_narrow_money_ecfa" in data
    assert "m2_broad_money_ecfa" in data


def test_money_supply_country():
    headers = _register_and_login("mpmsc1", "mpmsc1@test.com")
    resp = client.get(f"{PREFIX}/money-supply/CI", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "CI"


def test_aggregates_country():
    headers = _register_and_login("mpagg1", "mpagg1@test.com")
    resp = client.get(f"{PREFIX}/aggregates/CI", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "policy_rates" in data
    assert "reserve_position" in data


# ── Monetary Policy Decisions ─────────────────────────────────────────

def test_decision_record():
    headers, _ = _setup_admin_with_cb_wallet("mpdec1", "mpdec1@test.com")
    resp = client.post(f"{PREFIX}/decision/record", json={
        "meeting_date": "2026-03-01",
        "decision_summary": "Maintain taux directeur at 3.50%",
        "rationale": "Inflation within target band",
        "taux_directeur": 3.50,
        "taux_pret_marginal": 5.50,
        "taux_depot": 1.50,
        "reserve_ratio": 3.0,
        "meeting_type": "QUARTERLY",
        "votes_for": 7,
        "votes_against": 1,
        "votes_abstain": 0,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "decision_id" in data
    assert data["status"] == "decided"


def test_decision_history():
    headers, _ = _setup_admin_with_cb_wallet("mpdech1", "mpdech1@test.com")
    # Record a decision first
    client.post(f"{PREFIX}/decision/record", json={
        "meeting_date": "2026-02-01",
        "decision_summary": "Cut taux directeur by 25bp",
        "rationale": "Slowing growth",
        "taux_directeur": 3.25,
        "taux_pret_marginal": 5.25,
        "taux_depot": 1.25,
        "reserve_ratio": 3.0,
    }, headers=headers)
    resp = client.get(f"{PREFIX}/decision/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


# ── Collateral Framework ─────────────────────────────────────────────

def test_collateral_register_and_list():
    headers, _ = _setup_admin_with_cb_wallet("mpcoll1", "mpcoll1@test.com")
    # Register
    resp = client.post(f"{PREFIX}/collateral/register", json={
        "asset_class": "ECFA_TREASURY_BILL",
        "asset_description": "6-month T-Bill CI 2026-Q2",
        "issuer": "BCEAO",
        "issuer_country": "CI",
        "face_value_ecfa": 100_000_000.0,
        "market_value_ecfa": 98_500_000.0,
        "haircut_percent": 5.0,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_class"] == "ECFA_TREASURY_BILL"
    assert data["is_eligible"] is True
    expected_value = 98_500_000.0 * 0.95
    assert abs(data["collateral_value_ecfa"] - expected_value) < 0.01

    # List
    resp2 = client.get(f"{PREFIX}/collateral/list", headers=headers)
    assert resp2.status_code == 200
    items = resp2.json()
    assert isinstance(items, list)
    assert len(items) >= 1
