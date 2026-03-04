"""
Analytics routes — trend analysis, performance metrics, cross-country comparisons.
All endpoints require authentication and consume credits.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, ConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
limiter = Limiter(key_func=get_remote_address)


# ── Response schemas ─────────────────────────────────────────────────────────

class TrendPoint(BaseModel):
    period_date: date
    composite_value: float
    mom_change: Optional[float] = None
    trend_direction: Optional[str] = None


class CountryPerformance(BaseModel):
    country_code: str
    country_name: str
    tier: str
    latest_index: float
    period_date: date
    shipping_score: Optional[float] = None
    trade_score: Optional[float] = None
    infrastructure_score: Optional[float] = None
    economic_score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class CompositeStats(BaseModel):
    period_from: date
    period_to: date
    avg_composite: float
    max_composite: float
    min_composite: float
    range_composite: float
    months_analyzed: int
    avg_mom_change: Optional[float] = None
    months_up: int
    months_down: int
    months_flat: int


class CrossCountryComparison(BaseModel):
    period_date: date
    rankings: list[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/trends")
@limiter.limit("30/minute")
async def get_composite_trends(
    request: Request,
    months: int = Query(default=12, ge=1, le=60),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the WASI composite trend for the last N months.
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/analytics/trends")

    cutoff = date.today() - timedelta(days=months * 31)
    query = (
        db.query(WASIComposite)
        .filter(WASIComposite.period_date >= cutoff)
        .order_by(WASIComposite.period_date.asc())
    )
    result = paginate(query, pagination)
    result["items"] = [
        TrendPoint(
            period_date=c.period_date,
            composite_value=c.composite_value,
            mom_change=c.mom_change,
            trend_direction=c.trend_direction,
        )
        for c in result["items"]
    ]
    return result


@router.get("/stats", response_model=CompositeStats)
@limiter.limit("30/minute")
async def get_composite_stats(
    request: Request,
    months: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregate statistics over the composite history: avg, min, max, up/down months.
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/analytics/stats", cost_multiplier=2.0)

    cutoff = date.today() - timedelta(days=months * 31)
    records = (
        db.query(WASIComposite)
        .filter(WASIComposite.period_date >= cutoff)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="No composite data found. Ingest data and call POST /api/composite/calculate first.",
        )

    values = [r.composite_value for r in records]
    mom_changes = [r.mom_change for r in records if r.mom_change is not None]
    directions = [r.trend_direction for r in records]

    return CompositeStats(
        period_from=records[0].period_date,
        period_to=records[-1].period_date,
        avg_composite=round(sum(values) / len(values), 4),
        max_composite=round(max(values), 4),
        min_composite=round(min(values), 4),
        range_composite=round(max(values) - min(values), 4),
        months_analyzed=len(records),
        avg_mom_change=round(sum(mom_changes) / len(mom_changes), 4) if mom_changes else None,
        months_up=sum(1 for d in directions if d == "up"),
        months_down=sum(1 for d in directions if d == "down"),
        months_flat=sum(1 for d in directions if d == "flat"),
    )


@router.get("/performance", response_model=list[CountryPerformance])
@limiter.limit("30/minute")
async def get_country_performance(
    request: Request,
    period_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ranked list of all countries by index value for a given period (defaults to latest).
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/analytics/performance")

    if not period_date:
        period_date = db.query(func.max(CountryIndex.period_date)).scalar()

    if not period_date:
        raise HTTPException(status_code=404, detail="No index data available.")

    rows = (
        db.query(CountryIndex, Country)
        .join(Country, Country.id == CountryIndex.country_id)
        .filter(CountryIndex.period_date == period_date)
        .order_by(CountryIndex.index_value.desc())
        .all()
    )

    return [
        CountryPerformance(
            country_code=row.Country.code,
            country_name=row.Country.name,
            tier=row.Country.tier,
            latest_index=row.CountryIndex.index_value,
            period_date=row.CountryIndex.period_date,
            shipping_score=row.CountryIndex.shipping_score,
            trade_score=row.CountryIndex.trade_score,
            infrastructure_score=row.CountryIndex.infrastructure_score,
            economic_score=row.CountryIndex.economic_score,
        )
        for row in rows
    ]


@router.get("/compare", response_model=CrossCountryComparison)
@limiter.limit("30/minute")
async def compare_countries(
    request: Request,
    codes: str = Query(description="Comma-separated ISO-2 country codes, e.g. NG,CI,GH"),
    period_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Side-by-side comparison of specified countries for a period.
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/analytics/compare", cost_multiplier=2.0)

    country_codes = [c.strip().upper() for c in codes.split(",") if c.strip()]
    if not country_codes:
        raise HTTPException(status_code=422, detail="Provide at least one country code.")

    if not period_date:
        period_date = db.query(func.max(CountryIndex.period_date)).scalar()

    rows = (
        db.query(CountryIndex, Country)
        .join(Country, Country.id == CountryIndex.country_id)
        .filter(
            Country.code.in_(country_codes),
            CountryIndex.period_date == period_date,
        )
        .order_by(CountryIndex.index_value.desc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data for period {period_date} and codes {country_codes}.",
        )

    rankings = [
        {
            "rank": idx + 1,
            "country_code": row.Country.code,
            "country_name": row.Country.name,
            "index_value": row.CountryIndex.index_value,
            "shipping_score": row.CountryIndex.shipping_score,
            "trade_score": row.CountryIndex.trade_score,
            "infrastructure_score": row.CountryIndex.infrastructure_score,
            "economic_score": row.CountryIndex.economic_score,
            "weight": row.Country.weight,
        }
        for idx, row in enumerate(rows)
    ]

    return CrossCountryComparison(period_date=period_date, rankings=rankings)
