"""
WASI Backend API — Signals Route Tests

Tests for /api/signals/ endpoints: composite, countries, summary, market-divergence.
"""
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import (
    User, Country, CountryIndex, WASIComposite, StockMarketData,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="bsuser", email="bs@test.com", password="BsPasswd1"):
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
        json={"amount": amount, "reference_id": f"bs-test-{amount}"},
        headers=_auth(token),
    )


def _seed_composite():
    """Seed a WASIComposite and CountryIndex records."""
    db = TestingSessionLocal()
    ng = db.query(Country).filter(Country.code == "NG").first()
    ci = db.query(Country).filter(Country.code == "CI").first()
    if not ng:
        db.close()
        return

    comp = WASIComposite(
        period_date=date(2025, 1, 1),
        composite_value=62.5,
        countries_included=16,
        trend_direction="up",
        mom_change=1.5,
        yoy_change=3.0,
        sharpe_ratio=1.2,
        max_drawdown=0.05,
        annualized_volatility=0.08,
    )
    db.add(comp)

    for country, val in [(ng, 65.0), (ci, 58.0)]:
        if country:
            idx = CountryIndex(
                country_id=country.id,
                period_date=date(2025, 1, 1),
                index_value=val,
                shipping_score=70.0,
                trade_score=60.0,
                infrastructure_score=55.0,
                economic_score=50.0,
                data_source="test",
                confidence=0.85,
            )
            db.add(idx)
    db.commit()
    db.close()


def _seed_stock_data():
    """Seed stock market data for market-divergence test."""
    db = TestingSessionLocal()
    row = StockMarketData(
        exchange_code="NGX",
        index_name="NGX All-Share",
        country_codes="NG",
        trade_date=date(2025, 1, 1),
        index_value=100000.0,
        change_pct=2.5,
        market_cap_usd=55_000_000_000.0,
        volume_usd=150_000_000.0,
        data_source="kwayisi",
        confidence=0.85,
    )
    db.add(row)
    db.commit()
    db.close()


# ── GET /composite ───────────────────────────────────────────────────────────

def test_composite_requires_auth():
    resp = client.get("/api/signals/composite")
    assert resp.status_code == 401


def test_composite_no_data():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/signals/composite", headers=_auth(token))
    assert resp.status_code == 404


def test_composite_with_data():
    _seed_composite()
    token = _register_and_login(username="bs2", email="bs2@test.com")
    _topup(token)
    resp = client.get("/api/signals/composite", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["composite_value"] == 62.5
    assert data["signal"] in ("bullish", "strong_bullish", "bearish", "strong_bearish", "neutral")
    assert "reasons" in data


# ── GET /countries ───────────────────────────────────────────────────────────

def test_countries_requires_auth():
    resp = client.get("/api/signals/countries")
    assert resp.status_code == 401


def test_countries_no_data():
    token = _register_and_login(username="bs3", email="bs3@test.com")
    _topup(token)
    resp = client.get("/api/signals/countries", headers=_auth(token))
    assert resp.status_code == 404


def test_countries_with_data():
    _seed_composite()
    token = _register_and_login(username="bs4", email="bs4@test.com")
    _topup(token)
    resp = client.get("/api/signals/countries", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "signal" in data[0]
    assert "country_code" in data[0]


# ── GET /summary ─────────────────────────────────────────────────────────────

def test_summary_requires_auth():
    resp = client.get("/api/signals/summary")
    assert resp.status_code == 401


def test_summary_no_data():
    token = _register_and_login(username="bs5", email="bs5@test.com")
    _topup(token)
    resp = client.get("/api/signals/summary", headers=_auth(token))
    assert resp.status_code == 404


def test_summary_with_data():
    _seed_composite()
    token = _register_and_login(username="bs6", email="bs6@test.com")
    _topup(token)
    resp = client.get("/api/signals/summary", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "composite" in data
    assert "country_signals" in data
    assert "bullish_count" in data
    assert "bearish_count" in data
    assert "neutral_count" in data


# ── GET /market-divergence ───────────────────────────────────────────────────

def test_market_divergence_requires_auth():
    resp = client.get("/api/signals/market-divergence")
    assert resp.status_code == 401


def test_market_divergence_no_data():
    token = _register_and_login(username="bs7", email="bs7@test.com")
    _topup(token)
    resp = client.get("/api/signals/market-divergence", headers=_auth(token))
    assert resp.status_code == 404


def test_market_divergence_with_data():
    _seed_stock_data()
    _seed_composite()
    token = _register_and_login(username="bs8", email="bs8@test.com")
    _topup(token)
    resp = client.get("/api/signals/market-divergence", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert len(data["signals"]) >= 1
    assert "overvalued_count" in data
    assert "undervalued_count" in data
