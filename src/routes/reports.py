"""
Reports routes — structured JSON reports for export and consumption by clients.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timezone, date, datetime, timedelta
from typing import Optional
from pydantic import BaseModel, ConfigDict

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.engines.composite_engine import CompositeEngine
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/reports", tags=["Reports"])


# ── Response schemas ──────────────────────────────────────────────────────────

class MonthlyReportEntry(BaseModel):
    period_date: date
    composite_value: float
    countries_included: Optional[int] = None
    mom_change: Optional[float] = None
    trend_direction: Optional[str] = None


class CountrySummary(BaseModel):
    country_code: str
    country_name: str
    tier: str
    weight: float
    latest_index: Optional[float] = None
    period_date: Optional[date] = None


class ExecutiveSummary(BaseModel):
    report_date: date
    generated_at: datetime
    composite_latest: Optional[float] = None
    composite_period: Optional[date] = None
    trend_direction: Optional[str] = None
    mom_change: Optional[float] = None
    yoy_change: Optional[float] = None
    countries_with_data: int
    countries_registered: int
    months_of_history: int
    avg_composite_12m: Optional[float] = None
    annualized_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None


class FullReport(BaseModel):
    executive_summary: ExecutiveSummary
    monthly_history: list[MonthlyReportEntry]
    country_breakdown: list[CountrySummary]
    country_contributions: dict[str, float]
    generated_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/executive-summary", response_model=ExecutiveSummary)
async def get_executive_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    High-level executive summary of WASI current state.
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/reports/executive-summary", cost_multiplier=2.0)

    latest_composite = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )

    history_12m = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .limit(12)
        .all()
    )

    total_months = db.query(func.count(WASIComposite.id)).scalar() or 0
    countries_registered = db.query(func.count(Country.id)).filter(Country.is_active.is_(True)).scalar() or 0

    latest_date = db.query(func.max(CountryIndex.period_date)).scalar()
    countries_with_data = 0
    if latest_date:
        countries_with_data = (
            db.query(func.count(CountryIndex.id))
            .filter(CountryIndex.period_date == latest_date)
            .scalar() or 0
        )

    avg_12m = None
    if history_12m:
        avg_12m = round(sum(r.composite_value for r in history_12m) / len(history_12m), 4)

    return ExecutiveSummary(
        report_date=date.today(),
        generated_at=datetime.now(timezone.utc),
        composite_latest=latest_composite.composite_value if latest_composite else None,
        composite_period=latest_composite.period_date if latest_composite else None,
        trend_direction=latest_composite.trend_direction if latest_composite else None,
        mom_change=latest_composite.mom_change if latest_composite else None,
        yoy_change=latest_composite.yoy_change if latest_composite else None,
        countries_with_data=countries_with_data,
        countries_registered=countries_registered,
        months_of_history=total_months,
        avg_composite_12m=avg_12m,
        annualized_volatility=latest_composite.annualized_volatility if latest_composite else None,
        sharpe_ratio=latest_composite.sharpe_ratio if latest_composite else None,
    )


@router.get("/monthly", response_model=list[MonthlyReportEntry])
async def get_monthly_report(
    months: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Month-by-month composite values for the specified window.
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/reports/monthly")

    cutoff = date.today() - timedelta(days=months * 31)
    records = (
        db.query(WASIComposite)
        .filter(WASIComposite.period_date >= cutoff)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )

    return [
        MonthlyReportEntry(
            period_date=r.period_date,
            composite_value=r.composite_value,
            countries_included=r.countries_included,
            mom_change=r.mom_change,
            trend_direction=r.trend_direction,
        )
        for r in records
    ]


@router.get("/full", response_model=FullReport)
async def get_full_report(
    months: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Complete WASI report: executive summary + monthly history + country breakdown.
    Costs 5 credits.
    """
    deduct_credits(current_user, db, "/api/reports/full", cost_multiplier=5.0)

    # Latest composite
    latest = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )

    # Monthly history
    cutoff = date.today() - timedelta(days=months * 31)
    history = (
        db.query(WASIComposite)
        .filter(WASIComposite.period_date >= cutoff)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )

    # Country breakdown
    countries = db.query(Country).filter(Country.is_active.is_(True)).order_by(Country.weight.desc()).all()
    latest_date = db.query(func.max(CountryIndex.period_date)).scalar()

    index_map = {}
    if latest_date:
        for row in db.query(CountryIndex).filter(CountryIndex.period_date == latest_date).all():
            index_map[row.country_id] = row

    country_breakdown = [
        CountrySummary(
            country_code=c.code,
            country_name=c.name,
            tier=c.tier,
            weight=c.weight,
            latest_index=index_map[c.id].index_value if c.id in index_map else None,
            period_date=latest_date if c.id in index_map else None,
        )
        for c in countries
    ]

    # Country contributions from engine
    contributions = {}
    if latest_date and index_map:
        engine = CompositeEngine()
        country_code_map = {c.id: c.code for c in countries}
        available = {
            country_code_map[cid]: row.index_value
            for cid, row in index_map.items()
            if cid in country_code_map and country_code_map[cid] in engine.COUNTRY_WEIGHTS
        }
        total_w = sum(engine.COUNTRY_WEIGHTS[c] for c in available)
        contributions = {
            code: round(val * (engine.COUNTRY_WEIGHTS[code] / total_w), 4)
            for code, val in available.items()
        }

    # Executive summary
    total_months = db.query(func.count(WASIComposite.id)).scalar() or 0
    countries_registered = db.query(func.count(Country.id)).filter(Country.is_active.is_(True)).scalar() or 0
    countries_with_data = len(index_map)
    hist12 = history[-12:] if len(history) > 12 else history
    avg_12m = round(sum(r.composite_value for r in hist12) / len(hist12), 4) if hist12 else None

    summary = ExecutiveSummary(
        report_date=date.today(),
        generated_at=datetime.now(timezone.utc),
        composite_latest=latest.composite_value if latest else None,
        composite_period=latest.period_date if latest else None,
        trend_direction=latest.trend_direction if latest else None,
        mom_change=latest.mom_change if latest else None,
        yoy_change=latest.yoy_change if latest else None,
        countries_with_data=countries_with_data,
        countries_registered=countries_registered,
        months_of_history=total_months,
        avg_composite_12m=avg_12m,
        annualized_volatility=latest.annualized_volatility if latest else None,
        sharpe_ratio=latest.sharpe_ratio if latest else None,
    )

    monthly = [
        MonthlyReportEntry(
            period_date=r.period_date,
            composite_value=r.composite_value,
            countries_included=r.countries_included,
            mom_change=r.mom_change,
            trend_direction=r.trend_direction,
        )
        for r in history
    ]

    return FullReport(
        executive_summary=summary,
        monthly_history=monthly,
        country_breakdown=country_breakdown,
        country_contributions=contributions,
        generated_at=datetime.now(timezone.utc),
    )
