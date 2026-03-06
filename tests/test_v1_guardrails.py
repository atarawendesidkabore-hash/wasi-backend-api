from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


def _register_and_login(
    username: str = "v1user",
    email: str = "v1user@test.com",
    password: str = "V1Pass123",
) -> str:
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _topup(token: str, amount: float = 100.0) -> None:
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference_id": f"v1-test-{amount}"},
        headers=_auth(token),
    )


def _upgrade_to_pro(username: str) -> None:
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        assert user is not None
        user.tier = "pro"
        db.commit()
    finally:
        db.close()


def test_v1_fx_requires_auth():
    resp = client.get("/v1/market/fx")
    assert resp.status_code == 401


def test_v1_fx_success():
    token = _register_and_login(username="v1fx", email="v1fx@test.com")
    _topup(token)

    mocked_payload = {
        "result": "success",
        "time_last_update_utc": "Fri, 06 Mar 2026 00:00:00 +0000",
        "rates": {"EUR": 0.00152, "USD": 0.00164},
    }
    with patch(
        "src.routes.v1_guardrails._fetch_open_er_api",
        new=AsyncMock(return_value=mocked_payload),
    ):
        resp = client.get("/v1/market/fx?base=XOF&symbols=EUR,USD", headers=_auth(token))

    assert resp.status_code == 200
    data = resp.json()
    assert data["base"] == "XOF"
    assert data["source"] == "open.er-api.com"
    assert data["data_mode"] == "live"
    assert len(data["rates"]) == 2


def test_v1_fx_missing_realtime_data_message():
    token = _register_and_login(username="v1fx2", email="v1fx2@test.com")
    _topup(token)

    mocked_payload = {"result": "success", "rates": {}}
    with patch(
        "src.routes.v1_guardrails._fetch_open_er_api",
        new=AsyncMock(return_value=mocked_payload),
    ):
        resp = client.get("/v1/market/fx?base=XOF&symbols=EUR", headers=_auth(token))

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Je n'ai pas cette donnée en temps réel"


def test_v1_credit_decision_sovereign_veto():
    token = _register_and_login(username="v1credit", email="v1credit@test.com")
    _topup(token)
    resp = client.post(
        "/v1/credit/decision",
        json={
            "country": "BF",
            "loan_type": "dette_souveraine",
            "components": {
                "pays": 70,
                "politique": 60,
                "sectoriel": 65,
                "flux": 72,
                "corridor": 68,
                "emprunteur": 75,
                "change": 62,
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision_proposal"] == "VETOED"
    assert data["veto_applied"] is True
    assert data["human_review_required"] is True
    assert data["disclaimer"] == "Advisory only. Décision finale = validation humaine"


def test_v1_credit_decision_invalid_country():
    token = _register_and_login(username="v1credit2", email="v1credit2@test.com")
    _topup(token)
    resp = client.post(
        "/v1/credit/decision",
        json={
            "country": "US",
            "loan_type": "projet",
            "components": {
                "pays": 70,
                "politique": 60,
                "sectoriel": 65,
                "flux": 72,
                "corridor": 68,
                "emprunteur": 75,
                "change": 62,
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_v1_financial_analysis_local_mode():
    token = _register_and_login(username="v1analysis", email="v1analysis@test.com")
    _topup(token)

    resp = client.post(
        "/v1/ai/financial-analysis",
        json={
            "question": "Analyse risque pays Burkina Faso pour trade finance.",
            "context_data": {},
            "confidentiality_mode": "local",
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_used"] == "ollama/llama3.2"
    assert "Je n'ai pas cette donnée en temps réel" in data["missing_data_flags"]
    assert data["human_review_required"] is True
    assert data["disclaimer"] == "Advisory only. Décision finale = validation humaine"


def test_v1_financial_analysis_cloud_no_api_key():
    token = _register_and_login(username="v1analysis2", email="v1analysis2@test.com")
    _topup(token)

    with patch("src.routes.v1_guardrails.settings") as mocked_settings:
        mocked_settings.ANTHROPIC_API_KEY = ""
        resp = client.post(
            "/v1/ai/financial-analysis",
            json={
                "question": "Analyse financement projet CI.",
                "context_data": {"sources": ["api.worldbank.org"]},
                "confidentiality_mode": "cloud",
            },
            headers=_auth(token),
        )
    assert resp.status_code == 503


def test_v1_credit_decision_deducts_credits_for_pro_tier():
    username = "v1credits"
    token = _register_and_login(username=username, email="v1credits@test.com")
    _upgrade_to_pro(username)

    before = client.get("/api/auth/me", headers=_auth(token))
    assert before.status_code == 200
    balance_before = before.json()["x402_balance"]

    resp = client.post(
        "/v1/credit/decision",
        json={
            "country": "CI",
            "loan_type": "projet",
            "components": {
                "pays": 70,
                "politique": 60,
                "sectoriel": 65,
                "flux": 72,
                "corridor": 68,
                "emprunteur": 75,
                "change": 62,
            },
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200

    after = client.get("/api/auth/me", headers=_auth(token))
    assert after.status_code == 200
    balance_after = after.json()["x402_balance"]
    assert balance_before - balance_after == 5.0
