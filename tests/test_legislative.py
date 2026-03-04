"""
WASI Backend API — Legislative Route Tests

Tests for /api/v3/legislative/ endpoints: latest, summary, refresh,
country-level legislation, and impact assessment.
"""
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.legislative_models import LegislativeAct
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="leguser", email="leg@test.com", password="LegPass1"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _topup(token, amount=100.0):
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference_id": f"leg-test-{amount}"},
        headers=_auth(token),
    )


def _seed_legislative_data():
    """Seed LegislativeAct records for NG."""
    db = TestingSessionLocal()
    ng = db.query(Country).filter(Country.code == "NG").first()
    if not ng:
        db.close()
        return

    acts = [
        LegislativeAct(
            country_id=ng.id,
            title="Finance Act 2025",
            description="Amendments to tariff schedules for ECOWAS trade",
            act_number="FA-2025-001",
            act_date=date(2025, 1, 15),
            category="TARIFF",
            status="ENACTED",
            impact_type="POSITIVE",
            estimated_magnitude=8.0,
            source_name="Nigeria National Assembly",
            confidence=0.80,
            data_quality="high",
            data_source="laws_africa",
            is_active=True,
        ),
        LegislativeAct(
            country_id=ng.id,
            title="Port Reform Bill 2025",
            description="Restructuring NPA operations for efficiency",
            act_number="PRB-2025-002",
            act_date=date(2025, 2, 1),
            category="INFRASTRUCTURE",
            status="COMMITTEE",
            impact_type="NEUTRAL",
            estimated_magnitude=0.0,
            source_name="IPU Parline",
            confidence=0.60,
            data_quality="medium",
            data_source="ipu_parline",
            is_active=True,
        ),
    ]
    db.add_all(acts)
    db.commit()
    db.close()


# ── GET /latest ──────────────────────────────────────────────────────────────

def test_latest_requires_auth():
    resp = client.get("/api/v3/legislative/latest")
    assert resp.status_code == 401


def test_latest_returns_acts():
    _seed_legislative_data()
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/legislative/latest", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["country_code"] == "NG"
    assert "confidence_indicator" in data[0]


def test_latest_with_pagination():
    _seed_legislative_data()
    token = _register_and_login(username="leg2", email="leg2@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/latest?limit=1&offset=0", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── GET /summary ─────────────────────────────────────────────────────────────

def test_summary_requires_auth():
    resp = client.get("/api/v3/legislative/summary")
    assert resp.status_code == 401


def test_summary_returns_dashboard():
    _seed_legislative_data()
    token = _register_and_login(username="leg3", email="leg3@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/summary", headers=_auth(token))
    assert resp.status_code == 200


# ── GET /{country_code} ─────────────────────────────────────────────────────

def test_country_legislation_requires_auth():
    resp = client.get("/api/v3/legislative/NG")
    assert resp.status_code == 401


def test_country_legislation_valid():
    _seed_legislative_data()
    token = _register_and_login(username="leg4", email="leg4@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/NG", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(a["country_code"] == "NG" for a in data)


def test_country_legislation_invalid_code():
    token = _register_and_login(username="leg5", email="leg5@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/XX", headers=_auth(token))
    assert resp.status_code == 404
    assert "ECOWAS" in resp.json()["detail"]


# ── GET /{country_code}/impact ───────────────────────────────────────────────

def test_impact_requires_auth():
    resp = client.get("/api/v3/legislative/NG/impact")
    assert resp.status_code == 401


def test_impact_valid_country():
    _seed_legislative_data()
    token = _register_and_login(username="leg6", email="leg6@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/NG/impact", headers=_auth(token))
    assert resp.status_code == 200


def test_impact_invalid_country():
    token = _register_and_login(username="leg7", email="leg7@test.com")
    _topup(token)
    resp = client.get("/api/v3/legislative/XX/impact", headers=_auth(token))
    assert resp.status_code == 404
