from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex
from src.schemas.index import CountryIndexResponse
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter

router = APIRouter(prefix="/api/country", tags=["Country"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/{country_code}/index", response_model=CountryIndexResponse)
@limiter.limit("30/minute")
async def get_country_index(
    request: Request,
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    period_date: date | None = Query(default=None),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides period_date."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a specific country's index value.
    country_code is ISO 3166-1 alpha-2 (e.g. CI, NG, GH).
    Costs 1 credit.
    """
    deduct_credits(current_user, db, f"/api/country/{country_code}/index")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{country_code.upper()}' not found in WASI index",
        )

    query = db.query(CountryIndex).filter(CountryIndex.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        query = query.filter(CountryIndex.period_date.between(q_start, q_end))
        query = query.order_by(CountryIndex.period_date.desc())
    elif period_date:
        query = query.filter(CountryIndex.period_date == period_date)
    else:
        query = query.order_by(CountryIndex.period_date.desc())

    record = query.first()
    if not record:
        raise HTTPException(
            status_code=404,
            detail="No data available for this country/period",
        )
    return record


@router.get("/{country_code}/history", response_model=list[CountryIndexResponse])
@limiter.limit("20/minute")
async def get_country_history(
    request: Request,
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    months: int = Query(default=12, ge=1, le=60),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides months."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get historical index values for a country.
    Costs 2 credits (higher data volume).
    """
    deduct_credits(current_user, db, f"/api/country/{country_code}/history", cost_multiplier=2.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{country_code.upper()}' not found in WASI index",
        )

    query = db.query(CountryIndex).filter(CountryIndex.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        query = query.filter(CountryIndex.period_date.between(q_start, q_end))
    else:
        cutoff = date.today() - timedelta(days=months * 31)
        query = query.filter(CountryIndex.period_date >= cutoff)

    records = query.order_by(CountryIndex.period_date.desc()).all()
    return records
