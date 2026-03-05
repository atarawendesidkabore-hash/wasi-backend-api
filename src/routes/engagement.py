"""
Walk15-Style Engagement Routes — Gamification for data tokenization.

Endpoints (18 total, all under /api/v3/engagement/):
  GET  /wallet                          — My data wallet
  GET  /wallet/{cc}/leaderboard         — Country leaderboard
  GET  /badges                          — My badges (earned + progress)
  GET  /badges/catalog                  — All badge definitions
  GET  /challenges                      — Active + upcoming challenges
  GET  /challenges/{id}                 — Challenge details + leaderboard
  POST /challenges/{id}/join            — Join a challenge (FREE)
  GET  /impact                          — Lifetime impact dashboard
  GET  /impact/{period_month}           — Monthly impact breakdown
  GET  /rewards                         — Reward catalog
  POST /rewards/{code}/redeem           — Redeem a reward
  GET  /streak                          — Streak details
  GET  /tier                            — Tier info + progress
  GET  /country/{cc}/stats              — Country engagement stats
  POST /admin/challenges/create         — Create challenge
  POST /admin/rewards/create            — Add reward to catalog
  GET  /admin/engagement-summary        — Platform-wide metrics
  POST /admin/badges/seed               — Seed badge definitions
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.engagement_models import (
    DataWallet, BadgeDefinition, UserBadge, BadgeProgress,
    Challenge, ChallengeParticipation, ImpactRecord, RewardCatalog,
)
from src.schemas.engagement import (
    DataWalletResponse, StreakResponse, TierResponse,
    BadgeDefinitionResponse, UserBadgeResponse,
    ChallengeResponse, ChallengeDetailResponse, LeaderboardEntry,
    ImpactResponse, ImpactDashboardResponse, LifetimeImpact,
    RewardCatalogResponse, RewardRedeemResponse,
    CountryEngagementResponse, EngagementSummaryResponse,
    ChallengeCreateRequest, RewardCreateRequest,
)
from src.engines.engagement_engine import (
    WalletEngine, StreakEngine, BadgeEngine, ChallengeEngine,
    ImpactEngine, RewardEngine,
    STREAK_MULTIPLIERS, TIER_THRESHOLDS, TIER_ORDER, TIER_PERKS,
)
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits
from src.utils.phone_hash import phone_hash_from_user, truncate_phone_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/engagement", tags=["Engagement (Walk15)"])
limiter = Limiter(key_func=get_remote_address)

# Allowed challenge status values for query filtering
VALID_CHALLENGE_STATUSES = {"UPCOMING", "ACTIVE", "COMPLETED", "ARCHIVED"}


# ═══════════════════════════════════════════════════════════════════════
# 1. Wallet
# ═══════════════════════════════════════════════════════════════════════

@router.get("/wallet", response_model=DataWalletResponse)
@limiter.limit("30/minute")
async def get_wallet(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """My data wallet — streak, reputation, tier, multiplier. FREE."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()
    if not wallet:
        # Create empty wallet
        wallet = WalletEngine.get_or_create_wallet(db, ph, "NG")
        db.commit()
    return wallet


@router.get("/wallet/{country_code}/leaderboard")
@limiter.limit("10/minute")
async def wallet_leaderboard(
    request: Request,
    country_code: str = Path(..., min_length=2, max_length=2),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top wallets by reputation in a country. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/engagement/leaderboard", cost_multiplier=1.0)

    wallets = (
        db.query(DataWallet)
        .filter(DataWallet.country_code == country_code.upper())
        .order_by(desc(DataWallet.reputation_score))
        .limit(limit)
        .all()
    )
    return [
        {
            "rank": i + 1,
            "contributor_phone_hash": truncate_phone_hash(w.contributor_phone_hash),
            "country_code": w.country_code,
            "reputation_score": w.reputation_score,
            "tier": w.tier,
            "total_reports": w.total_reports,
            "current_streak": w.current_streak,
        }
        for i, w in enumerate(wallets)
    ]


# ═══════════════════════════════════════════════════════════════════════
# 2. Badges
# ═══════════════════════════════════════════════════════════════════════

@router.get("/badges", response_model=list[UserBadgeResponse])
@limiter.limit("30/minute")
async def get_my_badges(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """My badges — earned + in-progress. FREE."""
    ph = phone_hash_from_user(current_user)
    return BadgeEngine.get_user_badges(db, ph)


@router.get("/badges/catalog", response_model=list[BadgeDefinitionResponse])
@limiter.limit("10/minute")
async def get_badge_catalog(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All available badge definitions. FREE."""
    return (
        db.query(BadgeDefinition)
        .order_by(BadgeDefinition.sort_order)
        .all()
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. Challenges
# ═══════════════════════════════════════════════════════════════════════

@router.get("/challenges", response_model=list[ChallengeResponse])
@limiter.limit("20/minute")
async def get_challenges(
    request: Request,
    status: Optional[str] = Query(default=None, description="UPCOMING|ACTIVE|COMPLETED"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active + upcoming challenges. FREE."""
    q = db.query(Challenge)
    if status:
        status_val = status.upper()
        if status_val not in VALID_CHALLENGE_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(sorted(VALID_CHALLENGE_STATUSES))}")
        q = q.filter(Challenge.status == status_val)
    else:
        q = q.filter(Challenge.status.in_(["ACTIVE", "UPCOMING"]))

    challenges = q.order_by(Challenge.start_date).all()
    result = []
    for c in challenges:
        participant_count = db.query(func.count(ChallengeParticipation.id)).filter(
            ChallengeParticipation.challenge_id == c.id
        ).scalar() or 0
        result.append(ChallengeResponse(
            id=c.id,
            challenge_code=c.challenge_code,
            title_en=c.title_en,
            title_fr=c.title_fr,
            description_en=c.description_en,
            description_fr=c.description_fr,
            scope=c.scope,
            target_country_code=c.target_country_code,
            target_region=c.target_region,
            goal_metric=c.goal_metric,
            goal_target=c.goal_target,
            current_progress=c.current_progress,
            progress_pct=round((c.current_progress / c.goal_target) * 100, 1) if c.goal_target > 0 else 0,
            start_date=c.start_date,
            end_date=c.end_date,
            status=c.status,
            reward_multiplier=c.reward_multiplier,
            bonus_cfa=c.bonus_cfa,
            participant_count=participant_count,
        ))
    return result


@router.get("/challenges/{challenge_id}")
@limiter.limit("20/minute")
async def get_challenge_detail(
    request: Request,
    challenge_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Challenge details + leaderboard. FREE."""
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(404, "Challenge not found")

    participant_count = db.query(func.count(ChallengeParticipation.id)).filter(
        ChallengeParticipation.challenge_id == challenge_id
    ).scalar() or 0

    leaderboard = ChallengeEngine.get_leaderboard(db, challenge_id, limit=20)

    return {
        "id": challenge.id,
        "challenge_code": challenge.challenge_code,
        "title_en": challenge.title_en,
        "title_fr": challenge.title_fr,
        "description_en": challenge.description_en,
        "description_fr": challenge.description_fr,
        "scope": challenge.scope,
        "target_country_code": challenge.target_country_code,
        "target_region": challenge.target_region,
        "goal_metric": challenge.goal_metric,
        "goal_target": challenge.goal_target,
        "current_progress": challenge.current_progress,
        "progress_pct": round((challenge.current_progress / challenge.goal_target) * 100, 1) if challenge.goal_target > 0 else 0,
        "start_date": challenge.start_date,
        "end_date": challenge.end_date,
        "status": challenge.status,
        "reward_multiplier": challenge.reward_multiplier,
        "bonus_cfa": challenge.bonus_cfa,
        "participant_count": participant_count,
        "leaderboard": leaderboard,
    }


@router.post("/challenges/{challenge_id}/join")
@limiter.limit("10/minute")
async def join_challenge(
    request: Request,
    challenge_id: int = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Join a community challenge. FREE to encourage participation."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()
    country_code = wallet.country_code if wallet else "NG"

    try:
        participation = ChallengeEngine.join_challenge(
            db, challenge_id, ph, country_code
        )
        db.commit()
        return {
            "status": "joined",
            "challenge_id": challenge_id,
            "contribution_count": participation.contribution_count,
            "joined_at": participation.joined_at,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════════
# 4. Impact
# ═══════════════════════════════════════════════════════════════════════

@router.get("/impact")
@limiter.limit("20/minute")
async def get_impact_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lifetime impact dashboard. FREE."""
    ph = phone_hash_from_user(current_user)
    dashboard = ImpactEngine.get_user_dashboard(db, ph)
    if "error" in dashboard:
        raise HTTPException(404, dashboard["error"])

    wallet = dashboard["wallet"]

    # Streak info
    streak = wallet.current_streak or 0
    next_milestone = None
    next_mult = None
    for threshold, mult in STREAK_MULTIPLIERS:
        if streak < threshold:
            next_milestone = threshold
            next_mult = mult
    if next_milestone is None:
        next_milestone = 0
        next_mult = wallet.current_multiplier or 2.0

    return {
        "wallet": DataWalletResponse.model_validate(wallet),
        "current_streak": {
            "current_streak": wallet.current_streak,
            "longest_streak": wallet.longest_streak,
            "last_report_date": wallet.last_report_date,
            "streak_grace_used": wallet.streak_grace_used,
            "current_multiplier": wallet.current_multiplier,
            "next_milestone": next_milestone,
            "next_multiplier": next_mult,
        },
        "badges_earned": dashboard["badges_earned"],
        "badges_total": dashboard["badges_total"],
        "active_challenges": dashboard["active_challenges"],
        "lifetime_impact": dashboard["lifetime_impact"],
    }


@router.get("/impact/{period_month}", response_model=ImpactResponse)
@limiter.limit("20/minute")
async def get_monthly_impact(
    request: Request,
    period_month: str = Path(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Monthly impact breakdown. FREE."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()
    if not wallet:
        raise HTTPException(404, "No wallet found")

    record = ImpactEngine.calculate_user_impact(db, ph, period_month, wallet.country_code)
    db.commit()
    return record


# ═══════════════════════════════════════════════════════════════════════
# 5. Rewards
# ═══════════════════════════════════════════════════════════════════════

@router.get("/rewards", response_model=list[RewardCatalogResponse])
@limiter.limit("20/minute")
async def get_rewards(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reward catalog filtered by my tier. FREE."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()
    tier = wallet.tier if wallet else "BRONZE"
    return RewardEngine.get_catalog(db, tier)


@router.post("/rewards/{reward_code}/redeem", response_model=RewardRedeemResponse)
@limiter.limit("5/minute")
async def redeem_reward(
    request: Request,
    reward_code: str = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Redeem a reward from the catalog. FREE (costs from wallet balance)."""
    ph = phone_hash_from_user(current_user)
    try:
        result = RewardEngine.redeem_reward(db, ph, reward_code)
        db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══════════════════════════════════════════════════════════════════════
# 6. Streak & Tier
# ═══════════════════════════════════════════════════════════════════════

@router.get("/streak", response_model=StreakResponse)
@limiter.limit("30/minute")
async def get_streak(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current streak details. FREE."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()
    if not wallet:
        return StreakResponse(
            current_streak=0, longest_streak=0, last_report_date=None,
            streak_grace_used=False, current_multiplier=1.0,
            next_milestone=7, next_multiplier=1.25,
        )

    streak = wallet.current_streak or 0
    next_milestone = None
    next_mult = None
    for threshold, mult in STREAK_MULTIPLIERS:
        if streak < threshold:
            next_milestone = threshold
            next_mult = mult
    if next_milestone is None:
        next_milestone = 0
        next_mult = wallet.current_multiplier or 2.0

    return StreakResponse(
        current_streak=wallet.current_streak or 0,
        longest_streak=wallet.longest_streak or 0,
        last_report_date=wallet.last_report_date,
        streak_grace_used=wallet.streak_grace_used or False,
        current_multiplier=wallet.current_multiplier or 1.0,
        next_milestone=next_milestone,
        next_multiplier=next_mult,
    )


@router.get("/tier", response_model=TierResponse)
@limiter.limit("30/minute")
async def get_tier(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tier info + progress to next tier. FREE."""
    ph = phone_hash_from_user(current_user)
    wallet = db.query(DataWallet).filter(
        DataWallet.contributor_phone_hash == ph
    ).first()

    current_tier = wallet.tier if wallet else "BRONZE"
    score = wallet.reputation_score if wallet else 0

    # Find next tier
    tier_idx = TIER_ORDER.index(current_tier) if current_tier in TIER_ORDER else 0
    next_tier = TIER_ORDER[tier_idx + 1] if tier_idx < len(TIER_ORDER) - 1 else None

    # Points to next
    points_to_next = 0
    if next_tier:
        for threshold, name, _ in TIER_THRESHOLDS:
            if name == next_tier:
                points_to_next = max(0, threshold - score)
                break

    # Multiplier bonus
    mult_bonus = 0
    for _, name, bonus in TIER_THRESHOLDS:
        if name == current_tier:
            mult_bonus = bonus
            break

    return TierResponse(
        current_tier=current_tier,
        reputation_score=score,
        next_tier=next_tier,
        points_to_next=points_to_next,
        multiplier_bonus=mult_bonus,
        perks=TIER_PERKS.get(current_tier, []),
    )


# ═══════════════════════════════════════════════════════════════════════
# 7. Country Stats
# ═══════════════════════════════════════════════════════════════════════

@router.get("/country/{country_code}/stats", response_model=CountryEngagementResponse)
@limiter.limit("10/minute")
async def get_country_stats(
    request: Request,
    country_code: str = Path(..., min_length=2, max_length=2),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Country engagement stats. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v3/engagement/country/stats", cost_multiplier=1.0)
    cc = country_code.upper()

    total = db.query(func.count(DataWallet.id)).filter(
        DataWallet.country_code == cc
    ).scalar() or 0

    # Active in last 30 days
    cutoff = date.today() - timedelta(days=30)
    active_30d = db.query(func.count(DataWallet.id)).filter(
        DataWallet.country_code == cc,
        DataWallet.last_report_date >= cutoff,
    ).scalar() or 0

    avg_rep = db.query(func.avg(DataWallet.reputation_score)).filter(
        DataWallet.country_code == cc
    ).scalar() or 0

    avg_streak = db.query(func.avg(DataWallet.current_streak)).filter(
        DataWallet.country_code == cc
    ).scalar() or 0

    # Tier distribution
    tier_rows = (
        db.query(DataWallet.tier, func.count(DataWallet.id))
        .filter(DataWallet.country_code == cc)
        .group_by(DataWallet.tier)
        .all()
    )
    tier_dist = {r[0]: r[1] for r in tier_rows}

    # Top badges (most common in this country)
    top_badge_rows = (
        db.query(BadgeDefinition.badge_code, func.count(UserBadge.id))
        .join(UserBadge, UserBadge.badge_id == BadgeDefinition.id)
        .join(DataWallet, DataWallet.contributor_phone_hash == UserBadge.contributor_phone_hash)
        .filter(DataWallet.country_code == cc)
        .group_by(BadgeDefinition.badge_code)
        .order_by(desc(func.count(UserBadge.id)))
        .limit(5)
        .all()
    )
    top_badges = [r[0] for r in top_badge_rows]

    # Active challenges for this country
    active_ch = db.query(func.count(Challenge.id)).filter(
        Challenge.status == "ACTIVE",
        (Challenge.scope == "GLOBAL") | (Challenge.target_country_code == cc),
    ).scalar() or 0

    return CountryEngagementResponse(
        country_code=cc,
        total_reporters=total,
        active_reporters_30d=active_30d,
        avg_reputation=round(avg_rep, 2),
        avg_streak=round(avg_streak, 1),
        top_tier_distribution=tier_dist,
        top_badges=top_badges,
        active_challenges=active_ch,
    )


# ═══════════════════════════════════════════════════════════════════════
# 8. Admin
# ═══════════════════════════════════════════════════════════════════════

@router.post("/admin/challenges/create", response_model=ChallengeResponse)
@limiter.limit("5/minute")
async def create_challenge(
    request: Request,
    body: ChallengeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new community challenge. Admin only. Costs 10 credits."""
    deduct_credits(current_user, db, "/api/v3/engagement/admin/challenges", cost_multiplier=10.0)

    challenge = ChallengeEngine.create_challenge(
        db,
        challenge_code=body.challenge_code,
        title_en=body.title_en,
        title_fr=body.title_fr,
        description_en=body.description_en,
        description_fr=body.description_fr,
        scope=body.scope,
        target_country_code=body.target_country_code,
        target_region=body.target_region,
        goal_metric=body.goal_metric,
        goal_target=body.goal_target,
        start_date=body.start_date,
        end_date=body.end_date,
        reward_multiplier=body.reward_multiplier,
        bonus_cfa=body.bonus_cfa,
    )
    db.commit()

    return ChallengeResponse(
        id=challenge.id,
        challenge_code=challenge.challenge_code,
        title_en=challenge.title_en,
        title_fr=challenge.title_fr,
        description_en=challenge.description_en,
        description_fr=challenge.description_fr,
        scope=challenge.scope,
        target_country_code=challenge.target_country_code,
        target_region=challenge.target_region,
        goal_metric=challenge.goal_metric,
        goal_target=challenge.goal_target,
        current_progress=0,
        progress_pct=0,
        start_date=challenge.start_date,
        end_date=challenge.end_date,
        status=challenge.status,
        reward_multiplier=challenge.reward_multiplier,
        bonus_cfa=challenge.bonus_cfa,
        participant_count=0,
    )


@router.post("/admin/rewards/create", response_model=RewardCatalogResponse)
@limiter.limit("5/minute")
async def create_reward(
    request: Request,
    body: RewardCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Add a reward to the catalog. Admin only. Costs 5 credits."""
    deduct_credits(current_user, db, "/api/v3/engagement/admin/rewards", cost_multiplier=5.0)

    reward = RewardCatalog(
        reward_code=body.reward_code,
        name_en=body.name_en,
        name_fr=body.name_fr,
        description_en=body.description_en,
        description_fr=body.description_fr,
        reward_type=body.reward_type,
        cost_cfa=body.cost_cfa,
        min_tier=body.min_tier,
        partner_name=body.partner_name,
    )
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return reward


@router.get("/admin/engagement-summary", response_model=EngagementSummaryResponse)
@limiter.limit("5/minute")
async def engagement_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Platform-wide engagement metrics. Admin only. Costs 5 credits."""
    deduct_credits(current_user, db, "/api/v3/engagement/admin/summary", cost_multiplier=5.0)

    total_wallets = db.query(func.count(DataWallet.id)).scalar() or 0
    total_reports = db.query(func.coalesce(func.sum(DataWallet.total_reports), 0)).scalar()
    total_earned = db.query(func.coalesce(func.sum(DataWallet.total_earned_cfa), 0)).scalar()
    avg_rep = db.query(func.avg(DataWallet.reputation_score)).scalar() or 0
    avg_streak = db.query(func.avg(DataWallet.current_streak)).scalar() or 0

    tier_rows = (
        db.query(DataWallet.tier, func.count(DataWallet.id))
        .group_by(DataWallet.tier)
        .all()
    )
    tier_dist = {r[0]: r[1] for r in tier_rows}

    badges_total = db.query(func.count(UserBadge.id)).scalar() or 0
    active_ch = db.query(func.count(Challenge.id)).filter(
        Challenge.status == "ACTIVE"
    ).scalar() or 0

    countries = db.query(func.count(func.distinct(DataWallet.country_code))).scalar() or 0

    return EngagementSummaryResponse(
        total_wallets=total_wallets,
        total_reports_all=total_reports,
        total_earned_cfa_all=total_earned,
        avg_reputation=round(avg_rep, 2),
        avg_streak=round(avg_streak, 1),
        tier_distribution=tier_dist,
        badges_awarded_total=badges_total,
        active_challenges=active_ch,
        countries_with_data=countries,
    )


@router.post("/admin/badges/seed")
@limiter.limit("2/minute")
async def seed_badges(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Seed badge definitions (idempotent). Admin only. FREE."""
    created = BadgeEngine.seed_badges(db)
    db.commit()
    return {"status": "ok", "badges_created": created}
