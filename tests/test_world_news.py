"""
WASI Backend API — World News Intelligence Tests

Tests for:
  /api/v3/news/ endpoints (worldwide, daily-briefing, impact, exposure, refresh)
  Engine unit tests (3-layer scoring, magnitude, cascade thresholds)
"""
import json
from datetime import date, datetime, timezone, timedelta

from fastapi.testclient import TestClient

from src.main import app
from src.database.models import Country
from src.database.world_news_models import (
    WorldNewsEvent, NewsImpactAssessment, DailyNewsBriefing,
)
from src.engines.world_news_engine import (
    score_layer1_keyword,
    score_layer2_supply_chain,
    score_layer3_transmission,
    compute_relevance_score,
    compute_country_magnitude,
    determine_magnitude_sign,
    score_headline,
    RELEVANCE_THRESHOLD_CASCADE,
)
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)

# ── User counter to avoid collisions ─────────────────────────────────────────
_user_counter = 0


def _register_and_login():
    global _user_counter
    _user_counter += 1
    username = f"wnuser{_user_counter}"
    email = f"wn{_user_counter}@test.com"
    password = "WnPass123"
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _topup(token, amount=200.0):
    client.post(
        "/api/payment/topup",
        json={"amount": amount, "reference_id": f"wn-test-{amount}-{_user_counter}"},
        headers=_auth(token),
    )


def _seed_world_event(
    headline="Oil price surge shocks global markets",
    event_type="GLOBAL_COMMODITY_SHOCK",
    relevance=0.65,
    magnitude=-10.0,
    cascaded=False,
):
    """Seed a WorldNewsEvent and return its id."""
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    event = WorldNewsEvent(
        event_type=event_type,
        headline=headline,
        summary="Global oil prices surged after OPEC+ cut announcement",
        source_url="https://example.com/oil",
        source_name="Test Feed",
        source_region="GLOBAL",
        relevance_score=relevance,
        relevance_layer1_keyword=0.25,
        relevance_layer2_supply_chain=0.50,
        relevance_layer3_transmission=0.90,
        keywords_matched=json.dumps(["crude oil", "opec"]),
        global_magnitude=magnitude,
        detected_at=now,
        expires_at=now + timedelta(days=14),
        is_active=True,
        cascaded=cascaded,
    )
    db.add(event)
    db.commit()
    event_id = event.id
    db.close()
    return event_id


def _seed_impact_assessment(world_event_id, country_code="NG", magnitude=-5.0):
    """Seed a NewsImpactAssessment and return its id."""
    db = TestingSessionLocal()
    assessment = NewsImpactAssessment(
        world_news_event_id=world_event_id,
        country_code=country_code,
        direct_impact=0.60,
        indirect_impact=0.25,
        systemic_impact=0.27,
        country_magnitude=magnitude,
        transmission_channel="oil_price",
        explanation="oil_price: test assessment",
        news_event_created=False,
    )
    db.add(assessment)
    db.commit()
    assessment_id = assessment.id
    db.close()
    return assessment_id


# ═════════════════════════════════════════════════════════════════════
# AUTH TESTS — 401 without token
# ═════════════════════════════════════════════════════════════════════

def test_worldwide_requires_auth():
    resp = client.get("/api/v3/news/worldwide")
    assert resp.status_code == 401


def test_daily_briefing_requires_auth():
    resp = client.get("/api/v3/news/daily-briefing")
    assert resp.status_code == 401


def test_impact_requires_auth():
    resp = client.get("/api/v3/news/impact/1")
    assert resp.status_code == 401


def test_exposure_requires_auth():
    resp = client.get("/api/v3/news/country/NG/exposure")
    assert resp.status_code == 401


def test_refresh_requires_auth():
    resp = client.post("/api/v3/news/refresh")
    assert resp.status_code == 401


# ═════════════════════════════════════════════════════════════════════
# GET /worldwide
# ═════════════════════════════════════════════════════════════════════

def test_worldwide_returns_empty():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/worldwide", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_worldwide_returns_events():
    _seed_world_event()
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/worldwide", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["event_type"] == "GLOBAL_COMMODITY_SHOCK"


def test_worldwide_filter_event_type():
    _seed_world_event(event_type="GLOBAL_SHIPPING_DISRUPTION",
                      headline="Suez Canal blocked by grounded vessel")
    token = _register_and_login()
    _topup(token)
    resp = client.get(
        "/api/v3/news/worldwide?event_type=GLOBAL_SHIPPING_DISRUPTION",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["event_type"] == "GLOBAL_SHIPPING_DISRUPTION"


def test_worldwide_filter_min_relevance():
    _seed_world_event(relevance=0.10, headline="Low relevance event test")
    _seed_world_event(relevance=0.80, headline="High relevance event test")
    token = _register_and_login()
    _topup(token)
    resp = client.get(
        "/api/v3/news/worldwide?min_relevance=0.5",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["relevance_score"] >= 0.5


def test_worldwide_pagination():
    for i in range(3):
        _seed_world_event(headline=f"Paginated event {i}", relevance=0.50 + i * 0.1)
    token = _register_and_login()
    _topup(token)
    resp = client.get(
        "/api/v3/news/worldwide?page=1&page_size=2",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["page_size"] == 2


# ═════════════════════════════════════════════════════════════════════
# GET /daily-briefing
# ═════════════════════════════════════════════════════════════════════

def test_daily_briefing_generates():
    _seed_world_event()
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/daily-briefing", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "briefing_date" in data
    assert "top_events" in data
    assert "country_impacts" in data
    assert "watchlist" in data


def test_daily_briefing_cached():
    """Second call should return cached briefing (same date)."""
    _seed_world_event(headline="Cached briefing test event")
    token = _register_and_login()
    _topup(token)
    # First call generates
    resp1 = client.get("/api/v3/news/daily-briefing", headers=_auth(token))
    assert resp1.status_code == 200
    # Second call returns cached
    resp2 = client.get("/api/v3/news/daily-briefing", headers=_auth(token))
    assert resp2.status_code == 200
    assert resp1.json()["generated_at"] == resp2.json()["generated_at"]


# ═════════════════════════════════════════════════════════════════════
# GET /impact/{event_id}
# ═════════════════════════════════════════════════════════════════════

def test_impact_valid_event():
    event_id = _seed_world_event()
    _seed_impact_assessment(event_id, "NG", -5.0)
    _seed_impact_assessment(event_id, "GH", -3.0)
    token = _register_and_login()
    _topup(token)
    resp = client.get(f"/api/v3/news/impact/{event_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["countries_affected"] == 2
    assert data["world_event"]["id"] == event_id
    assert len(data["assessments"]) == 2


def test_impact_invalid_event():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/impact/99999", headers=_auth(token))
    assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════════════
# GET /country/{cc}/exposure
# ═════════════════════════════════════════════════════════════════════

def test_exposure_valid_country():
    event_id = _seed_world_event()
    _seed_impact_assessment(event_id, "NG", -5.0)
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/country/NG/exposure", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["country_code"] == "NG"
    assert data["total_active_global_events"] >= 1
    assert data["net_global_adjustment"] < 0


def test_exposure_invalid_country():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/country/ZZ/exposure", headers=_auth(token))
    assert resp.status_code == 404


def test_exposure_no_events():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v3/news/country/CV/exposure", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_active_global_events"] == 0
    assert data["net_global_adjustment"] == 0.0


# ═════════════════════════════════════════════════════════════════════
# POST /refresh
# ═════════════════════════════════════════════════════════════════════

def test_refresh_executes():
    token = _register_and_login()
    _topup(token)
    resp = client.post("/api/v3/news/refresh", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "global_events_detected" in data
    assert "briefing_generated" in data


# ═════════════════════════════════════════════════════════════════════
# ENGINE UNIT TESTS — direct function calls
# ═════════════════════════════════════════════════════════════════════

def test_layer1_keyword_scoring():
    """Verify exact threshold steps."""
    score0, kw0 = score_layer1_keyword("something unrelated")
    assert score0 == 0.0
    assert kw0 == []

    score1, kw1 = score_layer1_keyword("cocoa prices rising")
    assert score1 == 0.25
    assert "cocoa" in kw1

    # "nigeria" also contains "niger" substring → matches both → 3 keywords
    score2, kw2 = score_layer1_keyword("nigeria cocoa exports")
    assert score2 == 0.75
    assert len(kw2) == 3  # nigeria, cocoa, niger (substring)

    score3, kw3 = score_layer1_keyword("lagos cocoa exports")
    assert score3 == 0.50
    assert len(kw3) == 2  # lagos, cocoa

    score4, kw4 = score_layer1_keyword("nigeria ghana cocoa gold ecowas policy")
    assert score4 == 1.0
    assert len(kw4) >= 4


def test_layer2_supply_chain_scoring():
    """Verify partner weight returns."""
    assert score_layer2_supply_chain("nothing relevant here") == 0.0
    assert score_layer2_supply_chain("china exports rising") == 0.95
    assert score_layer2_supply_chain("india trade deficit") == 0.80
    assert score_layer2_supply_chain("suez canal blocked") == 0.85
    # Max of multiple matches
    assert score_layer2_supply_chain("china and india trade war") == 0.95


def test_layer3_transmission_scoring():
    """Verify channel detection and country impacts."""
    score, channel, impacts = score_layer3_transmission("nothing here")
    assert score == 0.0
    assert channel == ""
    assert impacts == {}

    score, channel, impacts = score_layer3_transmission("oil price surge brent crude")
    assert score == 0.90
    assert channel == "oil_price"
    assert "NG" in impacts
    assert impacts["NG"] == 0.95

    score, channel, impacts = score_layer3_transmission("cocoa price crash")
    assert score == 0.95
    assert channel == "cocoa_market"
    assert "CI" in impacts


def test_composite_relevance_score():
    """Verify weighted combination formula."""
    # All zeros
    assert compute_relevance_score(0.0, 0.0, 0.0) == 0.0

    # All ones
    assert compute_relevance_score(1.0, 1.0, 1.0) == 1.0

    # Exact calculation: 0.30*0.5 + 0.30*0.5 + 0.40*0.5 = 0.15+0.15+0.20 = 0.50
    assert compute_relevance_score(0.5, 0.5, 0.5) == 0.5

    # Verify precision
    result = compute_relevance_score(0.25, 0.30, 0.90)
    # 0.30*0.25 + 0.30*0.30 + 0.40*0.90 = 0.075 + 0.09 + 0.36 = 0.525
    assert result == 0.525


def test_country_magnitude_computation():
    """Verify cascade formula with tier multipliers."""
    # Primary country (NG, weight=0.28): tier_mul = 1.0
    mag = compute_country_magnitude(-10.0, 0.65, 0.95, 0.28)
    expected = round(-10.0 * 0.65 * 0.95 * 1.0, 4)
    assert mag == expected

    # Secondary country (BF, weight=0.04): tier_mul = 0.8
    mag = compute_country_magnitude(-10.0, 0.65, 0.50, 0.04)
    expected = round(-10.0 * 0.65 * 0.50 * 0.8, 4)
    assert mag == expected

    # Tertiary country (CV, weight=0.01): tier_mul = 0.6
    mag = compute_country_magnitude(-10.0, 0.65, 0.30, 0.01)
    expected = round(-10.0 * 0.65 * 0.30 * 0.6, 4)
    assert mag == expected

    # Clamping test: extreme values
    mag = compute_country_magnitude(-25.0, 1.0, 1.0, 0.28)
    assert mag == -25.0  # clamped


def test_magnitude_sign_determination():
    """Verify positive/negative sign detection."""
    # Clearly negative
    assert determine_magnitude_sign("Oil crisis crashes markets", -10.0) == -10.0

    # Clearly positive
    assert determine_magnitude_sign("Trade deal boosts recovery", -8.0) == 8.0

    # Neutral (uses default)
    assert determine_magnitude_sign("Update on market activity", -5.0) == -5.0


def test_relevance_below_cascade_threshold():
    """Events below 0.4000 should not trigger cascade in score_headline."""
    # Text with no West Africa references or trade partners — only event type keywords
    result = score_headline("semiconductor chip shortage hits factories")
    if result["event_type"]:
        # Layer1=0 (no WA keyword), Layer2=0 (no partner), Layer3 may match
        # Composite = 0.30*0 + 0.30*0 + 0.40*L3
        # For L3 to push above 0.40: needs L3 >= 1.0 → 0.40*1.0 = 0.40
        # But supply_chain channel scores are capped at 0.80 for this type
        # So composite can't exceed 0.40*0.80 = 0.32 without L1 or L2 matches
        assert result["relevance_score"] < RELEVANCE_THRESHOLD_CASCADE
