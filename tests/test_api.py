"""
WASI Backend API — Test Suite

Uses an in-memory SQLite database to isolate tests from the dev database.
Shared setup is in conftest.py (DB override, rate limiter disable, seed).
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Health ───────────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert "version" in data


# ── Auth: register ───────────────────────────────────────────────────────────

def test_register_user():
    response = client.post(
        "/api/auth/register",
        json={"username": "testuser", "email": "test@example.com", "password": "securepass123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["x402_balance"] == 10.0
    assert data["tier"] == "free"
    assert data["is_active"] is True
    assert "hashed_password" not in data


def test_register_duplicate_username():
    payload = {"username": "dup", "email": "dup@example.com", "password": "pass12345"}
    client.post("/api/auth/register", json=payload)
    response = client.post(
        "/api/auth/register",
        json={**payload, "email": "dup2@example.com"},
    )
    assert response.status_code == 409


def test_register_duplicate_email():
    client.post(
        "/api/auth/register",
        json={"username": "user1", "email": "shared@example.com", "password": "pass12345"},
    )
    response = client.post(
        "/api/auth/register",
        json={"username": "user2", "email": "shared@example.com", "password": "pass12345"},
    )
    assert response.status_code == 409


# ── Auth: login ──────────────────────────────────────────────────────────────

def _register_and_login(username="admin", email="admin@test.com", password="adminpass1"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_success():
    client.post(
        "/api/auth/register",
        json={"username": "loginuser", "email": "login@test.com", "password": "testpass456"},
    )
    response = client.post(
        "/api/auth/login",
        data={"username": "loginuser", "password": "testpass456"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password():
    client.post(
        "/api/auth/register",
        json={"username": "wrongpw", "email": "wrong@test.com", "password": "rightpassword"},
    )
    response = client.post(
        "/api/auth/login",
        data={"username": "wrongpw", "password": "wrongpassword"},
    )
    assert response.status_code == 401


def test_login_unknown_user():
    response = client.post(
        "/api/auth/login",
        data={"username": "nobody", "password": "whatever"},
    )
    assert response.status_code == 401


def test_get_me():
    token = _register_and_login()
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "admin"


def test_protected_endpoint_without_token():
    response = client.get("/api/indices/latest")
    assert response.status_code == 401


# ── Payment ──────────────────────────────────────────────────────────────────

def test_topup_credits():
    token = _register_and_login()
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/payment/topup",
        json={"amount": 50.0, "reference_id": "ref-test-001"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 60.0  # 10 initial + 50 topup


def test_topup_duplicate_reference():
    token = _register_and_login(username="payer", email="payer@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"amount": 10.0, "reference_id": "ref-unique-abc"}
    client.post("/api/payment/topup", json=payload, headers=headers)
    response = client.post("/api/payment/topup", json=payload, headers=headers)
    assert response.status_code == 409


def test_payment_status():
    token = _register_and_login(username="statususer", email="status@test.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/payment/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert "tier" in data
    assert isinstance(data["recent_transactions"], list)


# ── Engine unit tests ─────────────────────────────────────────────────────────

def test_composite_engine_weights_sum_to_one():
    from src.engines.composite_engine import CompositeEngine
    engine = CompositeEngine()
    total = sum(engine.COUNTRY_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_composite_calculation_uniform_input():
    """If all countries report the same score X, the composite should equal X."""
    from src.engines.composite_engine import CompositeEngine
    from datetime import date
    engine = CompositeEngine()
    mock_indices = {code: 70.0 for code in engine.COUNTRY_WEIGHTS}
    result = engine.calculate_composite(mock_indices, date.today())
    assert abs(result["composite_value"] - 70.0) < 0.01
    assert result["countries_included"] == 16


def test_composite_engine_partial_countries():
    """With fewer countries, weights are re-normalized and composite stays in range."""
    from src.engines.composite_engine import CompositeEngine
    from datetime import date
    engine = CompositeEngine()
    partial = {"NG": 80.0, "CI": 60.0}
    result = engine.calculate_composite(partial, date.today())
    assert 0.0 <= result["composite_value"] <= 100.0
    assert result["countries_included"] == 2


def test_index_calculation_engine_output_in_range():
    from src.engines.index_calculation import IndexCalculationEngine
    engine = IndexCalculationEngine()
    data = {
        "ship_arrivals":          250,
        "cargo_tonnage":          2_500_000,
        "container_teu":          500_000,
        "port_efficiency_score":  75.0,
        "dwell_time_days":        7.0,
        "gdp_growth_pct":         5.0,
        "trade_value_usd":        25_000_000_000,
    }
    result = engine.calculate_country_index(data)
    assert 0.0 <= result["index_value"] <= 100.0
    for key in ("shipping_score", "trade_score", "infrastructure_score", "economic_score"):
        assert 0.0 <= result[key] <= 100.0


def test_index_calculation_engine_zero_inputs():
    """Zero inputs should produce a near-zero index, not an error."""
    from src.engines.index_calculation import IndexCalculationEngine
    engine = IndexCalculationEngine()
    result = engine.calculate_country_index({})
    assert 0.0 <= result["index_value"] <= 100.0


def test_index_calculation_engine_max_inputs():
    """Maximum inputs should produce a near-100 index."""
    from src.engines.index_calculation import IndexCalculationEngine
    engine = IndexCalculationEngine()
    data = {
        "ship_arrivals":          500,
        "cargo_tonnage":          5_000_000,
        "container_teu":          1_000_000,
        "port_efficiency_score":  100.0,
        "dwell_time_days":        1.0,
        "gdp_growth_pct":         15.0,
        "trade_value_usd":        50_000_000_000,
    }
    result = engine.calculate_country_index(data)
    assert result["index_value"] > 90.0


# ── v3.0 Country set tests ────────────────────────────────────────────────────

def test_v30_ecowas_countries_present():
    """Composite engine must use the ECOWAS-focused v3.0 country set."""
    from src.engines.composite_engine import CompositeEngine
    engine = CompositeEngine()
    expected = {"NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
                "NE", "MR", "GW", "SL", "LR", "GM", "CV"}
    assert set(engine.COUNTRY_WEIGHTS.keys()) == expected


def test_v30_removed_countries_absent():
    """Old East/Central African countries must NOT be in the composite weights."""
    from src.engines.composite_engine import CompositeEngine
    engine = CompositeEngine()
    removed = {"CM", "AO", "TZ", "KE", "MA", "MZ", "ET", "MG", "MU"}
    for code in removed:
        assert code not in engine.COUNTRY_WEIGHTS, f"{code} should have been removed in v3.0"


# ── Transport engine tests ────────────────────────────────────────────────────

def test_transport_engine_landlocked_no_maritime():
    """Landlocked country (BF) should have zero maritime weight."""
    from src.engines.transport_engine import TransportEngine
    engine = TransportEngine()
    result = engine.calculate_transport_composite(
        "BF", None,
        air_index=55.0, rail_index=57.0, road_index=48.0,
    )
    assert result["w_maritime"] == 0.0
    assert result["transport_composite"] > 0.0
    assert result["country_profile"] == "landlocked_rail"


def test_transport_engine_island_no_rail():
    """Island country (CV) should have zero rail weight."""
    from src.engines.transport_engine import TransportEngine
    engine = TransportEngine()
    result = engine.calculate_transport_composite(
        "CV", None,
        maritime_index=65.0, air_index=70.0,
    )
    assert result["w_rail"] == 0.0
    assert result["country_profile"] == "small_island"
    assert 0.0 <= result["transport_composite"] <= 100.0


def test_transport_engine_uniform_input():
    """Uniform inputs should give composite equal to that value."""
    from src.engines.transport_engine import TransportEngine
    engine = TransportEngine()
    result = engine.calculate_transport_composite(
        "NG", None,
        maritime_index=75.0, air_index=75.0, rail_index=75.0, road_index=75.0,
    )
    assert abs(result["transport_composite"] - 75.0) < 0.01


# ── ML Guardrails tests ───────────────────────────────────────────────────────

def test_guardrail_high_confidence_passes():
    from src.utils.ml_guardrails import check_data_quality
    result = check_data_quality(0.90)
    assert result["pass"] is True
    assert result["warn"] is False
    assert result["quality_label"] == "high"


def test_guardrail_low_confidence_warns():
    from src.utils.ml_guardrails import check_data_quality
    result = check_data_quality(0.45)
    assert result["pass"] is True
    assert result["warn"] is True
    assert result["quality_label"] == "low"


def test_guardrail_very_low_confidence_rejects():
    from src.utils.ml_guardrails import check_data_quality
    result = check_data_quality(0.25)
    assert result["pass"] is False
    assert result["quality_label"] == "rejected"


def test_guardrail_calibration_pulls_toward_fifty():
    """Low confidence should pull the calibrated score toward 50."""
    from src.utils.ml_guardrails import calibrate_score
    raw = 90.0
    cal = calibrate_score(raw, confidence=0.30)
    assert cal < raw, "Low-confidence calibration should pull score down toward 50"
    assert cal > 50.0  # should still be above 50 for a high raw score


def test_guardrail_human_review_bank_always_required():
    from src.utils.ml_guardrails import requires_human_review
    result = requires_human_review(confidence=0.95, is_bank_credit=True)
    assert result["required"] is True


def test_guardrail_human_review_large_mom_change():
    from src.utils.ml_guardrails import requires_human_review
    result = requires_human_review(
        confidence=0.85,
        index_value=75.0,
        prev_index_value=50.0,   # 25 pt change > 20 threshold
    )
    assert result["required"] is True
    assert any("25.0" in r or "change" in r.lower() for r in result["reasons"])
