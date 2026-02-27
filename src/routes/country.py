from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex
from src.schemas.index import CountryIndexResponse
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/country", tags=["Country"])


@router.get("/{country_code}/index", response_model=CountryIndexResponse)
async def get_country_index(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    period_date: date | None = Query(default=None),
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
    if period_date:
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
async def get_country_history(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    months: int = Query(default=12, ge=1, le=60),
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

    cutoff = date.today() - timedelta(days=months * 31)
    records = (
        db.query(CountryIndex)
        .filter(
            CountryIndex.country_id == country.id,
            CountryIndex.period_date >= cutoff,
        )
        .order_by(CountryIndex.period_date.desc())
        .all()
    )
    return records
