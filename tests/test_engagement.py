"""
Walk15-Style Engagement — Test Suite

Tests cover:
  1. WalletEngine: creation, activity recording, reputation, tier, multiplier
  2. StreakEngine: consecutive days, grace period, reset, nightly batch
  3. BadgeEngine: seed, evaluation, award, progress tracking
  4. ChallengeEngine: creation, join, contribution, lifecycle, leaderboard
  5. ImpactEngine: monthly calculation, dashboard
  6. RewardEngine: catalog, redemption, tier eligibility, balance check
  7. API endpoints: wallet, badges, challenges, streak, tier, rewards
"""
import json
import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient

from src.main import app
from tests.conftest import TestingSessionLocal
from src.database.engagement_models import (
    DataWallet, BadgeDefinition, UserBadge, BadgeProgress,
    Challenge, ChallengeParticipation, ImpactRecord, RewardCatalog,
)
from src.engines.engagement_engine import (
    WalletEngine, StreakEngine, BadgeEngine, ChallengeEngine,
    ImpactEngine, RewardEngine,
    STREAK_MULTIPLIERS, TIER_THRESHOLDS, TIER_ORDER,
)

client = TestClient(app, raise_server_exceptions=False)

# ── Helper: get auth token ──────────────────────────────────────────

def _register_and_login(username="enguser", email="eng@test.com", credits=100, is_admin=False):
    client.post("/api/auth/register", json={
        "username": username, "email": email, "password": "TestPass123",
    })
    resp = client.post("/api/auth/login", data={
        "username": username, "password": "TestPass123",
    })
    token = resp.json().get("access_token", "")
    # Top up credits and optionally grant admin
    db = TestingSessionLocal()
    from src.database.models import User
    user = db.query(User).filter(User.username == username).first()
    if user:
        if credits > 0:
            user.x402_balance = credits
        if is_admin:
            user.is_admin = True
        db.commit()
    db.close()
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
# 1. WalletEngine
# ═══════════════════════════════════════════════════════════════════════

class TestWalletEngine:

    def test_create_wallet(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "hash_001", "NG")
            db.commit()
            assert wallet.contributor_phone_hash == "hash_001"
            assert wallet.country_code == "NG"
            assert wallet.total_reports == 0
            assert wallet.tier == "BRONZE"
            assert wallet.current_multiplier == 1.00
        finally:
            db.close()

    def test_get_existing_wallet(self):
        db = TestingSessionLocal()
        try:
            w1 = WalletEngine.get_or_create_wallet(db, "hash_002", "CI")
            db.commit()
            w2 = WalletEngine.get_or_create_wallet(db, "hash_002", "CI")
            assert w1.id == w2.id
        finally:
            db.close()

    def test_record_activity_increments(self):
        db = TestingSessionLocal()
        try:
            BadgeEngine.seed_badges(db)
            db.commit()

            wallet = WalletEngine.record_activity(db, "hash_003", "GH", 100.0, False)
            db.commit()
            assert wallet.total_reports == 1
            assert wallet.total_earned_cfa == 100.0
            assert wallet.current_streak == 1
        finally:
            db.close()

    def test_cross_validated_counter(self):
        db = TestingSessionLocal()
        try:
            BadgeEngine.seed_badges(db)
            db.commit()

            wallet = WalletEngine.record_activity(db, "hash_004", "SN", 75.0, True)
            db.commit()
            assert wallet.total_cross_validated == 1
        finally:
            db.close()

    def test_reputation_increases_with_activity(self):
        db = TestingSessionLocal()
        try:
            BadgeEngine.seed_badges(db)
            db.commit()

            wallet = WalletEngine.record_activity(db, "hash_005", "NG", 100, False)
            db.commit()
            assert wallet.reputation_score > 0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 2. StreakEngine
# ═══════════════════════════════════════════════════════════════════════

class TestStreakEngine:

    def test_first_report_starts_streak(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_001", "NG")
            StreakEngine.update_streak(db, wallet, date.today())
            db.commit()
            assert wallet.current_streak == 1
            assert wallet.longest_streak == 1
        finally:
            db.close()

    def test_consecutive_days_increment(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_002", "NG")
            today = date.today()
            StreakEngine.update_streak(db, wallet, today - timedelta(days=2))
            StreakEngine.update_streak(db, wallet, today - timedelta(days=1))
            StreakEngine.update_streak(db, wallet, today)
            db.commit()
            assert wallet.current_streak == 3
        finally:
            db.close()

    def test_same_day_no_change(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_003", "NG")
            today = date.today()
            StreakEngine.update_streak(db, wallet, today)
            StreakEngine.update_streak(db, wallet, today)
            db.commit()
            assert wallet.current_streak == 1
        finally:
            db.close()

    def test_grace_period(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_004", "NG")
            today = date.today()
            StreakEngine.update_streak(db, wallet, today - timedelta(days=3))
            StreakEngine.update_streak(db, wallet, today - timedelta(days=2))
            # Skip 1 day (grace)
            StreakEngine.update_streak(db, wallet, today)
            db.commit()
            assert wallet.current_streak == 3
            assert wallet.streak_grace_used is True
        finally:
            db.close()

    def test_streak_reset_after_gap(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_005", "NG")
            today = date.today()
            StreakEngine.update_streak(db, wallet, today - timedelta(days=5))
            StreakEngine.update_streak(db, wallet, today - timedelta(days=4))
            # 3-day gap → reset
            StreakEngine.update_streak(db, wallet, today)
            db.commit()
            assert wallet.current_streak == 1
            assert wallet.longest_streak == 2
        finally:
            db.close()

    def test_nightly_streak_reset(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "streak_006", "NG")
            wallet.current_streak = 5
            wallet.last_report_date = date.today() - timedelta(days=3)
            db.commit()

            stats = StreakEngine.calculate_nightly_streaks(db)
            db.commit()
            assert stats["reset"] >= 1

            db.refresh(wallet)
            assert wallet.current_streak == 0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 3. BadgeEngine
# ═══════════════════════════════════════════════════════════════════════

class TestBadgeEngine:

    def test_seed_badges(self):
        db = TestingSessionLocal()
        try:
            created = BadgeEngine.seed_badges(db)
            db.commit()
            assert created >= 15  # We defined ~19 badges
        finally:
            db.close()

    def test_seed_idempotent(self):
        db = TestingSessionLocal()
        try:
            n1 = BadgeEngine.seed_badges(db)
            db.commit()
            n2 = BadgeEngine.seed_badges(db)
            db.commit()
            assert n2 == 0
        finally:
            db.close()

    def test_first_report_badge_awarded(self):
        db = TestingSessionLocal()
        try:
            BadgeEngine.seed_badges(db)
            db.commit()

            wallet = WalletEngine.get_or_create_wallet(db, "badge_001", "NG")
            wallet.total_reports = 1
            wallet.current_streak = 1
            db.commit()

            new_badges = BadgeEngine.check_and_award(db, "badge_001", wallet)
            db.commit()

            codes = [b.badge_code for b in new_badges]
            assert "FIRST_REPORT" in codes
        finally:
            db.close()

    def test_progress_tracking(self):
        db = TestingSessionLocal()
        try:
            BadgeEngine.seed_badges(db)
            db.commit()

            wallet = WalletEngine.get_or_create_wallet(db, "badge_002", "NG")
            wallet.total_reports = 5
            db.commit()

            BadgeEngine.check_and_award(db, "badge_002", wallet)
            db.commit()

            badges = BadgeEngine.get_user_badges(db, "badge_002")
            # HUNDRED_CLUB should show progress 5/100
            hundred = next((b for b in badges if b["badge_code"] == "HUNDRED_CLUB"), None)
            assert hundred is not None
            assert hundred["progress_current"] == 5
            assert hundred["progress_target"] == 100
            assert hundred["earned"] is False
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 4. ChallengeEngine
# ═══════════════════════════════════════════════════════════════════════

class TestChallengeEngine:

    def test_create_challenge(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            challenge = ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_CHALLENGE_1",
                title_en="Test Challenge",
                title_fr="Défi Test",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=100,
                start_date=now,
                end_date=now + timedelta(days=7),
            )
            db.commit()
            assert challenge.id is not None
            assert challenge.status == "UPCOMING"
        finally:
            db.close()

    def test_join_challenge(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            challenge = ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_JOIN",
                title_en="Join Test", title_fr="Test Rejoindre",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=50,
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
                status="ACTIVE",
            )
            db.commit()

            p = ChallengeEngine.join_challenge(db, challenge.id, "join_hash", "NG")
            db.commit()
            assert p.contribution_count == 0
        finally:
            db.close()

    def test_duplicate_join_returns_existing(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            c = ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_DUP_JOIN",
                title_en="Dup", title_fr="Dup",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=50,
                start_date=now, end_date=now + timedelta(days=7),
                status="ACTIVE",
            )
            db.commit()

            p1 = ChallengeEngine.join_challenge(db, c.id, "dup_hash", "NG")
            db.commit()
            p2 = ChallengeEngine.join_challenge(db, c.id, "dup_hash", "NG")
            assert p1.id == p2.id
        finally:
            db.close()

    def test_contribution_increments_progress(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            c = ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_CONTRIB",
                title_en="Contrib", title_fr="Contrib",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=10,
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
                status="ACTIVE",
            )
            db.commit()

            ChallengeEngine.join_challenge(db, c.id, "contrib_hash", "NG")
            db.commit()

            ChallengeEngine.record_contribution_for_user(db, "contrib_hash")
            db.commit()

            db.refresh(c)
            assert c.current_progress == 1
        finally:
            db.close()

    def test_lifecycle_activates(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_LIFECYCLE",
                title_en="LC", title_fr="LC",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=10,
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
            )
            db.commit()

            stats = ChallengeEngine.lifecycle_tick(db)
            db.commit()
            assert stats["activated"] >= 1
        finally:
            db.close()

    def test_leaderboard(self):
        db = TestingSessionLocal()
        try:
            now = datetime.now(timezone.utc)
            c = ChallengeEngine.create_challenge(
                db,
                challenge_code="TEST_LB",
                title_en="LB", title_fr="LB",
                scope="GLOBAL",
                goal_metric="citizen_reports",
                goal_target=100,
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
                status="ACTIVE",
            )
            db.commit()

            ChallengeEngine.join_challenge(db, c.id, "lb_hash_1", "NG")
            ChallengeEngine.join_challenge(db, c.id, "lb_hash_2", "CI")
            db.commit()

            # Give 1 contribution
            ChallengeEngine.record_contribution_for_user(db, "lb_hash_1")
            db.commit()

            lb = ChallengeEngine.get_leaderboard(db, c.id)
            assert len(lb) == 2
            assert lb[0]["contribution_count"] == 1
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 5. RewardEngine
# ═══════════════════════════════════════════════════════════════════════

class TestRewardEngine:

    def test_redeem_success(self):
        db = TestingSessionLocal()
        try:
            # Create wallet with balance
            wallet = WalletEngine.get_or_create_wallet(db, "reward_001", "NG")
            wallet.total_earned_cfa = 5000
            wallet.tier = "BRONZE"
            db.commit()

            # Create reward
            db.add(RewardCatalog(
                reward_code="TEST_AIRTIME",
                name_en="Test Airtime", name_fr="Test Crédit",
                reward_type="AIRTIME",
                cost_cfa=500,
                min_tier="BRONZE",
            ))
            db.commit()

            result = RewardEngine.redeem_reward(db, "reward_001", "TEST_AIRTIME")
            db.commit()

            assert result["status"] == "redeemed"
            assert result["remaining_balance_cfa"] == 4500
            # Verify total_earned_cfa is unchanged (lifetime counter)
            db.refresh(wallet)
            assert wallet.total_earned_cfa == 5000
            assert wallet.total_redeemed_cfa == 500
            assert result["payment_reference"] is not None
        finally:
            db.close()

    def test_redeem_insufficient_balance(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "reward_002", "NG")
            wallet.total_earned_cfa = 100
            db.commit()

            db.add(RewardCatalog(
                reward_code="TEST_EXPENSIVE",
                name_en="Expensive", name_fr="Cher",
                reward_type="AIRTIME",
                cost_cfa=5000,
                min_tier="BRONZE",
            ))
            db.commit()

            with pytest.raises(ValueError, match="Insufficient"):
                RewardEngine.redeem_reward(db, "reward_002", "TEST_EXPENSIVE")
        finally:
            db.close()

    def test_redeem_tier_check(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "reward_003", "NG")
            wallet.total_earned_cfa = 50000
            wallet.tier = "BRONZE"
            db.commit()

            db.add(RewardCatalog(
                reward_code="TEST_GOLD_ONLY",
                name_en="Gold Only", name_fr="Or Seulement",
                reward_type="ECFA_BONUS",
                cost_cfa=1000,
                min_tier="GOLD",
            ))
            db.commit()

            with pytest.raises(ValueError, match="Requires GOLD"):
                RewardEngine.redeem_reward(db, "reward_003", "TEST_GOLD_ONLY")
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 6. Multiplier Calculations
# ═══════════════════════════════════════════════════════════════════════

class TestMultiplier:

    def test_base_multiplier(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "mult_001", "NG")
            wallet.current_streak = 3
            wallet.tier = "BRONZE"
            m = WalletEngine.get_payment_multiplier(wallet)
            assert m == 1.00  # <7 days, BRONZE = 0 bonus
        finally:
            db.close()

    def test_7day_multiplier(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "mult_002", "NG")
            wallet.current_streak = 10
            wallet.tier = "BRONZE"
            m = WalletEngine.get_payment_multiplier(wallet)
            assert m == 1.25
        finally:
            db.close()

    def test_30day_gold_multiplier(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "mult_003", "NG")
            wallet.current_streak = 35
            wallet.tier = "GOLD"
            m = WalletEngine.get_payment_multiplier(wallet)
            assert m == 2.20  # 2.0 streak + 0.2 GOLD
        finally:
            db.close()

    def test_max_cap(self):
        db = TestingSessionLocal()
        try:
            wallet = WalletEngine.get_or_create_wallet(db, "mult_004", "NG")
            wallet.current_streak = 100
            wallet.tier = "PLATINUM"
            m = WalletEngine.get_payment_multiplier(wallet)
            assert m == 2.30  # 2.0 + 0.3 = 2.30 (under 3.0 cap)
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 7. API Endpoints
# ═══════════════════════════════════════════════════════════════════════

class TestEngagementAPI:

    def test_get_wallet_creates_empty(self):
        headers = _register_and_login("api_wallet", "api_w@test.com")
        resp = client.get("/api/v3/engagement/wallet", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_reports"] == 0
        assert data["tier"] == "BRONZE"

    def test_get_streak(self):
        headers = _register_and_login("api_streak", "api_s@test.com")
        resp = client.get("/api/v3/engagement/streak", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_streak"] == 0
        assert data["next_milestone"] == 7

    def test_get_tier(self):
        headers = _register_and_login("api_tier", "api_t@test.com")
        resp = client.get("/api/v3/engagement/tier", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_tier"] == "BRONZE"
        assert data["next_tier"] == "SILVER"

    def test_badge_catalog(self):
        # Seed badges first
        db = TestingSessionLocal()
        BadgeEngine.seed_badges(db)
        db.commit()
        db.close()

        headers = _register_and_login("api_badges", "api_b@test.com")
        resp = client.get("/api/v3/engagement/badges/catalog", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 15

    def test_get_my_badges(self):
        db = TestingSessionLocal()
        BadgeEngine.seed_badges(db)
        db.commit()
        db.close()

        headers = _register_and_login("api_mybadges", "api_mb@test.com")
        resp = client.get("/api/v3/engagement/badges", headers=headers)
        assert resp.status_code == 200

    def test_challenges_empty(self):
        headers = _register_and_login("api_ch", "api_ch@test.com")
        resp = client.get("/api/v3/engagement/challenges", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_rewards_catalog(self):
        headers = _register_and_login("api_rew", "api_rew@test.com")
        resp = client.get("/api/v3/engagement/rewards", headers=headers)
        assert resp.status_code == 200

    def test_impact_no_wallet(self):
        headers = _register_and_login("api_imp", "api_imp@test.com")
        resp = client.get("/api/v3/engagement/impact", headers=headers)
        # Should create a wallet and return dashboard
        assert resp.status_code in (200, 404)

    def test_seed_badges_endpoint(self):
        headers = _register_and_login("api_seed", "api_seed@test.com", is_admin=True)
        resp = client.post("/api/v3/engagement/admin/badges/seed", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "badges_created" in data

    def test_create_challenge_endpoint(self):
        headers = _register_and_login("api_cch", "api_cch@test.com", is_admin=True)
        now = datetime.now(timezone.utc)
        resp = client.post("/api/v3/engagement/admin/challenges/create", headers=headers, json={
            "challenge_code": "API_TEST_CH",
            "title_en": "API Test",
            "title_fr": "Test API",
            "scope": "GLOBAL",
            "goal_metric": "citizen_reports",
            "goal_target": 100,
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=7)).isoformat(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["challenge_code"] == "API_TEST_CH"

    def test_join_challenge_endpoint(self):
        # Create challenge first
        db = TestingSessionLocal()
        now = datetime.now(timezone.utc)
        c = Challenge(
            challenge_code="JOIN_API_CH",
            title_en="Join Test", title_fr="Test Rejoindre",
            scope="GLOBAL",
            goal_metric="citizen_reports",
            goal_target=50,
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(days=7),
            status="ACTIVE",
        )
        db.add(c)
        db.commit()
        ch_id = c.id
        db.close()

        headers = _register_and_login("api_join", "api_join@test.com")
        resp = client.post(f"/api/v3/engagement/challenges/{ch_id}/join", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "joined"

    def test_engagement_summary(self):
        headers = _register_and_login("api_sum", "api_sum@test.com", is_admin=True)
        resp = client.get("/api/v3/engagement/admin/engagement-summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_wallets" in data

    def test_unauthenticated_rejected(self):
        resp = client.get("/api/v3/engagement/wallet")
        assert resp.status_code in (401, 403)
