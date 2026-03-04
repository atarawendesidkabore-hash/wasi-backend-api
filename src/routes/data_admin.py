"""
Data Administration routes — /api/v2/data/

Endpoints for monitoring data quality and triggering manual data refreshes.

  GET  /api/v2/data/status                — 1 credit   — data freshness per country
  POST /api/v2/data/worldbank/refresh     — 20 credits  — trigger WB indices scraper
  POST /api/v2/data/imf/refresh           — 10 credits  — trigger IMF WEO scraper
  POST /api/v2/data/acled/refresh         — 5 credits   — trigger ACLED conflict signals
  POST /api/v2/data/comtrade/refresh      — 10 credits  — trigger UN Comtrade scraper
  POST /api/v2/data/commodities/refresh   — 5 credits   — trigger WB Pink Sheet scraper
  GET  /api/v2/data/commodities/latest    — 1 credit    — latest commodity prices
  GET  /api/v2/data/macro/{country_code}  — 1 credit    — IMF macro indicators for a country
"""
import logging
from datetime import timezone, datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, MacroIndicator, CommodityPrice
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/data", tags=["Data Admin"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/status")
@limiter.limit("30/minute")
async def get_data_status(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Data freshness report: latest record date, source, confidence,
    and data quality per country. 1 credit.
    """
    deduct_credits(current_user, db, "/api/v2/data/status", cost_multiplier=1.0)

    countries = db.query(Country).filter(Country.is_active == True).all()
    rows = []
    for country in countries:
        latest = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.desc())
            .first()
        )
        macro = (
            db.query(MacroIndicator)
            .filter(MacroIndicator.country_id == country.id)
            .order_by(MacroIndicator.year.desc())
            .first()
        )
        rows.append({
            "country_code":  country.code,
            "country_name":  country.name,
            "latest_period": str(latest.period_date) if latest else None,
            "index_value":   round(latest.index_value, 2) if latest and latest.index_value else None,
            "data_source":   latest.data_source if latest else "no data",
            "confidence":    latest.confidence if latest else 0.0,
            "data_quality":  latest.data_quality if latest else "none",
            "days_old": (
                (date.today() - latest.period_date).days
                if latest and latest.period_date else None
            ),
            "imf_year":       macro.year if macro else None,
            "imf_gdp_growth": round(macro.gdp_growth_pct, 1) if macro and macro.gdp_growth_pct is not None else None,
            "imf_debt_gdp":   round(macro.debt_gdp_pct, 1) if macro and macro.debt_gdp_pct is not None else None,
        })

    # Summary
    has_data    = [r for r in rows if r["latest_period"]]
    wb_sourced  = [r for r in rows if r["data_source"] == "World Bank Open Data API"]
    high_qual   = [r for r in rows if r["data_quality"] == "high"]
    has_imf     = [r for r in rows if r["imf_year"]]

    # Latest commodity prices snapshot
    all_cp = db.query(CommodityPrice).order_by(
        CommodityPrice.commodity_code,
        CommodityPrice.period_date.desc()
    ).all()
    seen_codes: set = set()
    latest_commodities = []
    for cp in all_cp:
        if cp.commodity_code not in seen_codes:
            seen_codes.add(cp.commodity_code)
            latest_commodities.append({
                "code":    cp.commodity_code,
                "name":    cp.commodity_name,
                "price":   round(cp.price_usd, 2),
                "unit":    cp.unit,
                "period":  str(cp.period_date),
                "mom_pct": round(cp.pct_change_mom, 1) if cp.pct_change_mom is not None else None,
            })

    return {
        "checked_at":            str(datetime.now(timezone.utc)),
        "total_countries":       len(rows),
        "countries_with_data":   len(has_data),
        "worldbank_sourced":     len(wb_sourced),
        "high_quality":          len(high_qual),
        "countries_with_imf":    len(has_imf),
        "commodity_prices":      latest_commodities,
        "countries": sorted(rows, key=lambda x: x["confidence"] or 0, reverse=True),
    }


@router.post("/worldbank/refresh")
@limiter.limit("5/minute")
async def trigger_worldbank_refresh(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Manually trigger the World Bank data scraper for all 16 countries.
    Takes 60–120 seconds to complete. 20 credits — use sparingly.
    """
    deduct_credits(current_user, db, "/api/v2/data/worldbank/refresh", cost_multiplier=20.0)

    try:
        from src.pipelines.scrapers.worldbank_scraper import run_worldbank_scraper
        result = run_worldbank_scraper(db=None)
        return {
            "status":    "completed",
            "updated":   result["updated"],
            "skipped":   result["skipped"],
            "errors":    result["errors"],
            "data_year": result["data_year"],
            "countries": result["countries"],
            "note":      "Data updated. Composite index recalculates within 6h.",
        }
    except Exception as exc:
        logger.error("Manual WB refresh failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"World Bank refresh failed: {exc}")


@router.post("/imf/refresh")
@limiter.limit("5/minute")
async def trigger_imf_refresh(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Trigger IMF World Economic Outlook scraper for all 16 countries.
    Fetches GDP growth, inflation, debt/GDP, current account balance.
    10 credits.
    """
    deduct_credits(current_user, db, "/api/v2/data/imf/refresh", cost_multiplier=10.0)

    try:
        from src.pipelines.scrapers.imf_scraper import run_imf_scraper
        result = run_imf_scraper(db=None)
        return {
            "status":    "completed",
            "updated":   result["updated"],
            "skipped":   result["skipped"],
            "errors":    result["errors"],
            "data_year": result["data_year"],
            "countries": result["countries"],
        }
    except Exception as exc:
        logger.error("Manual IMF refresh failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"IMF refresh failed: {exc}")


@router.post("/acled/refresh")
@limiter.limit("5/minute")
async def trigger_acled_refresh(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Trigger ACLED conflict data scraper.
    Creates NewsEvent records for active security incidents.
    If ACLED_API_KEY is not configured, applies fallback Sahel corridor signals.
    5 credits.
    """
    deduct_credits(current_user, db, "/api/v2/data/acled/refresh", cost_multiplier=5.0)

    try:
        from src.pipelines.scrapers.acled_scraper import run_acled_scraper
        result = run_acled_scraper(db=None)
        return {
            "status":         "completed",
            "events_created": result["events_created"],
            "events_skipped": result["events_skipped"],
            "errors":         result["errors"],
            "api_used":       result["api_used"],
            "note": (
                "Live ACLED API used." if result["api_used"]
                else "Fallback signals applied (set ACLED_API_KEY + ACLED_EMAIL in .env for live data)."
            ),
        }
    except Exception as exc:
        logger.error("Manual ACLED refresh failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"ACLED refresh failed: {exc}")


@router.post("/comtrade/refresh")
@limiter.limit("5/minute")
async def trigger_comtrade_refresh(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Trigger UN Comtrade bilateral trade flows scraper.
    Fetches total exports/imports for all 16 countries.
    10 credits. Takes ~30–60 seconds (rate limited free tier).
    """
    deduct_credits(current_user, db, "/api/v2/data/comtrade/refresh", cost_multiplier=10.0)

    try:
        from src.pipelines.scrapers.comtrade_scraper import run_comtrade_scraper
        result = run_comtrade_scraper(db=None)
        return {
            "status":    "completed",
            "updated":   result["updated"],
            "skipped":   result["skipped"],
            "errors":    result["errors"],
            "data_year": result["data_year"],
            "api_used":  result["api_used"],
            "countries": result["countries"],
        }
    except Exception as exc:
        logger.error("Manual Comtrade refresh failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comtrade refresh failed: {exc}")


@router.post("/commodities/refresh")
@limiter.limit("5/minute")
async def trigger_commodity_refresh(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Trigger World Bank Pink Sheet commodity price scraper.
    Updates cocoa, crude oil, gold, cotton, coffee, iron ore spot prices.
    5 credits.
    """
    deduct_credits(current_user, db, "/api/v2/data/commodities/refresh", cost_multiplier=5.0)

    try:
        from src.pipelines.scrapers.commodity_scraper import run_commodity_scraper
        result = run_commodity_scraper(db=None)
        return {
            "status":        "completed",
            "updated":       result["updated"],
            "errors":        result["errors"],
            "latest_prices": result["latest_prices"],
            "commodities":   result["commodities"],
        }
    except Exception as exc:
        logger.error("Manual commodity refresh failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Commodity refresh failed: {exc}")


@router.get("/commodities/latest")
@limiter.limit("30/minute")
async def get_latest_commodities(
    request: Request,
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Latest commodity spot prices (cocoa, oil, gold, cotton, coffee, iron ore).
    Includes MoM and YoY % changes. 1 credit.
    """
    deduct_credits(current_user, db, "/api/v2/data/commodities/latest", cost_multiplier=1.0)

    cp_query = db.query(CommodityPrice)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        cp_query = cp_query.filter(CommodityPrice.period_date.between(q_start, q_end))

    all_cp = cp_query.order_by(
        CommodityPrice.commodity_code,
        CommodityPrice.period_date.desc()
    ).all()

    seen: set = set()
    latest = []
    for cp in all_cp:
        if cp.commodity_code not in seen:
            seen.add(cp.commodity_code)
            latest.append({
                "code":        cp.commodity_code,
                "name":        cp.commodity_name,
                "price_usd":   round(cp.price_usd, 2),
                "unit":        cp.unit,
                "period":      str(cp.period_date),
                "mom_pct":     round(cp.pct_change_mom, 1) if cp.pct_change_mom is not None else None,
                "yoy_pct":     round(cp.pct_change_yoy, 1) if cp.pct_change_yoy is not None else None,
                "data_source": cp.data_source,
                "fetched_at":  str(cp.fetched_at),
            })

    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No commodity price data available. Trigger POST /api/v2/data/commodities/refresh first."
        )

    return {
        "as_of":    str(datetime.now(timezone.utc)),
        "count":    len(latest),
        "prices":   latest,
        "note":     "World Bank Pink Sheet monthly averages. Cocoa & cotton critical for ECOWAS export revenues.",
    }


@router.get("/macro/{country_code}")
@limiter.limit("30/minute")
async def get_macro_indicators(
    request: Request,
    country_code: str,
    quarter: Optional[str] = Query(default=None, description="Filter by quarter year: Q1-2026 returns 2026 data. T3-2024 returns 2024 data."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    IMF WEO macroeconomic indicators for a specific country.
    Returns last 5 years including current-year projections.
    When quarter is provided, filters to that year's data.
    1 credit.
    """
    deduct_credits(current_user, db, f"/api/v2/data/macro/{country_code}", cost_multiplier=1.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    macro_query = db.query(MacroIndicator).filter(MacroIndicator.country_id == country.id)
    if quarter:
        q_start, _ = parse_quarter(quarter)
        macro_query = macro_query.filter(MacroIndicator.year == q_start.year)
    records = (
        macro_query
        .order_by(MacroIndicator.year.desc())
        .limit(5)
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No IMF data for {country_code}. Trigger POST /api/v2/data/imf/refresh first."
        )

    years = []
    for r in records:
        years.append({
            "year":                    r.year,
            "gdp_growth_pct":          round(r.gdp_growth_pct, 2) if r.gdp_growth_pct is not None else None,
            "inflation_pct":           round(r.inflation_pct, 2)  if r.inflation_pct  is not None else None,
            "debt_gdp_pct":            round(r.debt_gdp_pct, 1)   if r.debt_gdp_pct   is not None else None,
            "current_account_gdp_pct": round(r.current_account_gdp_pct, 2) if r.current_account_gdp_pct is not None else None,
            "unemployment_pct":        round(r.unemployment_pct, 1) if r.unemployment_pct is not None else None,
            "gdp_usd_billions":        round(r.gdp_usd_billions, 1) if r.gdp_usd_billions is not None else None,
            "is_projection":           r.is_projection,
            "confidence":              r.confidence,
            "data_source":             r.data_source,
        })

    latest = records[0]
    return {
        "country_code": country.code,
        "country_name": country.name,
        "data_source":  "IMF World Economic Outlook",
        "years":        years,
        "latest": {
            "year":            latest.year,
            "gdp_growth_pct":  latest.gdp_growth_pct,
            "inflation_pct":   latest.inflation_pct,
            "debt_gdp_pct":    latest.debt_gdp_pct,
            "current_account": latest.current_account_gdp_pct,
            "is_projection":   latest.is_projection,
        },
    }
