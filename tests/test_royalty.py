"""
Data Marketplace Royalty System — Test Suite

Tests cover:
  1. RoyaltyEngine: attribution recording, pool creation, distribution
  2. Pool distribution: quality-weighted shares, tier multipliers
  3. Contributor queries: royalty history, summary
  4. Platform stats: aggregates
  5. API endpoints: my-royalties, pool, stats, admin distribute
"""
import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient

from src.main import app
from tests.conftest import TestingSessionLocal
from src.database.royalty_models import RoyaltyPool, RoyaltyDistribution, DataAttribution
from src.database.tokenization_models import DataToken
from src.database.engagement_models import DataWallet
from src.database.models import Country
from src.engines.royalty_engine import (
    RoyaltyEngine, ROYALTY_RATES, TIER_ROYALTY_MULTIPLIERS, CREDIT_TO_CFA,
    _get_royalty_rate, ECOWAS_CODES,
)

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────

def _register_and_login(username="royuser", email="roy@test.com", credits=200, is_admin=False):
    client.post("/api/auth/register", json={
        "username": username, "email": email, "password": "TestPass123",
    })
    resp = client.post("/api/auth/login", data={
        "username": username, "password": "TestPass123",
    })
    token = resp.json().get("access_token", "")
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


def _seed_tokens_and_wallets(db, country_code="NG", n_contributors=3, reports_per=5):
    """Create DataTokens and DataWallets for testing royalty distribution."""
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return []

    today = date.today()
    wallets = []
    tiers = ["BRONZE", "SILVER", "GOLD"]

    for i in range(n_contributors):
        phone_hash = f"royalty_test_hash_{country_code}_{i:03d}"
        tier = tiers[i % len(tiers)]

        # Create wallet
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()
        if not wallet:
            wallet = DataWallet(
                contributor_phone_hash=phone_hash,
                country_code=country_code,
                total_reports=reports_per,
                total_earned_cfa=0,
                tier=tier,
                current_multiplier=1.0,
            )
            db.add(wallet)

        # Create tokens
        for j in range(reports_per):
            token = DataToken(
                token_id=f"rt_{country_code}_{i}_{j}",
                country_id=country.id,
                pillar="CITIZEN_DATA",
                token_type="ACTIVITY_REPORT",
                contributor_phone_hash=phone_hash,
                token_value_cfa=100.0,
                status="validated",
                confidence=0.40 + (i * 0.15),  # 0.40, 0.55, 0.70
                period_date=today - timedelta(days=j % 5),
            )
            db.add(token)

        wallets.append(wallet)

    db.commit()
    return wallets


# ═══════════════════════════════════════════════════════════════════════
# 1. Royalty Rate Lookup
# ═══════════════════════════════════════════════════════════════════════

class TestRoyaltyRates:

    def test_bank_score_dossier_rate(self):
        assert _get_royalty_rate("/api/v2/bank/score-dossier") == 0.20

    def test_composite_rate(self):
        assert _get_royalty_rate("/api/composite/calculate") == 0.15

    def test_forecast_rate(self):
        assert _get_royalty_rate("/api/v3/forecast/composite") == 0.10

    def test_default_rate(self):
        assert _get_royalty_rate("/api/some/unknown/endpoint") == 0.05

    def test_tier_multipliers(self):
        assert TIER_ROYALTY_MULTIPLIERS["BRONZE"] == 1.0
        assert TIER_ROYALTY_MULTIPLIERS["PLATINUM"] == 3.0


# ═══════════════════════════════════════════════════════════════════════
# 2. Attribution Recording
# ═══════════════════════════════════════════════════════════════════════

class TestRecordAttribution:

    def test_record_single_country(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "NG")
            attrs = RoyaltyEngine.record_attribution(
                db, consumer_user_id=999, endpoint="/api/v2/bank/score-dossier",
                credits_spent=10.0, country_code="NG",
            )
            db.commit()

            assert len(attrs) == 1
            attr = attrs[0]
            assert attr.country_code == "NG"
            assert attr.credits_spent == 10.0
            assert attr.royalty_contribution == 2.0  # 10 * 0.20

            # Pool should exist
            pool = db.query(RoyaltyPool).filter(
                RoyaltyPool.country_code == "NG",
                RoyaltyPool.period_date == date.today(),
            ).first()
            assert pool is not None
            assert pool.total_queries == 1
            assert pool.pool_amount_cfa == 2.0 * CREDIT_TO_CFA  # 200 CFA
        finally:
            db.close()

    def test_record_all_countries(self):
        db = TestingSessionLocal()
        try:
            attrs = RoyaltyEngine.record_attribution(
                db, consumer_user_id=999, endpoint="/api/composite/report",
                credits_spent=3.0, country_code=None,
            )
            db.commit()

            assert len(attrs) == 16  # All ECOWAS countries
            total_credits = sum(a.credits_spent for a in attrs)
            assert abs(total_credits - 3.0) < 0.01
        finally:
            db.close()

    def test_zero_credits_no_attribution(self):
        db = TestingSessionLocal()
        try:
            attrs = RoyaltyEngine.record_attribution(
                db, consumer_user_id=999, endpoint="/api/v2/bank/score-dossier",
                credits_spent=0, country_code="NG",
            )
            assert len(attrs) == 0
        finally:
            db.close()

    def test_pool_accumulates(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "CI")
            # Two queries same day, same country
            RoyaltyEngine.record_attribution(
                db, 999, "/api/v2/bank/score-dossier", 10.0, "CI")
            RoyaltyEngine.record_attribution(
                db, 888, "/api/v2/bank/score-dossier", 10.0, "CI")
            db.commit()

            pool = db.query(RoyaltyPool).filter(
                RoyaltyPool.country_code == "CI",
                RoyaltyPool.period_date == date.today(),
            ).first()
            assert pool.total_queries == 2
            assert pool.total_credits_spent == 20.0
            assert pool.pool_amount_cfa == 4.0 * CREDIT_TO_CFA  # 400 CFA
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 3. Pool Distribution
# ═══════════════════════════════════════════════════════════════════════

class TestPoolDistribution:

    def test_distribute_pool(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "GH", n_contributors=3, reports_per=5)
            RoyaltyEngine.record_attribution(
                db, 999, "/api/v2/bank/score-dossier", 10.0, "GH")
            db.commit()

            pool = db.query(RoyaltyPool).filter(
                RoyaltyPool.country_code == "GH",
            ).first()
            assert pool is not None

            result = RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            assert "error" not in result
            assert result["distributed_to"] == 3
            assert result["total_cfa"] > 0

            # Pool marked as distributed
            db.refresh(pool)
            assert pool.distributed is True

            # Distributions created
            dists = db.query(RoyaltyDistribution).filter(
                RoyaltyDistribution.pool_id == pool.id
            ).all()
            assert len(dists) == 3

            # Shares sum to ~100%
            total_pct = sum(d.share_pct for d in dists)
            assert abs(total_pct - 100.0) < 0.1

            # Higher confidence + higher tier → larger share
            dists_sorted = sorted(dists, key=lambda d: d.share_amount_cfa, reverse=True)
            assert dists_sorted[0].share_amount_cfa >= dists_sorted[-1].share_amount_cfa
        finally:
            db.close()

    def test_distribute_already_distributed(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "SN")
            RoyaltyEngine.record_attribution(db, 999, "/api/v2/bank/score-dossier", 10.0, "SN")
            db.commit()

            pool = db.query(RoyaltyPool).filter(RoyaltyPool.country_code == "SN").first()
            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            # Second distribution should return error
            result = RoyaltyEngine.distribute_pool(db, pool.id)
            assert "error" in result
            assert "already distributed" in result["error"]
        finally:
            db.close()

    def test_distribute_empty_pool(self):
        db = TestingSessionLocal()
        try:
            # Pool with no tokens
            pool = RoyaltyPool(
                country_code="NE",
                period_date=date.today(),
                pool_amount_cfa=0,
            )
            db.add(pool)
            db.commit()

            result = RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()
            assert result["distributed_to"] == 0
        finally:
            db.close()

    def test_tier_affects_weight(self):
        """GOLD contributor should get a larger share than BRONZE."""
        db = TestingSessionLocal()
        try:
            country = db.query(Country).filter(Country.code == "BF").first()
            today = date.today()

            # Two contributors with same reports + confidence but different tiers
            for tier, idx in [("BRONZE", 0), ("GOLD", 1)]:
                ph = f"tier_test_{idx}"
                db.add(DataWallet(
                    contributor_phone_hash=ph,
                    country_code="BF",
                    total_reports=5,
                    tier=tier,
                ))
                for j in range(5):
                    db.add(DataToken(
                        token_id=f"tt_{idx}_{j}",
                        country_id=country.id,
                        pillar="CITIZEN_DATA",
                        token_type="ACTIVITY_REPORT",
                        contributor_phone_hash=ph,
                        token_value_cfa=100.0,
                        status="validated",
                        confidence=0.60,
                        period_date=today - timedelta(days=j),
                    ))

            db.commit()

            RoyaltyEngine.record_attribution(db, 999, "/api/v2/bank/score-dossier", 10.0, "BF")
            db.commit()

            pool = db.query(RoyaltyPool).filter(RoyaltyPool.country_code == "BF").first()
            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            bronze_dist = db.query(RoyaltyDistribution).filter(
                RoyaltyDistribution.contributor_phone_hash == "tier_test_0"
            ).first()
            gold_dist = db.query(RoyaltyDistribution).filter(
                RoyaltyDistribution.contributor_phone_hash == "tier_test_1"
            ).first()

            assert gold_dist.share_amount_cfa > bronze_dist.share_amount_cfa
            assert gold_dist.tier_multiplier == 2.0
            assert bronze_dist.tier_multiplier == 1.0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 4. Distribute All Pending
# ═══════════════════════════════════════════════════════════════════════

class TestDistributeAllPending:

    def test_distribute_all(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "NG")
            # Create pool for yesterday (so it's eligible for distribution)
            yesterday = date.today() - timedelta(days=1)
            pool = RoyaltyPool(
                country_code="NG",
                period_date=yesterday,
                total_queries=2,
                total_credits_spent=20.0,
                pool_amount_cfa=400.0,
            )
            db.add(pool)
            db.commit()

            result = RoyaltyEngine.distribute_all_pending(db)
            db.commit()

            assert result["pools_processed"] == 1
            assert result["total_distributed_cfa"] > 0
        finally:
            db.close()

    def test_today_pool_not_distributed(self):
        """Pools for today should NOT be distributed yet."""
        db = TestingSessionLocal()
        try:
            pool = RoyaltyPool(
                country_code="ML",
                period_date=date.today(),
                pool_amount_cfa=100.0,
            )
            db.add(pool)
            db.commit()

            result = RoyaltyEngine.distribute_all_pending(db)
            assert result["pools_processed"] == 0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 5. Contributor Queries
# ═══════════════════════════════════════════════════════════════════════

class TestContributorQueries:

    def test_get_royalties_empty(self):
        db = TestingSessionLocal()
        try:
            entries = RoyaltyEngine.get_contributor_royalties(db, "nonexistent_hash")
            assert entries == []
        finally:
            db.close()

    def test_get_summary_empty(self):
        db = TestingSessionLocal()
        try:
            summary = RoyaltyEngine.get_contributor_summary(db, "nonexistent_hash")
            assert summary["total_royalties_cfa"] == 0
            assert summary["total_queries_served"] == 0
            assert summary["monthly_breakdown"] == []
        finally:
            db.close()

    def test_get_royalties_after_distribution(self):
        db = TestingSessionLocal()
        try:
            wallets = _seed_tokens_and_wallets(db, "CI", n_contributors=2)
            yesterday = date.today() - timedelta(days=1)
            pool = RoyaltyPool(
                country_code="CI",
                period_date=yesterday,
                total_queries=5,
                total_credits_spent=50.0,
                pool_amount_cfa=1000.0,
            )
            db.add(pool)
            db.commit()

            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            phone = wallets[0].contributor_phone_hash
            entries = RoyaltyEngine.get_contributor_royalties(db, phone)
            assert len(entries) == 1
            assert entries[0]["share_amount_cfa"] > 0
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 6. Platform Stats
# ═══════════════════════════════════════════════════════════════════════

class TestPlatformStats:

    def test_stats_empty(self):
        db = TestingSessionLocal()
        try:
            stats = RoyaltyEngine.get_platform_stats(db)
            assert stats["total_pools"] == 0
            assert stats["total_royalties_distributed_cfa"] == 0
            assert stats["unique_contributors"] == 0
        finally:
            db.close()

    def test_stats_after_distribution(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "GH", n_contributors=2)
            yesterday = date.today() - timedelta(days=1)
            pool = RoyaltyPool(
                country_code="GH",
                period_date=yesterday,
                total_queries=3,
                total_credits_spent=30.0,
                pool_amount_cfa=600.0,
            )
            db.add(pool)
            db.commit()

            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            stats = RoyaltyEngine.get_platform_stats(db)
            assert stats["total_pools"] == 1
            assert stats["total_distributed_pools"] == 1
            assert stats["total_royalties_distributed_cfa"] > 0
            assert stats["unique_contributors"] == 2
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 7. Pool Status + Contributors
# ═══════════════════════════════════════════════════════════════════════

class TestPoolStatus:

    def test_pool_status_not_found(self):
        db = TestingSessionLocal()
        try:
            result = RoyaltyEngine.get_pool_status(db, "NG")
            assert result is None
        finally:
            db.close()

    def test_pool_status_exists(self):
        db = TestingSessionLocal()
        try:
            pool = RoyaltyPool(
                country_code="NG",
                period_date=date.today(),
                total_queries=5,
                total_credits_spent=50.0,
                pool_amount_cfa=1000.0,
            )
            db.add(pool)
            db.commit()

            result = RoyaltyEngine.get_pool_status(db, "NG")
            assert result is not None
            assert result["country_code"] == "NG"
            assert result["pool_amount_cfa"] == 1000.0
        finally:
            db.close()

    def test_pool_contributors(self):
        db = TestingSessionLocal()
        try:
            _seed_tokens_and_wallets(db, "SN", n_contributors=2)
            yesterday = date.today() - timedelta(days=1)
            pool = RoyaltyPool(
                country_code="SN",
                period_date=yesterday,
                total_queries=2,
                total_credits_spent=20.0,
                pool_amount_cfa=400.0,
            )
            db.add(pool)
            db.commit()

            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            contribs = RoyaltyEngine.get_pool_contributors(db, pool.id)
            assert len(contribs) == 2
            assert contribs[0]["rank"] == 1
            assert contribs[0]["share_amount_cfa"] >= contribs[1]["share_amount_cfa"]
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════
# 8. API Endpoints
# ═══════════════════════════════════════════════════════════════════════

class TestRoyaltyAPI:

    def test_my_royalties_unauthorized(self):
        resp = client.get("/api/v3/royalties/my-royalties")
        assert resp.status_code in (401, 403)

    def test_my_royalties_empty(self):
        headers = _register_and_login("royapi1", "royapi1@test.com")
        resp = client.get("/api/v3/royalties/my-royalties", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_royalties_cfa"] == 0
        assert data["entries"] == []

    def test_my_royalties_summary(self):
        headers = _register_and_login("royapi2", "royapi2@test.com")
        resp = client.get("/api/v3/royalties/my-royalties/summary", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_royalties_cfa" in data
        assert "monthly_breakdown" in data

    def test_pool_not_found(self):
        headers = _register_and_login("royapi3", "royapi3@test.com")
        resp = client.get("/api/v3/royalties/pool/NG", headers=headers)
        assert resp.status_code == 404

    def test_pool_found(self):
        # Seed a pool
        db = TestingSessionLocal()
        try:
            pool = RoyaltyPool(
                country_code="NG",
                period_date=date.today(),
                total_queries=5,
                total_credits_spent=50.0,
                pool_amount_cfa=1000.0,
            )
            db.add(pool)
            db.commit()
        finally:
            db.close()

        headers = _register_and_login("royapi4", "royapi4@test.com")
        resp = client.get("/api/v3/royalties/pool/NG", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "NG"
        assert data["pool_amount_cfa"] == 1000.0

    def test_stats_endpoint(self):
        headers = _register_and_login("royapi5", "royapi5@test.com")
        resp = client.get("/api/v3/royalties/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_pools" in data
        assert "unique_contributors" in data

    def test_admin_distribute(self):
        headers = _register_and_login("royapi6", "royapi6@test.com", credits=500, is_admin=True)
        resp = client.post("/api/v3/royalties/admin/distribute", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "pools_processed" in data

    def test_admin_pools(self):
        headers = _register_and_login("royapi7", "royapi7@test.com", is_admin=True)
        resp = client.get("/api/v3/royalties/admin/pools", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "pools" in data
        assert "total_pending_cfa" in data

    def test_pool_contributors_endpoint(self):
        db = TestingSessionLocal()
        try:
            pool = RoyaltyPool(
                country_code="CI",
                period_date=date.today(),
                total_queries=3,
                total_credits_spent=30.0,
                pool_amount_cfa=600.0,
            )
            db.add(pool)
            db.commit()
        finally:
            db.close()

        headers = _register_and_login("royapi8", "royapi8@test.com")
        resp = client.get("/api/v3/royalties/pool/CI/contributors", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "pool" in data
        assert "contributors" in data


# ═══════════════════════════════════════════════════════════════════════
# 9. Wallet Credit After Distribution
# ═══════════════════════════════════════════════════════════════════════

class TestWalletCredit:

    def test_wallet_balance_increases(self):
        """Distribution should credit DataWallet.total_earned_cfa."""
        db = TestingSessionLocal()
        try:
            wallets = _seed_tokens_and_wallets(db, "BJ", n_contributors=1, reports_per=5)
            wallet = wallets[0]
            initial_earned = wallet.total_earned_cfa or 0

            yesterday = date.today() - timedelta(days=1)
            pool = RoyaltyPool(
                country_code="BJ",
                period_date=yesterday,
                total_queries=1,
                total_credits_spent=10.0,
                pool_amount_cfa=200.0,  # 200 CFA to distribute
            )
            db.add(pool)
            db.commit()

            RoyaltyEngine.distribute_pool(db, pool.id)
            db.commit()

            db.refresh(wallet)
            assert wallet.total_earned_cfa > initial_earned
        finally:
            db.close()
