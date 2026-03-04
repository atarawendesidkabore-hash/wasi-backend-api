"""
Tests for eCFA CBDC Wallet endpoints — /api/v3/ecfa/wallet/

Covers:
  - Auth guards (create, balance, freeze)
  - Wallet creation (retail, institutional, invalid country, invalid type)
  - Balance & info (happy path, IDOR protection)
  - PIN management (initial set, change requires current, wrong current PIN)
  - Freeze / unfreeze (success, wrong admin wallet)
  - Credit deduction (insufficient balance, free tier no charge)
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet
from src.utils.cbdc_crypto import hash_pin
from tests.conftest import TestingSessionLocal

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────

def _register_and_login(
    username="wusr", email="wusr@test.com",
    password="WalPass1!", is_admin=False,
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
                    balance: float = 500_000.0, pin: str = "1234") -> str:
    db = TestingSessionLocal()
    wid = str(uuid.uuid4())
    w = CbdcWallet(
        wallet_id=wid,
        user_id=user_id,
        country_id=country_id,
        wallet_type=wallet_type,
        kyc_tier=2 if wallet_type == "RETAIL" else 3,
        daily_limit_ecfa=5_000_000.0 if wallet_type == "RETAIL" else 999_999_999_999.0,
        balance_limit_ecfa=10_000_000.0 if wallet_type == "RETAIL" else 999_999_999_999.0,
        balance_ecfa=balance,
        available_balance_ecfa=balance,
        pin_hash=hash_pin(pin) if pin else None,
        status="active",
    )
    if wallet_type == "CENTRAL_BANK":
        w.institution_code = "BCEAO"
        w.institution_name = "BCEAO Treasury"
    db.add(w)
    db.commit()
    db.close()
    return wid


def _topup_credits(headers: dict, amount: int = 100):
    """Add credits to the authenticated user's account."""
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference": f"ref-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )


# ── Auth Guards ────────────────────────────────────────────────────────

def test_create_wallet_requires_auth():
    """POST /create without token -> 401."""
    resp = client.post("/api/v3/ecfa/wallet/create", json={})
    assert resp.status_code == 401


def test_balance_requires_auth():
    """GET /balance/fake-id without token -> 401."""
    resp = client.get("/api/v3/ecfa/wallet/balance/fake-id")
    assert resp.status_code == 401


def test_freeze_requires_admin():
    """POST /freeze with non-admin user -> 403."""
    headers = _register_and_login("wfrznonadm", "wfrznonadm@t.com", "WalPass1!")
    resp = client.post(
        "/api/v3/ecfa/wallet/freeze",
        json={
            "admin_wallet_id": "fake-admin",
            "target_wallet_id": "fake-target",
            "reason": "Testing non-admin freeze attempt",
        },
        headers=headers,
    )
    assert resp.status_code == 403


# ── Wallet Creation ──────────────────────────────────────────────────

def test_create_retail_wallet():
    """Create a RETAIL wallet via API -> 200, verify response fields."""
    headers = _register_and_login("wcreate1", "wcreate1@t.com", "WalPass1!")
    _topup_credits(headers, 100)

    resp = client.post(
        "/api/v3/ecfa/wallet/create",
        json={
            "country_code": "CI",
            "wallet_type": "RETAIL",
            "phone_hash": "abc123def456",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "wallet_id" in data
    assert data["wallet_type"] == "RETAIL"
    assert data["kyc_tier"] == 0
    assert data["status"] == "active"


def test_create_institutional_requires_admin():
    """Non-admin tries to create CENTRAL_BANK wallet -> 403."""
    headers = _register_and_login("winstno", "winstno@t.com", "WalPass1!")
    _topup_credits(headers, 100)

    resp = client.post(
        "/api/v3/ecfa/wallet/create",
        json={
            "country_code": "CI",
            "wallet_type": "CENTRAL_BANK",
            "phone_hash": "abc123",
            "pin": "1234",
            "institution_code": "BCEAO",
            "institution_name": "BCEAO Treasury",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_create_wallet_invalid_country():
    """Country code 'XX' does not exist -> 400."""
    headers = _register_and_login("winvcc", "winvcc@t.com", "WalPass1!")
    _topup_credits(headers, 100)

    resp = client.post(
        "/api/v3/ecfa/wallet/create",
        json={
            "country_code": "XX",
            "wallet_type": "RETAIL",
            "phone_hash": "abc123",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_create_wallet_invalid_type():
    """wallet_type 'INVALID' is not a valid type -> 400."""
    headers = _register_and_login("winvty", "winvty@t.com", "WalPass1!")
    _topup_credits(headers, 100)

    resp = client.post(
        "/api/v3/ecfa/wallet/create",
        json={
            "country_code": "CI",
            "wallet_type": "INVALID",
            "phone_hash": "abc123",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 400


# ── Balance & Info ───────────────────────────────────────────────────

def test_get_balance():
    """Create wallet via DB helper, GET /balance/{id} -> 200."""
    headers = _register_and_login("wbal1", "wbal1@t.com", "WalPass1!")
    _topup_credits(headers, 100)
    uid = _get_user_id("wbal1")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid, balance=250_000.0)

    resp = client.get(f"/api/v3/ecfa/wallet/balance/{wid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["wallet_id"] == wid


def test_get_info():
    """GET /info/{id} -> 200, verify wallet_type, kyc_tier, status present."""
    headers = _register_and_login("winfo1", "winfo1@t.com", "WalPass1!")
    _topup_credits(headers, 100)
    uid = _get_user_id("winfo1")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid)

    resp = client.get(f"/api/v3/ecfa/wallet/info/{wid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "wallet_type" in data
    assert "kyc_tier" in data
    assert "status" in data


def test_balance_idor_protection():
    """User A creates wallet, user B tries GET /balance/{A's wallet} -> 403."""
    headers_a = _register_and_login("widorA", "widorA@t.com", "WalPass1!")
    _topup_credits(headers_a, 100)
    uid_a = _get_user_id("widorA")
    cid = _get_country_id()
    wallet_a = _create_wallet(uid_a, cid)

    headers_b = _register_and_login("widorB", "widorB@t.com", "WalPass1!")
    _topup_credits(headers_b, 100)

    resp = client.get(f"/api/v3/ecfa/wallet/balance/{wallet_a}", headers=headers_b)
    assert resp.status_code == 403


# ── PIN Management ───────────────────────────────────────────────────

def test_set_pin_initial():
    """Create wallet WITHOUT pin, POST /set-pin with new_pin -> 200."""
    headers = _register_and_login("wpin1", "wpin1@t.com", "WalPass1!")
    uid = _get_user_id("wpin1")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid, pin=None)  # No initial PIN

    resp = client.post(
        "/api/v3/ecfa/wallet/set-pin",
        json={"wallet_id": wid, "new_pin": "5678"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["wallet_id"] == wid
    assert "PIN set successfully" in data["message"]


def test_set_pin_change_requires_current():
    """Wallet already has PIN, POST /set-pin without current_pin -> 400."""
    headers = _register_and_login("wpin2", "wpin2@t.com", "WalPass1!")
    uid = _get_user_id("wpin2")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid, pin="1234")  # Has existing PIN

    resp = client.post(
        "/api/v3/ecfa/wallet/set-pin",
        json={"wallet_id": wid, "new_pin": "9999"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_set_pin_wrong_current():
    """Wallet has PIN, provide wrong current_pin -> 401."""
    headers = _register_and_login("wpin3", "wpin3@t.com", "WalPass1!")
    uid = _get_user_id("wpin3")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid, pin="1234")

    resp = client.post(
        "/api/v3/ecfa/wallet/set-pin",
        json={"wallet_id": wid, "new_pin": "9999", "current_pin": "0000"},
        headers=headers,
    )
    assert resp.status_code == 401


# ── Freeze / Unfreeze ───────────────────────────────────────────────

def test_freeze_wallet_success():
    """Admin creates CB wallet + target retail wallet, POST /freeze -> 200."""
    headers = _register_and_login("wfrzadm", "wfrzadm@t.com", "WalPass1!", is_admin=True)
    _topup_credits(headers, 100)
    uid = _get_user_id("wfrzadm")
    cid = _get_country_id()
    admin_wid = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)

    # Create a target retail wallet (different user)
    headers2 = _register_and_login("wfrztgt", "wfrztgt@t.com", "WalPass1!")
    uid2 = _get_user_id("wfrztgt")
    target_wid = _create_wallet(uid2, cid, balance=100_000.0)

    resp = client.post(
        "/api/v3/ecfa/wallet/freeze",
        json={
            "admin_wallet_id": admin_wid,
            "target_wallet_id": target_wid,
            "reason": "Suspicious activity detected in compliance review",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "frozen"
    assert data["wallet_id"] == target_wid


def test_unfreeze_wallet_success():
    """Freeze then unfreeze a wallet -> both 200."""
    headers = _register_and_login("wufrzadm", "wufrzadm@t.com", "WalPass1!", is_admin=True)
    _topup_credits(headers, 100)
    uid = _get_user_id("wufrzadm")
    cid = _get_country_id()
    admin_wid = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)

    headers2 = _register_and_login("wufrztgt", "wufrztgt@t.com", "WalPass1!")
    uid2 = _get_user_id("wufrztgt")
    target_wid = _create_wallet(uid2, cid, balance=50_000.0)

    # Freeze first
    freeze_resp = client.post(
        "/api/v3/ecfa/wallet/freeze",
        json={
            "admin_wallet_id": admin_wid,
            "target_wallet_id": target_wid,
            "reason": "AML review pending for compliance check",
        },
        headers=headers,
    )
    assert freeze_resp.status_code == 200
    assert freeze_resp.json()["status"] == "frozen"

    # Now unfreeze
    unfreeze_resp = client.post(
        "/api/v3/ecfa/wallet/unfreeze",
        json={
            "admin_wallet_id": admin_wid,
            "target_wallet_id": target_wid,
            "reason": "AML review completed and cleared",
        },
        headers=headers,
    )
    assert unfreeze_resp.status_code == 200
    assert unfreeze_resp.json()["status"] == "active"


def test_freeze_wrong_admin_wallet():
    """Admin tries to use another user's wallet as admin_wallet_id -> 403."""
    # Admin user
    headers_admin = _register_and_login("wfrzwrg", "wfrzwrg@t.com", "WalPass1!", is_admin=True)
    _topup_credits(headers_admin, 100)

    # Another user who owns a CB wallet (also admin to create it)
    headers_other = _register_and_login("wfrzoth", "wfrzoth@t.com", "WalPass1!", is_admin=True)
    uid_other = _get_user_id("wfrzoth")
    cid = _get_country_id()
    other_cb_wid = _create_wallet(uid_other, cid, wallet_type="CENTRAL_BANK", balance=0.0)

    # Create a target to freeze
    headers_tgt = _register_and_login("wfrzwtgt", "wfrzwtgt@t.com", "WalPass1!")
    uid_tgt = _get_user_id("wfrzwtgt")
    target_wid = _create_wallet(uid_tgt, cid, balance=100_000.0)

    # Admin tries to freeze using other user's CB wallet
    resp = client.post(
        "/api/v3/ecfa/wallet/freeze",
        json={
            "admin_wallet_id": other_cb_wid,
            "target_wallet_id": target_wid,
            "reason": "Attempting freeze with wrong admin wallet",
        },
        headers=headers_admin,
    )
    assert resp.status_code == 403


# ── Credit Deduction ────────────────────────────────────────────────

def test_credit_deduction_insufficient():
    """Register user with 0 credits, try POST /create -> 402."""
    headers = _register_and_login("wnocred", "wnocred@t.com", "WalPass1!")
    # Do NOT topup — set tier to 'pro' (cost > 0) and balance to 0
    uid = _get_user_id("wnocred")
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == uid).first()
    user.tier = "pro"
    user.x402_balance = 0.0
    db.commit()
    db.close()

    resp = client.post(
        "/api/v3/ecfa/wallet/create",
        json={
            "country_code": "CI",
            "wallet_type": "RETAIL",
            "phone_hash": "abc123",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 402
    data = resp.json()
    detail = data["detail"]
    assert "balance" in detail
    assert "cost" in detail
    assert "topup_url" in detail


def test_credit_free_tier_no_charge():
    """Free-tier user can GET /balance without credit deduction."""
    headers = _register_and_login("wfree1", "wfree1@t.com", "WalPass1!")
    uid = _get_user_id("wfree1")

    # Set user tier to 'free' explicitly
    db = TestingSessionLocal()
    user = db.query(User).filter(User.id == uid).first()
    user.tier = "free"
    db.commit()
    db.close()

    cid = _get_country_id()
    wid = _create_wallet(uid, cid, balance=100_000.0)

    resp = client.get(f"/api/v3/ecfa/wallet/balance/{wid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["wallet_id"] == wid
