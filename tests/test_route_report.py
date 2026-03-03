"""
WASI Crowdsourced Route Report — Integration Tests

Tests the USSD Option 0 (Route Report) flow, aggregation, bridge to
RoadCorridor, and the API endpoints under /api/v2/ussd/routes/.
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import Country, RoadCorridor
from src.database.ussd_models import USSDRouteReport, USSDDailyAggregate
from src.engines.ussd_engine import (
    USSDMenuEngine, USSDDataAggregator,
    CORRIDORS, REPORT_TYPES, ROAD_SURFACES, FUEL_TYPES, REPORTER_TYPES,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────

def _register_and_login(username="route_user", email="route@test.com", password="RoutePass123"):
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


def _seed_route_reports(db, country_code="CI", days=3):
    """Seed route reports for testing."""
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    today = date.today()
    for day_offset in range(days):
        d = today - timedelta(days=day_offset)
        db.add(USSDRouteReport(
            country_id=country.id,
            period_date=d,
            corridor_code="ABIDJAN-OUAGADOUGOU",
            corridor_name="Abidjan - Ouagadougou",
            report_type="ROAD_CONDITION",
            road_surface="PAVED",
            condition_score=85.0,
            reporter_phone_hash="test_hash_123",
            reporter_type="TRUCKER",
            reporter_count=5,
            local_currency="XOF",
            confidence=0.55,
        ))
        db.add(USSDRouteReport(
            country_id=country.id,
            period_date=d,
            corridor_code="ABIDJAN-OUAGADOUGOU",
            corridor_name="Abidjan - Ouagadougou",
            report_type="BORDER_WAIT",
            wait_hours=8.0,
            reporter_phone_hash="test_hash_456",
            reporter_type="TRADER",
            reporter_count=3,
            local_currency="XOF",
            confidence=0.50,
        ))
    db.commit()


# ── Tests ────────────────────────────────────────────────────────

class TestCorridorMaps:
    """Verify reference maps are properly defined."""

    def test_corridors_count(self):
        assert len(CORRIDORS) == 12

    def test_report_types_count(self):
        assert len(REPORT_TYPES) == 4

    def test_corridor_tuple_structure(self):
        for key, val in CORRIDORS.items():
            assert len(val) == 4, f"Corridor {key} should have 4 elements"
            code, origin, dest, name = val
            assert len(origin) == 2
            assert len(dest) == 2


class TestUSSDRouteReportFlow:
    """Test USSD menu option 0 (route report) flow."""

    def test_main_menu_shows_option_0(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_menu_001",
                service_code="*384*WASI#",
                phone_number="+22507000001",
                text="",
            )
            assert "0. Rapport Route" in response
            assert response.startswith("CON")
        finally:
            db.close()

    def test_step0_corridor_list(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_001",
                service_code="*384*WASI#",
                phone_number="+22507000002",
                text="0",
            )
            assert response.startswith("CON")
            assert "Abidjan - Ouagadougou" in response
            assert stype == "ROUTE_REPORT"
        finally:
            db.close()

    def test_step1_report_type(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_002",
                service_code="*384*WASI#",
                phone_number="+22507000003",
                text="0*1",  # Corridor 1
            )
            assert response.startswith("CON")
            assert "État route" in response
            assert "Attente frontière" in response
        finally:
            db.close()

    def test_step2_reporter_type(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_003",
                service_code="*384*WASI#",
                phone_number="+22507000004",
                text="0*1*1",  # Corridor 1, Road condition
            )
            assert response.startswith("CON")
            assert "Chauffeur" in response
        finally:
            db.close()

    def test_step3_road_surface(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_004",
                service_code="*384*WASI#",
                phone_number="+22507000005",
                text="0*1*1*1",  # Corridor 1, Road condition, Trucker
            )
            assert response.startswith("CON")
            assert "Goudronné" in response
        finally:
            db.close()

    def test_step4_confirmation(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_005",
                service_code="*384*WASI#",
                phone_number="+22507000006",
                text="0*1*1*1*1",  # Corridor 1, Road condition, Trucker, Paved
            )
            assert response.startswith("CON")
            assert "Confirmer" in response
            assert "50 FCFA" in response
        finally:
            db.close()

    def test_full_flow_road_condition(self):
        """Complete flow: corridor → type → reporter → surface → confirm → save."""
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_full_001",
                service_code="*384*WASI#",
                phone_number="+22507000007",
                text="0*1*1*1*1*1",  # Corridor 1, Road, Trucker, Paved, Confirm
            )
            assert response.startswith("END")
            assert "Merci" in response
            assert "WASI vous remercie" in response
            assert stype == "ROUTE_REPORT"

            # Verify data was saved
            report = db.query(USSDRouteReport).first()
            assert report is not None
            assert report.corridor_code == "ABIDJAN-OUAGADOUGOU"
            assert report.report_type == "ROAD_CONDITION"
            assert report.road_surface == "PAVED"
            assert report.condition_score == 85.0
            assert report.reporter_type == "TRUCKER"
        finally:
            db.close()

    def test_full_flow_border_wait(self):
        """Complete flow for border wait report."""
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_border_001",
                service_code="*384*WASI#",
                phone_number="+22507000008",
                text="0*6*2*2*12*1",  # Lagos-Cotonou, Border wait, Trader, 12h, Confirm
            )
            assert response.startswith("END")
            assert "Merci" in response

            report = db.query(USSDRouteReport).filter(
                USSDRouteReport.report_type == "BORDER_WAIT"
            ).first()
            assert report is not None
            assert report.corridor_code == "LAGOS-COTONOU"
            assert report.wait_hours == 12.0
        finally:
            db.close()

    def test_cancel_flow(self):
        """User cancels at confirmation step."""
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_cancel_001",
                service_code="*384*WASI#",
                phone_number="+22507000009",
                text="0*1*1*1*1*2",  # All steps then Cancel
            )
            assert response.startswith("END")
            assert "annulé" in response

            # No data saved
            count = db.query(USSDRouteReport).count()
            assert count == 0
        finally:
            db.close()

    def test_invalid_corridor(self):
        db = TestingSessionLocal()
        try:
            engine = USSDMenuEngine(db)
            response, stype = engine.process_callback(
                session_id="test_route_invalid_001",
                service_code="*384*WASI#",
                phone_number="+22507000010",
                text="0*99",
            )
            assert response.startswith("END")
            assert "invalide" in response
        finally:
            db.close()


class TestRouteAggregation:
    """Test aggregation scoring of route reports."""

    def test_score_route_condition(self):
        db = TestingSessionLocal()
        try:
            _seed_route_reports(db, "CI", days=1)
            aggregator = USSDDataAggregator(db)
            country = db.query(Country).filter(Country.code == "CI").first()
            score = aggregator._score_route_condition(country.id, date.today())
            assert score is not None
            assert 0 <= score <= 100
        finally:
            db.close()

    def test_aggregate_includes_route(self):
        db = TestingSessionLocal()
        try:
            _seed_route_reports(db, "CI", days=1)
            aggregator = USSDDataAggregator(db)
            result = aggregator.aggregate_country("CI", date.today())
            assert "route_condition_score" in result
            assert result["route_condition_score"] is not None
        finally:
            db.close()


class TestBridgeToRoadCorridor:
    """Test bridge from USSDRouteReport to RoadCorridor."""

    def test_bridge_creates_road_corridor(self):
        db = TestingSessionLocal()
        try:
            _seed_route_reports(db, "CI", days=1)
            from src.tasks.ussd_aggregation import bridge_route_to_road_corridors
            result = bridge_route_to_road_corridors(db)
            assert result["status"] == "completed"
            assert result["corridors_updated"] >= 1

            # Verify RoadCorridor was created
            road = db.query(RoadCorridor).filter(
                RoadCorridor.corridor_name == "ABIDJAN-OUAGADOUGOU"
            ).first()
            assert road is not None
            assert road.data_source == "ussd_crowdsource"
        finally:
            db.close()

    def test_bridge_no_data(self):
        db = TestingSessionLocal()
        try:
            from src.tasks.ussd_aggregation import bridge_route_to_road_corridors
            result = bridge_route_to_road_corridors(db)
            assert result["status"] == "no_data"
        finally:
            db.close()


class TestRouteAPIEndpoints:
    """Test the /api/v2/ussd/routes/ endpoints."""

    def test_get_route_reports(self):
        db = TestingSessionLocal()
        try:
            _seed_route_reports(db, "CI", days=3)
        finally:
            db.close()

        token = _register_and_login("route_api_user1", "route1@test.com")
        resp = client.get(
            "/api/v2/ussd/routes/CI",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "CI"
        assert len(data["reports"]) >= 1
        assert data["reports"][0]["corridor_code"] == "ABIDJAN-OUAGADOUGOU"

    def test_get_route_reports_with_corridor_filter(self):
        db = TestingSessionLocal()
        try:
            _seed_route_reports(db, "CI", days=1)
        finally:
            db.close()

        token = _register_and_login("route_api_user2", "route2@test.com")
        resp = client.get(
            "/api/v2/ussd/routes/CI?corridor=ABIDJAN-OUAGADOUGOU",
            headers=_auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["corridor_code"] == "ABIDJAN-OUAGADOUGOU" for r in data["reports"])

    def test_get_route_reports_404(self):
        token = _register_and_login("route_api_user3", "route3@test.com")
        resp = client.get(
            "/api/v2/ussd/routes/ZZ",
            headers=_auth_header(token),
        )
        assert resp.status_code == 404
