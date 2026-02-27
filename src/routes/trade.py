"""
Trade routes — bilateral trade flows between WASI countries and global partners.

Endpoints allow querying:
  - Which WASI countries trade with a specific partner (e.g. Switzerland)
  - All trade partners of a specific WASI country
  - Top trading relationships across the platform
  - Trade balance statistics

All endpoints require authentication and consume credits.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from src.database.connection import get_db
from src.database.models import User, Country, BilateralTrade
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/trade", tags=["Trade"])


# ── Response schemas ──────────────────────────────────────────────────────────

class BilateralTradeEntry(BaseModel):
    wasi_country_code: str
    wasi_country_name: str
    partner_code: str
    partner_name: str
    year: int
    export_value_usd: float
    import_value_usd: float
    total_trade_usd: float
    trade_balance_usd: float
    top_exports: str
    top_imports: str

    model_config = ConfigDict(from_attributes=True)


class BilateralQueryResponse(BaseModel):
    partner_code: str
    partner_name: str
    year: int
    country_count: int
    total_trade_volume_usd: float
    entries: list[BilateralTradeEntry]
    generated_at: datetime


class CountryPartnersResponse(BaseModel):
    wasi_country_code: str
    wasi_country_name: str
    year: int
    partner_count: int
    total_trade_volume_usd: float
    partners: list[BilateralTradeEntry]
    generated_at: datetime


class TradeLeaderboard(BaseModel):
    year: int
    top_relationships: list[dict]
    generated_at: datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/bilateral", response_model=BilateralQueryResponse)
async def get_wasi_countries_by_partner(
    partner_code: str = Query(description="ISO-2 partner country code, e.g. CH, FR, CN"),
    year: int = Query(default=2022, ge=2015, le=2030),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Find all WASI countries that trade with the specified partner country.

    Example: /api/trade/bilateral?partner_code=CH&year=2022
    Returns all WASI countries that trade with Switzerland in 2022.
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/trade/bilateral")

    pc = partner_code.upper().strip()

    rows = (
        db.query(BilateralTrade, Country)
        .join(Country, Country.id == BilateralTrade.country_id)
        .filter(
            BilateralTrade.partner_code == pc,
            BilateralTrade.year == year,
        )
        .order_by(BilateralTrade.total_trade_usd.desc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No bilateral trade data found for partner '{pc}' in {year}. "
                   f"Available partners include: CH, CN, FR, DE, GB, IN, US, NL, BE, AE, ES, IT.",
        )

    entries = [
        BilateralTradeEntry(
            wasi_country_code=row.Country.code,
            wasi_country_name=row.Country.name,
            partner_code=row.BilateralTrade.partner_code,
            partner_name=row.BilateralTrade.partner_name,
            year=row.BilateralTrade.year,
            export_value_usd=row.BilateralTrade.export_value_usd,
            import_value_usd=row.BilateralTrade.import_value_usd,
            total_trade_usd=row.BilateralTrade.total_trade_usd,
            trade_balance_usd=row.BilateralTrade.trade_balance_usd,
            top_exports=row.BilateralTrade.top_exports,
            top_imports=row.BilateralTrade.top_imports,
        )
        for row in rows
    ]

    partner_name = rows[0].BilateralTrade.partner_name if rows else pc
    total_volume = sum(e.total_trade_usd for e in entries)

    return BilateralQueryResponse(
        partner_code=pc,
        partner_name=partner_name,
        year=year,
        country_count=len(entries),
        total_trade_volume_usd=total_volume,
        entries=entries,
        generated_at=datetime.utcnow(),
    )


@router.get("/partners/{country_code}", response_model=CountryPartnersResponse)
async def get_country_trade_partners(
    country_code: str,
    year: int = Query(default=2022, ge=2015, le=2030),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all trading partners of a specific WASI country for a given year.
    Results sorted by total trade volume (descending).
    Costs 1 credit.
    """
    deduct_credits(current_user, db, f"/api/trade/partners/{country_code}")

    code = country_code.upper().strip()
    country = db.query(Country).filter(Country.code == code).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{code}' not found in WASI.")

    rows = (
        db.query(BilateralTrade)
        .filter(
            BilateralTrade.country_id == country.id,
            BilateralTrade.year == year,
        )
        .order_by(BilateralTrade.total_trade_usd.desc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No bilateral trade data for {code} in {year}.",
        )

    partners = [
        BilateralTradeEntry(
            wasi_country_code=country.code,
            wasi_country_name=country.name,
            partner_code=r.partner_code,
            partner_name=r.partner_name,
            year=r.year,
            export_value_usd=r.export_value_usd,
            import_value_usd=r.import_value_usd,
            total_trade_usd=r.total_trade_usd,
            trade_balance_usd=r.trade_balance_usd,
            top_exports=r.top_exports,
            top_imports=r.top_imports,
        )
        for r in rows
    ]

    return CountryPartnersResponse(
        wasi_country_code=country.code,
        wasi_country_name=country.name,
        year=year,
        partner_count=len(partners),
        total_trade_volume_usd=sum(p.total_trade_usd for p in partners),
        partners=partners,
        generated_at=datetime.utcnow(),
    )


@router.get("/leaderboard", response_model=TradeLeaderboard)
async def get_trade_leaderboard(
    year: int = Query(default=2022, ge=2015, le=2030),
    limit: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Top bilateral trade relationships across all WASI countries, ranked by volume.
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/trade/leaderboard")

    rows = (
        db.query(BilateralTrade, Country)
        .join(Country, Country.id == BilateralTrade.country_id)
        .filter(BilateralTrade.year == year)
        .order_by(BilateralTrade.total_trade_usd.desc())
        .limit(limit)
        .all()
    )

    relationships = [
        {
            "rank": idx + 1,
            "wasi_country": row.Country.code,
            "wasi_country_name": row.Country.name,
            "partner": row.BilateralTrade.partner_code,
            "partner_name": row.BilateralTrade.partner_name,
            "total_trade_usd": row.BilateralTrade.total_trade_usd,
            "export_usd": row.BilateralTrade.export_value_usd,
            "import_usd": row.BilateralTrade.import_value_usd,
            "trade_balance_usd": row.BilateralTrade.trade_balance_usd,
            "top_exports": row.BilateralTrade.top_exports,
        }
        for idx, row in enumerate(rows)
    ]

    return TradeLeaderboard(
        year=year,
        top_relationships=relationships,
        generated_at=datetime.utcnow(),
    )


@router.get("/summary", response_model=dict)
async def get_trade_summary(
    year: int = Query(default=2022, ge=2015, le=2030),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregate trade statistics: total volume, top partners, surplus/deficit summary.
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/trade/summary", cost_multiplier=2.0)

    rows = (
        db.query(BilateralTrade, Country)
        .join(Country, Country.id == BilateralTrade.country_id)
        .filter(BilateralTrade.year == year)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No trade data for {year}.")

    # Partner aggregates
    partner_totals: dict = {}
    for r in rows:
        pc = r.BilateralTrade.partner_code
        pn = r.BilateralTrade.partner_name
        if pc not in partner_totals:
            partner_totals[pc] = {"partner_code": pc, "partner_name": pn,
                                  "total_trade_usd": 0.0, "country_count": 0}
        partner_totals[pc]["total_trade_usd"] += r.BilateralTrade.total_trade_usd
        partner_totals[pc]["country_count"] += 1

    top_partners = sorted(
        partner_totals.values(), key=lambda x: x["total_trade_usd"], reverse=True
    )[:10]

    total_volume = sum(r.BilateralTrade.total_trade_usd for r in rows)
    total_exports = sum(r.BilateralTrade.export_value_usd for r in rows)
    total_imports = sum(r.BilateralTrade.import_value_usd for r in rows)

    return {
        "year": year,
        "total_trade_volume_usd": total_volume,
        "total_exports_usd": total_exports,
        "total_imports_usd": total_imports,
        "overall_trade_balance_usd": total_exports - total_imports,
        "records_count": len(rows),
        "top_10_partners": top_partners,
        "generated_at": datetime.utcnow().isoformat(),
    }
