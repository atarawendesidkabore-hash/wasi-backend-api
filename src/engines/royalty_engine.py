"""
Data Marketplace Royalty Engine — Revenue flows backwards.

When institutions spend API credits querying citizen-generated data,
a percentage flows into royalty pools distributed to contributors
weighted by data quality, volume, and engagement tier.
"""

import logging
from datetime import date, timedelta, timezone, datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.royalty_models import RoyaltyPool, RoyaltyDistribution, DataAttribution
from src.database.connection import engine as _db_engine


def _year_month(col):
    """Database-agnostic YYYY-MM extraction from a date column."""
    if str(_db_engine.url).startswith('sqlite'):
        return func.strftime('%Y-%m', col)
    else:
        # PostgreSQL / MySQL
        return func.to_char(col, 'YYYY-MM')
from src.database.tokenization_models import DataToken
from src.database.engagement_models import DataWallet
from src.database.models import Country

logger = logging.getLogger(__name__)

# ── Royalty Rate by Endpoint (prefix-matched) ────────────────────────

ROYALTY_RATES = {
    "/api/v2/bank/score-dossier": 0.20,
    "/api/v2/bank/loan-advisory": 0.20,
    "/api/v2/bank/credit-context": 0.15,
    "/api/composite/calculate": 0.15,
    "/api/composite/report": 0.15,
    "/api/v3/forecast/": 0.10,
    "/api/v4/forecast/": 0.10,
    "/api/v3/tokenization/": 0.05,
    "_default": 0.05,
}

# ── Tier multipliers for distribution weighting ──────────────────────

TIER_ROYALTY_MULTIPLIERS = {
    "BRONZE": 1.0,
    "SILVER": 1.5,
    "GOLD": 2.0,
    "PLATINUM": 3.0,
}

# 1 API credit = 100 CFA for royalty calculation
CREDIT_TO_CFA = 100.0

# 16 ECOWAS countries
ECOWAS_CODES = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
    "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]


def _get_royalty_rate(endpoint: str) -> float:
    """Prefix-match the endpoint against ROYALTY_RATES."""
    for prefix, rate in ROYALTY_RATES.items():
        if prefix != "_default" and endpoint.startswith(prefix):
            return rate
    return ROYALTY_RATES["_default"]


class RoyaltyEngine:
    """Handles royalty attribution, pool accumulation, and distribution."""

    @staticmethod
    def record_attribution(
        db: Session,
        consumer_user_id: int,
        endpoint: str,
        credits_spent: float,
        country_code: str | None = None,
    ) -> list[DataAttribution]:
        """
        Called after deduct_credits() — records what data was consumed
        and accumulates royalties into the daily pool(s).

        If country_code is None, distributes equally across all 16 ECOWAS pools.
        Returns list of DataAttribution records created.
        """
        if credits_spent <= 0:
            return []

        rate = _get_royalty_rate(endpoint)
        royalty_credits = credits_spent * rate
        today = date.today()
        window_start = today - timedelta(days=7)

        # Determine target countries
        target_codes = [country_code] if country_code else ECOWAS_CODES
        per_country_credits = credits_spent / len(target_codes)
        per_country_royalty = royalty_credits / len(target_codes)

        attributions = []
        for cc in target_codes:
            # Count tokens and contributors for this country in the data window
            country_obj = db.query(Country).filter(Country.code == cc).first()
            token_count = 0
            contributor_count = 0
            avg_conf = 0.0

            if country_obj:
                stats = db.query(
                    func.count(DataToken.id),
                    func.count(func.distinct(DataToken.contributor_phone_hash)),
                    func.coalesce(func.avg(DataToken.confidence), 0.0),
                ).filter(
                    DataToken.country_id == country_obj.id,
                    DataToken.period_date >= window_start,
                    DataToken.period_date <= today,
                    DataToken.status.in_(["validated", "paid"]),
                ).first()

                if stats:
                    token_count = stats[0] or 0
                    contributor_count = stats[1] or 0
                    avg_conf = float(stats[2] or 0)

            # Create attribution record
            attr = DataAttribution(
                endpoint=endpoint,
                consumer_user_id=consumer_user_id,
                credits_spent=per_country_credits,
                royalty_contribution=per_country_royalty,
                country_code=cc,
                period_date_start=window_start,
                period_date_end=today,
                contributor_count=contributor_count,
                token_count=token_count,
                avg_confidence=round(avg_conf, 2),
            )
            db.add(attr)

            # Upsert royalty pool for (country_code, today)
            pool = db.query(RoyaltyPool).filter(
                RoyaltyPool.country_code == cc,
                RoyaltyPool.period_date == today,
            ).first()

            if not pool:
                pool = RoyaltyPool(
                    country_code=cc,
                    period_date=today,
                    royalty_rate_pct=rate * 100,
                )
                db.add(pool)
                db.flush()

            pool.total_queries = (pool.total_queries or 0) + 1
            pool.total_credits_spent = (pool.total_credits_spent or 0) + per_country_credits
            pool.pool_amount_cfa = (pool.pool_amount_cfa or 0) + (per_country_royalty * CREDIT_TO_CFA)
            pool.contributor_count = contributor_count

            attributions.append(attr)

        return attributions

    @staticmethod
    def distribute_pool(db: Session, pool_id: int) -> dict:
        """
        Distribute a single pool's CFA to its contributors,
        weighted by report_count × avg_confidence × tier_multiplier.
        """
        pool = db.query(RoyaltyPool).filter(RoyaltyPool.id == pool_id).first()
        if not pool:
            return {"error": "Pool not found"}
        if pool.distributed:
            return {"error": "Pool already distributed", "pool_id": pool_id}
        if pool.pool_amount_cfa <= 0:
            pool.distributed = True
            pool.distributed_at = datetime.now(timezone.utc)
            return {"pool_id": pool_id, "distributed_to": 0, "total_cfa": 0, "avg_share_cfa": 0}

        # Find country for this pool
        country = db.query(Country).filter(Country.code == pool.country_code).first()
        if not country:
            return {"error": f"Country {pool.country_code} not found"}

        window_start = pool.period_date - timedelta(days=7)
        window_end = pool.period_date

        # Get tokens for this country in the window
        tokens = db.query(
            DataToken.contributor_phone_hash,
            func.count(DataToken.id).label("report_count"),
            func.avg(DataToken.confidence).label("avg_confidence"),
        ).filter(
            DataToken.country_id == country.id,
            DataToken.period_date >= window_start,
            DataToken.period_date <= window_end,
            DataToken.status.in_(["validated", "paid"]),
        ).group_by(DataToken.contributor_phone_hash).all()

        if not tokens:
            pool.distributed = True
            pool.distributed_at = datetime.now(timezone.utc)
            pool.contributor_count = 0
            return {"pool_id": pool_id, "distributed_to": 0, "total_cfa": 0, "avg_share_cfa": 0}

        # Calculate quality weights
        contributors = []
        for row in tokens:
            phone_hash = row[0]
            report_count = row[1]
            avg_conf = float(row[2] or 0)

            # Look up tier from DataWallet
            wallet = db.query(DataWallet).filter(
                DataWallet.contributor_phone_hash == phone_hash
            ).first()
            tier = wallet.tier if wallet else "BRONZE"
            tier_mult = TIER_ROYALTY_MULTIPLIERS.get(tier, 1.0)

            weight = report_count * avg_conf * tier_mult
            contributors.append({
                "phone_hash": phone_hash,
                "report_count": report_count,
                "avg_confidence": round(avg_conf, 2),
                "tier_multiplier": tier_mult,
                "quality_weight": round(weight, 4),
            })

        total_weight = sum(c["quality_weight"] for c in contributors)
        if total_weight <= 0:
            pool.distributed = True
            pool.distributed_at = datetime.now(timezone.utc)
            return {"pool_id": pool_id, "distributed_to": 0, "total_cfa": 0, "avg_share_cfa": 0}

        # Create distribution records and credit wallets
        total_distributed = 0.0
        for c in contributors:
            share_pct = (c["quality_weight"] / total_weight) * 100
            share_cfa = pool.pool_amount_cfa * (c["quality_weight"] / total_weight)

            dist = RoyaltyDistribution(
                pool_id=pool.id,
                contributor_phone_hash=c["phone_hash"],
                country_code=pool.country_code,
                report_count=c["report_count"],
                avg_confidence=c["avg_confidence"],
                tier_multiplier=c["tier_multiplier"],
                quality_weight=c["quality_weight"],
                share_pct=round(share_pct, 4),
                share_amount_cfa=round(share_cfa, 2),
                status="credited",
                credited_at=datetime.now(timezone.utc),
            )
            db.add(dist)

            # Credit to DataWallet
            wallet = db.query(DataWallet).filter(
                DataWallet.contributor_phone_hash == c["phone_hash"]
            ).first()
            if wallet:
                wallet.total_earned_cfa = (wallet.total_earned_cfa or 0) + round(share_cfa, 2)

            total_distributed += share_cfa

        pool.distributed = True
        pool.distributed_at = datetime.now(timezone.utc)
        pool.contributor_count = len(contributors)

        return {
            "pool_id": pool_id,
            "country_code": pool.country_code,
            "period_date": str(pool.period_date),
            "distributed_to": len(contributors),
            "total_cfa": round(total_distributed, 2),
            "avg_share_cfa": round(total_distributed / len(contributors), 2),
        }

    @staticmethod
    def distribute_all_pending(db: Session) -> dict:
        """Process all undistributed pools where period_date < today."""
        today = date.today()
        pending = db.query(RoyaltyPool).filter(
            RoyaltyPool.distributed == False,
            RoyaltyPool.period_date < today,
        ).all()

        pools_processed = 0
        total_cfa = 0.0
        total_contributors = 0

        for pool in pending:
            result = RoyaltyEngine.distribute_pool(db, pool.id)
            if "error" not in result:
                pools_processed += 1
                total_cfa += result.get("total_cfa", 0)
                total_contributors += result.get("distributed_to", 0)

        return {
            "pools_processed": pools_processed,
            "total_distributed_cfa": round(total_cfa, 2),
            "total_contributors": total_contributors,
        }

    @staticmethod
    def get_contributor_royalties(db: Session, phone_hash: str, days: int = 90) -> list[dict]:
        """Query royalty distributions for a contributor."""
        cutoff = date.today() - timedelta(days=days)

        dists = db.query(RoyaltyDistribution).join(
            RoyaltyPool, RoyaltyDistribution.pool_id == RoyaltyPool.id
        ).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyPool.period_date >= cutoff,
        ).order_by(RoyaltyPool.period_date.desc()).all()

        results = []
        for d in dists:
            pool = db.query(RoyaltyPool).filter(RoyaltyPool.id == d.pool_id).first()
            results.append({
                "pool_id": d.pool_id,
                "period_date": pool.period_date if pool else None,
                "country_code": d.country_code,
                "report_count": d.report_count,
                "avg_confidence": d.avg_confidence,
                "tier_multiplier": d.tier_multiplier,
                "quality_weight": d.quality_weight,
                "share_pct": d.share_pct,
                "share_amount_cfa": d.share_amount_cfa,
                "status": d.status,
                "credited_at": d.credited_at,
            })

        return results

    @staticmethod
    def get_contributor_summary(db: Session, phone_hash: str) -> dict:
        """Aggregate royalty stats + monthly breakdown for last 6 months."""
        # Total stats
        totals = db.query(
            func.coalesce(func.sum(RoyaltyDistribution.share_amount_cfa), 0),
            func.coalesce(func.avg(RoyaltyDistribution.share_pct), 0),
            func.count(RoyaltyDistribution.id),
        ).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyDistribution.status == "credited",
        ).first()

        total_cfa = float(totals[0])
        avg_share = float(totals[1])
        total_entries = totals[2]

        # Count queries served (sum of pools this contributor appeared in)
        queries_served = db.query(
            func.coalesce(func.sum(RoyaltyPool.total_queries), 0)
        ).join(
            RoyaltyDistribution, RoyaltyDistribution.pool_id == RoyaltyPool.id
        ).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
        ).scalar() or 0

        # Monthly breakdown (last 6 months)
        six_months_ago = date.today() - timedelta(days=180)
        monthly_raw = db.query(
            _year_month(RoyaltyPool.period_date).label("month"),
            func.sum(RoyaltyDistribution.share_amount_cfa).label("total_cfa"),
            func.count(RoyaltyDistribution.id).label("pools_count"),
        ).join(
            RoyaltyPool, RoyaltyDistribution.pool_id == RoyaltyPool.id
        ).filter(
            RoyaltyDistribution.contributor_phone_hash == phone_hash,
            RoyaltyDistribution.status == "credited",
            RoyaltyPool.period_date >= six_months_ago,
        ).group_by("month").order_by(_year_month(RoyaltyPool.period_date).desc()).all()

        monthly = []
        for row in monthly_raw:
            # Get queries served for this month
            month_queries = db.query(
                func.coalesce(func.sum(RoyaltyPool.total_queries), 0)
            ).join(
                RoyaltyDistribution, RoyaltyDistribution.pool_id == RoyaltyPool.id
            ).filter(
                RoyaltyDistribution.contributor_phone_hash == phone_hash,
                _year_month(RoyaltyPool.period_date) == row[0],
            ).scalar() or 0

            monthly.append({
                "month": row[0],
                "total_cfa": round(float(row[1] or 0), 2),
                "pools_count": row[2],
                "queries_served": int(month_queries),
            })

        return {
            "contributor_phone_hash": phone_hash,
            "total_royalties_cfa": round(total_cfa, 2),
            "total_queries_served": int(queries_served),
            "avg_share_pct": round(avg_share, 4),
            "monthly_breakdown": monthly,
        }

    @staticmethod
    def get_pool_status(db: Session, country_code: str, period_date: date | None = None) -> dict | None:
        """Returns pool details for a country/date."""
        target_date = period_date or date.today()
        pool = db.query(RoyaltyPool).filter(
            RoyaltyPool.country_code == country_code,
            RoyaltyPool.period_date == target_date,
        ).first()

        if not pool:
            return None

        return {
            "id": pool.id,
            "country_code": pool.country_code,
            "period_date": pool.period_date,
            "total_queries": pool.total_queries,
            "total_credits_spent": pool.total_credits_spent,
            "royalty_rate_pct": pool.royalty_rate_pct,
            "pool_amount_cfa": pool.pool_amount_cfa,
            "contributor_count": pool.contributor_count,
            "distributed": pool.distributed,
            "distributed_at": pool.distributed_at,
        }

    @staticmethod
    def get_pool_contributors(db: Session, pool_id: int) -> list[dict]:
        """Top contributors for a pool with their shares."""
        dists = db.query(RoyaltyDistribution).filter(
            RoyaltyDistribution.pool_id == pool_id,
        ).order_by(RoyaltyDistribution.share_amount_cfa.desc()).all()

        result = []
        for rank, d in enumerate(dists, 1):
            result.append({
                "rank": rank,
                "contributor_phone_hash": d.contributor_phone_hash[:12] + "...",
                "report_count": d.report_count,
                "avg_confidence": d.avg_confidence,
                "tier_multiplier": d.tier_multiplier,
                "quality_weight": d.quality_weight,
                "share_pct": d.share_pct,
                "share_amount_cfa": d.share_amount_cfa,
            })

        return result

    @staticmethod
    def get_platform_stats(db: Session) -> dict:
        """Platform-wide royalty statistics."""
        total_pools = db.query(func.count(RoyaltyPool.id)).scalar() or 0
        distributed_pools = db.query(func.count(RoyaltyPool.id)).filter(
            RoyaltyPool.distributed == True
        ).scalar() or 0
        pending_pools = total_pools - distributed_pools

        total_royalties = db.query(
            func.coalesce(func.sum(RoyaltyDistribution.share_amount_cfa), 0)
        ).filter(RoyaltyDistribution.status == "credited").scalar() or 0

        total_credits = db.query(
            func.coalesce(func.sum(RoyaltyPool.total_credits_spent), 0)
        ).scalar() or 0

        total_attributions = db.query(func.count(DataAttribution.id)).scalar() or 0

        unique_contributors = db.query(
            func.count(func.distinct(RoyaltyDistribution.contributor_phone_hash))
        ).filter(RoyaltyDistribution.status == "credited").scalar() or 0

        avg_per_contributor = (
            float(total_royalties) / unique_contributors
            if unique_contributors > 0 else 0
        )

        return {
            "total_pools": total_pools,
            "total_distributed_pools": distributed_pools,
            "total_pending_pools": pending_pools,
            "total_royalties_distributed_cfa": round(float(total_royalties), 2),
            "total_credits_consumed": round(float(total_credits), 2),
            "total_attributions": total_attributions,
            "avg_royalty_per_contributor": round(avg_per_contributor, 2),
            "unique_contributors": unique_contributors,
        }
