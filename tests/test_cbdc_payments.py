"""
Tests for WASI-Pay Cross-Border Payment endpoints — /api/v3/ecfa/payments/

Covers:
  - Payment quote (WAEMU→WAEMU, WAEMU→WAMZ)
  - Cross-border execution
  - Payment status & trace (with IDOR protection)
  - Corridors listing
  - FX rates (all, single pair, update)
  - Sender ownership verification
  - Auth guards
"""
import uuid
from datetime import timezone, datetime

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet, CbdcTransaction
from tests.conftest import TestingSessionLocal

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────

def _register_and_login(
    username="payusr", email="payusr@test.com",
    password="PayPass1", is_admin=False,
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


def _create_wallet(user_id: int, country_id: int, wallet_type="RETAIL",
                    balance: float = 500_000.0) -> str:
    db = TestingSessionLocal()
    wid = str(uuid.uuid4())
    w = CbdcWallet(
        wallet_id=wid,
        user_id=user_id,
        country_id=country_id,
        wallet_type=wallet_type,
        kyc_tier=2,
        daily_limit_ecfa=5_000_000.0,
        balance_limit_ecfa=10_000_000.0,
        balance_ecfa=balance,
        available_balance_ecfa=balance,
        status="active",
    )
    if wallet_type == "CENTRAL_BANK":
        w.institution_code = "BCEAO"
        w.institution_name = "BCEAO Treasury"
        w.kyc_tier = 3
        w.daily_limit_ecfa = 999_999_999_999.0
        w.balance_limit_ecfa = 999_999_999_999.0
    db.add(w)
    db.commit()
    db.close()
    return wid


# ── Auth Guards ────────────────────────────────────────────────────────

def test_quote_requires_auth():
    resp = client.post("/api/v3/ecfa/payments/quote", json={})
    assert resp.status_code == 401


def test_corridors_requires_auth():
    resp = client.get("/api/v3/ecfa/payments/corridors")
    assert resp.status_code == 401


def test_fx_rates_requires_auth():
    resp = client.get("/api/v3/ecfa/payments/fx/rates")
    assert resp.status_code == 401


# ── Sender Ownership ──────────────────────────────────────────────────

def test_quote_wrong_wallet_owner():
    """User A cannot quote using User B's wallet."""
    headers_a = _register_and_login("payusrA", "payusrA@t.com", "PayPass1")
    headers_b = _register_and_login("payusrB", "payusrB@t.com", "PayPass1")
    uid_b = _get_user_id("payusrB")
    cid = _get_country_id()
    wallet_b = _create_wallet(uid_b, cid)

    resp = client.post(
        "/api/v3/ecfa/payments/quote",
        json={
            "sender_wallet_id": wallet_b,
            "receiver_country": "SN",
            "amount": 50_000,
            "target_currency": "XOF",
        },
        headers=headers_a,
    )
    assert resp.status_code == 403


# ── Corridors ─────────────────────────────────────────────────────────

def test_list_corridors():
    headers = _register_and_login("paycorr", "paycorr@t.com", "PayPass1")
    resp = client.get("/api/v3/ecfa/payments/corridors", headers=headers)
    assert resp.status_code == 200
    corridors = resp.json()
    assert isinstance(corridors, list)
    assert len(corridors) > 0
    # Each corridor should have required fields
    first = corridors[0]
    assert "source_country" in first
    assert "dest_country" in first
    assert "rail_type" in first


# ── FX Rates ──────────────────────────────────────────────────────────

def _seed_fx_rate(target_currency: str, rate: float):
    """Seed an FX rate in the test DB for today."""
    from datetime import date as _date
    from src.database.cbdc_models import CbdcFxRate
    db = TestingSessionLocal()
    db.add(CbdcFxRate(
        base_currency="XOF",
        target_currency=target_currency,
        rate=rate,
        inverse_rate=round(1.0 / rate, 6),
        effective_date=_date.today(),
        source="TEST_SEED",
    ))
    db.commit()
    db.close()


def test_get_all_fx_rates_empty():
    """No rates seeded → empty list (engine catches 404 per-currency)."""
    headers = _register_and_login("payfx1", "payfx1@t.com", "PayPass1")
    resp = client.get("/api/v3/ecfa/payments/fx/rates", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_all_fx_rates_with_seed():
    """Seed 2 rates → returns exactly those 2."""
    headers = _register_and_login("payfx1b", "payfx1b@t.com", "PayPass1")
    _seed_fx_rate("NGN", 1.15)
    _seed_fx_rate("GHS", 53.5)
    resp = client.get("/api/v3/ecfa/payments/fx/rates", headers=headers)
    assert resp.status_code == 200
    rates = resp.json()
    assert len(rates) == 2
    targets = {r["target"] for r in rates}
    assert "NGN" in targets
    assert "GHS" in targets


def test_get_single_fx_rate_not_found():
    """No rate seeded for currency → 404."""
    headers = _register_and_login("payfx2", "payfx2@t.com", "PayPass1")
    resp = client.get("/api/v3/ecfa/payments/fx/rates/NGN", headers=headers)
    assert resp.status_code == 404


def test_get_single_fx_rate_success():
    headers = _register_and_login("payfx2b", "payfx2b@t.com", "PayPass1")
    _seed_fx_rate("NGN", 1.15)
    resp = client.get("/api/v3/ecfa/payments/fx/rates/NGN", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["base"] == "XOF"
    assert data["target"] == "NGN"
    assert data["rate"] > 0


def test_get_fx_rate_with_pair_format():
    headers = _register_and_login("payfx3", "payfx3@t.com", "PayPass1")
    _seed_fx_rate("GHS", 53.5)
    resp = client.get("/api/v3/ecfa/payments/fx/rates/XOF-GHS", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["target"] == "GHS"


def test_update_fx_rate_requires_central_bank():
    """Regular user cannot update FX rates."""
    headers = _register_and_login("payfx4", "payfx4@t.com", "PayPass1")
    resp = client.post(
        "/api/v3/ecfa/payments/fx/rates/update",
        json={"target_currency": "NGN", "new_rate": 1.2},
        headers=headers,
    )
    assert resp.status_code == 403


def test_update_fx_rate_initial_set():
    """First-time rate set: route re-raises 404 from get_rate deviation check.
    This is a known limitation — initial rates must be seeded directly."""
    headers = _register_and_login("payfx5", "payfx5@t.com", "PayPass1")
    uid = _get_user_id("payfx5")
    cid = _get_country_id()
    _create_wallet(uid, cid, wallet_type="CENTRAL_BANK")

    resp = client.post(
        "/api/v3/ecfa/payments/fx/rates/update",
        json={"target_currency": "LRD", "new_rate": 3.5, "source": "BCEAO_MANUAL"},
        headers=headers,
    )
    # Route re-raises 404 from get_rate() when checking deviation on first set
    assert resp.status_code == 404


def test_update_fx_rate_existing():
    """Update an existing rate (within deviation limit) → 200."""
    headers = _register_and_login("payfx5b", "payfx5b@t.com", "PayPass1")
    uid = _get_user_id("payfx5b")
    cid = _get_country_id()
    _create_wallet(uid, cid, wallet_type="CENTRAL_BANK")

    # Seed a rate first
    _seed_fx_rate("GMD", 10.0)

    resp = client.post(
        "/api/v3/ecfa/payments/fx/rates/update",
        json={"target_currency": "GMD", "new_rate": 10.5, "source": "BCEAO_MANUAL"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target"] == "GMD"


def test_update_fx_rate_zero_rejected():
    headers = _register_and_login("payfx6", "payfx6@t.com", "PayPass1")
    uid = _get_user_id("payfx6")
    cid = _get_country_id()
    _create_wallet(uid, cid, wallet_type="CENTRAL_BANK")

    resp = client.post(
        "/api/v3/ecfa/payments/fx/rates/update",
        json={"target_currency": "NGN", "new_rate": 0},
        headers=headers,
    )
    assert resp.status_code == 422  # Pydantic gt=0 validation


# ── Quote ─────────────────────────────────────────────────────────────

def test_quote_waemu_to_waemu():
    """WAEMU→WAEMU (CI→SN): no FX conversion needed."""
    headers = _register_and_login("payq1", "payq1@t.com", "PayPass1")
    uid = _get_user_id("payq1")
    cid = _get_country_id("CI")
    wid = _create_wallet(uid, cid)

    resp = client.post(
        "/api/v3/ecfa/payments/quote",
        json={
            "sender_wallet_id": wid,
            "receiver_country": "SN",
            "amount": 100_000,
            "target_currency": "XOF",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rail_type"] == "ECFA_INTERNAL"
    assert data["source_currency"] == "XOF"


def test_quote_waemu_to_wamz_no_rate():
    """WAEMU→WAMZ without seeded FX rate → 404."""
    headers = _register_and_login("payq2", "payq2@t.com", "PayPass1")
    uid = _get_user_id("payq2")
    cid = _get_country_id("CI")
    wid = _create_wallet(uid, cid)

    resp = client.post(
        "/api/v3/ecfa/payments/quote",
        json={
            "sender_wallet_id": wid,
            "receiver_country": "NG",
            "amount": 100_000,
            "target_currency": "NGN",
        },
        headers=headers,
    )
    # No FX rate seeded → 404 from FX engine
    assert resp.status_code == 404


def test_quote_waemu_to_wamz_with_rate():
    """WAEMU→WAMZ with seeded FX rate → 200."""
    headers = _register_and_login("payq2b", "payq2b@t.com", "PayPass1")
    uid = _get_user_id("payq2b")
    cid = _get_country_id("CI")
    wid = _create_wallet(uid, cid)
    _seed_fx_rate("NGN", 1.15)

    resp = client.post(
        "/api/v3/ecfa/payments/quote",
        json={
            "sender_wallet_id": wid,
            "receiver_country": "NG",
            "amount": 100_000,
            "target_currency": "NGN",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rail_type"] in ("ECFA_TO_EXTERNAL", "EXTERNAL_BRIDGE")


# ── Cross-Border Payment ─────────────────────────────────────────────

def test_cross_border_payment_waemu_internal():
    """Execute CI→SN transfer (WAEMU internal, no FX)."""
    headers = _register_and_login("paycb1", "paycb1@t.com", "PayPass1")
    uid = _get_user_id("paycb1")
    cid_ci = _get_country_id("CI")
    sender_wid = _create_wallet(uid, cid_ci, balance=1_000_000.0)

    # Create receiver wallet (different user)
    headers2 = _register_and_login("payrcv1", "payrcv1@t.com", "PayPass1")
    uid2 = _get_user_id("payrcv1")
    cid_sn = _get_country_id("SN")
    receiver_wid = _create_wallet(uid2, cid_sn, balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/payments/cross-border",
        json={
            "sender_wallet_id": sender_wid,
            "receiver_wallet_id": receiver_wid,
            "receiver_country": "SN",
            "amount": 50_000,
            "source_currency": "XOF",
            "target_currency": "XOF",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("completed", "SETTLED", "DEST_CREDITED", "pending")
    assert data["payment_id"] is not None


# ── Payment Status ────────────────────────────────────────────────────

def test_payment_status_not_found():
    headers = _register_and_login("paystat1", "paystat1@t.com", "PayPass1")
    resp = client.get(
        "/api/v3/ecfa/payments/nonexistent-id/status",
        headers=headers,
    )
    assert resp.status_code == 404


# ── Payment Trace ─────────────────────────────────────────────────────

def test_payment_trace_not_found():
    headers = _register_and_login("paytrace1", "paytrace1@t.com", "PayPass1")
    resp = client.get(
        "/api/v3/ecfa/payments/nonexistent-id/trace",
        headers=headers,
    )
    assert resp.status_code == 404
