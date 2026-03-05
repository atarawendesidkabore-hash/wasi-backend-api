"""
Walk15-Style Engagement Engine — Gamification for data tokenization.

6 engine classes:
  A. WalletEngine    — Data wallet CRUD + activity recording
  B. StreakEngine     — Streak calculation + nightly batch
  C. BadgeEngine      — Badge evaluation + award
  D. ChallengeEngine  — Community challenges lifecycle
  E. ImpactEngine     — Monthly impact calculation
  F. RewardEngine     — Reward catalog + redemption
"""
from __future__ import annotations

import json
import logging
from datetime import timezone, datetime, date, timedelta
from typing import List, Optional

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from src.database.engagement_models import (
    DataWallet, BadgeDefinition, UserBadge, BadgeProgress,
    Challenge, ChallengeParticipation, ImpactRecord, RewardCatalog,
)
from src.database.tokenization_models import (
    DataToken, DailyActivityDeclaration,
)

logger = logging.getLogger(__name__)


# ── Streak multiplier thresholds ─────────────────────────────────────
STREAK_MULTIPLIERS = [
    (30, 2.00),
    (14, 1.50),
    (7, 1.25),
    (0, 1.00),
]

# ── Tier thresholds ──────────────────────────────────────────────────
TIER_THRESHOLDS = [
    (75, "PLATINUM", 0.30),
    (50, "GOLD", 0.20),
    (25, "SILVER", 0.10),
    (0, "BRONZE", 0.00),
]

TIER_ORDER = ["BRONZE", "SILVER", "GOLD", "PLATINUM"]

TIER_PERKS = {
    "BRONZE": ["Base access", "Standard payment queue"],
    "SILVER": ["Priority payment queue", "Silver badge"],
    "GOLD": ["Exclusive challenges", "GOLD-tier rewards", "Priority payments"],
    "PLATINUM": ["All rewards unlocked", "2x grace days", "Maximum multiplier bonus"],
}

MAX_MULTIPLIER = 3.00


# ═══════════════════════════════════════════════════════════════════════
# A. WalletEngine
# ═══════════════════════════════════════════════════════════════════════
class WalletEngine:

    @staticmethod
    def get_or_create_wallet(
        db: Session, phone_hash: str, country_code: str,
    ) -> DataWallet:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()
        if wallet:
            return wallet
        wallet = DataWallet(
            contributor_phone_hash=phone_hash,
            country_code=country_code,
        )
        db.add(wallet)
        db.flush()
        return wallet

    @staticmethod
    def record_activity(
        db: Session,
        phone_hash: str,
        country_code: str,
        cfa_earned: float,
        is_cross_validated: bool = False,
    ) -> DataWallet:
        """Record a new activity and update wallet stats."""
        wallet = WalletEngine.get_or_create_wallet(db, phone_hash, country_code)

        # 1. Increment counters
        wallet.total_reports = (wallet.total_reports or 0) + 1
        wallet.total_earned_cfa = (wallet.total_earned_cfa or 0) + cfa_earned
        if is_cross_validated:
            wallet.total_cross_validated = (wallet.total_cross_validated or 0) + 1

        # 2. Update streak
        today = date.today()
        StreakEngine.update_streak(db, wallet, today)

        # 3. Recalculate reputation, tier, multiplier
        WalletEngine._recalculate(db, wallet)

        db.flush()
        return wallet

    @staticmethod
    def _recalculate(db: Session, wallet: DataWallet) -> None:
        """Recalculate reputation score, tier, and multiplier."""
        # Count badges earned
        badge_count = db.query(func.count(UserBadge.id)).filter(
            UserBadge.contributor_phone_hash == wallet.contributor_phone_hash
        ).scalar() or 0

        # Count challenge participations
        challenge_count = db.query(func.count(ChallengeParticipation.id)).filter(
            ChallengeParticipation.contributor_phone_hash == wallet.contributor_phone_hash
        ).scalar() or 0

        # Cross-validated percentage
        total = wallet.total_reports or 1
        xv_pct = (wallet.total_cross_validated or 0) / total

        # Reputation formula
        reputation = (
            min(30, (wallet.total_reports or 0) * 0.3) +
            min(25, (wallet.current_streak or 0) * 0.83) +
            min(20, xv_pct * 20) +
            min(15, badge_count * 1.5) +
            min(10, challenge_count * 2.5)
        )
        wallet.reputation_score = round(min(100, reputation), 2)

        # Tier
        for threshold, tier_name, _ in TIER_THRESHOLDS:
            if wallet.reputation_score >= threshold:
                wallet.tier = tier_name
                break

        # Multiplier = streak_mult + tier_bonus (capped at MAX)
        wallet.current_multiplier = WalletEngine.get_payment_multiplier(wallet)

    @staticmethod
    def get_payment_multiplier(wallet: DataWallet) -> float:
        """Calculate payment multiplier from streak + tier."""
        # Streak multiplier
        streak = wallet.current_streak or 0
        streak_mult = 1.00
        for threshold, mult in STREAK_MULTIPLIERS:
            if streak >= threshold:
                streak_mult = mult
                break

        # Tier bonus
        tier_bonus = 0.00
        for _, tier_name, bonus in TIER_THRESHOLDS:
            if wallet.tier == tier_name:
                tier_bonus = bonus
                break

        return min(MAX_MULTIPLIER, round(streak_mult + tier_bonus, 2))


# ═══════════════════════════════════════════════════════════════════════
# B. StreakEngine
# ═══════════════════════════════════════════════════════════════════════
class StreakEngine:

    @staticmethod
    def update_streak(db: Session, wallet: DataWallet, report_date: date) -> DataWallet:
        """Update streak based on a new report date."""
        last = wallet.last_report_date

        if last == report_date:
            # Already reported today — no change
            return wallet

        if last is not None:
            gap = (report_date - last).days
            if gap == 1:
                # Consecutive day
                wallet.current_streak = (wallet.current_streak or 0) + 1
                wallet.streak_grace_used = False
            elif gap == 2 and not wallet.streak_grace_used:
                # 1 missed day — grace period
                wallet.current_streak = (wallet.current_streak or 0) + 1
                wallet.streak_grace_used = True
            else:
                # Streak broken
                wallet.current_streak = 1
                wallet.streak_grace_used = False
        else:
            # First ever report
            wallet.current_streak = 1

        wallet.last_report_date = report_date

        # Update longest
        if wallet.current_streak > (wallet.longest_streak or 0):
            wallet.longest_streak = wallet.current_streak

        return wallet

    @staticmethod
    def calculate_nightly_streaks(db: Session) -> dict:
        """Nightly batch: reset broken streaks, apply grace."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        stats = {"checked": 0, "reset": 0, "graced": 0}

        # All wallets with active streaks that didn't report yesterday
        wallets = db.query(DataWallet).filter(
            DataWallet.current_streak > 0,
            DataWallet.last_report_date < yesterday,
        ).all()

        for w in wallets:
            stats["checked"] += 1
            if w.last_report_date == two_days_ago and not w.streak_grace_used:
                w.streak_grace_used = True
                stats["graced"] += 1
            elif w.last_report_date is not None and w.last_report_date < two_days_ago:
                w.current_streak = 0
                w.streak_grace_used = False
                stats["reset"] += 1

        db.flush()
        logger.info(f"Nightly streaks: {stats}")
        return stats


# ═══════════════════════════════════════════════════════════════════════
# C. BadgeEngine
# ═══════════════════════════════════════════════════════════════════════

# Badge seed data: ~20 badges
BADGE_SEED = [
    # Onboarding
    {
        "badge_code": "FIRST_REPORT", "name_en": "First Report", "name_fr": "Premier Rapport",
        "description_en": "Submit your first data report", "description_fr": "Soumettez votre premier rapport",
        "category": "ONBOARDING", "rarity": "COMMON", "icon_emoji": "🌱",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 1}),
        "pillar": None, "sort_order": 1,
    },
    # Consistency
    {
        "badge_code": "WEEK_WARRIOR", "name_en": "Week Warrior", "name_fr": "Guerrier 7 Jours",
        "description_en": "Maintain a 7-day reporting streak", "description_fr": "Maintenez une série de 7 jours",
        "category": "CONSISTENCY", "rarity": "COMMON", "icon_emoji": "🔥",
        "unlock_condition": json.dumps({"metric": "current_streak", "threshold": 7}),
        "pillar": None, "sort_order": 10,
    },
    {
        "badge_code": "FORTNIGHT_FIRE", "name_en": "Fortnight Fire", "name_fr": "Flamme 14 Jours",
        "description_en": "Maintain a 14-day reporting streak", "description_fr": "Maintenez une série de 14 jours",
        "category": "CONSISTENCY", "rarity": "RARE", "icon_emoji": "🔥",
        "unlock_condition": json.dumps({"metric": "current_streak", "threshold": 14}),
        "pillar": None, "sort_order": 11,
    },
    {
        "badge_code": "MONTHLY_MASTER", "name_en": "Monthly Master", "name_fr": "Maître du Mois",
        "description_en": "Maintain a 30-day reporting streak", "description_fr": "Maintenez une série de 30 jours",
        "category": "CONSISTENCY", "rarity": "EPIC", "icon_emoji": "⭐",
        "unlock_condition": json.dumps({"metric": "current_streak", "threshold": 30}),
        "pillar": None, "sort_order": 12,
    },
    {
        "badge_code": "CENTURION", "name_en": "Centurion", "name_fr": "Centurion",
        "description_en": "Maintain a 100-day reporting streak", "description_fr": "Maintenez une série de 100 jours",
        "category": "CONSISTENCY", "rarity": "LEGENDARY", "icon_emoji": "👑",
        "unlock_condition": json.dumps({"metric": "current_streak", "threshold": 100}),
        "pillar": None, "sort_order": 13,
    },
    # Quality
    {
        "badge_code": "CROSS_VALIDATOR", "name_en": "Cross-Validator", "name_fr": "Validateur Croisé",
        "description_en": "Have 10 reports cross-validated", "description_fr": "10 rapports validés par croisement",
        "category": "QUALITY", "rarity": "COMMON", "icon_emoji": "✅",
        "unlock_condition": json.dumps({"metric": "total_cross_validated", "threshold": 10}),
        "pillar": None, "sort_order": 20,
    },
    {
        "badge_code": "TRUSTED_SOURCE", "name_en": "Trusted Source", "name_fr": "Source Fiable",
        "description_en": "Have 50 reports cross-validated", "description_fr": "50 rapports validés par croisement",
        "category": "QUALITY", "rarity": "EPIC", "icon_emoji": "🛡️",
        "unlock_condition": json.dumps({"metric": "total_cross_validated", "threshold": 50}),
        "pillar": None, "sort_order": 21,
    },
    # Community
    {
        "badge_code": "MARKET_SENTINEL", "name_en": "Market Sentinel", "name_fr": "Sentinelle du Marché",
        "description_en": "Submit 50 market price reports", "description_fr": "Soumettez 50 rapports de prix",
        "category": "COMMUNITY", "rarity": "RARE", "icon_emoji": "📊",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 50}),
        "pillar": "CITIZEN_DATA", "sort_order": 30,
    },
    {
        "badge_code": "ROAD_WATCHER", "name_en": "Road Watcher", "name_fr": "Veilleur des Routes",
        "description_en": "Submit 20 road condition reports", "description_fr": "Soumettez 20 rapports routiers",
        "category": "COMMUNITY", "rarity": "RARE", "icon_emoji": "🛣️",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 20}),
        "pillar": "CITIZEN_DATA", "sort_order": 31,
    },
    {
        "badge_code": "HEALTH_GUARDIAN", "name_en": "Health Guardian", "name_fr": "Gardien de Santé",
        "description_en": "Submit 20 health facility reports", "description_fr": "Soumettez 20 rapports de santé",
        "category": "COMMUNITY", "rarity": "RARE", "icon_emoji": "🏥",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 20}),
        "pillar": "CITIZEN_DATA", "sort_order": 32,
    },
    # Milestone
    {
        "badge_code": "HUNDRED_CLUB", "name_en": "Hundred Club", "name_fr": "Club des Cent",
        "description_en": "Submit 100 reports", "description_fr": "Soumettez 100 rapports",
        "category": "MILESTONE", "rarity": "RARE", "icon_emoji": "💯",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 100}),
        "pillar": None, "sort_order": 40,
    },
    {
        "badge_code": "THOUSAND_STRONG", "name_en": "Thousand Strong", "name_fr": "Force des Mille",
        "description_en": "Submit 1000 reports", "description_fr": "Soumettez 1000 rapports",
        "category": "MILESTONE", "rarity": "LEGENDARY", "icon_emoji": "🏆",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 1000}),
        "pillar": None, "sort_order": 41,
    },
    # Pillar-specific
    {
        "badge_code": "BUSINESS_PIONEER", "name_en": "Business Pioneer", "name_fr": "Pionnier Entreprise",
        "description_en": "Submit your first business data report", "description_fr": "Premier rapport entreprise",
        "category": "ONBOARDING", "rarity": "COMMON", "icon_emoji": "💼",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 1}),
        "pillar": "BUSINESS_DATA", "sort_order": 50,
    },
    {
        "badge_code": "FASO_BUILDER", "name_en": "Faso Builder", "name_fr": "Bâtisseur Faso",
        "description_en": "Complete 10 worker check-ins", "description_fr": "Effectuez 10 pointages ouvrier",
        "category": "MILESTONE", "rarity": "RARE", "icon_emoji": "🔨",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 10}),
        "pillar": "FASO_MEABO", "sort_order": 51,
    },
    {
        "badge_code": "CIVIC_VOTER", "name_en": "Civic Voter", "name_fr": "Électeur Civique",
        "description_en": "Submit 10 milestone verification votes", "description_fr": "Soumettez 10 votes de vérification",
        "category": "COMMUNITY", "rarity": "RARE", "icon_emoji": "🗳️",
        "unlock_condition": json.dumps({"metric": "total_reports", "threshold": 10}),
        "pillar": "FASO_MEABO", "sort_order": 52,
    },
    # Streak records
    {
        "badge_code": "STREAK_SURVIVOR", "name_en": "Streak Survivor", "name_fr": "Survivant de Série",
        "description_en": "Use your grace day and maintain the streak", "description_fr": "Utilisez votre jour de grâce",
        "category": "CONSISTENCY", "rarity": "RARE", "icon_emoji": "🛟",
        "unlock_condition": json.dumps({"metric": "streak_grace_used", "threshold": 1}),
        "pillar": None, "sort_order": 14,
    },
    # Earning milestones
    {
        "badge_code": "FIRST_THOUSAND_CFA", "name_en": "First 1,000 CFA", "name_fr": "Premier 1 000 CFA",
        "description_en": "Earn 1,000 CFA from data reports", "description_fr": "Gagnez 1 000 CFA de rapports",
        "category": "MILESTONE", "rarity": "COMMON", "icon_emoji": "💰",
        "unlock_condition": json.dumps({"metric": "total_earned_cfa", "threshold": 1000}),
        "pillar": None, "sort_order": 42,
    },
    {
        "badge_code": "TEN_THOUSAND_CFA", "name_en": "10,000 CFA Earner", "name_fr": "10 000 CFA Gagné",
        "description_en": "Earn 10,000 CFA from data reports", "description_fr": "Gagnez 10 000 CFA de rapports",
        "category": "MILESTONE", "rarity": "EPIC", "icon_emoji": "💎",
        "unlock_condition": json.dumps({"metric": "total_earned_cfa", "threshold": 10000}),
        "pillar": None, "sort_order": 43,
    },
    # Challenge participant
    {
        "badge_code": "CHALLENGER", "name_en": "Challenger", "name_fr": "Participant Défi",
        "description_en": "Join your first community challenge", "description_fr": "Rejoignez votre premier défi",
        "category": "COMMUNITY", "rarity": "COMMON", "icon_emoji": "🎯",
        "unlock_condition": json.dumps({"metric": "challenge_participations", "threshold": 1}),
        "pillar": None, "sort_order": 33,
    },
]


class BadgeEngine:

    @staticmethod
    def seed_badges(db: Session) -> int:
        """Seed badge definitions (idempotent)."""
        created = 0
        for badge_data in BADGE_SEED:
            existing = db.query(BadgeDefinition).filter(
                BadgeDefinition.badge_code == badge_data["badge_code"]
            ).first()
            if not existing:
                db.add(BadgeDefinition(**badge_data))
                created += 1
        db.flush()
        logger.info(f"Badge seed: {created} new badges created")
        return created

    @staticmethod
    def check_and_award(
        db: Session, phone_hash: str, wallet: DataWallet,
    ) -> List[BadgeDefinition]:
        """Evaluate all badge conditions and award new ones."""
        # Already earned badge IDs
        earned_ids = set(
            row[0] for row in db.query(UserBadge.badge_id).filter(
                UserBadge.contributor_phone_hash == phone_hash
            ).all()
        )

        # Challenge participation count for CHALLENGER badge
        challenge_count = db.query(func.count(ChallengeParticipation.id)).filter(
            ChallengeParticipation.contributor_phone_hash == phone_hash
        ).scalar() or 0

        # Build metrics dict
        metrics = {
            "total_reports": wallet.total_reports or 0,
            "current_streak": wallet.current_streak or 0,
            "longest_streak": wallet.longest_streak or 0,
            "total_cross_validated": wallet.total_cross_validated or 0,
            "total_earned_cfa": wallet.total_earned_cfa or 0,
            "streak_grace_used": 1 if wallet.streak_grace_used else 0,
            "challenge_participations": challenge_count,
        }

        all_badges = db.query(BadgeDefinition).all()
        newly_awarded = []

        for badge in all_badges:
            if badge.id in earned_ids:
                continue

            condition = json.loads(badge.unlock_condition)
            metric_name = condition.get("metric", "")
            threshold = condition.get("threshold", 0)
            current_val = metrics.get(metric_name, 0)

            # Update progress
            BadgeEngine._update_progress(db, phone_hash, badge, current_val, threshold)

            if current_val >= threshold:
                # Award badge
                user_badge = UserBadge(
                    contributor_phone_hash=phone_hash,
                    badge_id=badge.id,
                    progress_value=current_val,
                )
                db.add(user_badge)
                newly_awarded.append(badge)
                logger.info(f"Badge awarded: {badge.badge_code} → {phone_hash[:8]}...")

        if newly_awarded:
            db.flush()
        return newly_awarded

    @staticmethod
    def _update_progress(
        db: Session, phone_hash: str, badge: BadgeDefinition,
        current_value: int, target_value: int,
    ) -> None:
        """Upsert badge progress record."""
        progress = db.query(BadgeProgress).filter(
            BadgeProgress.contributor_phone_hash == phone_hash,
            BadgeProgress.badge_id == badge.id,
        ).first()

        if progress:
            progress.current_value = current_value
            progress.last_updated = datetime.now(timezone.utc)
        else:
            db.add(BadgeProgress(
                contributor_phone_hash=phone_hash,
                badge_id=badge.id,
                current_value=current_value,
                target_value=target_value,
            ))

    @staticmethod
    def get_user_badges(db: Session, phone_hash: str) -> list:
        """Get all badges with earned status and progress."""
        all_badges = db.query(BadgeDefinition).order_by(BadgeDefinition.sort_order).all()

        earned_map = {}
        for ub in db.query(UserBadge).filter(
            UserBadge.contributor_phone_hash == phone_hash
        ).all():
            earned_map[ub.badge_id] = ub

        progress_map = {}
        for bp in db.query(BadgeProgress).filter(
            BadgeProgress.contributor_phone_hash == phone_hash
        ).all():
            progress_map[bp.badge_id] = bp

        result = []
        for badge in all_badges:
            earned = earned_map.get(badge.id)
            progress = progress_map.get(badge.id)
            condition = json.loads(badge.unlock_condition)
            target = condition.get("threshold", 0)
            current = progress.current_value if progress else 0

            result.append({
                "badge_code": badge.badge_code,
                "name_en": badge.name_en,
                "name_fr": badge.name_fr,
                "category": badge.category,
                "rarity": badge.rarity,
                "icon_emoji": badge.icon_emoji,
                "earned_at": earned.earned_at if earned else None,
                "earned": earned is not None,
                "progress_current": min(current, target),
                "progress_target": target,
                "progress_pct": round(min(current / target, 1.0) * 100, 1) if target > 0 else 0,
            })
        return result


# ═══════════════════════════════════════════════════════════════════════
# D. ChallengeEngine
# ═══════════════════════════════════════════════════════════════════════
class ChallengeEngine:

    @staticmethod
    def create_challenge(db: Session, **kwargs) -> Challenge:
        challenge = Challenge(**kwargs)
        db.add(challenge)
        db.flush()
        logger.info(f"Challenge created: {challenge.challenge_code}")
        return challenge

    @staticmethod
    def join_challenge(
        db: Session, challenge_id: int, phone_hash: str, country_code: str,
    ) -> ChallengeParticipation:
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            raise ValueError("Challenge not found")
        if challenge.status not in ("ACTIVE", "UPCOMING"):
            raise ValueError(f"Challenge is {challenge.status}, cannot join")

        # Check scope
        if challenge.scope == "COUNTRY" and challenge.target_country_code:
            if country_code != challenge.target_country_code:
                raise ValueError(f"Challenge restricted to {challenge.target_country_code}")

        # Check duplicate
        existing = db.query(ChallengeParticipation).filter(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.contributor_phone_hash == phone_hash,
        ).first()
        if existing:
            return existing

        participation = ChallengeParticipation(
            challenge_id=challenge_id,
            contributor_phone_hash=phone_hash,
            country_code=country_code,
        )
        db.add(participation)
        db.flush()
        return participation

    @staticmethod
    def record_contribution_for_user(db: Session, phone_hash: str) -> None:
        """Auto-increment contribution for all active challenges the user joined."""
        now = datetime.now(timezone.utc)
        active_participations = (
            db.query(ChallengeParticipation)
            .join(Challenge)
            .filter(
                ChallengeParticipation.contributor_phone_hash == phone_hash,
                Challenge.status == "ACTIVE",
            )
            .all()
        )
        for p in active_participations:
            p.contribution_count = (p.contribution_count or 0) + 1
            p.challenge.current_progress = (p.challenge.current_progress or 0) + 1

            # Check if challenge goal reached
            if p.challenge.current_progress >= p.challenge.goal_target:
                p.challenge.status = "COMPLETED"
                logger.info(f"Challenge completed: {p.challenge.challenge_code}")

        if active_participations:
            db.flush()

    @staticmethod
    def get_leaderboard(db: Session, challenge_id: int, limit: int = 20) -> list:
        rows = (
            db.query(ChallengeParticipation)
            .filter(ChallengeParticipation.challenge_id == challenge_id)
            .order_by(desc(ChallengeParticipation.contribution_count))
            .limit(limit)
            .all()
        )
        result = []
        for rank, p in enumerate(rows, 1):
            # Try to get reputation from wallet
            wallet = db.query(DataWallet).filter(
                DataWallet.contributor_phone_hash == p.contributor_phone_hash
            ).first()
            result.append({
                "rank": rank,
                "contributor_phone_hash": p.contributor_phone_hash[:12] + "...",
                "country_code": p.country_code,
                "contribution_count": p.contribution_count or 0,
                "reputation_score": wallet.reputation_score if wallet else 0,
            })
        return result

    @staticmethod
    def lifecycle_tick(db: Session) -> dict:
        """Transition challenge statuses based on dates."""
        now = datetime.now(timezone.utc)
        stats = {"activated": 0, "completed": 0}

        # UPCOMING → ACTIVE
        upcoming = db.query(Challenge).filter(
            Challenge.status == "UPCOMING",
            Challenge.start_date <= now,
        ).all()
        for c in upcoming:
            c.status = "ACTIVE"
            stats["activated"] += 1

        # ACTIVE → COMPLETED (time expired)
        expired = db.query(Challenge).filter(
            Challenge.status == "ACTIVE",
            Challenge.end_date < now,
        ).all()
        for c in expired:
            c.status = "COMPLETED"
            stats["completed"] += 1

        if stats["activated"] or stats["completed"]:
            db.flush()
        logger.info(f"Challenge lifecycle: {stats}")
        return stats


# ═══════════════════════════════════════════════════════════════════════
# E. ImpactEngine
# ═══════════════════════════════════════════════════════════════════════
class ImpactEngine:

    @staticmethod
    def calculate_user_impact(
        db: Session, phone_hash: str, period_month: str, country_code: str,
    ) -> ImpactRecord:
        """Calculate monthly impact for a contributor."""
        # Parse month range
        year, month = int(period_month[:4]), int(period_month[5:7])
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)

        # Count reports
        reports = db.query(func.count(DataToken.id)).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= start,
            DataToken.period_date < end,
        ).scalar() or 0

        # Count cross-validated
        xv_count = db.query(func.count(DailyActivityDeclaration.id)).filter(
            DailyActivityDeclaration.contributor_phone_hash == phone_hash,
            DailyActivityDeclaration.period_date >= start,
            DailyActivityDeclaration.period_date < end,
            DailyActivityDeclaration.is_cross_validated.is_(True),
        ).scalar() or 0

        # Count distinct regions
        regions = db.query(func.count(func.distinct(
            DailyActivityDeclaration.location_region
        ))).filter(
            DailyActivityDeclaration.contributor_phone_hash == phone_hash,
            DailyActivityDeclaration.period_date >= start,
            DailyActivityDeclaration.period_date < end,
            DailyActivityDeclaration.location_region.isnot(None),
        ).scalar() or 0

        # Avg data quality
        avg_conf = db.query(func.avg(DataToken.confidence)).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= start,
            DataToken.period_date < end,
        ).scalar() or 0

        formal_equiv = xv_count // 20
        est_usd = round(reports * 0.15, 2)  # ~$0.15 per report value estimate

        # Upsert
        record = db.query(ImpactRecord).filter(
            ImpactRecord.contributor_phone_hash == phone_hash,
            ImpactRecord.period_month == period_month,
        ).first()

        if record:
            record.reports_submitted = reports
            record.cross_validated_count = xv_count
            record.regions_covered = regions
            record.countries_helped = 1 if reports > 0 else 0
            record.data_quality_avg = round(avg_conf, 2)
            record.formal_surveys_equivalent = formal_equiv
            record.estimated_value_usd = est_usd
        else:
            record = ImpactRecord(
                contributor_phone_hash=phone_hash,
                period_month=period_month,
                country_code=country_code,
                reports_submitted=reports,
                cross_validated_count=xv_count,
                regions_covered=regions,
                countries_helped=1 if reports > 0 else 0,
                data_quality_avg=round(avg_conf, 2),
                formal_surveys_equivalent=formal_equiv,
                estimated_value_usd=est_usd,
            )
            db.add(record)

        db.flush()
        return record

    @staticmethod
    def get_user_dashboard(db: Session, phone_hash: str) -> dict:
        """Full user engagement dashboard."""
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        if not wallet:
            return {"error": "No wallet found"}

        # Badge counts
        badges_earned = db.query(func.count(UserBadge.id)).filter(
            UserBadge.contributor_phone_hash == phone_hash
        ).scalar() or 0
        badges_total = db.query(func.count(BadgeDefinition.id)).scalar() or 0

        # Active challenges
        active_challenges = (
            db.query(func.count(ChallengeParticipation.id))
            .join(Challenge)
            .filter(
                ChallengeParticipation.contributor_phone_hash == phone_hash,
                Challenge.status == "ACTIVE",
            )
            .scalar() or 0
        )

        # Lifetime impact
        impact_agg = db.query(
            func.sum(ImpactRecord.reports_submitted),
            func.sum(ImpactRecord.cross_validated_count),
            func.sum(ImpactRecord.regions_covered),
            func.sum(ImpactRecord.countries_helped),
            func.sum(ImpactRecord.formal_surveys_equivalent),
            func.sum(ImpactRecord.estimated_value_usd),
        ).filter(
            ImpactRecord.contributor_phone_hash == phone_hash
        ).first()

        return {
            "wallet": wallet,
            "badges_earned": badges_earned,
            "badges_total": badges_total,
            "active_challenges": active_challenges,
            "lifetime_impact": {
                "total_reports": impact_agg[0] or 0,
                "total_cross_validated": impact_agg[1] or 0,
                "total_regions": impact_agg[2] or 0,
                "total_countries_helped": impact_agg[3] or 0,
                "total_formal_surveys_equivalent": impact_agg[4] or 0,
                "total_value_usd": float(impact_agg[5] or 0),
            },
        }


# ═══════════════════════════════════════════════════════════════════════
# F. RewardEngine
# ═══════════════════════════════════════════════════════════════════════
class RewardEngine:

    @staticmethod
    def get_catalog(db: Session, tier: str = "BRONZE") -> list:
        """Get available rewards filtered by tier."""
        tier_idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
        eligible_tiers = TIER_ORDER[:tier_idx + 1]

        return (
            db.query(RewardCatalog)
            .filter(
                RewardCatalog.is_active.is_(True),
                RewardCatalog.min_tier.in_(eligible_tiers),
            )
            .order_by(RewardCatalog.cost_cfa)
            .all()
        )

    @staticmethod
    def redeem_reward(
        db: Session, phone_hash: str, reward_code: str,
    ) -> dict:
        """Redeem a reward from the catalog."""
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()
        if not wallet:
            raise ValueError("No wallet found")

        reward = db.query(RewardCatalog).filter(
            RewardCatalog.reward_code == reward_code,
            RewardCatalog.is_active.is_(True),
        ).first()
        if not reward:
            raise ValueError("Reward not found or inactive")

        # Check tier eligibility
        wallet_tier_idx = TIER_ORDER.index(wallet.tier) if wallet.tier in TIER_ORDER else 0
        reward_tier_idx = TIER_ORDER.index(reward.min_tier) if reward.min_tier in TIER_ORDER else 0
        if wallet_tier_idx < reward_tier_idx:
            raise ValueError(f"Requires {reward.min_tier} tier (you are {wallet.tier})")

        # Check balance (available = earned - redeemed)
        available = (wallet.total_earned_cfa or 0) - (wallet.total_redeemed_cfa or 0)
        if available < reward.cost_cfa:
            raise ValueError(
                f"Insufficient balance: {available:.2f} CFA "
                f"(need {reward.cost_cfa} CFA)"
            )

        # Atomic deduction: increment redeemed counter (total_earned_cfa stays intact)
        from sqlalchemy import text
        result = db.execute(
            text(
                "UPDATE data_wallets "
                "SET total_redeemed_cfa = COALESCE(total_redeemed_cfa, 0) + :cost "
                "WHERE contributor_phone_hash = :ph "
                "AND (COALESCE(total_earned_cfa, 0) - COALESCE(total_redeemed_cfa, 0)) >= :cost"
            ),
            {"cost": float(reward.cost_cfa), "ph": phone_hash},
        )
        if result.rowcount == 0:
            raise ValueError("Insufficient balance (concurrent redemption)")

        db.refresh(wallet)

        # Generate payment reference
        import uuid
        payment_ref = None
        if reward.reward_type in ("AIRTIME", "DATA_BUNDLE"):
            payment_ref = f"REWARD-{reward.reward_type}-{uuid.uuid4().hex[:8].upper()}"
        elif reward.reward_type == "ECFA_BONUS":
            payment_ref = f"ECFA-BONUS-{uuid.uuid4().hex[:8].upper()}"

        db.flush()
        remaining = (wallet.total_earned_cfa or 0) - (wallet.total_redeemed_cfa or 0)
        logger.info(
            f"Reward redeemed: {reward_code} by {phone_hash[:8]}... "
            f"({reward.cost_cfa} CFA, remaining: {remaining:.2f} CFA)"
        )

        return {
            "status": "redeemed",
            "reward_code": reward_code,
            "reward_name": reward.name_en,
            "cost_cfa": reward.cost_cfa,
            "payment_reference": payment_ref,
            "remaining_balance_cfa": remaining,
        }
