"""
WASI Forecast API — Integration Tests

Uses the same in-memory SQLite + StaticPool pattern from conftest.py.
Seeds historical data, then tests the /api/v3/forecast/ endpoints.
"""
import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import (
    Base, Country, CountryIndex, WASIComposite,
    CommodityPrice, MacroIndicator,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────

def _register_and_login(username="fc_user", email="fc@test.com", password="FcPass123"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    return resp.json()["access_token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_country_index(db, country_code="NG", n_periods=6):
    """Seed n_periods of CountryIndex data for a country."""
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    base_date = date(2024, 1, 1)
    base_value = 45.0
    for i in range(n_periods):
        month = base_date.month + i
        year = base_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        db.add(CountryIndex(
            country_id=country.id,
            period_date=date(year, month, 1),
            index_value=round(base_value + i * 2.5, 2),
            shipping_score=50.0,
            trade_score=45.0,
            infrastructure_score=40.0,
            economic_score=35.0,
            confidence=0.80,
            data_quality="medium",
            data_source="test_seed",
        ))
    db.commit()


def _seed_composite(db, n_periods=6):
    """Seed n_periods of WASIComposite data."""
    base_date = date(2024, 1, 1)
    base_value = 50.0
    for i in range(n_periods):
        month = base_date.month + i
        year = base_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        db.add(WASIComposite(
            period_date=date(year, month, 1),
            composite_value=round(base_value + i * 1.5, 2),
            countries_included=16,
            calculation_version="3.0",
            calculated_at=datetime.utcnow(),
        ))
    db.commit()


def _seed_commodity(db, code="COCOA", n_periods=6):
    """Seed n_periods of CommodityPrice data."""
    base_date = date(2024, 1, 1)
    base_price = 3200.0
    for i in range(n_periods):
        month = base_date.month + i
        year = base_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        db.add(CommodityPrice(
            commodity_code=code,
            commodity_name=code.title(),
            unit="USD/mt",
            period_date=date(year, month, 1),
            price_usd=round(base_price + i * 100, 2),
            data_source="test_seed",
        ))
    db.commit()


def _seed_macro(db, country_code="NG", n_years=5):
    """Seed n_years of MacroIndicator data."""
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    base_year = 2020
    for i in range(n_years):
        db.add(MacroIndicator(
            country_id=country.id,
            year=base_year + i,
            gdp_growth_pct=round(3.0 + i * 0.3, 2),
            inflation_pct=round(12.0 - i * 0.5, 2),
            data_source="test_seed",
            is_projection=False,
            confidence=0.85,
        ))
    db.commit()


# ── Auth Required ────────────────────────────────────────────────

def test_forecast_country_index_unauthorized():
    resp = client.get("/api/v3/forecast/NG/index")
    assert resp.status_code == 401


def test_forecast_composite_unauthorized():
    resp = client.get("/api/v3/forecast/composite")
    assert resp.status_code == 401


# ── Country Index Forecast ───────────────────────────────────────

def test_forecast_country_index_success():
    token = _register_and_login("ci1", "ci1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_country_index(db, "NG", 6)
    finally:
        db.close()

    resp = client.get("/api/v3/forecast/NG/index?horizon=3", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "country_index"
    assert data["target_code"] == "NG"
    assert data["horizon"] == 3
    assert len(data["periods"]) == 3
    assert data["data_points_used"] == 6
    assert len(data["methods_used"]) == 3  # linear, ses, holt (n=6 >= 5)


def test_forecast_country_index_unknown_country():
    token = _register_and_login("ci2", "ci2@test.com")
    resp = client.get("/api/v3/forecast/ZZ/index", headers=_auth_header(token))
    assert resp.status_code == 404


def test_forecast_country_index_invalid_horizon():
    token = _register_and_login("ci3", "ci3@test.com")
    resp = client.get("/api/v3/forecast/NG/index?horizon=7", headers=_auth_header(token))
    assert resp.status_code == 400


# ── Composite Forecast ───────────────────────────────────────────

def test_forecast_composite_success():
    token = _register_and_login("cp1", "cp1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_composite(db, 6)
    finally:
        db.close()

    resp = client.get("/api/v3/forecast/composite?horizon=6", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "composite_index"
    assert data["target_code"] == "WASI_COMPOSITE"
    assert len(data["periods"]) == 6


# ── Commodity Forecast ───────────────────────────────────────────

def test_forecast_commodity_success():
    token = _register_and_login("cm1", "cm1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_commodity(db, "COCOA", 6)
    finally:
        db.close()

    resp = client.get("/api/v3/forecast/commodity/COCOA?horizon=3", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "commodity_price"
    assert data["target_code"] == "COCOA"
    assert len(data["periods"]) == 3


def test_forecast_commodity_invalid_code():
    token = _register_and_login("cm2", "cm2@test.com")
    resp = client.get("/api/v3/forecast/commodity/UNOBTANIUM", headers=_auth_header(token))
    assert resp.status_code == 400


# ── Macro Forecast ───────────────────────────────────────────────

def test_forecast_macro_gdp_success():
    token = _register_and_login("mc1", "mc1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_macro(db, "NG", 5)
    finally:
        db.close()

    resp = client.get(
        "/api/v3/forecast/NG/macro?indicator=gdp_growth&horizon=2",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "macro_gdp_growth"
    assert len(data["periods"]) == 2


def test_forecast_macro_inflation_success():
    token = _register_and_login("mc2", "mc2@test.com")
    db = TestingSessionLocal()
    try:
        _seed_macro(db, "NG", 5)
    finally:
        db.close()

    resp = client.get(
        "/api/v3/forecast/NG/macro?indicator=inflation&horizon=1",
        headers=_auth_header(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_type"] == "macro_inflation"


def test_forecast_macro_invalid_indicator():
    token = _register_and_login("mc3", "mc3@test.com")
    resp = client.get(
        "/api/v3/forecast/NG/macro?indicator=cheese",
        headers=_auth_header(token),
    )
    assert resp.status_code == 400


# ── Summary ──────────────────────────────────────────────────────

def test_forecast_summary_success():
    token = _register_and_login("sm1", "sm1@test.com")
    resp = client.get("/api/v3/forecast/summary", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "countries" in data
    assert data["total_countries"] > 0
    assert "generated_at" in data


# ── Refresh ──────────────────────────────────────────────────────

def test_forecast_refresh():
    token = _register_and_login("rf1", "rf1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_country_index(db, "NG", 6)
        _seed_composite(db, 6)
        _seed_commodity(db, "COCOA", 6)
        _seed_macro(db, "NG", 5)
    finally:
        db.close()

    resp = client.post("/api/v3/forecast/refresh", headers=_auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["country_forecasts_computed"] >= 1
    assert data["commodities_computed"] >= 1
    assert data["duration_seconds"] >= 0


# ── Confidence bands structure ───────────────────────────────────

def test_forecast_confidence_bands_present():
    token = _register_and_login("cb1", "cb1@test.com")
    db = TestingSessionLocal()
    try:
        _seed_country_index(db, "NG", 6)
    finally:
        db.close()

    resp = client.get("/api/v3/forecast/NG/index?horizon=3", headers=_auth_header(token))
    data = resp.json()
    for period in data["periods"]:
        assert "forecast_value" in period
        assert "lower_1sigma" in period
        assert "upper_1sigma" in period
        assert "lower_2sigma" in period
        assert "upper_2sigma" in period
        assert period["lower_2sigma"] <= period["lower_1sigma"] <= period["forecast_value"]
        assert period["forecast_value"] <= period["upper_1sigma"] <= period["upper_2sigma"]
