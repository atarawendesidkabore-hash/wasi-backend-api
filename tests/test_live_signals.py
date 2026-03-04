"""
WASI Backend API — Live Signals Route Tests

Tests for /api/v2/signals/ endpoints: live, /{country_code}/live, events, sweep.
"""
from datetime import date, datetime, timezone, timedelta

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country, LiveSignal, NewsEvent
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="siguser", email="sig@test.com", password="SigPass1"):
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
        json={"amount": amount, "reference_id": f"sig-test-{amount}"},
        headers=_auth(token),
    )


def _seed_signals():
    """Seed LiveSignal and NewsEvent for NG."""
    db = TestingSessionLocal()
    ng = db.query(Country).filter(Country.code == "NG").first()
    if not ng:
        db.close()
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    signal = LiveSignal(
        country_id=ng.id,
        period_date=date.today(),
        base_index=65.0,
        live_adjustment=-3.5,
        adjusted_index=61.5,
        computed_at=now,
    )
    event = NewsEvent(
        country_id=ng.id,
        event_type="PORT_DISRUPTION",
        headline="Lagos port congestion causes 3-day delays",
        magnitude=-3.5,
        detected_at=now,
        expires_at=now + timedelta(days=3),
        is_active=True,
        source_name="Reuters",
    )
    db.add_all([signal, event])
    db.commit()
    db.close()


# ── GET /live ────────────────────────────────────────────────────────────────

def test_live_requires_auth():
    resp = client.get("/api/v2/signals/live")
    assert resp.status_code == 401


def test_live_returns_signals():
    _seed_signals()
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/signals/live", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert data["total"] >= 1


# ── GET /{country_code}/live ─────────────────────────────────────────────────

def test_country_live_requires_auth():
    resp = client.get("/api/v2/signals/NG/live")
    assert resp.status_code == 401


def test_country_live_valid():
    _seed_signals()
    token = _register_and_login(username="sig2", email="sig2@test.com")
    _topup(token)
    resp = client.get("/api/v2/signals/NG/live", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "NG"
    assert "signal" in data
    assert "active_events" in data
    assert len(data["active_events"]) >= 1
    assert data["active_events"][0]["event_type"] == "PORT_DISRUPTION"


def test_country_live_invalid():
    token = _register_and_login(username="sig3", email="sig3@test.com")
    _topup(token)
    resp = client.get("/api/v2/signals/ZZ/live", headers=_auth(token))
    assert resp.status_code == 404


# ── GET /events ──────────────────────────────────────────────────────────────

def test_events_requires_auth():
    resp = client.get("/api/v2/signals/events")
    assert resp.status_code == 401


def test_events_returns_active():
    _seed_signals()
    token = _register_and_login(username="sig4", email="sig4@test.com")
    _topup(token)
    resp = client.get("/api/v2/signals/events", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


def test_events_filter_by_type():
    _seed_signals()
    token = _register_and_login(username="sig5", email="sig5@test.com")
    _topup(token)
    resp = client.get(
        "/api/v2/signals/events?event_type=PORT_DISRUPTION",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["event_type"] == "PORT_DISRUPTION" for e in data["items"])


# ── POST /sweep ──────────────────────────────────────────────────────────────

def test_sweep_requires_auth():
    resp = client.post("/api/v2/signals/sweep")
    assert resp.status_code == 401


def test_sweep_executes():
    token = _register_and_login(username="sig6", email="sig6@test.com")
    _topup(token)
    resp = client.post("/api/v2/signals/sweep", headers=_auth(token))
    # sweep_news may return 200 even with no RSS data — just verify it doesn't crash
    assert resp.status_code == 200
