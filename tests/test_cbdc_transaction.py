"""
Tests for eCFA CBDC Transaction endpoints — /api/v3/ecfa/tx/

Covers:
  - P2P send (with wallet ownership verification)
  - Merchant payment
  - Cash-in / cash-out
  - Mint & burn (Central Bank admin only)
  - Transaction status (with IDOR protection)
  - Transaction history (pagination)
  - Auth guards
"""
import uuid
from datetime import timezone, datetime

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet, CbdcTransaction
from src.utils.cbdc_crypto import hash_pin
from tests.conftest import TestingSessionLocal

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────

def _register_and_login(
    username="txusr", email="txusr@test.com",
    password="TxPass1!", is_admin=False,
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


# ── Auth Guards ────────────────────────────────────────────────────────

def test_send_requires_auth():
    resp = client.post("/api/v3/ecfa/tx/send", json={})
    assert resp.status_code == 401


def test_mint_requires_auth():
    resp = client.post("/api/v3/ecfa/tx/mint", json={})
    assert resp.status_code == 401


def test_history_requires_auth():
    resp = client.get("/api/v3/ecfa/tx/history/some-wallet")
    assert resp.status_code == 401


# ── Wallet Ownership ──────────────────────────────────────────────────

def test_send_wrong_wallet_owner():
    """User A cannot send from User B's wallet."""
    headers_a = _register_and_login("txownerA", "txownerA@t.com", "TxPass1!")
    headers_b = _register_and_login("txownerB", "txownerB@t.com", "TxPass1!")
    uid_b = _get_user_id("txownerB")
    cid = _get_country_id()
    wallet_b = _create_wallet(uid_b, cid)

    uid_a = _get_user_id("txownerA")
    wallet_a = _create_wallet(uid_a, cid, balance=100_000.0)

    resp = client.post(
        "/api/v3/ecfa/tx/send",
        json={
            "sender_wallet_id": wallet_b,  # belongs to B
            "receiver_wallet_id": wallet_a,
            "amount_ecfa": 10_000,
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers_a,  # A is authenticated
    )
    assert resp.status_code in (403, 404)  # 404 if wallet not found, 403 if access denied


# ── P2P Send ──────────────────────────────────────────────────────────

def test_send_p2p_success():
    headers = _register_and_login("txsend1", "txsend1@t.com", "TxPass1!")
    uid = _get_user_id("txsend1")
    cid = _get_country_id()
    sender = _create_wallet(uid, cid, balance=200_000.0)

    # Create a receiver wallet (another user)
    headers2 = _register_and_login("txrecv1", "txrecv1@t.com", "TxPass1!")
    uid2 = _get_user_id("txrecv1")
    receiver = _create_wallet(uid2, cid, balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/tx/send",
        json={
            "sender_wallet_id": sender,
            "receiver_wallet_id": receiver,
            "amount_ecfa": 50_000,
            "tx_type": "TRANSFER_P2P",
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["amount_ecfa"] == 50_000


def test_send_with_ussd_pin():
    """USSD channel requires a valid PIN."""
    headers = _register_and_login("txpin1", "txpin1@t.com", "TxPass1!")
    uid = _get_user_id("txpin1")
    cid = _get_country_id()
    sender = _create_wallet(uid, cid, balance=200_000.0, pin="4321")

    headers2 = _register_and_login("txpinr1", "txpinr1@t.com", "TxPass1!")
    uid2 = _get_user_id("txpinr1")
    receiver = _create_wallet(uid2, cid, balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/tx/send",
        json={
            "sender_wallet_id": sender,
            "receiver_wallet_id": receiver,
            "amount_ecfa": 10_000,
            "tx_type": "TRANSFER_P2P",
            "channel": "USSD",
            "pin": "4321",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ── Merchant Payment ──────────────────────────────────────────────────

def test_merchant_payment():
    headers = _register_and_login("txmerch1", "txmerch1@t.com", "TxPass1!")
    uid = _get_user_id("txmerch1")
    cid = _get_country_id()
    sender = _create_wallet(uid, cid, balance=300_000.0)

    # Create a merchant wallet (another user)
    headers2 = _register_and_login("txmshop", "txmshop@t.com", "TxPass1!")
    uid2 = _get_user_id("txmshop")
    merchant = _create_wallet(uid2, cid, wallet_type="RETAIL", balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/tx/merchant-pay",
        json={
            "sender_wallet_id": sender,
            "receiver_wallet_id": merchant,
            "amount_ecfa": 25_000,
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"


# ── Cash-In / Cash-Out ───────────────────────────────────────────────

def test_cash_in():
    headers = _register_and_login("txcashi", "txcashi@t.com", "TxPass1!")
    uid = _get_user_id("txcashi")
    cid = _get_country_id()
    agent = _create_wallet(uid, cid, balance=1_000_000.0)

    headers2 = _register_and_login("txcashiu", "txcashiu@t.com", "TxPass1!")
    uid2 = _get_user_id("txcashiu")
    user_wallet = _create_wallet(uid2, cid, balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/tx/cash-in",
        json={
            "sender_wallet_id": agent,
            "receiver_wallet_id": user_wallet,
            "amount_ecfa": 50_000,
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_cash_out():
    headers = _register_and_login("txcasho", "txcasho@t.com", "TxPass1!")
    uid = _get_user_id("txcasho")
    cid = _get_country_id()
    user_wallet = _create_wallet(uid, cid, balance=200_000.0)

    headers2 = _register_and_login("txcashoa", "txcashoa@t.com", "TxPass1!")
    uid2 = _get_user_id("txcashoa")
    agent = _create_wallet(uid2, cid, balance=1_000_000.0)

    resp = client.post(
        "/api/v3/ecfa/tx/cash-out",
        json={
            "sender_wallet_id": user_wallet,
            "receiver_wallet_id": agent,
            "amount_ecfa": 30_000,
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ── Mint (Central Bank Only) ─────────────────────────────────────────

def test_mint_requires_admin():
    headers = _register_and_login("txmint1", "txmint1@t.com", "TxPass1!")
    resp = client.post(
        "/api/v3/ecfa/tx/mint",
        json={
            "central_bank_wallet_id": "cb-001",
            "target_wallet_id": "w-001",
            "amount_ecfa": 1_000_000,
            "reference": "INIT_MINT",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_mint_requires_cbdc_role():
    """Admin without CENTRAL_BANK wallet → 403."""
    headers = _register_and_login("txmint2", "txmint2@t.com", "TxPass1!", is_admin=True)
    resp = client.post(
        "/api/v3/ecfa/tx/mint",
        json={
            "central_bank_wallet_id": "cb-001",
            "target_wallet_id": "w-001",
            "amount_ecfa": 1_000_000,
            "reference": "INIT_MINT",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_mint_success():
    headers = _register_and_login("txmint3", "txmint3@t.com", "TxPass1!", is_admin=True)
    uid = _get_user_id("txmint3")
    cid = _get_country_id()
    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    target = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    resp = client.post(
        "/api/v3/ecfa/tx/mint",
        json={
            "central_bank_wallet_id": cb,
            "target_wallet_id": target,
            "amount_ecfa": 500_000,
            "reference": "INITIAL_MINT",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["amount_ecfa"] == 500_000
    assert data["target_new_balance"] == 500_000


# ── Burn (Central Bank Only) ─────────────────────────────────────────

def test_burn_requires_admin():
    headers = _register_and_login("txburn1", "txburn1@t.com", "TxPass1!")
    resp = client.post(
        "/api/v3/ecfa/tx/burn",
        json={
            "central_bank_wallet_id": "cb-001",
            "source_wallet_id": "w-001",
            "amount_ecfa": 100_000,
            "reference": "BURN_REF",
        },
        headers=headers,
    )
    assert resp.status_code == 403


def test_burn_success():
    headers = _register_and_login("txburn2", "txburn2@t.com", "TxPass1!", is_admin=True)
    uid = _get_user_id("txburn2")
    cid = _get_country_id()
    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    source = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    # First mint to give the source wallet a balance
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
    db = TestingSessionLocal()
    engine = CbdcLedgerEngine(db)
    engine.mint(cb, source, 200_000.0, "PREMINT")
    db.close()

    resp = client.post(
        "/api/v3/ecfa/tx/burn",
        json={
            "central_bank_wallet_id": cb,
            "source_wallet_id": source,
            "amount_ecfa": 50_000,
            "reference": "BURN_EXCESS",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["source_new_balance"] == 150_000


# ── Transaction Status ────────────────────────────────────────────────

def test_tx_status_not_found():
    headers = _register_and_login("txstat1", "txstat1@t.com", "TxPass1!")
    resp = client.get(
        "/api/v3/ecfa/tx/status/nonexistent-tx-id",
        headers=headers,
    )
    assert resp.status_code == 404


def test_tx_status_idor_protection():
    """User C should not see User D's transaction."""
    headers_d = _register_and_login("txidorD", "txidorD@t.com", "TxPass1!")
    uid_d = _get_user_id("txidorD")
    cid = _get_country_id()
    sender_d = _create_wallet(uid_d, cid, balance=200_000.0)

    headers_d2 = _register_and_login("txidorD2", "txidorD2@t.com", "TxPass1!")
    uid_d2 = _get_user_id("txidorD2")
    recv_d = _create_wallet(uid_d2, cid, balance=0.0)

    # D sends to D2
    send_resp = client.post(
        "/api/v3/ecfa/tx/send",
        json={
            "sender_wallet_id": sender_d,
            "receiver_wallet_id": recv_d,
            "amount_ecfa": 10_000,
            "channel": "USSD",
            "pin": "1234",
        },
        headers=headers_d,
    )
    assert send_resp.status_code == 200
    tx_id = send_resp.json()["transaction_id"]

    # User C (unrelated) tries to view
    headers_c = _register_and_login("txidorC", "txidorC@t.com", "TxPass1!")
    resp = client.get(f"/api/v3/ecfa/tx/status/{tx_id}", headers=headers_c)
    assert resp.status_code == 403


# ── Transaction History ───────────────────────────────────────────────

def test_tx_history_empty():
    headers = _register_and_login("txhist1", "txhist1@t.com", "TxPass1!")
    uid = _get_user_id("txhist1")
    cid = _get_country_id()
    wid = _create_wallet(uid, cid, balance=0.0)

    resp = client.get(f"/api/v3/ecfa/tx/history/{wid}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["wallet_id"] == wid
    assert data["total_count"] == 0
    assert data["transactions"] == []


def test_tx_history_with_transactions():
    headers = _register_and_login("txhist2", "txhist2@t.com", "TxPass1!")
    uid = _get_user_id("txhist2")
    cid = _get_country_id()
    sender = _create_wallet(uid, cid, balance=500_000.0)

    headers2 = _register_and_login("txhist2r", "txhist2r@t.com", "TxPass1!")
    uid2 = _get_user_id("txhist2r")
    receiver = _create_wallet(uid2, cid, balance=0.0)

    # Make 3 transactions
    for _ in range(3):
        client.post(
            "/api/v3/ecfa/tx/send",
            json={
                "sender_wallet_id": sender,
                "receiver_wallet_id": receiver,
                "amount_ecfa": 10_000,
                "channel": "USSD",
                "pin": "1234",
            },
            headers=headers,
        )

    resp = client.get(f"/api/v3/ecfa/tx/history/{sender}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 3
    assert len(data["transactions"]) == 3
    # All should be SENT direction
    for tx in data["transactions"]:
        assert tx["direction"] == "SENT"


def test_tx_history_pagination():
    headers = _register_and_login("txhist3", "txhist3@t.com", "TxPass1!")
    uid = _get_user_id("txhist3")
    cid = _get_country_id()
    sender = _create_wallet(uid, cid, balance=1_000_000.0)

    headers2 = _register_and_login("txhist3r", "txhist3r@t.com", "TxPass1!")
    uid2 = _get_user_id("txhist3r")
    receiver = _create_wallet(uid2, cid, balance=0.0)

    # Make 5 transactions
    for _ in range(5):
        client.post(
            "/api/v3/ecfa/tx/send",
            json={
                "sender_wallet_id": sender,
                "receiver_wallet_id": receiver,
                "amount_ecfa": 5_000,
                "channel": "USSD",
                "pin": "1234",
            },
            headers=headers,
        )

    # Page 1, size 2
    resp = client.get(
        f"/api/v3/ecfa/tx/history/{sender}?page=1&page_size=2",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 5
    assert len(data["transactions"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_tx_history_wrong_owner():
    """User cannot view another user's wallet history."""
    headers_a = _register_and_login("txhistA", "txhistA@t.com", "TxPass1!")
    headers_b = _register_and_login("txhistB", "txhistB@t.com", "TxPass1!")
    uid_b = _get_user_id("txhistB")
    cid = _get_country_id()
    wallet_b = _create_wallet(uid_b, cid)

    resp = client.get(f"/api/v3/ecfa/tx/history/{wallet_b}", headers=headers_a)
    assert resp.status_code == 403
