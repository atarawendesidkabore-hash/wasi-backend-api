"""
WASI Trade Corridor Intelligence — Integration + Unit Tests

Tests the /api/v3/corridors/ endpoints and the CorridorIntelligenceEngine.
Seeds corridor definitions, road corridor data, FX rates, and bilateral trade.
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import Base, Country, RoadCorridor, BilateralTrade, NewsEvent
from src.database.corridor_models import TradeCorridor, CorridorAssessment
from src.database.fx_models import FxDailyRate
from src.engines.corridor_engine import (
    CorridorIntelligenceEngine, seed_corridors, CORRIDOR_SEEDS,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=True)


# ── Helpers ──────────────────────────────────────────────────────────────

def _register_and_login(username="coruser", email="cor@test.com", password="CorPass123"):
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


def _seed_corridors(db):
    """Seed the 10 trade corridor definitions."""
    seed_corridors(db)


def _seed_road_data(db):
    """Seed RoadCorridor data for testing transport score."""
    from src.database.models import Country
    ng = db.query(Country).filter(Country.code == "NG").first()
    ci = db.query(Country).filter(Country.code == "CI").first()
    gh = db.query(Country).filter(Country.code == "GH").first()
    sn = db.query(Country).filter(Country.code == "SN").first()

    today = date.today()
    corridors = [
        (ng, "LAGOS-ABIDJAN", 4.2, 18.0, 62.0, 4200),
        (ci, "ABIDJAN-BAMAKO", 5.0, 16.0, 64.0, 3100),
        (gh, "TEMA-OUAGADOUGOU", 5.8, 24.0, 55.0, 2800),
        (sn, "DAKAR-BAMAKO", 6.5, 20.0, 58.0, 1800),
    ]
    for country, name, transit, border, quality, trucks in corridors:
        if country is None:
            continue
        db.add(RoadCorridor(
            country_id=country.id,
            period_date=today,
            corridor_name=name,
            avg_transit_days=transit,
            border_wait_hours=border,
            road_quality_score=quality,
            truck_count=trucks,
            road_index=65.0,
            data_source="test_seed",
            confidence=0.75,
        ))
    db.commit()


def _seed_fx_rates(db, n_days=5):
    """Seed FX rates for trade cost computation."""
    today = date.today()
    rates = {"NGN": 1550.0, "GHS": 15.2, "XOF": 603.5}
    for cc, base_rate in rates.items():
        for d in range(n_days):
            day = today - timedelta(days=n_days - 1 - d)
            db.add(FxDailyRate(
                currency_code=cc,
                rate_date=day,
                rate_to_usd=base_rate,
                rate_to_eur=round(base_rate / 0.92, 6),
                rate_to_xof=round(base_rate / 603.5, 6),
                data_source="test_seed",
                confidence=1.0,
            ))
    db.commit()


def _seed_bilateral_trade(db):
    """Seed bilateral trade data between corridor endpoints."""
    ng = db.query(Country).filter(Country.code == "NG").first()
    ci = db.query(Country).filter(Country.code == "CI").first()
    gh = db.query(Country).filter(Country.code == "GH").first()
    sn = db.query(Country).filter(Country.code == "SN").first()

    pairs = [
        (ng, "CI", 850_000_000, 420_000_000),
        (ci, "NG", 420_000_000, 850_000_000),
        (gh, "BF", 320_000_000, 180_000_000),
        (sn, "ML", 280_000_000, 150_000_000),
        (ci, "ML", 350_000_000, 200_000_000),
        (ci, "GH", 200_000_000, 250_000_000),
    ]
    for country, partner, exports, imports in pairs:
        if country is None:
            continue
        db.add(BilateralTrade(
            country_id=country.id,
            partner_code=partner,
            partner_name=partner,
            year=2024,
            export_value_usd=exports,
            import_value_usd=imports,
            total_trade_usd=exports + imports,
            trade_balance_usd=exports - imports,
            data_source="test_seed",
            confidence=0.80,
        ))
    db.commit()


def _seed_news_event(db, country_code, event_type="PORT_DISRUPTION", magnitude=-15):
    """Seed a news event for risk score testing."""
    from datetime import datetime, timezone
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    db.add(NewsEvent(
        country_id=country.id,
        event_type=event_type,
        headline=f"Test {event_type} in {country_code}",
        magnitude=magnitude,
        detected_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        is_active=True,
    ))
    db.commit()


def _seed_all(db):
    """Full seed for integration tests."""
    _seed_corridors(db)
    _seed_road_data(db)
    _seed_fx_rates(db)
    _seed_bilateral_trade(db)


# ── Engine Unit Tests ────────────────────────────────────────────────────

class TestCorridorEngine:

    def test_seed_corridors(self):
        db = TestingSessionLocal()
        try:
            count = seed_corridors(db)
            assert count == 10
            assert db.query(TradeCorridor).count() == 10
            # Second call should skip
            count2 = seed_corridors(db)
            assert count2 == 0
        finally:
            db.close()

    def test_transport_score_with_road_data(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            _seed_road_data(db)
            engine = CorridorIntelligenceEngine(db)
            score = engine._transport_score("NG", "CI", "LAGOS-ABIDJAN")
            assert score is not None
            assert 0 <= score <= 100
        finally:
            db.close()

    def test_fx_score_same_zone(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            _seed_fx_rates(db)
            engine = CorridorIntelligenceEngine(db)
            score = engine._fx_score("CI", "SN")
            assert score is not None
            assert score == 100.0  # Same CFA zone → zero FX cost
        finally:
            db.close()

    def test_fx_score_cross_zone(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            _seed_fx_rates(db)
            engine = CorridorIntelligenceEngine(db)
            score = engine._fx_score("NG", "CI")
            assert score is not None
            assert score < 100  # Cross-zone → has FX cost
            assert score > 0
        finally:
            db.close()

    def test_trade_volume_score(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            _seed_bilateral_trade(db)
            engine = CorridorIntelligenceEngine(db)
            score = engine._trade_volume_score("NG", "CI")
            assert score is not None
            assert 0 < score <= 100
        finally:
            db.close()

    def test_risk_score_baseline(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            engine = CorridorIntelligenceEngine(db)
            score = engine._risk_score("CI", "SN")
            assert score == 80.0  # Baseline with no active events
        finally:
            db.close()

    def test_risk_score_with_disruption(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            _seed_news_event(db, "NG", "PORT_DISRUPTION", -15)
            engine = CorridorIntelligenceEngine(db)
            score = engine._risk_score("NG", "CI")
            assert score < 80.0  # Should drop due to active event
        finally:
            db.close()

    def test_assess_corridor(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            result = engine.assess_corridor("LAGOS-ABIDJAN")
            db.commit()
            assert result is not None
            assert result["corridor_code"] == "LAGOS-ABIDJAN"
            assert result["from_country_code"] == "NG"
            assert result["to_country_code"] == "CI"
            assert result["corridor_composite"] is not None
            assert 0 <= result["corridor_composite"] <= 100
            assert result["bottleneck"] is not None
            assert result["data_sources_used"] >= 2
        finally:
            db.close()

    def test_corridor_ranking(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            engine.assess_all_corridors()
            db.commit()
            ranking = engine.get_corridor_ranking()
            assert len(ranking) == 10
            assert ranking[0]["rank"] == 1
            # First should have highest composite
            if ranking[0]["corridor_composite"] and ranking[-1]["corridor_composite"]:
                assert ranking[0]["corridor_composite"] >= ranking[-1]["corridor_composite"]
        finally:
            db.close()

    def test_bottleneck_identifies_weakest(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            engine.assess_corridor("LAGOS-ABIDJAN")
            db.commit()
            result = engine.get_bottleneck_analysis("LAGOS-ABIDJAN")
            assert result is not None
            assert len(result["bottlenecks"]) > 0
            # Bottlenecks should be sorted ascending
            scores = [b["score"] for b in result["bottlenecks"]]
            assert scores == sorted(scores)
            assert result["overall_assessment"] != ""
        finally:
            db.close()

    def test_dashboard_aggregate(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            engine.assess_all_corridors()
            db.commit()
            dashboard = engine.get_ecowas_corridor_dashboard()
            assert dashboard["total_corridors"] == 10
            assert dashboard["avg_corridor_score"] is not None
            assert dashboard["best_corridor"] is not None
            assert dashboard["worst_corridor"] is not None
            assert len(dashboard["corridors"]) == 10
        finally:
            db.close()

    def test_corridor_comparison(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            result = engine.get_corridor_comparison(["LAGOS-ABIDJAN", "DAKAR-BAMAKO"])
            db.commit()
            assert result["count"] == 2
            assert len(result["corridors"]) == 2
            assert "best_on" in result
        finally:
            db.close()

    def test_corridor_history(self):
        db = TestingSessionLocal()
        try:
            _seed_all(db)
            engine = CorridorIntelligenceEngine(db)
            engine.assess_corridor("LAGOS-ABIDJAN")
            db.commit()
            result = engine.get_corridor_history("LAGOS-ABIDJAN", 30)
            assert result is not None
            assert result["corridor_code"] == "LAGOS-ABIDJAN"
            assert len(result["history"]) >= 1
        finally:
            db.close()

    def test_assess_invalid_corridor(self):
        db = TestingSessionLocal()
        try:
            _seed_corridors(db)
            engine = CorridorIntelligenceEngine(db)
            result = engine.assess_corridor("NONEXISTENT")
            assert result is None
        finally:
            db.close()


# ── API Integration Tests ────────────────────────────────────────────────

def _seed_and_get_token():
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()
    return _register_and_login()


def test_corridors_unauthenticated():
    resp = client.get("/api/v3/corridors/")
    assert resp.status_code in (401, 403)


def test_list_corridors():
    token = _seed_and_get_token()
    resp = client.get("/api/v3/corridors/", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 10
    assert len(data["corridors"]) == 10
    codes = {c["corridor_code"] for c in data["corridors"]}
    assert "LAGOS-ABIDJAN" in codes
    assert "TEMA-OUAGA" in codes


def test_corridor_detail():
    token = _register_and_login("cor2", "cor2@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    resp = client.get("/api/v3/corridors/LAGOS-ABIDJAN", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["corridor_code"] == "LAGOS-ABIDJAN"
    assert data["from_country_code"] == "NG"
    assert data["to_country_code"] == "CI"
    assert data["corridor_composite"] is not None


def test_corridor_invalid():
    token = _register_and_login("cor3", "cor3@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_corridors(db)
    finally:
        db.close()
    resp = client.get("/api/v3/corridors/INVALID", headers=_auth(token))
    assert resp.status_code == 404


def test_corridor_ranking():
    token = _register_and_login("cor4", "cor4@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    resp = client.get("/api/v3/corridors/ranking", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rankings"]) == 10
    assert data["rankings"][0]["rank"] == 1


def test_corridor_comparison():
    token = _register_and_login("cor5", "cor5@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    resp = client.get(
        "/api/v3/corridors/compare?codes=LAGOS-ABIDJAN,DAKAR-BAMAKO",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert "best_on" in data


def test_corridor_bottleneck():
    token = _register_and_login("cor6", "cor6@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    resp = client.get("/api/v3/corridors/LAGOS-ABIDJAN/bottleneck", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["corridor_code"] == "LAGOS-ABIDJAN"
    assert len(data["bottlenecks"]) > 0
    assert data["overall_assessment"] != ""


def test_corridor_dashboard():
    token = _register_and_login("cor7", "cor7@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    resp = client.get("/api/v3/corridors/dashboard", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_corridors"] == 10
    assert "avg_corridor_score" in data
    assert "weighted_corridor_health" in data
    assert "best_corridor" in data


def test_corridor_history_api():
    token = _register_and_login("cor8", "cor8@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_all(db)
    finally:
        db.close()

    # First trigger an assessment
    client.get("/api/v3/corridors/LAGOS-ABIDJAN", headers=_auth(token))
    # Then get history
    resp = client.get("/api/v3/corridors/LAGOS-ABIDJAN/history?days=30", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["corridor_code"] == "LAGOS-ABIDJAN"
    assert len(data["history"]) >= 1


def test_corridor_history_invalid_days():
    token = _register_and_login("cor9", "cor9@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_corridors(db)
    finally:
        db.close()
    resp = client.get(
        "/api/v3/corridors/LAGOS-ABIDJAN/history?days=999",
        headers=_auth(token),
    )
    assert resp.status_code == 400
