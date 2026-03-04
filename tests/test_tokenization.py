"""
Data Tokenization Test Suite — 25 tests covering all 3 pillars.

Uses the shared conftest.py: in-memory SQLite with StaticPool,
seeded countries, rate limiters disabled.
"""
import json
import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────

def _register_and_login(username="tokenuser", email="token@test.com", password="TokenPass1"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _topup(token: str, amount: float = 100.0):
    """Top up credits for testing."""
    client.post(
        "/api/payment/topup",
        json={"amount": amount},
        headers=_auth_header(token),
    )


# ── 1. Tokenization Status (Dashboard) ───────────────────────────────

def test_tokenization_status_requires_auth():
    resp = client.get("/api/v3/tokenization/status")
    assert resp.status_code in (401, 403)


def test_tokenization_status():
    token = _register_and_login("statuser", "status@test.com")
    _topup(token)
    resp = client.get("/api/v3/tokenization/status", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tokens" in data
    assert "tokens_by_pillar" in data
    assert "tokens_by_country" in data
    assert "total_paid_cfa" in data
    assert "countries_active" in data


# ── 2. Tokens by Country ─────────────────────────────────────────────

def test_get_tokens_by_country():
    token = _register_and_login("tokenlister", "tlist@test.com")
    _topup(token)
    resp = client.get("/api/v3/tokenization/tokens/NG", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_get_tokens_invalid_country():
    token = _register_and_login("tokenlister2", "tlist2@test.com")
    _topup(token)
    resp = client.get("/api/v3/tokenization/tokens/XX", headers=_auth_header(token))
    assert resp.status_code == 404


# ── 3. Citizen Activities ────────────────────────────────────────────

def test_get_activities():
    token = _register_and_login("actuser", "act@test.com")
    _topup(token)
    resp = client.get("/api/v3/tokenization/activities/BF", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ── 4. Business Data Submission ──────────────────────────────────────

def test_business_submit():
    token = _register_and_login("bizuser", "biz@test.com")
    _topup(token)
    resp = client.post(
        "/api/v3/tokenization/business/submit",
        json={
            "country_code": "CI",
            "business_type": "TRADING",
            "metric_type": "SALES_VOLUME",
            "metrics": json.dumps({"declared_value_cfa": 2_000_000}),
            "period_date": "2026-03-01",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "B"
    assert data["credit_rate_pct"] == 10.0
    assert data["credit_earned_cfa"] == 200_000.0  # 10% of 2M


def test_business_submit_tier_a():
    token = _register_and_login("biztiera", "biztiera@test.com")
    _topup(token)
    resp = client.post(
        "/api/v3/tokenization/business/submit",
        json={
            "country_code": "NG",
            "business_type": "MANUFACTURING",
            "metric_type": "CUSTOMS_DECLARATION",
            "metrics": json.dumps({"declared_value_cfa": 1_000_000}),
            "period_date": "2026-03-01",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "A"
    assert data["credit_rate_pct"] == 15.0
    assert data["credit_earned_cfa"] == 150_000.0


def test_business_submit_tier_c():
    token = _register_and_login("biztierc", "biztierc@test.com")
    _topup(token)
    resp = client.post(
        "/api/v3/tokenization/business/submit",
        json={
            "country_code": "GH",
            "business_type": "SERVICES",
            "metric_type": "EMPLOYEE_COUNT",
            "metrics": json.dumps({"declared_value_cfa": 500_000}),
            "period_date": "2026-03-01",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "C"
    assert data["credit_rate_pct"] == 5.0
    assert data["credit_earned_cfa"] == 25_000.0


def test_business_tax_credit_cap():
    """Tax credit capped at 5M CFA per business per year."""
    token = _register_and_login("capper", "cap@test.com")
    _topup(token, 500.0)

    # First submission: 40M × 15% = 6M → capped to 5M
    resp = client.post(
        "/api/v3/tokenization/business/submit",
        json={
            "country_code": "SN",
            "business_type": "TRADING",
            "metric_type": "CUSTOMS_DECLARATION",
            "metrics": json.dumps({"declared_value_cfa": 40_000_000}),
            "period_date": "2026-03-01",
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["credit_earned_cfa"] == 5_000_000.0  # capped

    # Second submission: cap already reached → 0
    resp2 = client.post(
        "/api/v3/tokenization/business/submit",
        json={
            "country_code": "SN",
            "business_type": "TRADING",
            "metric_type": "BANK_STATEMENT",
            "metrics": json.dumps({"declared_value_cfa": 10_000_000}),
            "period_date": "2026-03-02",
        },
        headers=_auth_header(token),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["credit_earned_cfa"] == 0  # cap exhausted


# ── 5. Business Credits ──────────────────────────────────────────────

def test_get_business_credits():
    token = _register_and_login("creduser", "cred@test.com")
    _topup(token)
    resp = client.get(
        "/api/v3/tokenization/business/CI/credits",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── 6. Contract Milestones ───────────────────────────────────────────

def test_get_contracts():
    token = _register_and_login("contuser", "cont@test.com")
    _topup(token)
    resp = client.get(
        "/api/v3/tokenization/contracts/BF",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ── 7. Milestone Verification (FREE) ─────────────────────────────────

def test_verify_milestone_not_found():
    token = _register_and_login("verifier", "verify@test.com")
    resp = client.post(
        "/api/v3/tokenization/contracts/nonexistent-contract/verify",
        params={"milestone_number": 1},
        json={
            "verifier_type": "CITIZEN",
            "vote": "APPROVE",
            "completion_pct": 80.0,
        },
        headers=_auth_header(token),
    )
    assert resp.status_code == 404


# ── 8. Workers ───────────────────────────────────────────────────────

def test_get_workers():
    token = _register_and_login("wrkuser", "wrk@test.com")
    _topup(token)
    resp = client.get(
        "/api/v3/tokenization/workers/NG",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ── 9. Payments ──────────────────────────────────────────────────────

def test_get_payments():
    token = _register_and_login("payuser", "pay@test.com")
    _topup(token)
    resp = client.get(
        "/api/v3/tokenization/payments/CI",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── 10. Aggregation ──────────────────────────────────────────────────

def test_trigger_aggregation():
    token = _register_and_login("agguser", "agg@test.com")
    _topup(token)
    resp = client.post(
        "/api/v3/tokenization/aggregate/calculate",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("completed", "no_data")


# ── 11. Engine Unit Tests ────────────────────────────────────────────

def test_engine_citizen_token():
    """Test TokenizationEngine.create_citizen_token directly."""
    from tests.conftest import TestingSessionLocal
    from src.engines.tokenization_engine import TokenizationEngine

    db = TestingSessionLocal()
    try:
        engine = TokenizationEngine(db)
        result = engine.create_citizen_token(
            country_code="BF",
            phone_hash="a" * 64,
            activity_type="FARM_WORK",
            location_name="Ouagadougou",
            location_region="Centre",
        )
        assert result["status"] == "created"
        assert result["payment_cfa"] == 100
        assert result["activity_type"] == "FARM_WORK"
        assert "token_id" in result
    finally:
        db.close()


def test_engine_citizen_token_update():
    """Second report from same person/type/location/date updates existing."""
    from tests.conftest import TestingSessionLocal
    from src.engines.tokenization_engine import TokenizationEngine

    db = TestingSessionLocal()
    try:
        engine = TokenizationEngine(db)
        # First report
        r1 = engine.create_citizen_token(
            country_code="CI",
            phone_hash="b" * 64,
            activity_type="MARKET_PRICE",
            location_name="Abidjan",
            quantity_value=500.0,
        )
        assert r1["status"] == "created"
        assert r1["payment_cfa"] == 75

        # Second report same day → updates (no double pay)
        r2 = engine.create_citizen_token(
            country_code="CI",
            phone_hash="b" * 64,
            activity_type="MARKET_PRICE",
            location_name="Abidjan",
            quantity_value=520.0,
        )
        assert r2["status"] == "updated"
        assert r2["payment_cfa"] == 0  # no double pay
    finally:
        db.close()


def test_engine_worker_not_registered():
    """Worker check-in fails if worker not registered."""
    from tests.conftest import TestingSessionLocal
    from src.engines.tokenization_engine import TokenizationEngine

    db = TestingSessionLocal()
    try:
        engine = TokenizationEngine(db)
        result = engine.create_worker_checkin(
            worker_phone_hash="c" * 64,
            contract_id="test-contract-001",
            country_code="GH",
        )
        assert "error" in result
        assert "not registered" in result["error"]
    finally:
        db.close()


def test_cross_validation():
    """3+ independent reporters → cross-validated with confidence boost."""
    from tests.conftest import TestingSessionLocal
    from src.engines.tokenization_engine import TokenizationEngine
    from src.engines.tokenization_engine import CrossValidationEngine
    from datetime import date

    db = TestingSessionLocal()
    try:
        engine = TokenizationEngine(db)

        # 4 independent reporters in same region
        for i in range(4):
            engine.create_citizen_token(
                country_code="SN",
                phone_hash=f"{chr(100 + i)}" * 64,
                activity_type="CROP_YIELD",
                location_name="Thiès",
                location_region="Thiès",
                quantity_value=400 + i * 10,
            )

        validator = CrossValidationEngine(db)
        from src.database.models import Country
        sn = db.query(Country).filter(Country.code == "SN").first()
        result = validator.validate_citizen_reports(sn.id, date.today(), "CROP_YIELD")

        assert result["validated"] >= 4
        assert result["total"] >= 4
    finally:
        db.close()


def test_payment_pricing():
    """Verify activity payment amounts."""
    from src.engines.tokenization_engine import TokenizationEngine

    assert TokenizationEngine.price_token("ACTIVITY_REPORT", "FARM_WORK") == 100
    assert TokenizationEngine.price_token("ACTIVITY_REPORT", "HEALTH_FACILITY") == 200
    assert TokenizationEngine.price_token("ACTIVITY_REPORT", "WEATHER") == 50
    assert TokenizationEngine.price_token("WORKER_CHECKIN") == 2500
    assert TokenizationEngine.price_token("MILESTONE_VERIFY") == 50


# ── 12. USSD Menu Tests ──────────────────────────────────────────────

def test_ussd_main_menu_shows_tokenization():
    """USSD main menu should show options 7, 8, 9."""
    from tests.conftest import TestingSessionLocal
    from src.engines.ussd_engine import USSDMenuEngine

    db = TestingSessionLocal()
    try:
        engine = USSDMenuEngine(db)
        response, stype = engine.process_callback(
            session_id="test-sess-001",
            service_code="*384*WASI#",
            phone_number="+22607000001",
            text="",
        )
        assert "7. Activité quotidienne" in response
        assert "8. Données entreprise" in response
        assert "9. Faso Meabo check-in" in response
    finally:
        db.close()


def test_ussd_option7_activity_menu():
    """Option 7 shows activity type menu."""
    from tests.conftest import TestingSessionLocal
    from src.engines.ussd_engine import USSDMenuEngine

    db = TestingSessionLocal()
    try:
        engine = USSDMenuEngine(db)
        response, stype = engine.process_callback(
            session_id="test-sess-002",
            service_code="*384*WASI#",
            phone_number="+22607000002",
            text="7",
        )
        assert "Activité quotidienne" in response
        assert "Travaux agricoles" in response
        assert stype == "ACTIVITY_DECLARATION"
    finally:
        db.close()


def test_ussd_option8_business_menu():
    """Option 8 shows business type menu."""
    from tests.conftest import TestingSessionLocal
    from src.engines.ussd_engine import USSDMenuEngine

    db = TestingSessionLocal()
    try:
        engine = USSDMenuEngine(db)
        response, stype = engine.process_callback(
            session_id="test-sess-003",
            service_code="*384*WASI#",
            phone_number="+22607000003",
            text="8",
        )
        assert "entreprise" in response.lower()
        assert stype == "BUSINESS_SUBMISSION"
    finally:
        db.close()


def test_ussd_option9_checkin_menu():
    """Option 9 shows worker check-in prompt."""
    from tests.conftest import TestingSessionLocal
    from src.engines.ussd_engine import USSDMenuEngine

    db = TestingSessionLocal()
    try:
        engine = USSDMenuEngine(db)
        response, stype = engine.process_callback(
            session_id="test-sess-004",
            service_code="*384*WASI#",
            phone_number="+22607000004",
            text="9",
        )
        assert "Faso Meabo" in response
        assert "contrat" in response.lower()
        assert stype == "WORKER_CHECKIN"
    finally:
        db.close()
