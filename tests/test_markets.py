"""
WASI Backend API — Markets Route Tests

Tests for /api/markets/ endpoints: latest, history, summary, divergence,
divergence/history.
"""
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import (
    User, Country, CountryIndex, StockMarketData, DivergenceSnapshot,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="mktuser", email="mkt@test.com", password="MktPass1"):
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
        json={"amount": amount, "reference_id": f"mkt-test-{amount}"},
        headers=_auth(token),
    )


def _seed_stock_data():
    """Seed stock market data for NGX and BRVM."""
    db = TestingSessionLocal()
    rows = [
        StockMarketData(
            exchange_code="NGX",
            index_name="NGX All-Share",
            country_codes="NG",
            trade_date=date(2025, 1, 1),
            index_value=100000.0,
            change_pct=2.5,
            ytd_change_pct=5.0,
            market_cap_usd=55_000_000_000.0,
            volume_usd=150_000_000.0,
            data_source="kwayisi",
            confidence=0.85,
        ),
        StockMarketData(
            exchange_code="NGX",
            index_name="NGX All-Share",
            country_codes="NG",
            trade_date=date(2024, 10, 1),
            index_value=95000.0,
            change_pct=1.0,
            market_cap_usd=50_000_000_000.0,
            data_source="kwayisi",
            confidence=0.85,
        ),
        StockMarketData(
            exchange_code="BRVM",
            index_name="BRVM Composite",
            country_codes="CI,SN,BJ,TG",
            trade_date=date(2025, 1, 1),
            index_value=250.0,
            change_pct=-1.0,
            market_cap_usd=12_000_000_000.0,
            data_source="brvm",
            confidence=0.80,
        ),
    ]
    db.add_all(rows)
    db.commit()
    db.close()


def _seed_divergence_snapshot():
    """Seed a divergence snapshot for history test."""
    db = TestingSessionLocal()
    snap = DivergenceSnapshot(
        exchange_code="NGX",
        index_name="NGX All-Share",
        snapshot_date=date(2025, 1, 1),
        stock_index_value=100000.0,
        stock_change_pct=5.26,
        avg_wasi_score=65.0,
        fundamentals_change_pct=2.0,
        divergence_pct=3.26,
        signal="overvalued",
        liquidity_flag=False,
    )
    db.add(snap)
    db.commit()
    db.close()


# ── GET /latest ──────────────────────────────────────────────────────────────

def test_latest_requires_auth():
    resp = client.get("/api/markets/latest")
    assert resp.status_code == 401


def test_latest_no_data():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/markets/latest", headers=_auth(token))
    assert resp.status_code == 404


def test_latest_with_data():
    _seed_stock_data()
    token = _register_and_login(username="mkt2", email="mkt2@test.com")
    _topup(token)
    resp = client.get("/api/markets/latest", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    codes = {r["exchange_code"] for r in data}
    assert "NGX" in codes
    assert "BRVM" in codes


def test_latest_includes_freshness():
    _seed_stock_data()
    token = _register_and_login(username="mkt3", email="mkt3@test.com")
    _topup(token)
    resp = client.get("/api/markets/latest", headers=_auth(token))
    assert resp.status_code == 200
    for row in resp.json():
        assert "data_age_days" in row
        assert "wasi_weight" in row


# ── GET /history ─────────────────────────────────────────────────────────────

def test_history_requires_auth():
    resp = client.get("/api/markets/history?exchange_code=NGX")
    assert resp.status_code == 401


def test_history_no_data():
    token = _register_and_login(username="mkt4", email="mkt4@test.com")
    _topup(token)
    resp = client.get("/api/markets/history?exchange_code=XYZ", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_history_with_data():
    _seed_stock_data()
    token = _register_and_login(username="mkt5", email="mkt5@test.com")
    _topup(token)
    resp = client.get("/api/markets/history?exchange_code=NGX&months=24", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


# ── GET /summary ─────────────────────────────────────────────────────────────

def test_summary_requires_auth():
    resp = client.get("/api/markets/summary")
    assert resp.status_code == 401


def test_summary_with_data():
    _seed_stock_data()
    token = _register_and_login(username="mkt6", email="mkt6@test.com")
    _topup(token)
    resp = client.get("/api/markets/summary", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "exchanges" in data
    assert "total_market_cap_usd" in data
    assert "wasi_coverage_pct" in data
    assert data["total_market_cap_usd"] > 0


# ── GET /divergence ──────────────────────────────────────────────────────────

def test_divergence_requires_auth():
    resp = client.get("/api/markets/divergence")
    assert resp.status_code == 401


def test_divergence_no_data():
    token = _register_and_login(username="mkt7", email="mkt7@test.com")
    _topup(token)
    resp = client.get("/api/markets/divergence", headers=_auth(token))
    assert resp.status_code == 404


def test_divergence_with_data():
    _seed_stock_data()
    token = _register_and_login(username="mkt8", email="mkt8@test.com")
    _topup(token)
    resp = client.get("/api/markets/divergence", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "signal" in data[0]
    assert "narrative" in data[0]
    assert "divergence_pct" in data[0]


# ── GET /divergence/history ──────────────────────────────────────────────────

def test_divergence_history_requires_auth():
    resp = client.get("/api/markets/divergence/history?exchange_code=NGX")
    assert resp.status_code == 401


def test_divergence_history_no_data():
    token = _register_and_login(username="mkt9", email="mkt9@test.com")
    _topup(token)
    resp = client.get("/api/markets/divergence/history?exchange_code=NGX", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_divergence_history_with_data():
    _seed_divergence_snapshot()
    token = _register_and_login(username="mkt10", email="mkt10@test.com")
    _topup(token)
    resp = client.get(
        "/api/markets/divergence/history?exchange_code=NGX&months=24",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["exchange_code"] == "NGX"
    assert data["items"][0]["signal"] == "overvalued"
