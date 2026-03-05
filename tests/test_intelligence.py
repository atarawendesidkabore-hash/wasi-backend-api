"""
Personalized Data Intelligence — Test Suite

Tests cover:
  1. ProfileCard: reputation breakdown, weakest factor, tier progress
  2. DataSpecialization: pillar/type distribution, expertise labels
  3. QualityTrends: confidence trajectory, direction, percentile
  4. EarningProjection: monthly rate, what-if scenarios
  5. CoverageOpportunities: underserved types, geographic gaps
  6. Nudges: streak risk, tier progress, priority ordering
  7. WrappedSummary: annual stats, peer percentile, badges
  8. API endpoints: 7 GET endpoints (all FREE)
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient

from src.main import app
from tests.conftest import TestingSessionLocal
from src.database.engagement_models import (
    DataWallet, UserBadge, BadgeDefinition,
    Challenge, ChallengeParticipation, ImpactRecord,
)
from src.database.tokenization_models import DataToken
from src.database.royalty_models import RoyaltyPool, RoyaltyDistribution
from src.database.models import Country
from src.engines.intelligence_engine import ContributorIntelligenceEngine

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────

def _register_and_login(username="intuser", email="int@test.com", credits=0):
    client.post("/api/auth/register", json={
        "username": username, "email": email, "password": "TestPass123",
    })
    resp = client.post("/api/auth/login", data={
        "username": username, "password": "TestPass123",
    })
    token = resp.json().get("access_token", "")
    if credits > 0:
        db = TestingSessionLocal()
        from src.database.models import User
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.x402_balance = credits
            db.commit()
        db.close()
    return {"Authorization": f"Bearer {token}"}


def _seed_wallet(db, phone_hash="intel_001", country_code="NG", **kwargs):
    """Create a DataWallet with given attributes."""
    defaults = {
        "total_reports": 50,
        "total_earned_cfa": 5000,
        "total_cross_validated": 20,
        "current_streak": 15,
        "longest_streak": 25,
        "last_report_date": date.today() - timedelta(days=1),
        "reputation_score": 45.0,
        "tier": "SILVER",
        "current_multiplier": 1.35,
    }
    defaults.update(kwargs)
    wallet = DataWallet(
        contributor_phone_hash=phone_hash,
        country_code=country_code,
        **defaults,
    )
    db.add(wallet)
    db.commit()
    return wallet


def _seed_tokens(db, phone_hash="intel_001", country_code="NG",
                 token_type="MARKET_PRICE", count=10, confidence=0.60):
    """Seed DataToken records for a contributor."""
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    today = date.today()
    for i in range(count):
        db.add(DataToken(
            token_id=f"it_{phone_hash}_{token_type}_{i}",
            country_id=country.id,
            pillar="CITIZEN_DATA",
            token_type=token_type,
            contributor_phone_hash=phone_hash,
            token_value_cfa=100.0,
            status="validated",
            confidence=confidence,
            period_date=today - timedelta(days=i % 20),
            location_name=f"Region_{i % 3}",
        ))
    db.commit()


# ═══════════════════════════════════════════════════════════════════════
# 1. Profile Card
# ═══════════════════════════════════════════════════════════════════════

class TestProfileCard:

    def test_new_user_empty_profile(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_profile_card(db, "nonexistent")
            assert result["tier"] == "BRONZE"
            assert result["reputation_score"] == 0
            assert result["tier_progress"]["next_tier"] == "SILVER"
            assert result["tier_progress"]["points_to_next"] == 25.0
            # Weakest factor should exist
            assert result["weakest_factor"]["factor"] in [
                "volume", "consistency", "quality", "badges", "community"
            ]
        finally:
            db.close()

    def test_active_user_breakdown(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "profile_001", total_reports=50, current_streak=10,
                         total_cross_validated=30, reputation_score=40.0, tier="SILVER")
            result = ContributorIntelligenceEngine.get_profile_card(db, "profile_001")

            assert result["tier"] == "SILVER"
            assert result["reputation_score"] == 40.0
            assert result["country_code"] == "NG"

            # Check breakdown has all 5 components
            breakdown = result["reputation_breakdown"]
            assert "volume" in breakdown
            assert "consistency" in breakdown
            assert "quality" in breakdown
            assert "badges" in breakdown
            assert "community" in breakdown

            # Volume: min(30, 50*0.3) = 15.0
            assert breakdown["volume"]["current"] == 15.0
        finally:
            db.close()

    def test_weakest_factor_is_community_when_no_challenges(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "profile_002", total_reports=100, current_streak=30,
                         total_cross_validated=80, reputation_score=55.0, tier="GOLD")
            result = ContributorIntelligenceEngine.get_profile_card(db, "profile_002")

            # With 0 challenges and 0 badges, community (0/10) or badges (0/15)
            # should have the largest gap
            wf = result["weakest_factor"]
            assert wf["factor"] in ["community", "badges"]
            assert wf["gap"] > 0
            assert len(wf["advice_en"]) > 0
            assert len(wf["advice_fr"]) > 0
        finally:
            db.close()

    def test_tier_progress_platinum_has_no_next(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "profile_003", reputation_score=85.0, tier="PLATINUM")
            result = ContributorIntelligenceEngine.get_profile_card(db, "profile_003")
            assert result["tier_progress"]["next_tier"] is None
            assert result["tier_progress"]["points_to_next"] == 0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 2. Data Specialization
# ═══════════════════════════════════════════════════════════════════════

class TestSpecialization:

    def test_empty_specialization(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_data_specialization(db, "nonexistent")
            assert result["total_tokens"] == 0
            assert result["expertise_label_en"] == "Data Reporter"
        finally:
            db.close()

    def test_single_type_specialization(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "spec_001")
            _seed_tokens(db, "spec_001", token_type="MARKET_PRICE", count=20)

            result = ContributorIntelligenceEngine.get_data_specialization(db, "spec_001")
            assert result["total_tokens"] == 20
            assert result["primary_pillar"] == "CITIZEN_DATA"
            assert result["expertise_label_en"] == "Market Price Expert"
            assert result["expertise_label_fr"] == "Expert Prix du Marché"

            # Single type → 100%
            types = result["token_type_distribution"]
            assert len(types) == 1
            assert types[0]["token_type"] == "MARKET_PRICE"
            assert types[0]["pct"] == 100.0
        finally:
            db.close()

    def test_diversified_types(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "spec_002")
            _seed_tokens(db, "spec_002", token_type="MARKET_PRICE", count=10)
            _seed_tokens(db, "spec_002", token_type="CROP_YIELD", count=8)
            _seed_tokens(db, "spec_002", token_type="ROAD_CONDITION", count=5)

            result = ContributorIntelligenceEngine.get_data_specialization(db, "spec_002")
            assert result["total_tokens"] == 23
            # MARKET_PRICE has the most → primary type
            types = result["token_type_distribution"]
            assert types[0]["token_type"] == "MARKET_PRICE"
            assert len(types) == 3

            # Country comparison
            assert result["country_comparison"]["your_token_types"] == 3
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 3. Quality Trends
# ═══════════════════════════════════════════════════════════════════════

class TestQualityTrends:

    def test_empty_quality(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_quality_trends(db, "nonexistent")
            assert result["monthly_trends"] == []
            assert result["confidence_direction"] == "stable"
        finally:
            db.close()

    def test_quality_with_data(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "qual_001")
            _seed_tokens(db, "qual_001", count=15, confidence=0.65)

            result = ContributorIntelligenceEngine.get_quality_trends(db, "qual_001")
            assert len(result["monthly_trends"]) >= 1
            # Should have reports
            assert result["monthly_trends"][0]["reports_count"] > 0
            assert result["monthly_trends"][0]["avg_confidence"] > 0
        finally:
            db.close()

    def test_country_percentile(self):
        db = TestingSessionLocal()
        try:
            # Create two contributors with different confidence
            _seed_wallet(db, "qual_low", reputation_score=20.0, tier="BRONZE")
            _seed_tokens(db, "qual_low", count=5, confidence=0.30)
            _seed_wallet(db, "qual_high", reputation_score=60.0, tier="GOLD")
            _seed_tokens(db, "qual_high", count=5, confidence=0.90)

            # High confidence should rank higher
            result_high = ContributorIntelligenceEngine.get_quality_trends(db, "qual_high")
            result_low = ContributorIntelligenceEngine.get_quality_trends(db, "qual_low")
            assert result_high["country_percentile"] >= result_low["country_percentile"]
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 4. Earning Projection
# ═══════════════════════════════════════════════════════════════════════

class TestEarningProjection:

    def test_no_history(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_earning_projection(db, "nonexistent")
            assert result["lifetime_earnings_cfa"] == 0
            assert result["current_monthly_rate_cfa"] == 0
        finally:
            db.close()

    def test_with_token_earnings(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "earn_001", total_earned_cfa=10000)
            _seed_tokens(db, "earn_001", count=20, confidence=0.70)

            result = ContributorIntelligenceEngine.get_earning_projection(db, "earn_001")
            assert result["lifetime_earnings_cfa"] == 10000
            # Tokens were seeded with value 100 CFA each, validated
            assert result["token_earnings_cfa"] > 0
        finally:
            db.close()

    def test_what_if_scenarios(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "earn_002", tier="SILVER", current_streak=10,
                         current_multiplier=1.35, total_earned_cfa=5000)
            _seed_tokens(db, "earn_002", count=10)

            result = ContributorIntelligenceEngine.get_earning_projection(db, "earn_002")
            # Should have next_tier and max_streak scenarios
            scenario_types = [s["scenario"] for s in result["what_if_scenarios"]]
            assert "next_tier" in scenario_types
            assert "max_streak" in scenario_types
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 5. Coverage Opportunities
# ═══════════════════════════════════════════════════════════════════════

class TestCoverageOpportunities:

    def test_empty_opportunities(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_coverage_opportunities(db, "nonexistent")
            assert result["country_code"] == "NG"
            assert isinstance(result["underserved_token_types"], list)
            assert isinstance(result["geographic_gaps"], list)
        finally:
            db.close()

    def test_underserved_types_found(self):
        db = TestingSessionLocal()
        try:
            # Create one contributor reporting only MARKET_PRICE
            _seed_wallet(db, "opp_001")
            _seed_tokens(db, "opp_001", token_type="MARKET_PRICE", count=20)

            result = ContributorIntelligenceEngine.get_coverage_opportunities(db, "opp_001")
            # Many token types should be underserved (0 reporters)
            assert len(result["underserved_token_types"]) > 0
        finally:
            db.close()

    def test_matching_challenges(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "opp_002")

            # Create an active challenge
            ch = Challenge(
                challenge_code="TEST_INTEL_CH",
                title_en="Test Challenge",
                title_fr="Défi Test",
                scope="COUNTRY",
                target_country_code="NG",
                goal_metric="citizen_reports",
                goal_target=100,
                current_progress=40,
                start_date=datetime.now(timezone.utc) - timedelta(days=5),
                end_date=datetime.now(timezone.utc) + timedelta(days=25),
                status="ACTIVE",
            )
            db.add(ch)
            db.commit()

            result = ContributorIntelligenceEngine.get_coverage_opportunities(db, "opp_002")
            assert len(result["matching_challenges"]) >= 1
            assert result["matching_challenges"][0]["title_fr"] == "Défi Test"
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 6. Nudges
# ═══════════════════════════════════════════════════════════════════════

class TestNudges:

    def test_onboarding_nudge_for_new_user(self):
        db = TestingSessionLocal()
        try:
            nudges = ContributorIntelligenceEngine.get_nudges(db, "nonexistent")
            assert len(nudges) == 1
            assert nudges[0]["type"] == "ONBOARDING"
            assert nudges[0]["priority"] == 1
        finally:
            db.close()

    def test_streak_risk_nudge(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "nudge_001", current_streak=20,
                         last_report_date=date.today() - timedelta(days=1))
            nudges = ContributorIntelligenceEngine.get_nudges(db, "nudge_001")
            streak_nudges = [n for n in nudges if n["type"] == "STREAK_RISK"]
            assert len(streak_nudges) >= 1
            assert streak_nudges[0]["priority"] == 1
        finally:
            db.close()

    def test_tier_progress_nudge(self):
        db = TestingSessionLocal()
        try:
            # Close to GOLD threshold (50)
            _seed_wallet(db, "nudge_002", reputation_score=45.0, tier="SILVER",
                         current_streak=3, last_report_date=date.today())
            nudges = ContributorIntelligenceEngine.get_nudges(db, "nudge_002")
            tier_nudges = [n for n in nudges if n["type"] == "TIER_PROGRESS"]
            assert len(tier_nudges) >= 1
            assert "GOLD" in tier_nudges[0]["message_en"]
        finally:
            db.close()

    def test_nudge_priority_ordering(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "nudge_003", current_streak=28,
                         reputation_score=48.0, tier="SILVER",
                         last_report_date=date.today() - timedelta(days=1))
            nudges = ContributorIntelligenceEngine.get_nudges(db, "nudge_003")
            # Should be sorted by priority
            for i in range(len(nudges) - 1):
                assert nudges[i]["priority"] <= nudges[i + 1]["priority"]
        finally:
            db.close()

    def test_max_5_nudges(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "nudge_004", current_streak=28,
                         reputation_score=48.0, tier="SILVER",
                         last_report_date=date.today() - timedelta(days=1))
            _seed_tokens(db, "nudge_004", count=10)
            nudges = ContributorIntelligenceEngine.get_nudges(db, "nudge_004")
            assert len(nudges) <= 5
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 7. Wrapped Summary
# ═══════════════════════════════════════════════════════════════════════

class TestWrappedSummary:

    def test_empty_year(self):
        db = TestingSessionLocal()
        try:
            result = ContributorIntelligenceEngine.get_wrapped_summary(db, "nonexistent", 2026)
            assert result["total_reports"] == 0
            assert result["total_earned_cfa"] == 0
            assert result["top_token_types"] == []
            assert result["months_active"] == 0
        finally:
            db.close()

    def test_wrapped_with_data(self):
        db = TestingSessionLocal()
        try:
            _seed_wallet(db, "wrap_001", longest_streak=25)
            _seed_tokens(db, "wrap_001", token_type="MARKET_PRICE", count=15)
            _seed_tokens(db, "wrap_001", token_type="CROP_YIELD", count=5)

            result = ContributorIntelligenceEngine.get_wrapped_summary(db, "wrap_001", 2026)
            assert result["total_reports"] == 20
            assert result["streak_record"] == 25
            assert len(result["top_token_types"]) >= 1
            assert result["top_token_types"][0]["token_type"] == "MARKET_PRICE"
            assert result["months_active"] >= 1
            assert result["regions_helped"] >= 1
            assert result["peer_percentile"] >= 0
        finally:
            db.close()

    def test_wrapped_peer_percentile(self):
        db = TestingSessionLocal()
        try:
            # Two contributors: one prolific, one sparse
            _seed_wallet(db, "wrap_top", longest_streak=30)
            _seed_tokens(db, "wrap_top", count=50, confidence=0.80)
            _seed_wallet(db, "wrap_low", longest_streak=3,
                         total_reports=5, reputation_score=10.0, tier="BRONZE")
            _seed_tokens(db, "wrap_low", count=3, confidence=0.30)

            top_result = ContributorIntelligenceEngine.get_wrapped_summary(db, "wrap_top", 2026)
            low_result = ContributorIntelligenceEngine.get_wrapped_summary(db, "wrap_low", 2026)
            assert top_result["peer_percentile"] >= low_result["peer_percentile"]
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 8. API Endpoints
# ═══════════════════════════════════════════════════════════════════════

class TestIntelligenceAPI:

    def test_profile_unauthorized(self):
        resp = client.get("/api/v3/intelligence/profile")
        assert resp.status_code in (401, 403)

    def test_profile_endpoint(self):
        headers = _register_and_login("intapi1", "intapi1@test.com")
        resp = client.get("/api/v3/intelligence/profile", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "reputation_breakdown" in data
        assert "weakest_factor" in data
        assert "tier_progress" in data

    def test_specialization_endpoint(self):
        headers = _register_and_login("intapi2", "intapi2@test.com")
        resp = client.get("/api/v3/intelligence/specialization", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "primary_pillar" in data
        assert "expertise_label_en" in data

    def test_quality_endpoint(self):
        headers = _register_and_login("intapi3", "intapi3@test.com")
        resp = client.get("/api/v3/intelligence/quality?months=3", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "confidence_direction" in data
        assert "country_percentile" in data

    def test_earnings_endpoint(self):
        headers = _register_and_login("intapi4", "intapi4@test.com")
        resp = client.get("/api/v3/intelligence/earnings", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "current_monthly_rate_cfa" in data
        assert "what_if_scenarios" in data

    def test_opportunities_endpoint(self):
        headers = _register_and_login("intapi5", "intapi5@test.com")
        resp = client.get("/api/v3/intelligence/opportunities", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "underserved_token_types" in data
        assert "geographic_gaps" in data

    def test_nudges_endpoint(self):
        headers = _register_and_login("intapi6", "intapi6@test.com")
        resp = client.get("/api/v3/intelligence/nudges?locale=fr", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # New user should get at least ONBOARDING nudge
        assert len(data) >= 1

    def test_wrapped_endpoint(self):
        headers = _register_and_login("intapi7", "intapi7@test.com")
        resp = client.get("/api/v3/intelligence/wrapped?year=2026", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_reports" in data
        assert "impact_summary" in data
        assert data["year"] == 2026
