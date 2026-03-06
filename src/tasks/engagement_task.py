"""
Walk15-Style Engagement Tasks — Scheduler jobs + demo data seeder.

Schedule:
  - run_nightly_streaks()       — daily 00:30 UTC (reset broken streaks)
  - run_badge_check()           — every 4h (batch badge evaluation)
  - run_challenge_lifecycle()   — every 1h (UPCOMING→ACTIVE→COMPLETED)
  - run_monthly_impact()        — 1st of month 03:00 UTC
  - seed_engagement_demo_data() — startup (if 0 wallets)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import threading
import uuid
from datetime import timezone, date, datetime, timedelta

from src.database.connection import SessionLocal
from src.database.models import Country
from src.database.engagement_models import (
    DataWallet, BadgeDefinition, UserBadge, BadgeProgress,
    Challenge, ChallengeParticipation, ImpactRecord, RewardCatalog,
)
from src.engines.engagement_engine import (
    WalletEngine, StreakEngine, BadgeEngine, ChallengeEngine,
    ImpactEngine, RewardEngine, BADGE_SEED,
)
from src.config import settings

logger = logging.getLogger(__name__)
_engagement_lock = threading.Lock()

# 16 ECOWAS countries
ECOWAS_COUNTRIES = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
    "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]

# Wallets per country (scaled by economy size)
WALLETS_PER_COUNTRY = {
    "NG": 30, "CI": 20, "GH": 15, "SN": 12,
    "BF": 8, "ML": 6, "GN": 6, "BJ": 5, "TG": 5,
    "NE": 3, "MR": 2, "GW": 2, "SL": 2, "LR": 2, "GM": 2, "CV": 1,
}

REGIONS = {
    "NG": ["Lagos", "Kano", "Abuja", "Port Harcourt", "Ibadan"],
    "CI": ["Abidjan", "Bouaké", "San-Pédro", "Yamoussoukro"],
    "GH": ["Accra", "Kumasi", "Tema", "Takoradi"],
    "SN": ["Dakar", "Touba", "Thiès", "Saint-Louis"],
    "BF": ["Ouagadougou", "Bobo-Dioulasso"],
    "ML": ["Bamako", "Sikasso"],
    "GN": ["Conakry", "Nzérékoré"],
    "BJ": ["Cotonou", "Porto-Novo"],
    "TG": ["Lomé", "Kara"],
    "NE": ["Niamey"],
    "MR": ["Nouakchott"],
    "GW": ["Bissau"],
    "SL": ["Freetown"],
    "LR": ["Monrovia"],
    "GM": ["Banjul"],
    "CV": ["Praia"],
}


def _demo_phone_hash(cc: str, idx: int) -> str:
    """Generate deterministic phone hash for demo data."""
    raw = f"demo-{cc}-{idx}"
    return hmac.new(
        settings.SECRET_KEY.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()


# ══════════════════════════════════════════════════════════════════════
#  Scheduler Tasks
# ══════════════════════════════════════════════════════════════════════

def run_nightly_streaks(db=None) -> dict:
    """Nightly streak maintenance — reset broken streaks, apply grace."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        result = StreakEngine.calculate_nightly_streaks(db)
        db.commit()
        return result
    except Exception as exc:
        logger.error("Nightly streak check failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


def run_badge_check(db=None) -> dict:
    """Batch badge evaluation for all active wallets."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    if not _engagement_lock.acquire(blocking=False):
        logger.warning("Badge check already running, skipping")
        return {"status": "skipped"}

    try:
        total_awarded = 0
        total_checked = 0
        batch_size = 100
        offset = 0
        while True:
            batch = (
                db.query(DataWallet)
                .filter(DataWallet.total_reports > 0)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            for wallet in batch:
                new_badges = BadgeEngine.check_and_award(
                    db, wallet.contributor_phone_hash, wallet
                )
                total_awarded += len(new_badges)
            total_checked += len(batch)
            db.commit()
            offset += batch_size

        logger.info(f"Badge check: {total_checked} wallets checked, {total_awarded} badges awarded")
        return {
            "status": "completed",
            "wallets_checked": total_checked,
            "badges_awarded": total_awarded,
        }
    except Exception as exc:
        logger.error("Badge check failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        _engagement_lock.release()
        if own_session:
            db.close()


def run_challenge_lifecycle(db=None) -> dict:
    """Transition challenge statuses based on dates."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        result = ChallengeEngine.lifecycle_tick(db)
        db.commit()
        return result
    except Exception as exc:
        logger.error("Challenge lifecycle failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


def run_monthly_impact(db=None) -> dict:
    """Calculate previous month impact for all active wallets."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        today = date.today()
        if today.month == 1:
            prev = f"{today.year - 1}-12"
        else:
            prev = f"{today.year}-{today.month - 1:02d}"

        wallets = db.query(DataWallet).filter(
            DataWallet.total_reports > 0
        ).all()

        count = 0
        for wallet in wallets:
            ImpactEngine.calculate_user_impact(
                db, wallet.contributor_phone_hash, prev, wallet.country_code
            )
            count += 1

        db.commit()
        logger.info(f"Monthly impact: {count} wallets processed for {prev}")
        return {"status": "completed", "period": prev, "wallets_processed": count}
    except Exception as exc:
        logger.error("Monthly impact failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


# ══════════════════════════════════════════════════════════════════════
#  Demo Data Seeder
# ══════════════════════════════════════════════════════════════════════

def seed_engagement_demo_data(db=None) -> dict:
    """Seed demo engagement data: wallets, badges, challenges, rewards."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # Check if already seeded
        existing = db.query(DataWallet).count()
        if existing > 0:
            logger.info(f"Engagement already seeded ({existing} wallets)")
            return {"status": "skipped", "existing_wallets": existing}

        # 1. Seed badges
        BadgeEngine.seed_badges(db)
        db.flush()

        # 2. Seed reward catalog
        _seed_rewards(db)
        db.flush()

        # 3. Seed wallets with varied engagement levels
        total_wallets = 0
        total_badges = 0

        for cc in ECOWAS_COUNTRIES:
            n_wallets = WALLETS_PER_COUNTRY.get(cc, 2)
            regions = REGIONS.get(cc, [cc])

            for idx in range(n_wallets):
                ph = _demo_phone_hash(cc, idx)

                # Varied engagement levels
                if idx == 0:
                    # Power user: high streak, many reports
                    streak = random.randint(20, 45)
                    reports = random.randint(80, 200)
                    earned = reports * random.randint(80, 150)
                    xv = int(reports * random.uniform(0.4, 0.7))
                elif idx < n_wallets // 3:
                    # Active user
                    streak = random.randint(7, 20)
                    reports = random.randint(20, 80)
                    earned = reports * random.randint(60, 120)
                    xv = int(reports * random.uniform(0.2, 0.5))
                elif idx < n_wallets * 2 // 3:
                    # Casual user
                    streak = random.randint(1, 7)
                    reports = random.randint(5, 25)
                    earned = reports * random.randint(50, 100)
                    xv = int(reports * random.uniform(0.1, 0.3))
                else:
                    # New user
                    streak = random.randint(0, 2)
                    reports = random.randint(1, 5)
                    earned = reports * random.randint(50, 80)
                    xv = 0

                last_report = date.today() - timedelta(days=random.randint(0, 3))

                wallet = DataWallet(
                    contributor_phone_hash=ph,
                    country_code=cc,
                    total_reports=reports,
                    total_earned_cfa=earned,
                    total_cross_validated=xv,
                    current_streak=streak,
                    longest_streak=max(streak, streak + random.randint(0, 10)),
                    last_report_date=last_report,
                    streak_grace_used=random.random() < 0.2,
                )

                # Calculate reputation and tier
                WalletEngine._recalculate(db, wallet)
                db.add(wallet)
                db.flush()

                # Award eligible badges
                new_badges = BadgeEngine.check_and_award(db, ph, wallet)
                total_badges += len(new_badges)
                total_wallets += 1

        # 4. Seed challenges
        _seed_challenges(db)
        db.flush()

        # 5. Seed some challenge participations
        _seed_participations(db)
        db.flush()

        db.commit()
        logger.info(
            f"Engagement demo data seeded: {total_wallets} wallets, "
            f"{total_badges} badges awarded"
        )
        return {
            "status": "seeded",
            "wallets": total_wallets,
            "badges_awarded": total_badges,
        }

    except Exception as exc:
        logger.error("Engagement demo seed failed: %s", exc)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


def _seed_rewards(db):
    """Seed reward catalog."""
    rewards = [
        {
            "reward_code": "AIRTIME_500",
            "name_en": "500 CFA Airtime",
            "name_fr": "Crédit téléphone 500 CFA",
            "description_en": "500 CFA airtime top-up for any network",
            "description_fr": "Recharge téléphonique 500 CFA tout réseau",
            "reward_type": "AIRTIME",
            "cost_cfa": 500,
            "min_tier": "BRONZE",
        },
        {
            "reward_code": "AIRTIME_1000",
            "name_en": "1,000 CFA Airtime",
            "name_fr": "Crédit téléphone 1 000 CFA",
            "description_en": "1,000 CFA airtime top-up",
            "description_fr": "Recharge téléphonique 1 000 CFA",
            "reward_type": "AIRTIME",
            "cost_cfa": 1000,
            "min_tier": "BRONZE",
        },
        {
            "reward_code": "DATA_100MB",
            "name_en": "100MB Mobile Data",
            "name_fr": "100 Mo données mobiles",
            "description_en": "100MB data bundle valid for 7 days",
            "description_fr": "Forfait 100 Mo valide 7 jours",
            "reward_type": "DATA_BUNDLE",
            "cost_cfa": 750,
            "min_tier": "BRONZE",
        },
        {
            "reward_code": "DATA_500MB",
            "name_en": "500MB Mobile Data",
            "name_fr": "500 Mo données mobiles",
            "description_en": "500MB data bundle valid for 30 days",
            "description_fr": "Forfait 500 Mo valide 30 jours",
            "reward_type": "DATA_BUNDLE",
            "cost_cfa": 2500,
            "min_tier": "SILVER",
        },
        {
            "reward_code": "ECFA_BONUS_1000",
            "name_en": "1,000 eCFA Bonus",
            "name_fr": "Bonus 1 000 eCFA",
            "description_en": "1,000 eCFA credited to your digital wallet",
            "description_fr": "1 000 eCFA crédités sur votre portefeuille",
            "reward_type": "ECFA_BONUS",
            "cost_cfa": 800,
            "min_tier": "SILVER",
        },
        {
            "reward_code": "ECFA_BONUS_5000",
            "name_en": "5,000 eCFA Bonus",
            "name_fr": "Bonus 5 000 eCFA",
            "description_en": "5,000 eCFA credited to your digital wallet",
            "description_fr": "5 000 eCFA crédités sur votre portefeuille",
            "reward_type": "ECFA_BONUS",
            "cost_cfa": 3500,
            "min_tier": "GOLD",
        },
        {
            "reward_code": "PARTNER_MARKET_DISCOUNT",
            "name_en": "10% Market Discount",
            "name_fr": "Réduction marché 10%",
            "description_en": "10% discount at partner market vendors",
            "description_fr": "Réduction de 10% chez les vendeurs partenaires",
            "reward_type": "PARTNER_DISCOUNT",
            "cost_cfa": 1500,
            "min_tier": "GOLD",
            "partner_name": "ECOWAS Market Alliance",
        },
        {
            "reward_code": "PLATINUM_ECFA_10000",
            "name_en": "10,000 eCFA Premium Bonus",
            "name_fr": "Bonus Premium 10 000 eCFA",
            "description_en": "Exclusive platinum reward: 10,000 eCFA",
            "description_fr": "Récompense exclusive platine : 10 000 eCFA",
            "reward_type": "ECFA_BONUS",
            "cost_cfa": 7000,
            "min_tier": "PLATINUM",
        },
    ]

    for r_data in rewards:
        existing = db.query(RewardCatalog).filter(
            RewardCatalog.reward_code == r_data["reward_code"]
        ).first()
        if not existing:
            db.add(RewardCatalog(**r_data))


def _seed_challenges(db):
    """Seed demo challenges."""
    now = datetime.now(timezone.utc)
    challenges = [
        {
            "challenge_code": "ABIDJAN_MARKET_Q1",
            "title_en": "Abidjan Market Coverage",
            "title_fr": "Couverture Marché Abidjan",
            "description_en": "Report 500 commodity prices from Abidjan markets in 7 days",
            "description_fr": "Rapportez 500 prix de matières premières des marchés d'Abidjan en 7 jours",
            "scope": "REGIONAL",
            "target_country_code": "CI",
            "target_region": "Abidjan",
            "goal_metric": "citizen_reports",
            "goal_target": 500,
            "current_progress": 312,
            "start_date": now - timedelta(days=3),
            "end_date": now + timedelta(days=4),
            "status": "ACTIVE",
            "reward_multiplier": 1.50,
            "bonus_cfa": 500,
        },
        {
            "challenge_code": "LAGOS_ROAD_WATCH",
            "title_en": "Lagos Road Watch",
            "title_fr": "Surveillance Routes Lagos",
            "description_en": "200 road condition reports across Lagos state",
            "description_fr": "200 rapports de conditions routières à Lagos",
            "scope": "REGIONAL",
            "target_country_code": "NG",
            "target_region": "Lagos",
            "goal_metric": "citizen_reports",
            "goal_target": 200,
            "current_progress": 45,
            "start_date": now - timedelta(days=1),
            "end_date": now + timedelta(days=13),
            "status": "ACTIVE",
            "reward_multiplier": 1.25,
            "bonus_cfa": 300,
        },
        {
            "challenge_code": "ECOWAS_HEALTH_MARCH",
            "title_en": "ECOWAS Health March",
            "title_fr": "Marche Santé CEDEAO",
            "description_en": "1000 health facility reports across all 16 ECOWAS countries",
            "description_fr": "1 000 rapports de santé à travers les 16 pays de la CEDEAO",
            "scope": "GLOBAL",
            "target_country_code": None,
            "target_region": None,
            "goal_metric": "citizen_reports",
            "goal_target": 1000,
            "current_progress": 0,
            "start_date": now + timedelta(days=5),
            "end_date": now + timedelta(days=35),
            "status": "UPCOMING",
            "reward_multiplier": 2.00,
            "bonus_cfa": 1000,
        },
        {
            "challenge_code": "GHANA_BIZ_DATA",
            "title_en": "Ghana Business Data Push",
            "title_fr": "Push Données Entreprises Ghana",
            "description_en": "100 business data submissions from Ghanaian businesses",
            "description_fr": "100 soumissions de données d'entreprises ghanéennes",
            "scope": "COUNTRY",
            "target_country_code": "GH",
            "target_region": None,
            "goal_metric": "business_submissions",
            "goal_target": 100,
            "current_progress": 22,
            "start_date": now - timedelta(days=5),
            "end_date": now + timedelta(days=25),
            "status": "ACTIVE",
            "reward_multiplier": 1.50,
            "bonus_cfa": 750,
        },
    ]

    for c_data in challenges:
        existing = db.query(Challenge).filter(
            Challenge.challenge_code == c_data["challenge_code"]
        ).first()
        if not existing:
            db.add(Challenge(**c_data))


def _seed_participations(db):
    """Seed some challenge participations for demo wallets."""
    db.flush()

    active_challenges = db.query(Challenge).filter(
        Challenge.status == "ACTIVE"
    ).all()

    for challenge in active_challenges:
        # Get wallets matching challenge scope
        wallet_q = db.query(DataWallet)
        if challenge.target_country_code:
            wallet_q = wallet_q.filter(
                DataWallet.country_code == challenge.target_country_code
            )

        wallets = wallet_q.limit(10).all()
        for w in wallets:
            existing = db.query(ChallengeParticipation).filter(
                ChallengeParticipation.challenge_id == challenge.id,
                ChallengeParticipation.contributor_phone_hash == w.contributor_phone_hash,
            ).first()
            if not existing:
                db.add(ChallengeParticipation(
                    challenge_id=challenge.id,
                    contributor_phone_hash=w.contributor_phone_hash,
                    country_code=w.country_code,
                    contribution_count=random.randint(1, 20),
                ))
