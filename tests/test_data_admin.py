"""
WASI Backend API — Data Admin Route Tests

Tests for /api/v2/data/ endpoints: status, commodity/macro queries,
and admin-only refresh triggers.
"""
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import (
    User, Country, CountryIndex, MacroIndicator, CommodityPrice,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register_and_login(username="datauser", email="data@test.com", password="DataPass1", is_admin=False):
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
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _topup(token, amount=100.0):
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference_id": f"data-test-{amount}"},
        headers=_auth(token),
    )


def _seed_data():
    """Seed CountryIndex, MacroIndicator, and CommodityPrice rows for NG."""
    db = TestingSessionLocal()
    ng = db.query(Country).filter(Country.code == "NG").first()
    if not ng:
        db.close()
        return

    ci = CountryIndex(
        country_id=ng.id,
        period_date=date(2025, 1, 1),
        index_value=65.5,
        shipping_score=70.0,
        trade_score=60.0,
        infrastructure_score=55.0,
        economic_score=50.0,
        data_source="World Bank Open Data API",
        confidence=0.85,
        data_quality="high",
    )
    mi = MacroIndicator(
        country_id=ng.id,
        year=2025,
        gdp_growth_pct=3.2,
        inflation_pct=15.1,
        debt_gdp_pct=38.5,
        current_account_gdp_pct=-1.2,
        unemployment_pct=33.0,
        gdp_usd_billions=480.0,
        data_source="imf_weo",
        is_projection=False,
        confidence=0.90,
    )
    cp = CommodityPrice(
        commodity_code="COCOA",
        commodity_name="Cocoa",
        unit="USD/mt",
        period_date=date(2025, 1, 1),
        price_usd=4200.00,
        pct_change_mom=2.5,
        pct_change_yoy=12.0,
        data_source="wb_pinksheet",
    )
    db.add_all([ci, mi, cp])
    db.commit()
    db.close()


# ── GET /status ──────────────────────────────────────────────────────────────

def test_status_requires_auth():
    resp = client.get("/api/v2/data/status")
    assert resp.status_code == 401


def test_status_returns_country_list():
    _seed_data()
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v2/data/status", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "total_countries" in data
    assert "countries" in data
    assert data["total_countries"] > 0
    assert "countries_with_data" in data


def test_status_includes_commodity_prices():
    _seed_data()
    token = _register_and_login(username="datausr2", email="data2@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/status", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "commodity_prices" in data
    prices = data["commodity_prices"]
    assert len(prices) >= 1
    assert prices[0]["code"] == "COCOA"


# ── GET /commodities/latest ──────────────────────────────────────────────────

def test_commodities_latest_requires_auth():
    resp = client.get("/api/v2/data/commodities/latest")
    assert resp.status_code == 401


def test_commodities_latest_with_data():
    _seed_data()
    token = _register_and_login(username="comusr", email="com@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/commodities/latest", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert data["prices"][0]["code"] == "COCOA"
    assert data["prices"][0]["price_usd"] == 4200.00


def test_commodities_latest_empty():
    """No commodity data → 404."""
    token = _register_and_login(username="comusr2", email="com2@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/commodities/latest", headers=_auth(token))
    assert resp.status_code == 404


# ── GET /macro/{country_code} ────────────────────────────────────────────────

def test_macro_requires_auth():
    resp = client.get("/api/v2/data/macro/NG")
    assert resp.status_code == 401


def test_macro_valid_country():
    _seed_data()
    token = _register_and_login(username="macusr", email="mac@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/macro/NG", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "NG"
    assert len(data["years"]) >= 1
    assert data["latest"]["gdp_growth_pct"] == 3.2


def test_macro_invalid_country():
    token = _register_and_login(username="macusr2", email="mac2@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/macro/XX", headers=_auth(token))
    assert resp.status_code == 404


def test_macro_no_data():
    """Country exists but no macro records → 404."""
    token = _register_and_login(username="macusr3", email="mac3@test.com")
    _topup(token)
    resp = client.get("/api/v2/data/macro/GH", headers=_auth(token))
    assert resp.status_code == 404


# ── POST /worldbank/refresh — admin only ─────────────────────────────────────

def test_worldbank_refresh_requires_admin():
    token = _register_and_login(username="nonadm", email="nonadm@test.com")
    _topup(token)
    resp = client.post("/api/v2/data/worldbank/refresh", headers=_auth(token))
    assert resp.status_code == 403


def test_imf_refresh_requires_admin():
    token = _register_and_login(username="nonadm2", email="nonadm2@test.com")
    _topup(token)
    resp = client.post("/api/v2/data/imf/refresh", headers=_auth(token))
    assert resp.status_code == 403


def test_acled_refresh_requires_admin():
    token = _register_and_login(username="nonadm3", email="nonadm3@test.com")
    _topup(token)
    resp = client.post("/api/v2/data/acled/refresh", headers=_auth(token))
    assert resp.status_code == 403


def test_comtrade_refresh_requires_admin():
    token = _register_and_login(username="nonadm4", email="nonadm4@test.com")
    _topup(token)
    resp = client.post("/api/v2/data/comtrade/refresh", headers=_auth(token))
    assert resp.status_code == 403


def test_commodities_refresh_requires_admin():
    token = _register_and_login(username="nonadm5", email="nonadm5@test.com")
    _topup(token)
    resp = client.post("/api/v2/data/commodities/refresh", headers=_auth(token))
    assert resp.status_code == 403
