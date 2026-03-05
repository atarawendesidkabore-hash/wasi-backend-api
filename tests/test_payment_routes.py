"""
HTTP route tests for X402 Payment endpoints — /api/payment/

Tests:
  - POST /api/payment/topup (admin-only credit top-up)
  - GET  /api/payment/status (balance + recent transactions)
"""
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User
from tests.conftest import TestingSessionLocal

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────

def _register_and_login(username, email, password="PayPass1!", is_admin=False):
    client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    if is_admin:
        db = TestingSessionLocal()
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.is_admin = True
            db.commit()
        db.close()
    resp = client.post("/api/auth/login", data={
        "username": username, "password": password,
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Auth Guard Tests ──────────────────────────────────────────────────

def test_topup_requires_auth():
    resp = client.post("/api/payment/topup", json={
        "amount": 100.0, "reference_id": "ref-001",
    })
    assert resp.status_code == 401


def test_topup_requires_admin():
    headers = _register_and_login("paynonadm", "paynonadm@test.com", is_admin=False)
    resp = client.post("/api/payment/topup", json={
        "amount": 100.0, "reference_id": "ref-002",
    }, headers=headers)
    assert resp.status_code == 403


def test_status_requires_auth():
    resp = client.get("/api/payment/status")
    assert resp.status_code == 401


# ── Functional Tests ──────────────────────────────────────────────────

def test_topup_success():
    headers = _register_and_login("payadm1", "payadm1@test.com", is_admin=True)

    # Get initial balance
    status_before = client.get("/api/payment/status", headers=headers).json()
    balance_before = status_before["balance"]

    resp = client.post("/api/payment/topup", json={
        "amount": 500.0, "reference_id": "topup-test-001",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == balance_before + 500.0
    assert len(data["recent_transactions"]) >= 1
    assert data["recent_transactions"][0]["transaction_type"] == "topup"
    assert data["recent_transactions"][0]["amount"] == 500.0


def test_topup_idempotency():
    headers = _register_and_login("payadm2", "payadm2@test.com", is_admin=True)

    # First topup succeeds
    resp1 = client.post("/api/payment/topup", json={
        "amount": 100.0, "reference_id": "idempotent-ref-001",
    }, headers=headers)
    assert resp1.status_code == 200

    # Duplicate reference_id → 409
    resp2 = client.post("/api/payment/topup", json={
        "amount": 200.0, "reference_id": "idempotent-ref-001",
    }, headers=headers)
    assert resp2.status_code == 409


def test_status_returns_balance_and_transactions():
    headers = _register_and_login("payadm3", "payadm3@test.com", is_admin=True)

    # Do a topup first
    client.post("/api/payment/topup", json={
        "amount": 250.0, "reference_id": "status-test-001",
    }, headers=headers)

    resp = client.get("/api/payment/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data
    assert "balance" in data
    assert "tier" in data
    assert isinstance(data["recent_transactions"], list)
    assert len(data["recent_transactions"]) >= 1
