"""
Walk15-Style Engagement Models — Gamification layer for data tokenization.

8 models supporting 5 layers:
  Layer 1: DataWallet (streak, reputation, tier, multiplier)
  Layer 2: BadgeDefinition, UserBadge, BadgeProgress
  Layer 3: Challenge, ChallengeParticipation
  Layer 4: ImpactRecord
  Layer 5: RewardCatalog
"""

from datetime import timezone, datetime, date
from sqlalchemy import (
    Column, Integer, Float, Numeric, String, Text, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from src.database.models import Base


# ---------------------------------------------------------------------------
# Model 1: DataWallet — the "step counter" (one per contributor)
# ---------------------------------------------------------------------------
class DataWallet(Base):
    __tablename__ = "data_wallets"

    id = Column(Integer, primary_key=True, index=True)
    contributor_phone_hash = Column(String(64), unique=True, nullable=False, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # Cumulative stats
    total_reports = Column(Integer, default=0, nullable=False)
    total_earned_cfa = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)
    total_redeemed_cfa = Column(Numeric(18, 2, asdecimal=False), default=0, nullable=False)
    total_cross_validated = Column(Integer, default=0, nullable=False)

    # Streak
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_report_date = Column(Date, nullable=True)
    streak_grace_used = Column(Boolean, default=False, nullable=False)

    # Reputation (0.00 - 100.00)
    reputation_score = Column(Numeric(5, 2, asdecimal=False), default=0.00, nullable=False)

    # Tier: BRONZE | SILVER | GOLD | PLATINUM
    tier = Column(String(10), default="BRONZE", nullable=False, index=True)

    # Payment multiplier (driven by streak + tier)
    current_multiplier = Column(Numeric(3, 2, asdecimal=False), default=1.00, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    badges = relationship("UserBadge", back_populates="wallet", foreign_keys="UserBadge.contributor_phone_hash", primaryjoin="DataWallet.contributor_phone_hash == UserBadge.contributor_phone_hash")


# ---------------------------------------------------------------------------
# Model 2: BadgeDefinition — badge catalog (seeded once)
# ---------------------------------------------------------------------------
class BadgeDefinition(Base):
    __tablename__ = "badge_definitions"

    id = Column(Integer, primary_key=True, index=True)
    badge_code = Column(String(40), unique=True, nullable=False, index=True)

    # Display
    name_en = Column(String(100), nullable=False)
    name_fr = Column(String(100), nullable=False)
    description_en = Column(Text)
    description_fr = Column(Text)

    # Classification
    category = Column(String(20), nullable=False, index=True)
    # ONBOARDING | CONSISTENCY | QUALITY | COMMUNITY | MILESTONE
    rarity = Column(String(12), nullable=False)
    # COMMON | RARE | EPIC | LEGENDARY
    icon_emoji = Column(String(10))

    # Unlock condition (JSON): {"metric": "total_reports", "threshold": 1}
    unlock_condition = Column(Text, nullable=False)

    # Pillar filter: NULL=any pillar, or CITIZEN_DATA | BUSINESS_DATA | FASO_MEABO
    pillar = Column(String(20), nullable=True)

    sort_order = Column(Integer, default=0)

    # Relationships
    user_badges = relationship("UserBadge", back_populates="badge")
    progress_records = relationship("BadgeProgress", back_populates="badge")


# ---------------------------------------------------------------------------
# Model 3: UserBadge — earned badges per contributor
# ---------------------------------------------------------------------------
class UserBadge(Base):
    __tablename__ = "user_badges"

    id = Column(Integer, primary_key=True, index=True)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badge_definitions.id"), nullable=False)

    earned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    progress_value = Column(Integer, default=0)

    # Relationships
    badge = relationship("BadgeDefinition", back_populates="user_badges")
    wallet = relationship(
        "DataWallet",
        back_populates="badges",
        foreign_keys=[contributor_phone_hash],
        primaryjoin="UserBadge.contributor_phone_hash == DataWallet.contributor_phone_hash",
    )

    __table_args__ = (
        UniqueConstraint("contributor_phone_hash", "badge_id", name="uq_user_badge"),
    )


# ---------------------------------------------------------------------------
# Model 4: BadgeProgress — partial completion tracking
# ---------------------------------------------------------------------------
class BadgeProgress(Base):
    __tablename__ = "badge_progress"

    id = Column(Integer, primary_key=True, index=True)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)
    badge_id = Column(Integer, ForeignKey("badge_definitions.id"), nullable=False)

    current_value = Column(Integer, default=0, nullable=False)
    target_value = Column(Integer, nullable=False)

    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    badge = relationship("BadgeDefinition", back_populates="progress_records")

    __table_args__ = (
        UniqueConstraint("contributor_phone_hash", "badge_id", name="uq_badge_progress"),
    )


# ---------------------------------------------------------------------------
# Model 5: Challenge — community challenges
# ---------------------------------------------------------------------------
class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, index=True)
    challenge_code = Column(String(40), unique=True, nullable=False, index=True)

    # Display
    title_en = Column(String(200), nullable=False)
    title_fr = Column(String(200), nullable=False)
    description_en = Column(Text)
    description_fr = Column(Text)

    # Scope: REGIONAL | COUNTRY | GLOBAL
    scope = Column(String(10), nullable=False)
    target_country_code = Column(String(2), nullable=True, index=True)
    target_region = Column(String(100), nullable=True)

    # Goal
    goal_metric = Column(String(30), nullable=False)
    # citizen_reports | cross_validated | unique_reporters | business_submissions | worker_checkins
    goal_target = Column(Integer, nullable=False)
    current_progress = Column(Integer, default=0, nullable=False)

    # Timing
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)

    # Lifecycle: UPCOMING → ACTIVE → COMPLETED → ARCHIVED
    status = Column(String(12), default="UPCOMING", nullable=False, index=True)

    # Rewards
    reward_multiplier = Column(Numeric(3, 2, asdecimal=False), default=1.50, nullable=False)
    bonus_cfa = Column(Numeric(12, 2, asdecimal=False), default=0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    participants = relationship("ChallengeParticipation", back_populates="challenge")


# ---------------------------------------------------------------------------
# Model 6: ChallengeParticipation — per-user enrollment + contribution
# ---------------------------------------------------------------------------
class ChallengeParticipation(Base):
    __tablename__ = "challenge_participations"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)
    country_code = Column(String(2), nullable=False)

    contribution_count = Column(Integer, default=0, nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    challenge = relationship("Challenge", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("challenge_id", "contributor_phone_hash", name="uq_challenge_participant"),
    )


# ---------------------------------------------------------------------------
# Model 7: ImpactRecord — per-user monthly impact summary
# ---------------------------------------------------------------------------
class ImpactRecord(Base):
    __tablename__ = "impact_records"

    id = Column(Integer, primary_key=True, index=True)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)
    period_month = Column(String(7), nullable=False, index=True)  # "2026-03"
    country_code = Column(String(2), nullable=False)

    # Impact metrics
    reports_submitted = Column(Integer, default=0, nullable=False)
    cross_validated_count = Column(Integer, default=0, nullable=False)
    regions_covered = Column(Integer, default=0, nullable=False)
    countries_helped = Column(Integer, default=0, nullable=False)
    data_quality_avg = Column(Numeric(4, 2, asdecimal=False), default=0, nullable=False)

    # Economic equivalence
    formal_surveys_equivalent = Column(Integer, default=0, nullable=False)
    estimated_value_usd = Column(Numeric(10, 2, asdecimal=False), default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("contributor_phone_hash", "period_month", name="uq_impact_month"),
    )


# ---------------------------------------------------------------------------
# Model 8: RewardCatalog — redeemable rewards
# ---------------------------------------------------------------------------
class RewardCatalog(Base):
    __tablename__ = "reward_catalog"

    id = Column(Integer, primary_key=True, index=True)
    reward_code = Column(String(40), unique=True, nullable=False, index=True)

    # Display
    name_en = Column(String(100), nullable=False)
    name_fr = Column(String(100), nullable=False)
    description_en = Column(Text)
    description_fr = Column(Text)

    # Type: AIRTIME | DATA_BUNDLE | ECFA_BONUS | PARTNER_DISCOUNT
    reward_type = Column(String(20), nullable=False)

    cost_cfa = Column(Numeric(12, 2, asdecimal=False), nullable=False)
    min_tier = Column(String(10), default="BRONZE", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Partner info (for PARTNER_DISCOUNT type)
    partner_name = Column(String(100), nullable=True)
