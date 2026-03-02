"""
WASI Backend API — Bank Module Tests

Tests for /api/v2/bank/ endpoints: credit-context, loan-advisory, score-dossier.
Validates authentication, country validation, scoring bounds, COBOL formatting,
and credit deduction. Shared setup is in conftest.py.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, BankDossierScore
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="bankuser", email="bank@test.com", password="bankpass1"):
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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _topup(token: str, amount: float = 100.0):
    """Give the test user enough credits for bank operations."""
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference_id": f"bank-test-{amount}"},
        headers=_auth_headers(token),
    )


# ── Credit Context ────────────────────────────────────────────────────────────

def test_credit_context_requires_auth():
    resp = client.get("/api/v2/bank/credit-context/NG")
    assert resp.status_code == 401


def test_credit_context_valid_country():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/bank/credit-context/NG", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "NG"
    assert "indicative_score" in data
    assert "indicative_rating" in data
    assert "wasi_index" in data
    assert "trade_summary" in data


def test_credit_context_invalid_country():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/bank/credit-context/XX", headers=_auth_headers(token))
    assert resp.status_code == 422
    assert "WASI v3.0" in resp.json()["detail"]


def test_credit_context_old_country():
    """CM (Cameroon) was removed in v3.0 — should be rejected."""
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/bank/credit-context/CM", headers=_auth_headers(token))
    assert resp.status_code == 422


# ── Loan Advisory ─────────────────────────────────────────────────────────────

def test_loan_advisory_requires_auth():
    resp = client.post("/api/v2/bank/loan-advisory", json={
        "country_code": "NG", "sector": "agriculture",
        "loan_amount_usd": 500000, "loan_term_months": 24,
    })
    assert resp.status_code == 401


def test_loan_advisory_valid():
    token = _register_and_login(username="ladv", email="ladv@test.com")
    _topup(token)
    resp = client.post("/api/v2/bank/loan-advisory", json={
        "country_code": "GH", "sector": "logistics",
        "loan_amount_usd": 1_000_000, "loan_term_months": 36,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "GH"
    assert "indicative_rating" in data
    assert "advisory_narrative" in data
    assert data["bank_review_required"] is True


def test_loan_advisory_invalid_country():
    token = _register_and_login(username="ladv2", email="ladv2@test.com")
    _topup(token)
    resp = client.post("/api/v2/bank/loan-advisory", json={
        "country_code": "US", "sector": "agriculture",
        "loan_amount_usd": 500000, "loan_term_months": 24,
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


# ── Score Dossier ─────────────────────────────────────────────────────────────

def test_score_dossier_requires_auth():
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "NG", "sector": "mining",
        "loan_amount_usd": 2_000_000, "loan_term_months": 60,
    })
    assert resp.status_code == 401


def test_score_dossier_valid():
    token = _register_and_login(username="sdoss", email="sdoss@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "SN", "sector": "agriculture",
        "loan_amount_usd": 5_000_000, "loan_term_months": 48,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "SN"
    assert "overall_score" in data
    assert "risk_rating" in data
    assert "cobol_record" in data
    assert data["bank_review_required"] is True


def test_score_dossier_invalid_country():
    token = _register_and_login(username="sdoss2", email="sdoss2@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "AO", "sector": "mining",
        "loan_amount_usd": 1_000_000, "loan_term_months": 24,
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


def test_score_dossier_excessive_loan():
    """Loan > $1B should be rejected by Pydantic validation."""
    token = _register_and_login(username="sdoss3", email="sdoss3@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "NG", "sector": "logistics",
        "loan_amount_usd": 2_000_000_000,  # $2B — exceeds $1B cap
        "loan_term_months": 60,
    }, headers=_auth_headers(token))
    assert resp.status_code == 422


def test_score_dossier_cobol_fields():
    """COBOL record fields must have correct fixed widths."""
    token = _register_and_login(username="sdoss4", email="sdoss4@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "CI", "sector": "manufacturing",
        "loan_amount_usd": 10_000_000, "loan_term_months": 36,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    cobol = resp.json()["cobol_record"]

    assert len(cobol["SCORE_9V2"]) == 9
    assert cobol["SCORE_9V2"].isdigit()

    assert len(cobol["RATING_X5"]) == 5

    assert len(cobol["MAX_LOAN_15V2"]) == 15
    assert cobol["MAX_LOAN_15V2"].isdigit()

    assert len(cobol["PREMIUM_4"]) == 4
    assert cobol["PREMIUM_4"].isdigit()

    assert len(cobol["WACC_6V2"]) == 6
    assert cobol["WACC_6V2"].isdigit()

    assert len(cobol["CALC_DATE_8"]) == 8
    assert cobol["CALC_DATE_8"].isdigit()

    assert cobol["REVIEW_FLAG_1"] == "Y"


def test_score_dossier_score_bounds():
    """Overall score must be in [0, 100]."""
    token = _register_and_login(username="sdoss5", email="sdoss5@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "BF", "sector": "agriculture",
        "loan_amount_usd": 500_000, "loan_term_months": 12,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    score = resp.json()["overall_score"]
    assert 0.0 <= score <= 100.0


def test_score_dossier_persisted():
    """Score dossier result should be saved to DB."""
    token = _register_and_login(username="sdoss6", email="sdoss6@test.com")
    _topup(token, 200)
    resp = client.post("/api/v2/bank/score-dossier", json={
        "country_code": "NG", "sector": "logistics",
        "loan_amount_usd": 3_000_000, "loan_term_months": 24,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    dossier_id = resp.json()["dossier_id"]

    db = TestingSessionLocal()
    try:
        record = db.query(BankDossierScore).filter(BankDossierScore.id == dossier_id).first()
        assert record is not None
        assert record.loan_amount_usd == 3_000_000
        assert record.sector == "logistics"
        assert record.bank_review_required is True
    finally:
        db.close()


def test_score_dossier_credits_deducted():
    """Score dossier should deduct 10 credits (pro tier: query_cost=1.0 * multiplier=10)."""
    token = _register_and_login(username="sdoss7", email="sdoss7@test.com")
    _topup(token, 100)

    # Upgrade user to pro tier so credits are actually charged
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == "sdoss7").first()
        user.tier = "pro"
        db.commit()
    finally:
        db.close()

    # Check balance before
    me_before = client.get("/api/auth/me", headers=_auth_headers(token)).json()
    balance_before = me_before["x402_balance"]

    client.post("/api/v2/bank/score-dossier", json={
        "country_code": "GH", "sector": "mining",
        "loan_amount_usd": 1_000_000, "loan_term_months": 36,
    }, headers=_auth_headers(token))

    me_after = client.get("/api/auth/me", headers=_auth_headers(token)).json()
    balance_after = me_after["x402_balance"]

    assert balance_before - balance_after == pytest.approx(10.0, abs=0.01)
