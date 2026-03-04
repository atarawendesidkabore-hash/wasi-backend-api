"""
USSD Integration Test Suite — covers HTTP endpoints, multi-step flows,
provider management, session upsert, input validation, and aggregation.

Uses the shared conftest.py: in-memory SQLite with StaticPool,
seeded countries, rate limiters disabled.
"""
import hashlib
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User
from src.database.ussd_models import USSDConsent
from src.engines.ussd_engine import _hash_phone
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────

_user_counter = 0


def _unique_user():
    global _user_counter
    _user_counter += 1
    return f"ussduser{_user_counter}", f"ussd{_user_counter}@test.com"


def _register_and_login(username=None, email=None, password="UssdPass1", is_admin=False):
    if username is None:
        username, email = _unique_user()
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
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _topup(token: str, amount: float = 500.0):
    client.post("/api/payment/topup", json={"amount": amount}, headers=_auth_header(token))


def _seed_consent(phone_number: str):
    """Pre-create a consent record so the USSD engine skips the consent gate."""
    db = TestingSessionLocal()
    ph = _hash_phone(phone_number)
    existing = db.query(USSDConsent).filter(USSDConsent.phone_hash == ph).first()
    if not existing:
        db.add(USSDConsent(phone_hash=ph, consented=True))
        db.commit()
    db.close()


def _register_admin():
    """Register admin user and return token."""
    token = _register_and_login("ussdroot", "ussdroot@test.com", is_admin=True)
    _topup(token, 5000.0)
    return token


def _seed_provider(admin_token: str, code="TEST_MNO", name="Test MNO"):
    """Register a USSD provider and return the response."""
    resp = client.post(
        "/api/v2/ussd/providers",
        json={
            "provider_code": code,
            "provider_name": name,
            "country_codes": "CI,BF,NG",
            "ussd_shortcode": "*384*999#",
        },
        headers=_auth_header(admin_token),
    )
    return resp


# ═══════════════════════════════════════════════════════════════════════
# A. Provider Management
# ═══════════════════════════════════════════════════════════════════════

def test_register_provider_returns_api_key():
    """Registration response must include the plaintext api_key (Bug #3 fix)."""
    admin = _register_admin()
    resp = _seed_provider(admin, "ORANGE_CI", "Orange CI")
    assert resp.status_code == 200
    data = resp.json()
    assert "api_key" in data, f"api_key missing from response: {data.keys()}"
    assert len(data["api_key"]) > 10
    assert data["provider_code"] == "ORANGE_CI"


def test_register_provider_duplicate_409():
    admin = _register_admin()
    _seed_provider(admin, "DUP_MNO", "Dup MNO")
    resp = _seed_provider(admin, "DUP_MNO", "Dup MNO")
    assert resp.status_code == 409


def test_list_providers():
    admin = _register_admin()
    _seed_provider(admin, "LIST_MNO", "List MNO")
    resp = client.get("/api/v2/ussd/providers", headers=_auth_header(admin))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_providers_requires_auth():
    resp = client.get("/api/v2/ussd/providers")
    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════
# B. USSD Callback — multi-step flows
# ═══════════════════════════════════════════════════════════════════════

def _setup_callback():
    """Create admin + provider, return the provider API key header."""
    admin = _register_admin()
    resp = _seed_provider(admin, "CB_MNO", "Callback MNO")
    api_key = resp.json()["api_key"]
    return {"X-Provider-Key": api_key}


def test_callback_main_menu():
    headers = _setup_callback()
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": "cb-main-001",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607100001",
        "text": "",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "WASI" in data["response"] or "1." in data["response"]


def test_callback_requires_provider_key():
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": "cb-no-key",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607100002",
        "text": "",
    })
    # Header(...) makes X-Provider-Key required → 422 if missing
    assert resp.status_code in (401, 403, 422)


def test_callback_invalid_provider_key():
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": "cb-bad-key",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607100003",
        "text": "",
    }, headers={"X-Provider-Key": "invalid-key-12345"})
    assert resp.status_code in (401, 403)


def test_callback_session_upsert():
    """Same session_id with 2 callbacks must NOT crash (Bug #1 fix)."""
    headers = _setup_callback()
    # First callback — main menu
    resp1 = client.post("/api/v2/ussd/callback", json={
        "sessionId": "upsert-001",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607100010",
        "text": "",
    }, headers=headers)
    assert resp1.status_code == 200

    # Second callback — same session_id, select option 1
    resp2 = client.post("/api/v2/ussd/callback", json={
        "sessionId": "upsert-001",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607100010",
        "text": "1",
    }, headers=headers)
    assert resp2.status_code == 200, f"Session upsert failed: {resp2.text}"


def test_callback_commodity_flow():
    """Full option 1 flow: select commodity → enter price → confirm."""
    headers = _setup_callback()
    phone = "+22607200001"
    _seed_consent(phone)
    sid = "commodity-flow-001"

    # Step 1: select option 1 (commodity)
    r1 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "1",
    }, headers=headers)
    assert r1.status_code == 200
    assert "produit" in r1.json()["response"].lower()

    # Step 2: select first commodity
    r2 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "1*1",
    }, headers=headers)
    assert r2.status_code == 200
    assert "prix" in r2.json()["response"].lower()

    # Step 3: enter price
    r3 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "1*1*5000",
    }, headers=headers)
    assert r3.status_code == 200
    assert "confirmer" in r3.json()["response"].lower()

    # Step 4: confirm
    r4 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "1*1*5000*1",
    }, headers=headers)
    assert r4.status_code == 200
    assert "merci" in r4.json()["response"].lower() or "enregistr" in r4.json()["response"].lower()


def test_callback_invalid_direction():
    """Invalid trade direction choice returns error (Bug #4 fix)."""
    headers = _setup_callback()
    phone = "+22607200002"
    sid = "dir-err-001"

    # Trade menu: border post 1, goods category 1, invalid direction 9
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "2*1*1*9",
    }, headers=headers)
    assert resp.status_code == 200
    assert "invalide" in resp.json()["response"].lower() or "END" in resp.json()["response"]


def test_callback_price_out_of_range():
    """Commodity price > 10M returns error (Bug #5 fix)."""
    headers = _setup_callback()
    phone = "+22607200003"
    sid = "price-range-001"

    # Commodity menu: product 1, price 99999999 (out of range)
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "1*1*99999999",
    }, headers=headers)
    assert resp.status_code == 200
    assert "limites" in resp.json()["response"].lower() or "END" in resp.json()["response"]


def test_callback_delay_out_of_range():
    """Port delay > 720h returns error (Bug #5 fix)."""
    headers = _setup_callback()
    phone = "+22607200004"
    sid = "delay-range-001"

    # Port menu: port 1, congestion 1, delay 9999
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "3*1*1*9999",
    }, headers=headers)
    assert resp.status_code == 200
    assert "limites" in resp.json()["response"].lower() or "END" in resp.json()["response"]


def test_callback_option7_full_flow():
    """Full option 7 (activity declaration) flow."""
    headers = _setup_callback()
    phone = "+22607300001"
    sid = "opt7-full-001"

    # Select option 7
    r1 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "7",
    }, headers=headers)
    assert r1.status_code == 200

    # Select activity type 1
    r2 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "7*1",
    }, headers=headers)
    assert r2.status_code == 200

    # Enter location
    r3 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "7*1*Abidjan",
    }, headers=headers)
    assert r3.status_code == 200

    # Enter value
    r4 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "7*1*Abidjan*500",
    }, headers=headers)
    assert r4.status_code == 200

    # Confirm
    r5 = client.post("/api/v2/ussd/callback", json={
        "sessionId": sid, "serviceCode": "*384*WASI#",
        "phoneNumber": phone, "text": "7*1*Abidjan*500*1",
    }, headers=headers)
    assert r5.status_code == 200


def test_callback_ecfa_option6_menu():
    """Option 6 shows eCFA wallet menu."""
    headers = _setup_callback()
    _seed_consent("+22607400001")
    resp = client.post("/api/v2/ussd/callback", json={
        "sessionId": "ecfa-001",
        "serviceCode": "*384*WASI#",
        "phoneNumber": "+22607400001",
        "text": "6",
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "eCFA" in data["response"] or "Solde" in data["response"] or "wallet" in data["response"].lower()


# ═══════════════════════════════════════════════════════════════════════
# C. Mobile Money Push
# ═══════════════════════════════════════════════════════════════════════

def test_push_mobile_money_requires_key():
    resp = client.post("/api/v2/ussd/mobile-money/push", json={
        "country_code": "CI",
        "provider_code": "ORANGE",
        "period_date": "2026-03-01",
        "transaction_count": 1000,
        "total_value_local": 50000000,
        "local_currency": "XOF",
        "fx_rate_usd": 610.0,
    })
    # Header(...) makes X-Provider-Key required → 422 if missing
    assert resp.status_code in (401, 403, 422)


def test_push_mobile_money_success():
    headers = _setup_callback()
    resp = client.post("/api/v2/ussd/mobile-money/push", json={
        "country_code": "CI",
        "provider_code": "CB_MNO",
        "period_date": "2026-03-01",
        "transaction_count": 1000,
        "total_value_local": 50000000,
        "local_currency": "XOF",
        "fx_rate_usd": 610.0,
    }, headers=headers)
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# D. Authenticated Query Endpoints
# ═══════════════════════════════════════════════════════════════════════

def test_status_requires_auth():
    resp = client.get("/api/v2/ussd/status")
    assert resp.status_code in (401, 403)


def test_status_success():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/status", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "total_providers" in data


def test_aggregate_all():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/aggregate/all", headers=_auth_header(token))
    assert resp.status_code == 200


def test_aggregate_country():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/aggregate/CI", headers=_auth_header(token))
    assert resp.status_code == 200


def test_aggregate_summary():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/aggregate/summary", headers=_auth_header(token))
    assert resp.status_code == 200


def test_aggregate_calculate():
    token = _register_and_login()
    _topup(token, 1000.0)
    resp = client.post("/api/v2/ussd/aggregate/calculate", headers=_auth_header(token))
    assert resp.status_code == 200


def test_commodity_reports():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/commodity/CI", headers=_auth_header(token))
    assert resp.status_code == 200


def test_trade_declarations():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/trade/CI", headers=_auth_header(token))
    assert resp.status_code == 200


def test_port_clearances():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/port/CI", headers=_auth_header(token))
    assert resp.status_code == 200


def test_mobile_money_flows():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/mobile-money/CI", headers=_auth_header(token))
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# E. Route Endpoints (Bug #2 fix verification)
# ═══════════════════════════════════════════════════════════════════════

def test_route_reports_by_country():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/ussd/routes/CI", headers=_auth_header(token))
    assert resp.status_code == 200
    assert "reports" in resp.json()


def test_corridor_reports_route_ordering():
    """Corridor route must NOT match as {country_code} (Bug #2 fix)."""
    token = _register_and_login()
    _topup(token)
    resp = client.get(
        "/api/v2/ussd/routes/corridor/ABIDJAN-OUAGA",
        headers=_auth_header(token),
    )
    # Should reach corridor handler, not country handler
    # 404 is OK (no data), 422 would mean it hit the wrong route
    assert resp.status_code in (200, 404), f"Route ordering bug: got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════
# F. Aggregation Engine
# ═══════════════════════════════════════════════════════════════════════

def test_aggregator_weights_sum():
    """USSDDataAggregator weights must sum to 1.0."""
    from src.engines.ussd_engine import USSDDataAggregator
    total = sum(USSDDataAggregator.WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, not 1.0"


def test_aggregator_empty_data():
    """Aggregation with no data should return no_data or 0 records."""
    from tests.conftest import TestingSessionLocal
    from src.tasks.ussd_aggregation import run_ussd_aggregation

    db = TestingSessionLocal()
    try:
        result = run_ussd_aggregation(db)
        assert result.get("status") in ("completed", "no_data") or result.get("total_data_points", 0) == 0
    finally:
        db.close()
