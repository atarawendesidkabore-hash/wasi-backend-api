"""
Personalized Data Intelligence Engine — Spotify Wrapped for data producers.

Pure analytics layer over existing tables. No new DB models.
Aggregates signals from DataWallet, DataToken, ImpactRecord, RoyaltyDistribution,
UserBadge, ChallengeParticipation to generate personalized insights and nudges.
"""

import logging
from datetime import date, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.engagement_models import (
    DataWallet, UserBadge, BadgeDefinition,
    Challenge, ChallengeParticipation, ImpactRecord,
)
from src.database.tokenization_models import DataToken
from src.database.royalty_models import RoyaltyDistribution, RoyaltyPool
from src.database.models import Country
from src.database.connection import engine as _db_engine


def _year_month(col):
    """Database-agnostic YYYY-MM extraction from a date column."""
    if str(_db_engine.url).startswith('sqlite'):
        return func.strftime('%Y-%m', col)
    else:
        return func.to_char(col, 'YYYY-MM')


def _year(col):
    """Database-agnostic YYYY extraction from a datetime column."""
    if str(_db_engine.url).startswith('sqlite'):
        return func.strftime('%Y', col)
    else:
        return func.to_char(col, 'YYYY')
from src.engines.engagement_engine import (
    TIER_THRESHOLDS, TIER_ORDER, STREAK_MULTIPLIERS,
)

logger = logging.getLogger(__name__)

# ── Token Type → Expertise Labels ────────────────────────────────────

EXPERTISE_LABELS = {
    "MARKET_PRICE": ("Market Price Expert", "Expert Prix du Marché"),
    "CROP_YIELD": ("Crop Yield Scout", "Éclaireur Rendement"),
    "ROAD_CONDITION": ("Road Condition Scout", "Veilleur des Routes"),
    "WEATHER": ("Weather Reporter", "Rapporteur Météo"),
    "WATER_ACCESS": ("Water Access Monitor", "Moniteur Accès Eau"),
    "HEALTH_FACILITY": ("Health Sentinel", "Sentinelle Santé"),
    "SCHOOL_STATUS": ("Education Monitor", "Moniteur Éducation"),
    "ACTIVITY_REPORT": ("Activity Reporter", "Rapporteur d'Activité"),
    "SALES_DATA": ("Sales Data Analyst", "Analyste Ventes"),
    "INVENTORY": ("Inventory Tracker", "Suiveur d'Inventaire"),
    "SUPPLIER": ("Supply Chain Scout", "Éclaireur Chaîne"),
    "TRADE_VOLUME": ("Trade Volume Expert", "Expert Volume Commerce"),
    "EMPLOYEE_COUNT": ("Employment Monitor", "Moniteur Emploi"),
    "MILESTONE_VERIFY": ("Project Verifier", "Vérificateur Projet"),
    "WORKER_CHECKIN": ("Worker Attendance", "Présence Travailleur"),
}

# Advice per reputation factor
_FACTOR_ADVICE = {
    "volume": (
        "Submit more reports to boost your volume score",
        "Soumettez plus de rapports pour augmenter votre score volume",
    ),
    "consistency": (
        "Report daily to build your streak and consistency score",
        "Rapportez chaque jour pour construire votre série",
    ),
    "quality": (
        "Get your reports cross-validated by other reporters in your area",
        "Faites valider vos rapports par d'autres rapporteurs",
    ),
    "badges": (
        "Complete badge challenges to earn more achievements",
        "Complétez les défis de badges pour gagner plus de récompenses",
    ),
    "community": (
        "Join active challenges to boost your community score",
        "Rejoignez des défis actifs pour augmenter votre score communauté",
    ),
}


class ContributorIntelligenceEngine:
    """Personalized analytics over existing behavioral data."""

    # ══════════════════════════════════════════════════════════════════
    # 1. Profile Card
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_profile_card(db: Session, phone_hash: str) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        if not wallet:
            return _empty_profile(phone_hash)

        # Compute reputation sub-components
        badge_count = db.query(func.count(UserBadge.id)).filter(
            UserBadge.contributor_phone_hash == phone_hash
        ).scalar() or 0

        challenge_count = db.query(func.count(ChallengeParticipation.id)).filter(
            ChallengeParticipation.contributor_phone_hash == phone_hash
        ).scalar() or 0

        total = max(wallet.total_reports or 0, 1)
        xv_pct = (wallet.total_cross_validated or 0) / total

        components = {
            "volume": {"current": round(min(30, (wallet.total_reports or 0) * 0.3), 2), "max": 30, "label": "Rapports"},
            "consistency": {"current": round(min(25, (wallet.current_streak or 0) * 0.83), 2), "max": 25, "label": "Série"},
            "quality": {"current": round(min(20, xv_pct * 20), 2), "max": 20, "label": "Qualité"},
            "badges": {"current": round(min(15, badge_count * 1.5), 2), "max": 15, "label": "Badges"},
            "community": {"current": round(min(10, challenge_count * 2.5), 2), "max": 10, "label": "Communauté"},
        }

        # Weakest factor (largest gap)
        weakest_name = max(components, key=lambda k: components[k]["max"] - components[k]["current"])
        wc = components[weakest_name]
        advice_en, advice_fr = _FACTOR_ADVICE.get(weakest_name, ("", ""))

        # Tier progress
        current_tier = wallet.tier or "BRONZE"
        tier_idx = TIER_ORDER.index(current_tier) if current_tier in TIER_ORDER else 0
        next_tier = TIER_ORDER[tier_idx + 1] if tier_idx + 1 < len(TIER_ORDER) else None
        points_to_next = 0.0
        if next_tier:
            for threshold, tname, _ in TIER_THRESHOLDS:
                if tname == next_tier:
                    points_to_next = max(0, threshold - (wallet.reputation_score or 0))
                    break

        # Estimate days to advance from recent daily gain rate
        estimated_days = None
        if points_to_next > 0:
            # Check reputation change over last 30 days via ImpactRecord
            thirty_ago = date.today() - timedelta(days=30)
            recent_impacts = db.query(ImpactRecord).filter(
                ImpactRecord.contributor_phone_hash == phone_hash,
                ImpactRecord.period_month >= thirty_ago.strftime("%Y-%m"),
            ).all()
            if recent_impacts and wallet.reputation_score and wallet.reputation_score > 0:
                # Approximate: reports per day → reputation gain
                total_recent_reports = sum(r.reports_submitted or 0 for r in recent_impacts)
                daily_reports = total_recent_reports / 30.0
                # Each report adds ~0.3 to reputation (from volume component)
                daily_gain = daily_reports * 0.3
                if daily_gain > 0:
                    estimated_days = max(1, int(points_to_next / daily_gain))

        return {
            "contributor_phone_hash": phone_hash,
            "country_code": wallet.country_code,
            "reputation_score": wallet.reputation_score or 0,
            "tier": current_tier,
            "tier_progress": {
                "current_tier": current_tier,
                "next_tier": next_tier,
                "points_to_next": round(points_to_next, 2),
                "estimated_days_to_advance": estimated_days,
            },
            "reputation_breakdown": components,
            "weakest_factor": {
                "factor": weakest_name,
                "current": wc["current"],
                "max": wc["max"],
                "gap": round(wc["max"] - wc["current"], 2),
                "advice_en": advice_en,
                "advice_fr": advice_fr,
            },
        }

    # ══════════════════════════════════════════════════════════════════
    # 2. Data Specialization
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_data_specialization(db: Session, phone_hash: str) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        if not wallet:
            return _empty_specialization(phone_hash)

        # Pillar distribution
        pillar_rows = db.query(
            DataToken.pillar,
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
        ).group_by(DataToken.pillar).all()

        total_tokens = sum(r[1] for r in pillar_rows) if pillar_rows else 0
        pillar_dist = {}
        primary_pillar = "CITIZEN_DATA"
        max_pillar_count = 0
        for pillar, cnt in pillar_rows:
            pct = round((cnt / total_tokens * 100) if total_tokens > 0 else 0, 1)
            pillar_dist[pillar] = {"count": cnt, "pct": pct}
            if cnt > max_pillar_count:
                max_pillar_count = cnt
                primary_pillar = pillar

        # Ensure all pillars present
        for p in ["CITIZEN_DATA", "BUSINESS_DATA", "FASO_MEABO"]:
            if p not in pillar_dist:
                pillar_dist[p] = {"count": 0, "pct": 0.0}

        # Token type distribution
        type_rows = db.query(
            DataToken.token_type,
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
        ).group_by(DataToken.token_type).order_by(func.count(DataToken.id).desc()).all()

        type_dist = []
        top_type = "ACTIVITY_REPORT"
        for tt, cnt in type_rows:
            pct = round((cnt / total_tokens * 100) if total_tokens > 0 else 0, 1)
            type_dist.append({"token_type": tt, "count": cnt, "pct": pct})
        if type_rows:
            top_type = type_rows[0][0]

        label_en, label_fr = EXPERTISE_LABELS.get(top_type, ("Data Reporter", "Rapporteur de Données"))

        # Country comparison: avg distinct token types per contributor
        country_code = wallet.country_code
        country_obj = db.query(Country).filter(Country.code == country_code).first()

        avg_types = 1.0
        your_types = len(type_rows)
        if country_obj:
            # Count distinct types per contributor in same country
            sub = db.query(
                DataToken.contributor_phone_hash,
                func.count(func.distinct(DataToken.token_type)).label("n_types"),
            ).filter(
                DataToken.country_id == country_obj.id,
            ).group_by(DataToken.contributor_phone_hash).subquery()

            avg_result = db.query(func.avg(sub.c.n_types)).scalar()
            avg_types = round(float(avg_result or 1), 1)

        # Specialization score (Herfindahl): sum of squared shares
        specialization_score = 0.0
        if total_tokens > 0:
            for _, cnt in type_rows:
                share = cnt / total_tokens
                specialization_score += share * share
            specialization_score = round(specialization_score * len(type_rows), 2)

        return {
            "contributor_phone_hash": phone_hash,
            "total_tokens": total_tokens,
            "primary_pillar": primary_pillar,
            "pillar_distribution": pillar_dist,
            "token_type_distribution": type_dist,
            "expertise_label_en": label_en,
            "expertise_label_fr": label_fr,
            "country_comparison": {
                "avg_token_types": avg_types,
                "your_token_types": your_types,
                "specialization_score": specialization_score,
            },
        }

    # ══════════════════════════════════════════════════════════════════
    # 3. Quality Trends
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_quality_trends(db: Session, phone_hash: str, months: int = 6) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        country_code = wallet.country_code if wallet else "NG"
        cutoff = date.today() - timedelta(days=months * 31)

        # Monthly trends from DataToken
        monthly_rows = db.query(
            _year_month(DataToken.period_date).label("month"),
            func.avg(DataToken.confidence).label("avg_conf"),
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= cutoff,
        ).group_by("month").order_by(_year_month(DataToken.period_date)).all()

        trends = []
        for month_str, avg_conf, cnt in monthly_rows:
            # Cross-validation rate: tokens with status='validated' or confidence >= 0.70
            validated = db.query(func.count(DataToken.id)).filter(
                DataToken.contributor_phone_hash == phone_hash,
                _year_month(DataToken.period_date) == month_str,
                DataToken.confidence >= 0.70,
            ).scalar() or 0
            xv_rate = round((validated / cnt * 100) if cnt > 0 else 0, 1)

            trends.append({
                "month": month_str,
                "avg_confidence": round(float(avg_conf or 0), 3),
                "cross_validation_rate": xv_rate,
                "reports_count": cnt,
            })

        # Direction
        direction = "stable"
        change_pct = 0.0
        if len(trends) >= 2:
            first = trends[0]["avg_confidence"]
            last = trends[-1]["avg_confidence"]
            if first > 0:
                change_pct = round(((last - first) / first) * 100, 1)
                if change_pct > 5:
                    direction = "improving"
                elif change_pct < -5:
                    direction = "declining"

        # Country percentile
        country_obj = db.query(Country).filter(Country.code == country_code).first()
        country_avg = 0.0
        percentile = 50.0

        if country_obj:
            # Get avg confidence per contributor in same country
            contributor_avgs = db.query(
                DataToken.contributor_phone_hash,
                func.avg(DataToken.confidence).label("avg_c"),
            ).filter(
                DataToken.country_id == country_obj.id,
                DataToken.period_date >= cutoff,
            ).group_by(DataToken.contributor_phone_hash).all()

            if contributor_avgs:
                all_avgs = [float(r[1] or 0) for r in contributor_avgs]
                country_avg = round(sum(all_avgs) / len(all_avgs), 3)

                # Find this user's rank
                user_avg = 0.0
                for r in contributor_avgs:
                    if r[0] == phone_hash:
                        user_avg = float(r[1] or 0)
                        break

                below_count = sum(1 for a in all_avgs if a < user_avg)
                percentile = round((below_count / len(all_avgs)) * 100, 1)

        return {
            "contributor_phone_hash": phone_hash,
            "monthly_trends": trends,
            "confidence_direction": direction,
            "confidence_change_pct": change_pct,
            "country_percentile": percentile,
            "country_avg_confidence": country_avg,
        }

    # ══════════════════════════════════════════════════════════════════
    # 4. Earning Projection
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_earning_projection(db: Session, phone_hash: str) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        lifetime = float(wallet.total_earned_cfa or 0) if wallet else 0
        current_tier = wallet.tier if wallet else "BRONZE"
        current_mult = float(wallet.current_multiplier or 1.0) if wallet else 1.0

        # Last 30 days token earnings
        thirty_ago = date.today() - timedelta(days=30)
        token_earnings = db.query(
            func.coalesce(func.sum(DataToken.token_value_cfa), 0)
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.status.in_(["validated", "paid"]),
            DataToken.period_date >= thirty_ago,
        ).scalar() or 0
        token_earnings = float(token_earnings)

        # Last 30 days royalty earnings
        royalty_earnings = db.query(
            func.coalesce(func.sum(RoyaltyDistribution.share_amount_cfa), 0)
        ).join(RoyaltyPool, RoyaltyDistribution.pool_id == RoyaltyPool.id).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyDistribution.status == "credited",
            RoyaltyPool.period_date >= thirty_ago,
        ).scalar() or 0
        royalty_earnings = float(royalty_earnings)

        monthly_rate = token_earnings + royalty_earnings

        # What-if scenarios
        scenarios = []

        # 1. Next tier
        tier_idx = TIER_ORDER.index(current_tier) if current_tier in TIER_ORDER else 0
        if tier_idx + 1 < len(TIER_ORDER):
            next_tier = TIER_ORDER[tier_idx + 1]
            next_bonus = 0.0
            for _, tname, bonus in TIER_THRESHOLDS:
                if tname == next_tier:
                    next_bonus = bonus
                    break
            current_bonus = 0.0
            for _, tname, bonus in TIER_THRESHOLDS:
                if tname == current_tier:
                    current_bonus = bonus
                    break
            if current_mult > 0:
                new_mult = current_mult - current_bonus + next_bonus
                projected = monthly_rate * (new_mult / current_mult)
                uplift = round(((projected - monthly_rate) / max(monthly_rate, 1)) * 100, 1)
                scenarios.append({
                    "scenario": "next_tier",
                    "description_en": f"If you reach {next_tier} tier",
                    "description_fr": f"Si vous atteignez le niveau {next_tier}",
                    "projected_monthly_cfa": round(projected, 2),
                    "uplift_pct": uplift,
                })

        # 2. Max streak (30-day, 2.0x)
        current_streak = wallet.current_streak if wallet else 0
        if current_streak < 30:
            # Current streak multiplier
            current_streak_mult = 1.0
            for threshold, mult in STREAK_MULTIPLIERS:
                if current_streak >= threshold:
                    current_streak_mult = mult
                    break
            if current_streak_mult < 2.0 and current_mult > 0:
                delta = 2.0 - current_streak_mult
                new_mult = current_mult + delta
                projected = monthly_rate * (new_mult / current_mult)
                uplift = round(((projected - monthly_rate) / max(monthly_rate, 1)) * 100, 1)
                scenarios.append({
                    "scenario": "max_streak",
                    "description_en": "If you reach 30-day streak (2.0x multiplier)",
                    "description_fr": "Si vous atteignez 30 jours de série (2.0x)",
                    "projected_monthly_cfa": round(projected, 2),
                    "uplift_pct": uplift,
                })

        # 3. Double reports
        if monthly_rate > 0:
            scenarios.append({
                "scenario": "double_reports",
                "description_en": "If you double your report frequency",
                "description_fr": "Si vous doublez votre fréquence de rapports",
                "projected_monthly_cfa": round(monthly_rate * 2, 2),
                "uplift_pct": 100.0,
            })

        return {
            "contributor_phone_hash": phone_hash,
            "lifetime_earnings_cfa": round(lifetime, 2),
            "current_monthly_rate_cfa": round(monthly_rate, 2),
            "projected_next_month_cfa": round(monthly_rate, 2),
            "royalty_earnings_cfa": round(royalty_earnings, 2),
            "token_earnings_cfa": round(token_earnings, 2),
            "what_if_scenarios": scenarios,
        }

    # ══════════════════════════════════════════════════════════════════
    # 5. Coverage Opportunities
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_coverage_opportunities(db: Session, phone_hash: str) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        country_code = wallet.country_code if wallet else "NG"
        country = db.query(Country).filter(Country.code == country_code).first()

        underserved = []
        geographic_gaps = []
        matching_challenges = []

        if country:
            thirty_ago = date.today() - timedelta(days=30)

            # Count reporters per token type in this country (last 30d)
            type_reporters = db.query(
                DataToken.token_type,
                func.count(func.distinct(DataToken.contributor_phone_hash)).label("reporters"),
            ).filter(
                DataToken.country_id == country.id,
                DataToken.period_date >= thirty_ago,
            ).group_by(DataToken.token_type).all()

            type_map = {r[0]: r[1] for r in type_reporters}
            total_types = len(type_map)
            avg_reporters = sum(type_map.values()) / max(total_types, 1)

            # Find underserved types (sorted by fewest reporters)
            all_types = list(EXPERTISE_LABELS.keys())
            for tt in sorted(all_types, key=lambda t: type_map.get(t, 0)):
                reporters = type_map.get(tt, 0)
                if reporters < avg_reporters:
                    uplift = round(((avg_reporters / max(reporters, 1)) - 1) * 100, 1)
                    underserved.append({
                        "token_type": tt,
                        "reporters_count": reporters,
                        "country_avg_reporters": round(avg_reporters, 1),
                        "potential_royalty_uplift_pct": uplift,
                    })
                if len(underserved) >= 5:
                    break

            # Geographic gaps: count reporters per location
            location_reporters = db.query(
                DataToken.location_name,
                func.count(func.distinct(DataToken.contributor_phone_hash)).label("reporters"),
            ).filter(
                DataToken.country_id == country.id,
                DataToken.period_date >= thirty_ago,
                DataToken.location_name.isnot(None),
            ).group_by(DataToken.location_name).order_by(
                func.count(func.distinct(DataToken.contributor_phone_hash))
            ).limit(5).all()

            for loc, reps in location_reporters:
                level = "HIGH" if reps <= 1 else ("MEDIUM" if reps <= 3 else "LOW")
                geographic_gaps.append({
                    "region": loc or "Unknown",
                    "reporters_count": reps,
                    "opportunity_level": level,
                })

        # Matching challenges: active challenges user hasn't joined
        joined_ids = [r[0] for r in db.query(
            ChallengeParticipation.challenge_id
        ).filter(
            ChallengeParticipation.contributor_phone_hash == phone_hash
        ).all()]

        active_challenges = db.query(Challenge).filter(
            Challenge.status == "ACTIVE",
        ).all()

        for ch in active_challenges:
            if ch.id in joined_ids:
                continue
            # Check country match
            if ch.target_country_code and ch.target_country_code != country_code:
                continue
            progress_pct = round((ch.current_progress / max(ch.goal_target, 1)) * 100, 1)
            matching_challenges.append({
                "challenge_id": ch.id,
                "title_fr": ch.title_fr,
                "goal_metric": ch.goal_metric,
                "progress_pct": progress_pct,
                "match_reason_fr": f"Défi actif dans votre pays ({country_code})",
            })

        return {
            "contributor_phone_hash": phone_hash,
            "country_code": country_code,
            "underserved_token_types": underserved,
            "geographic_gaps": geographic_gaps,
            "matching_challenges": matching_challenges,
        }

    # ══════════════════════════════════════════════════════════════════
    # 6. Nudges
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_nudges(db: Session, phone_hash: str, locale: str = "fr") -> list[dict]:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        nudges = []
        today = date.today()

        if not wallet:
            nudges.append({
                "type": "ONBOARDING",
                "priority": 1,
                "message_en": "Start reporting data to earn CFA and build your reputation!",
                "message_fr": "Commencez à rapporter des données pour gagner des CFA!",
                "action_hint": "submit_report",
            })
            return nudges

        # 1. STREAK_RISK (priority 1)
        streak = wallet.current_streak or 0
        last_report = wallet.last_report_date
        if streak >= 7 and last_report:
            days_since = (today - last_report).days if isinstance(last_report, date) else 0
            if days_since == 1:
                nudges.append({
                    "type": "STREAK_RISK",
                    "priority": 1,
                    "message_en": f"Submit a report today to keep your {streak}-day streak!",
                    "message_fr": f"Soumettez un rapport pour garder votre série de {streak} jours!",
                    "action_hint": "submit_report",
                })

        # Streak milestone approaching
        if 28 <= streak < 30:
            nudges.append({
                "type": "STREAK_RISK",
                "priority": 1,
                "message_en": f"{30 - streak} more days to reach 2.0x multiplier!",
                "message_fr": f"Encore {30 - streak} jours pour atteindre le multiplicateur 2.0x!",
                "action_hint": "submit_report",
            })

        # 2. TIER_PROGRESS (priority 2)
        current_tier = wallet.tier or "BRONZE"
        tier_idx = TIER_ORDER.index(current_tier) if current_tier in TIER_ORDER else 0
        if tier_idx + 1 < len(TIER_ORDER):
            next_tier = TIER_ORDER[tier_idx + 1]
            for threshold, tname, _ in TIER_THRESHOLDS:
                if tname == next_tier:
                    points_to_next = max(0, threshold - (wallet.reputation_score or 0))
                    if points_to_next <= 10:
                        nudges.append({
                            "type": "TIER_PROGRESS",
                            "priority": 2,
                            "message_en": f"You're {points_to_next:.0f} points from {next_tier} tier!",
                            "message_fr": f"Vous êtes à {points_to_next:.0f} pts du niveau {next_tier}!",
                            "action_hint": "boost_reputation",
                        })
                    break

        # 3. COVERAGE_GAP (priority 3)
        wallet_country = wallet.country_code
        country_obj = db.query(Country).filter(Country.code == wallet_country).first()
        if country_obj:
            thirty_ago = today - timedelta(days=30)
            type_counts = db.query(
                DataToken.token_type,
                func.count(func.distinct(DataToken.contributor_phone_hash)).label("reporters"),
            ).filter(
                DataToken.country_id == country_obj.id,
                DataToken.period_date >= thirty_ago,
            ).group_by(DataToken.token_type).all()

            for tt, reporters in sorted(type_counts, key=lambda x: x[1]):
                if reporters <= 3:
                    label_en, label_fr = EXPERTISE_LABELS.get(tt, (tt, tt))
                    nudges.append({
                        "type": "COVERAGE_GAP",
                        "priority": 3,
                        "message_en": f"{tt} has only {reporters} reporters — higher royalties!",
                        "message_fr": f"{tt} n'a que {reporters} rapporteurs — royalties plus élevées!",
                        "action_hint": "submit_report",
                    })
                    break  # Only one coverage gap nudge

        # 4. QUALITY_TIP (priority 3)
        six_months_ago = today - timedelta(days=180)
        monthly_conf = db.query(
            _year_month(DataToken.period_date).label("month"),
            func.avg(DataToken.confidence).label("avg_conf"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= six_months_ago,
        ).group_by("month").order_by(_year_month(DataToken.period_date)).all()

        if len(monthly_conf) >= 2:
            first_conf = float(monthly_conf[0][1] or 0)
            last_conf = float(monthly_conf[-1][1] or 0)
            if first_conf > 0 and ((last_conf - first_conf) / first_conf) < -0.05:
                drop_pct = round(abs((last_conf - first_conf) / first_conf) * 100, 0)
                nudges.append({
                    "type": "QUALITY_TIP",
                    "priority": 3,
                    "message_en": f"Your confidence dropped {drop_pct:.0f}% — submit when more validators are online",
                    "message_fr": f"Votre confiance a baissé de {drop_pct:.0f}% — rapportez quand plus de validateurs sont en ligne",
                    "action_hint": "improve_quality",
                })

        # 5. CHALLENGE_MATCH (priority 4)
        joined_ids = {r[0] for r in db.query(
            ChallengeParticipation.challenge_id
        ).filter(
            ChallengeParticipation.contributor_phone_hash == phone_hash
        ).all()}

        unjoin_challenge = db.query(Challenge).filter(
            Challenge.status == "ACTIVE",
            ~Challenge.id.in_(joined_ids) if joined_ids else True,
        ).first()

        if unjoin_challenge:
            nudges.append({
                "type": "CHALLENGE_MATCH",
                "priority": 4,
                "message_en": f"Join challenge '{unjoin_challenge.title_en}' for bonus CFA!",
                "message_fr": f"Rejoignez le défi '{unjoin_challenge.title_fr}' pour des CFA bonus!",
                "action_hint": "join_challenge",
            })

        # 6. EARNING_BOOST (priority 4) — only if no other earning nudge
        if not any(n["type"] == "TIER_PROGRESS" for n in nudges):
            nudges.append({
                "type": "EARNING_BOOST",
                "priority": 4,
                "message_en": "Double your daily reports to double your monthly earnings!",
                "message_fr": "Doublez vos rapports quotidiens pour doubler vos revenus mensuels!",
                "action_hint": "submit_report",
            })

        # Sort by priority, return top 5
        nudges.sort(key=lambda n: n["priority"])
        return nudges[:5]

    # ══════════════════════════════════════════════════════════════════
    # 7. Wrapped Summary
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def get_wrapped_summary(db: Session, phone_hash: str, year: int = 2026) -> dict:
        wallet = db.query(DataWallet).filter(
            DataWallet.contributor_phone_hash == phone_hash
        ).first()

        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Total reports this year
        total_reports = db.query(func.count(DataToken.id)).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
        ).scalar() or 0

        # Total earned (token values this year)
        total_earned = db.query(
            func.coalesce(func.sum(DataToken.token_value_cfa), 0)
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.status.in_(["validated", "paid"]),
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
        ).scalar() or 0

        # Add royalty earnings
        royalty_total = db.query(
            func.coalesce(func.sum(RoyaltyDistribution.share_amount_cfa), 0)
        ).join(RoyaltyPool, RoyaltyDistribution.pool_id == RoyaltyPool.id).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyDistribution.status == "credited",
            RoyaltyPool.period_date >= year_start,
            RoyaltyPool.period_date <= year_end,
        ).scalar() or 0

        total_earned = float(total_earned) + float(royalty_total)

        # Top 3 token types
        top_types = db.query(
            DataToken.token_type,
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
        ).group_by(DataToken.token_type).order_by(func.count(DataToken.id).desc()).limit(3).all()

        # Top region
        top_region_row = db.query(
            DataToken.location_name,
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
            DataToken.location_name.isnot(None),
        ).group_by(DataToken.location_name).order_by(func.count(DataToken.id).desc()).first()

        top_region = top_region_row[0] if top_region_row else None

        # Peer percentile
        country_code = wallet.country_code if wallet else "NG"
        country_obj = db.query(Country).filter(Country.code == country_code).first()
        percentile = 50.0
        if country_obj:
            contributor_counts = db.query(
                DataToken.contributor_phone_hash,
                func.count(DataToken.id).label("cnt"),
            ).filter(
                DataToken.country_id == country_obj.id,
                DataToken.period_date >= year_start,
                DataToken.period_date <= year_end,
            ).group_by(DataToken.contributor_phone_hash).all()

            if contributor_counts:
                all_counts = [r[1] for r in contributor_counts]
                my_count = 0
                for r in contributor_counts:
                    if r[0] == phone_hash:
                        my_count = r[1]
                        break
                below = sum(1 for c in all_counts if c < my_count)
                percentile = round((below / len(all_counts)) * 100, 1)

        # Data citations (approximate from RoyaltyDistribution)
        citations = db.query(func.count(RoyaltyDistribution.id)).join(
            RoyaltyPool, RoyaltyDistribution.pool_id == RoyaltyPool.id
        ).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyPool.period_date >= year_start,
            RoyaltyPool.period_date <= year_end,
        ).scalar() or 0

        # Distinct regions
        regions_helped = db.query(
            func.count(func.distinct(DataToken.location_name))
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
            DataToken.location_name.isnot(None),
        ).scalar() or 0

        # Badges earned this year
        badges_this_year = db.query(UserBadge, BadgeDefinition).join(
            BadgeDefinition, UserBadge.badge_id == BadgeDefinition.id
        ).filter(
            UserBadge.contributor_phone_hash == phone_hash,
            UserBadge.earned_at.isnot(None),
            _year(UserBadge.earned_at) == str(year),
        ).all()

        badge_list = []
        for ub, bd in badges_this_year:
            badge_list.append({
                "badge_code": bd.badge_code,
                "name_fr": bd.name_fr,
                "earned_at": ub.earned_at.isoformat() if ub.earned_at else "",
            })

        # Months active
        months_active = db.query(
            func.count(func.distinct(_year_month(DataToken.period_date)))
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
        ).scalar() or 0

        # Best month
        best_month_row = db.query(
            _year_month(DataToken.period_date).label("month"),
            func.count(DataToken.id).label("cnt"),
        ).filter(
            DataToken.contributor_phone_hash == phone_hash,
            DataToken.period_date >= year_start,
            DataToken.period_date <= year_end,
        ).group_by("month").order_by(func.count(DataToken.id).desc()).first()

        best_month = None
        if best_month_row:
            best_month = {"month": best_month_row[0], "reports": best_month_row[1]}

        # Impact summary from ImpactRecord
        impact_records = db.query(ImpactRecord).filter(
            ImpactRecord.contributor_phone_hash == phone_hash,
            ImpactRecord.period_month >= f"{year}-01",
            ImpactRecord.period_month <= f"{year}-12",
        ).all()

        surveys_eq = sum(r.formal_surveys_equivalent or 0 for r in impact_records)
        value_usd = sum(r.estimated_value_usd or 0 for r in impact_records)

        return {
            "contributor_phone_hash": phone_hash,
            "year": year,
            "total_reports": total_reports,
            "total_earned_cfa": round(total_earned, 2),
            "streak_record": wallet.longest_streak if wallet else 0,
            "top_token_types": [{"token_type": r[0], "count": r[1]} for r in top_types],
            "top_region": top_region,
            "peer_percentile": percentile,
            "data_citations": citations,
            "regions_helped": regions_helped,
            "badges_earned_this_year": badge_list,
            "months_active": months_active,
            "best_month": best_month,
            "impact_summary": {
                "formal_surveys_equivalent": surveys_eq,
                "estimated_value_usd": round(value_usd, 2),
            },
        }


# ── Empty response helpers ───────────────────────────────────────────

def _empty_profile(phone_hash: str) -> dict:
    components = {
        "volume": {"current": 0, "max": 30, "label": "Rapports"},
        "consistency": {"current": 0, "max": 25, "label": "Série"},
        "quality": {"current": 0, "max": 20, "label": "Qualité"},
        "badges": {"current": 0, "max": 15, "label": "Badges"},
        "community": {"current": 0, "max": 10, "label": "Communauté"},
    }
    return {
        "contributor_phone_hash": phone_hash,
        "country_code": "XX",
        "reputation_score": 0,
        "tier": "BRONZE",
        "tier_progress": {
            "current_tier": "BRONZE",
            "next_tier": "SILVER",
            "points_to_next": 25.0,
            "estimated_days_to_advance": None,
        },
        "reputation_breakdown": components,
        "weakest_factor": {
            "factor": "volume",
            "current": 0,
            "max": 30,
            "gap": 30,
            "advice_en": _FACTOR_ADVICE["volume"][0],
            "advice_fr": _FACTOR_ADVICE["volume"][1],
        },
    }


def _empty_specialization(phone_hash: str) -> dict:
    return {
        "contributor_phone_hash": phone_hash,
        "total_tokens": 0,
        "primary_pillar": "CITIZEN_DATA",
        "pillar_distribution": {
            "CITIZEN_DATA": {"count": 0, "pct": 0.0},
            "BUSINESS_DATA": {"count": 0, "pct": 0.0},
            "FASO_MEABO": {"count": 0, "pct": 0.0},
        },
        "token_type_distribution": [],
        "expertise_label_en": "Data Reporter",
        "expertise_label_fr": "Rapporteur de Données",
        "country_comparison": {
            "avg_token_types": 0.0,
            "your_token_types": 0,
            "specialization_score": 0.0,
        },
    }
