"""
Data Marketplace Royalty Routes — Revenue flows backwards.

Endpoints (8 total, all under /api/v3/royalties/):
  GET  /my-royalties                      — My royalty history (FREE)
  GET  /my-royalties/summary              — Monthly breakdown + lifetime (FREE)
  GET  /pool/{country_code}               — Current royalty pool (1 cr)
  GET  /pool/{country_code}/contributors  — Top contributors + shares (2 cr)
  GET  /attribution/{query_log_id}        — Data lineage for a query (1 cr)
  GET  /stats                             — Platform-wide royalty stats (1 cr)
  POST /admin/distribute                  — Trigger manual distribution (5 cr)
  GET  /admin/pools                       — All pools + status (3 cr)
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.royalty_models import RoyaltyPool, RoyaltyDistribution, DataAttribution
from src.schemas.royalty import (
    RoyaltyHistoryResponse, RoyaltyEntryResponse,
    RoyaltySummaryResponse, MonthlyRoyalty,
    RoyaltyPoolResponse,
    PoolContributorsResponse, PoolContributorEntry,
    DataAttributionResponse,
    RoyaltyStatsResponse,
    AdminPoolListResponse, AdminPoolEntry,
)
from src.engines.royalty_engine import RoyaltyEngine
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits
from src.utils.phone_hash import phone_hash_from_user, truncate_phone_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/royalties", tags=["Data Royalties"])
limiter = Limiter(key_func=get_remote_address)


# ═══════════════════════════════════════════════════════════════════════
# 1. My Royalties (FREE)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/my-royalties", response_model=RoyaltyHistoryResponse)
@limiter.limit("30/minute")
def get_my_royalties(
    request: Request,
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """My royalty history — passive income from data marketplace."""
    phone = phone_hash_from_user(user)
    entries = RoyaltyEngine.get_contributor_royalties(db, phone, days=days)
    total = sum(e["share_amount_cfa"] for e in entries)

    return RoyaltyHistoryResponse(
        contributor_phone_hash=phone,
        total_royalties_cfa=round(total, 2),
        entries=[RoyaltyEntryResponse(**e) for e in entries],
    )


# ═══════════════════════════════════════════════════════════════════════
# 2. My Royalties Summary (FREE)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/my-royalties/summary", response_model=RoyaltySummaryResponse)
@limiter.limit("30/minute")
def get_my_royalties_summary(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Monthly breakdown + lifetime royalty stats."""
    phone = phone_hash_from_user(user)
    summary = RoyaltyEngine.get_contributor_summary(db, phone)

    return RoyaltySummaryResponse(
        contributor_phone_hash=summary["contributor_phone_hash"],
        total_royalties_cfa=summary["total_royalties_cfa"],
        total_queries_served=summary["total_queries_served"],
        avg_share_pct=summary["avg_share_pct"],
        monthly_breakdown=[MonthlyRoyalty(**m) for m in summary["monthly_breakdown"]],
    )


# ═══════════════════════════════════════════════════════════════════════
# 3. Pool Status (1 credit)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/pool/{country_code}", response_model=RoyaltyPoolResponse)
@limiter.limit("30/minute")
def get_pool_status(
    request: Request,
    country_code: str = Path(..., min_length=2, max_length=2),
    period_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Current royalty pool for a country."""
    deduct_credits(user, db, "/api/v3/royalties/pool", "GET", 1.0)

    result = RoyaltyEngine.get_pool_status(db, country_code.upper(), period_date)
    if not result:
        raise HTTPException(404, f"No royalty pool found for {country_code.upper()}")

    return RoyaltyPoolResponse(**result)


# ═══════════════════════════════════════════════════════════════════════
# 4. Pool Contributors (2 credits)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/pool/{country_code}/contributors", response_model=PoolContributorsResponse)
@limiter.limit("20/minute")
def get_pool_contributors(
    request: Request,
    country_code: str = Path(..., min_length=2, max_length=2),
    period_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Top contributors and their royalty shares for a country pool."""
    deduct_credits(user, db, "/api/v3/royalties/pool/contributors", "GET", 2.0)

    pool_data = RoyaltyEngine.get_pool_status(db, country_code.upper(), period_date)
    if not pool_data:
        raise HTTPException(404, f"No royalty pool found for {country_code.upper()}")

    pool_id = pool_data["id"]
    contributors = RoyaltyEngine.get_pool_contributors(db, pool_id)

    return PoolContributorsResponse(
        pool=RoyaltyPoolResponse(**pool_data),
        contributors=[PoolContributorEntry(**c) for c in contributors],
    )


# ═══════════════════════════════════════════════════════════════════════
# 5. Data Attribution / Lineage (1 credit)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/attribution/{query_log_id}", response_model=list[DataAttributionResponse])
@limiter.limit("30/minute")
def get_data_attribution(
    request: Request,
    query_log_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Data lineage — which country data was consumed by a specific query."""
    deduct_credits(user, db, "/api/v3/royalties/attribution", "GET", 1.0)

    attrs = db.query(DataAttribution).filter(
        DataAttribution.query_log_id == query_log_id
    ).all()

    if not attrs:
        raise HTTPException(404, f"No attribution found for query_log_id={query_log_id}")

    return [DataAttributionResponse.model_validate(a) for a in attrs]


# ═══════════════════════════════════════════════════════════════════════
# 6. Platform Stats (1 credit)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=RoyaltyStatsResponse)
@limiter.limit("20/minute")
def get_royalty_stats(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Platform-wide royalty statistics."""
    deduct_credits(user, db, "/api/v3/royalties/stats", "GET", 1.0)

    stats = RoyaltyEngine.get_platform_stats(db)
    return RoyaltyStatsResponse(**stats)


# ═══════════════════════════════════════════════════════════════════════
# 7. Admin: Trigger Distribution (5 credits)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/admin/distribute")
@limiter.limit("5/minute")
def admin_distribute(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger manual distribution of all pending royalty pools. (Admin: credit-gated, no role system.)"""
    deduct_credits(user, db, "/api/v3/royalties/admin/distribute", "POST", 5.0)

    result = RoyaltyEngine.distribute_all_pending(db)
    db.commit()
    return {"status": "ok", **result}


# ═══════════════════════════════════════════════════════════════════════
# 8. Admin: All Pools (3 credits)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/admin/pools", response_model=AdminPoolListResponse)
@limiter.limit("10/minute")
def admin_list_pools(
    request: Request,
    distributed: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """All royalty pools with distribution status. Admin only."""
    deduct_credits(user, db, "/api/v3/royalties/admin/pools", "GET", 3.0)

    query = db.query(RoyaltyPool)
    if distributed is not None:
        query = query.filter(RoyaltyPool.distributed == distributed)

    pools = query.order_by(RoyaltyPool.period_date.desc()).limit(100).all()

    pending_cfa = sum(p.pool_amount_cfa for p in pools if not p.distributed)
    distributed_cfa = sum(p.pool_amount_cfa for p in pools if p.distributed)

    return AdminPoolListResponse(
        pools=[AdminPoolEntry.model_validate(p) for p in pools],
        total_pending_cfa=round(pending_cfa, 2),
        total_distributed_cfa=round(distributed_cfa, 2),
    )
