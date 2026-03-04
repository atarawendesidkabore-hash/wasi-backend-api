"""
Test Suite — Alert/Webhook System

Tests CRUD routes, delivery history, status dashboard, engine logic,
and condition checking.
"""
import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from src.main import app
from src.database.alert_models import AlertRule, AlertDelivery
from src.database.models import User, Country, CountryIndex
from src.engines.alert_engine import _check_condition, generate_webhook_secret
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────────

def _register_and_login(username="alertuser", email="alert@test.com", password="Pass12345"):
    """Register a user, top up credits, and return auth headers."""
    client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    # Give user enough credits for testing
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    if user:
        user.x402_balance = 500.0
    db.commit()
    db.close()

    resp = client.post("/api/auth/login", data={
        "username": username, "password": password,
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_rule(headers, **overrides):
    """Create a rule via API and return the response JSON."""
    payload = {
        "event_source": "WASI_INDEX",
        "condition": "DROP_GT",
        "threshold_value": 5.0,
        "webhook_url": "http://localhost:9999/hook",
        "cooldown_seconds": 60,
    }
    payload.update(overrides)
    resp = client.post("/api/v3/alerts/rules", json=payload, headers=headers)
    return resp


# ── Auth requirement ─────────────────────────────────────────────────

def test_rules_requires_auth():
    resp = client.get("/api/v3/alerts/rules")
    assert resp.status_code == 401


def test_status_requires_auth():
    resp = client.get("/api/v3/alerts/status")
    assert resp.status_code == 401


# ── Rule CRUD ────────────────────────────────────────────────────────

def test_create_rule():
    headers = _register_and_login("create1", "create1@test.com")
    resp = _create_rule(headers, name="Test WASI Drop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_source"] == "WASI_INDEX"
    assert data["condition"] == "DROP_GT"
    assert data["is_active"] is True
    # webhook_secret should be returned on creation
    assert "webhook_secret" in data
    assert len(data["webhook_secret"]) == 64


def test_create_rule_invalid_event_source():
    headers = _register_and_login("create2", "create2@test.com")
    resp = _create_rule(headers, event_source="INVALID")
    assert resp.status_code == 422


def test_create_rule_invalid_condition():
    headers = _register_and_login("create3", "create3@test.com")
    resp = _create_rule(headers, condition="INVALID")
    assert resp.status_code == 422


def test_list_rules():
    headers = _register_and_login("list1", "list1@test.com")
    _create_rule(headers, name="Rule A")
    _create_rule(headers, name="Rule B", event_source="NEWS_EVENT", condition="ANY")
    resp = client.get("/api/v3/alerts/rules", headers=headers)
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 2
    # webhook_secret should NOT be in list responses
    for r in rules:
        assert "webhook_secret" not in r


def test_get_single_rule():
    headers = _register_and_login("get1", "get1@test.com")
    create_resp = _create_rule(headers, name="Single")
    rule_id = create_resp.json()["id"]
    resp = client.get(f"/api/v3/alerts/rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Single"


def test_get_rule_not_found():
    headers = _register_and_login("get2", "get2@test.com")
    resp = client.get("/api/v3/alerts/rules/9999", headers=headers)
    assert resp.status_code == 404


def test_update_rule():
    headers = _register_and_login("upd1", "upd1@test.com")
    create_resp = _create_rule(headers, name="Original")
    rule_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/v3/alerts/rules/{rule_id}",
        json={"name": "Updated", "threshold_value": 10.0},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"
    assert resp.json()["threshold_value"] == 10.0


def test_delete_rule():
    headers = _register_and_login("del1", "del1@test.com")
    create_resp = _create_rule(headers, name="ToDelete")
    rule_id = create_resp.json()["id"]

    resp = client.delete(f"/api/v3/alerts/rules/{rule_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["detail"] == "Alert rule deactivated."

    # Verify it's deactivated, not deleted
    get_resp = client.get(f"/api/v3/alerts/rules/{rule_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


def test_delete_rule_not_found():
    headers = _register_and_login("del2", "del2@test.com")
    resp = client.delete("/api/v3/alerts/rules/9999", headers=headers)
    assert resp.status_code == 404


# ── Max rules limit ──────────────────────────────────────────────────

def test_max_rules_per_user():
    headers = _register_and_login("max1", "max1@test.com")
    # Create 20 rules (the maximum)
    for i in range(20):
        resp = _create_rule(headers, name=f"Rule {i}")
        assert resp.status_code == 200, f"Rule {i} failed: {resp.text}"

    # The 21st should fail
    resp = _create_rule(headers, name="Rule 21 overflow")
    assert resp.status_code == 400
    assert "Maximum" in resp.json()["detail"]


# ── Delivery history ─────────────────────────────────────────────────

def test_deliveries_empty():
    headers = _register_and_login("dlv1", "dlv1@test.com")
    resp = client.get("/api/v3/alerts/deliveries", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_delivery_detail_not_found():
    headers = _register_and_login("dlv2", "dlv2@test.com")
    resp = client.get("/api/v3/alerts/deliveries/9999", headers=headers)
    assert resp.status_code == 404


# ── Status dashboard ─────────────────────────────────────────────────

def test_status_dashboard():
    headers = _register_and_login("stat1", "stat1@test.com")
    _create_rule(headers, name="Status Test")
    resp = client.get("/api/v3/alerts/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rules"] == 1
    assert data["active_rules"] == 1
    assert data["total_deliveries"] == 0
    assert data["deliveries_last_24h"] == 0
    assert data["credits_spent_last_24h"] == 0.0
    assert data["failed_deliveries_last_24h"] == 0


# ── Isolation: users can't see each other's rules ────────────────────

def test_rule_isolation():
    headers_a = _register_and_login("isoA", "isoA@test.com")
    headers_b = _register_and_login("isoB", "isoB@test.com")

    create_resp = _create_rule(headers_a, name="User A Rule")
    rule_id = create_resp.json()["id"]

    # User B can't access User A's rule
    resp = client.get(f"/api/v3/alerts/rules/{rule_id}", headers=headers_b)
    assert resp.status_code == 404

    # User B sees an empty list
    resp = client.get("/api/v3/alerts/rules", headers=headers_b)
    assert resp.status_code == 200
    assert len(resp.json()) == 0


# ── Engine unit tests ────────────────────────────────────────────────

def test_check_condition_drop_gt():
    assert _check_condition("DROP_GT", -6.0, 50.0, 5.0) is True
    assert _check_condition("DROP_GT", -4.0, 50.0, 5.0) is False
    assert _check_condition("DROP_GT", 6.0, 50.0, 5.0) is False


def test_check_condition_rise_gt():
    assert _check_condition("RISE_GT", 6.0, 50.0, 5.0) is True
    assert _check_condition("RISE_GT", 4.0, 50.0, 5.0) is False
    assert _check_condition("RISE_GT", -6.0, 50.0, 5.0) is False


def test_check_condition_change_gt():
    assert _check_condition("CHANGE_GT", 6.0, 50.0, 5.0) is True
    assert _check_condition("CHANGE_GT", -6.0, 50.0, 5.0) is True
    assert _check_condition("CHANGE_GT", 3.0, 50.0, 5.0) is False


def test_check_condition_below():
    assert _check_condition("BELOW", 0.0, 40.0, 50.0) is True
    assert _check_condition("BELOW", 0.0, 60.0, 50.0) is False


def test_check_condition_above():
    assert _check_condition("ABOVE", 0.0, 60.0, 50.0) is True
    assert _check_condition("ABOVE", 0.0, 40.0, 50.0) is False


def test_check_condition_any():
    assert _check_condition("ANY", 0.0, 0.0, 0.0) is True
    assert _check_condition("ANY", 999.0, 999.0, None) is True


def test_check_condition_no_threshold():
    assert _check_condition("DROP_GT", -10.0, 50.0, None) is False
    assert _check_condition("RISE_GT", 10.0, 50.0, None) is False


def test_generate_webhook_secret():
    secret = generate_webhook_secret()
    assert len(secret) == 64
    # Should be hex string
    int(secret, 16)


# ── Test webhook endpoint ────────────────────────────────────────────

@patch("src.engines.alert_engine.httpx.post")
def test_test_webhook(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    headers = _register_and_login("testhook1", "testhook1@test.com")
    create_resp = _create_rule(headers, name="Hook Test")
    rule_id = create_resp.json()["id"]

    resp = client.post(f"/api/v3/alerts/rules/{rule_id}/test", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"
    mock_post.assert_called_once()
