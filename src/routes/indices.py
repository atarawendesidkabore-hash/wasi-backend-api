from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import timezone, datetime, date, timedelta
from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.schemas.index import AllIndicesResponse, CountryIndexResponse
from src.schemas.composite import CompositeResponse
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/indices", tags=["Indices"])


@router.get("/latest", response_model=AllIndicesResponse)
async def get_latest_indices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent index value for all WASI countries. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/indices/latest")

    subq = (
        db.query(
            CountryIndex.country_id,
            func.max(CountryIndex.period_date).label("max_date"),
        )
        .group_by(CountryIndex.country_id)
        .subquery()
    )

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


@router.get("/history", response_model=list[CompositeResponse])
async def get_composite_history(
    months: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the WASI composite index history. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/indices/history")

    cutoff = date.today() - timedelta(days=months * 31)
    composites = (
        db.query(WASIComposite)
        .filter(WASIComposite.period_date >= cutoff)
        .order_by(WASIComposite.period_date.desc())
        .all()
    )
    return composites


@router.get("/all", response_model=list[CountryIndexResponse])
async def get_all_country_indices(
    period_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all country index values for a specific month. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/indices/all")

    if not period_date:
        period_date = db.query(func.max(CountryIndex.period_date)).scalar()

    rows = (
        db.query(CountryIndex)
        .filter(CountryIndex.period_date == period_date)
        .all()
    )
    return rows
