from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import timezone, datetime, date, timedelta
from typing import Optional
from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.schemas.index import AllIndicesResponse, CountryIndexResponse
from src.schemas.composite import CompositeResponse
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter
from src.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/api/indices", tags=["Indices"])

limiter = Limiter(key_func=get_remote_address)


@router.get("/latest", response_model=AllIndicesResponse)
@limiter.limit("30/minute")
async def get_latest_indices(
    request: Request,
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, 2026-Q2, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent index value for all WASI countries. Free (essential endpoint)."""
    deduct_credits(current_user, db, "/api/indices/latest", cost_multiplier=0.0)

    base_query = db.query(CountryIndex.country_id, func.max(CountryIndex.period_date).label("max_date"))
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        base_query = base_query.filter(CountryIndex.period_date.between(q_start, q_end))

    subq = base_query.group_by(CountryIndex.country_id).subquery()

    rows = (
        db.query(CountryIndex, Country)
        .join(
            subq,
            and_(
                CountryIndex.country_id == subq.c.country_id,
                CountryIndex.period_date == subq.c.max_date,
            ),
        )
        .join(Country, Country.id == CountryIndex.country_id)
        .all()
    )

    if not rows:
        return AllIndicesResponse(
            period_date=date.today(),
            indices={},
            confidence_indicators={},
            generated_at=datetime.now(timezone.utc),
        )

    indices = {row.Country.code: row.CountryIndex.index_value for row in rows}
    max_date = max(row.CountryIndex.period_date for row in rows)

    def _indicator(conf):
        if conf is None:
            return "grey"
        if conf >= 0.8:
            return "green"
        if conf >= 0.5:
            return "yellow"
        return "red"

    confidence_indicators = {
        row.Country.code: _indicator(row.CountryIndex.confidence)
        for row in rows
    }

    return AllIndicesResponse(
        period_date=max_date,
        indices=indices,
        confidence_indicators=confidence_indicators,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/history")
@limiter.limit("30/minute")
async def get_composite_history(
    request: Request,
    months: int = Query(default=12, ge=1, le=60),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc."),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the WASI composite index history. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/indices/history")

    query = db.query(WASIComposite)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        query = query.filter(WASIComposite.period_date.between(q_start, q_end))
    else:
        cutoff = date.today() - timedelta(days=months * 31)
        query = query.filter(WASIComposite.period_date >= cutoff)

    return paginate(query.order_by(WASIComposite.period_date.desc()), pagination)


@router.get("/all")
@limiter.limit("30/minute")
async def get_all_country_indices(
    request: Request,
    period_date: date | None = Query(default=None),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides period_date."),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all country index values for a specific month or quarter. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/indices/all")

    if quarter:
        q_start, q_end = parse_quarter(quarter)
        query = (
            db.query(CountryIndex)
            .filter(CountryIndex.period_date.between(q_start, q_end))
            .order_by(CountryIndex.period_date.desc())
        )
    else:
        if not period_date:
            period_date = db.query(func.max(CountryIndex.period_date)).scalar()
        query = (
            db.query(CountryIndex)
            .filter(CountryIndex.period_date == period_date)
        )
    return paginate(query, pagination)
