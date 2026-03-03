"""
WASI FX Analytics — Integration + Unit Tests

Tests the /api/v3/fx/ endpoints and the FxAnalyticsEngine.
Seeds FxDailyRate data for all 9 ECOWAS currencies.
"""
import math
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import Base, Country
from src.database.fx_models import FxDailyRate, FxVolatility
from src.engines.fx_analytics_engine import (
    FxAnalyticsEngine, REGIME_MAP, COUNTRY_CURRENCY, ALL_CURRENCIES,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=True)


# ── Helpers ──────────────────────────────────────────────────────────────

def _register_and_login(username="fxuser", email="fx@test.com", password="FxPass123"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# Approximate rates (1 USD = X currency)
_SEED_RATES = {
    "NGN": 1550.0, "GHS": 15.2, "GMD": 70.0, "GNF": 8600.0,
    "SLE": 22.5, "LRD": 192.0, "MRU": 39.5, "CVE": 101.0,
    "XOF": 603.5,
}


def _seed_fx_rates(db, n_days=10):
    """Seed FxDailyRate rows for all 9 currencies over n_days."""
    today = date.today()
    for cc, base_rate in _SEED_RATES.items():
        for d in range(n_days):
            day = today - timedelta(days=n_days - 1 - d)
            # Slight daily drift: +/- 0.2% per day for floating, near-0 for pegged
            regime = REGIME_MAP.get(cc, "FLOATING")
            if regime == "PEGGED":
                drift = 0.0001 * (d % 3 - 1)  # tiny EUR/USD fluctuation
            else:
                drift = 0.002 * (d % 5 - 2)  # ±0.4% range

            rate_usd = round(base_rate * (1.0 + drift), 6)
            rate_eur = round(rate_usd / 0.92, 6)
            rate_xof = round(rate_usd / 603.5, 6)

            # Compute simple pct_change_1d
            pct_1d = round(drift * 100, 4) if d > 0 else None

            db.add(FxDailyRate(
                currency_code=cc,
                rate_date=day,
                rate_to_usd=rate_usd,
                rate_to_eur=rate_eur,
                rate_to_xof=rate_xof,
                pct_change_1d=pct_1d,
                data_source="test_seed",
                confidence=1.0,
            ))
    db.commit()


# ── Engine Unit Tests ────────────────────────────────────────────────────

class TestFxAnalyticsEngine:

    def test_current_rates(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 5)
            engine = FxAnalyticsEngine(db)
            rates = engine.get_current_rates()
            assert len(rates) == 9
            codes = {r["currency_code"] for r in rates}
            assert "NGN" in codes
            assert "XOF" in codes
            assert "CVE" in codes
        finally:
            db.close()

    def test_currency_profile(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 5)
            engine = FxAnalyticsEngine(db)
            profile = engine.get_currency_profile("NGN")
            assert profile is not None
            assert profile["currency_code"] == "NGN"
            assert profile["regime"] == "FLOATING"
            assert profile["latest_rate_usd"] > 0
            assert "NG" in profile["countries"]
        finally:
            db.close()

    def test_currency_profile_invalid(self):
        db = TestingSessionLocal()
        try:
            engine = FxAnalyticsEngine(db)
            assert engine.get_currency_profile("INVALID") is None
        finally:
            db.close()

    def test_rate_history(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 10)
            engine = FxAnalyticsEngine(db)
            history = engine.get_rate_history("GHS", 30)
            assert len(history) == 10
            assert history[0]["rate_to_usd"] > 0
        finally:
            db.close()

    def test_compute_volatility(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 10)
            engine = FxAnalyticsEngine(db)
            vol = engine.compute_volatility("NGN")
            db.commit()
            assert vol["currency_code"] == "NGN"
            assert vol["regime"] == "FLOATING"
            # With seed data drift, volatility should be non-zero
            assert vol["volatility_7d"] is not None or vol["volatility_30d"] is not None
        finally:
            db.close()

    def test_trade_cost_same_zone(self):
        db = TestingSessionLocal()
        try:
            engine = FxAnalyticsEngine(db)
            result = engine.compute_trade_cost("CI", "SN", 100_000)
            assert result["same_currency_zone"] is True
            assert result["total_fx_cost_usd"] == 0.0
            assert result["fx_cost_pct"] == 0.0
            assert result["from_currency"] == "XOF"
            assert result["to_currency"] == "XOF"
        finally:
            db.close()

    def test_trade_cost_cross_zone(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 10)
            engine = FxAnalyticsEngine(db)
            # Compute volatility first so trade cost has vol data
            engine.compute_volatility("NGN")
            db.commit()
            result = engine.compute_trade_cost("NG", "CI", 100_000)
            assert result["same_currency_zone"] is False
            assert result["spread_cost_usd"] > 0
            assert result["from_currency"] == "NGN"
            assert result["to_currency"] == "XOF"
        finally:
            db.close()

    def test_regime_divergence(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 10)
            engine = FxAnalyticsEngine(db)
            engine.recompute_all_volatility()
            db.commit()
            result = engine.get_regime_divergence()
            assert "cfa_zone" in result
            assert "floating_zone" in result
            assert "interpretation" in result
            assert len(result["cfa_zone"]["currencies"]) == 2
            assert len(result["floating_zone"]["currencies"]) == 6
        finally:
            db.close()

    def test_dashboard(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 5)
            engine = FxAnalyticsEngine(db)
            result = engine.get_ecowas_fx_dashboard()
            assert result["total_countries"] == 16
            assert "weighted_fx_risk" in result
            # CFA zone countries should have fx_risk_score == 0
            cfa_countries = [c for c in result["countries"] if c["regime"] == "PEGGED"]
            for c in cfa_countries:
                assert c["fx_risk_score"] == 0.0
        finally:
            db.close()

    def test_recompute_all_volatility(self):
        db = TestingSessionLocal()
        try:
            _seed_fx_rates(db, 10)
            engine = FxAnalyticsEngine(db)
            result = engine.recompute_all_volatility()
            db.commit()
            assert result["currencies_computed"] == 9
        finally:
            db.close()


# ── API Integration Tests ────────────────────────────────────────────────

def _seed_and_get_token():
    """Seed FX data and return auth token."""
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 10)
    finally:
        db.close()
    return _register_and_login()


def test_fx_rates_unauthenticated():
    resp = client.get("/api/v3/fx/rates")
    assert resp.status_code in (401, 403)


def test_fx_rates_all():
    token = _seed_and_get_token()
    resp = client.get("/api/v3/fx/rates", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 9
    assert data["xof_eur_peg"] == 655.957
    codes = {c["currency_code"] for c in data["currencies"]}
    assert "NGN" in codes
    assert "XOF" in codes


def test_fx_currency_profile():
    token = _register_and_login("fx2", "fx2@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 5)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/rates/NGN", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency_code"] == "NGN"
    assert data["regime"] == "FLOATING"
    assert "NG" in data["countries"]


def test_fx_currency_profile_invalid():
    token = _register_and_login("fx3", "fx3@t.com", "Pass1234")
    resp = client.get("/api/v3/fx/rates/INVALID", headers=_auth(token))
    assert resp.status_code == 400


def test_fx_rate_history():
    token = _register_and_login("fx4", "fx4@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 10)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/rates/GHS/history?days=30", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency_code"] == "GHS"
    assert data["regime"] == "FLOATING"
    assert len(data["history"]) == 10


def test_fx_rate_history_invalid_days():
    token = _register_and_login("fx5", "fx5@t.com", "Pass1234")
    resp = client.get("/api/v3/fx/rates/NGN/history?days=999", headers=_auth(token))
    assert resp.status_code == 400


def test_fx_trade_cost_same_zone():
    token = _register_and_login("fx6", "fx6@t.com", "Pass1234")
    resp = client.get("/api/v3/fx/trade-cost/CI/SN?amount=100000", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["same_currency_zone"] is True
    assert data["total_fx_cost_usd"] == 0.0


def test_fx_trade_cost_cross_zone():
    token = _register_and_login("fx7", "fx7@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 10)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/trade-cost/NG/CI?amount=100000", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["same_currency_zone"] is False
    assert data["spread_cost_usd"] > 0
    assert data["fx_cost_pct"] > 0


def test_fx_trade_cost_invalid_country():
    token = _register_and_login("fx8", "fx8@t.com", "Pass1234")
    resp = client.get("/api/v3/fx/trade-cost/XX/CI", headers=_auth(token))
    assert resp.status_code == 400


def test_fx_dashboard():
    token = _register_and_login("fx9", "fx9@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 5)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/dashboard", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_countries"] == 16
    assert "weighted_fx_risk" in data
    assert data["regime_summary"]["pegged"] == 9  # 8 CFA + CV


def test_fx_regime_divergence():
    token = _register_and_login("fx10", "fx10@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 10)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/regime-divergence", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "cfa_zone" in data
    assert "floating_zone" in data
    assert "interpretation" in data


def test_fx_volatility():
    token = _register_and_login("fx11", "fx11@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_fx_rates(db, 10)
    finally:
        db.close()

    resp = client.get("/api/v3/fx/volatility", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["currencies"]) == 9
