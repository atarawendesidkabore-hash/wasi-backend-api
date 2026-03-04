"""
Forecast routes — /api/v3/forecast/

Time-series forecasting for WASI economic indicators.
Serves cached forecast results from the forecast_results table.
Falls back to live computation if no cached result exists.
"""
import asyncio
import logging
from datetime import timezone, date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import (
    User, Country, CountryIndex, WASIComposite,
    CommodityPrice, MacroIndicator,
)
from src.database.forecast_models import ForecastResult
from src.engines.forecast_engine import ForecastEngine
from src.schemas.forecast import (
    ForecastResponse, ForecastSummaryItem, ForecastSummaryResponse,
    ForecastRefreshResponse, ForecastPeriod,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.periods import parse_quarter
from src.tasks.forecast_task import run_forecast_update, _persist_forecast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/forecast", tags=["Forecast"])

limiter = Limiter(key_func=get_remote_address)

_engine = ForecastEngine()

VALID_HORIZONS = {3, 6, 12}
VALID_COMMODITIES = {"COCOA", "BRENT", "GOLD", "COTTON", "COFFEE", "IRON_ORE"}
VALID_INDICATORS = {"gdp_growth", "inflation"}
VALID_EXCHANGES = {"NGX", "GSE", "BRVM"}
VALID_ECFA_AGGREGATES = {"circulation", "m0", "m1", "m2", "velocity"}
INDICATOR_COLUMNS = {"gdp_growth": "gdp_growth_pct", "inflation": "inflation_pct"}
CACHE_MAX_AGE_HOURS = 24


# ── Helpers ──────────────────────────────────────────────────────

def _get_cached_forecast(
    db: Session,
    target_type: str,
    target_code: str,
    horizon: int,
    quarter: Optional[str] = None,
) -> Optional[ForecastResponse]:
    """Return cached forecast if fresh enough, else None.
    When quarter is provided, only return forecast periods within that quarter.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_MAX_AGE_HOURS)
    query = (
        db.query(ForecastResult)
        .filter(
            ForecastResult.target_type == target_type,
            ForecastResult.target_code == target_code,
            ForecastResult.horizon_months == horizon,
            ForecastResult.calculated_at >= cutoff,
        )
    )
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        query = query.filter(ForecastResult.period_date.between(q_start, q_end))

    rows = query.order_by(ForecastResult.period_date.asc()).all()
    if not rows:
        return None

    first = rows[0]
    periods = [
        ForecastPeriod(
            period_offset=i + 1,
            period_date=r.period_date,
            forecast_value=r.forecast_value,
            lower_1sigma=r.lower_1sigma or r.forecast_value,
            upper_1sigma=r.upper_1sigma or r.forecast_value,
            lower_2sigma=r.lower_2sigma or r.forecast_value,
            upper_2sigma=r.upper_2sigma or r.forecast_value,
        )
        for i, r in enumerate(rows)
    ]

    methods = first.methods_used.split(",") if first.methods_used else []
    return ForecastResponse(
        target_type=target_type,
        target_code=target_code,
        horizon=horizon,
        last_actual_date=str(first.last_actual_date) if first.last_actual_date else None,
        last_actual_value=first.last_actual_value,
        data_points_used=first.data_points_used or 0,
        methods_used=methods,
        ensemble_weights={m: round(1.0 / len(methods), 4) for m in methods} if methods else {},
        residual_std=first.residual_std,
        confidence_score=first.confidence or 1.0,
        periods=periods,
        method_forecasts={},
        calculated_at=first.calculated_at,
    )


def _build_response(result: dict) -> ForecastResponse:
    """Convert engine result dict into ForecastResponse."""
    periods = [ForecastPeriod(**p) for p in result.get("periods", [])]
    return ForecastResponse(
        target_type=result.get("target_type", "unknown"),
        target_code=result.get("target_code", "unknown"),
        horizon=result.get("horizon", 0),
        last_actual_date=result.get("last_actual_date"),
        last_actual_value=result.get("last_actual_value"),
        data_points_used=result.get("data_points_used", 0),
        methods_used=result.get("methods_used", []),
        ensemble_weights=result.get("ensemble_weights", {}),
        residual_std=result.get("residual_std"),
        confidence_score=result.get("confidence_score", 0.0),
        periods=periods,
        method_forecasts=result.get("method_forecasts", {}),
        calculated_at=datetime.now(timezone.utc),
        error=result.get("error"),
    )


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/composite", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_composite(
    request: Request,
    horizon: int = Query(default=6, description="Forecast horizon in months (3, 6, or 12)"),
    quarter: Optional[str] = Query(default=None, description="Filter forecast periods by quarter: Q1-2026, T3-2025, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast the aggregate WASI Composite index. Costs 5 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/composite", cost_multiplier=5.0)

    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=400, detail=f"horizon must be one of {sorted(VALID_HORIZONS)}")

    cached = _get_cached_forecast(db, "composite_index", "WASI_COMPOSITE", horizon, quarter)
    if cached:
        return cached

    composites = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )
    if len(composites) < 3:
        raise HTTPException(status_code=404, detail="Insufficient composite data for forecasting")

    values = [r.composite_value for r in composites]
    dates = [r.period_date for r in composites]
    result = _engine.forecast_composite(values, dates, horizon)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)


@router.get("/summary", response_model=ForecastSummaryResponse)
@limiter.limit("20/minute")
async def forecast_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All-countries forecast summary dashboard. Costs 10 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/summary", cost_multiplier=10.0)

    countries = db.query(Country).filter(Country.is_active == True).all()
    items = []

    for country in countries:
        # Get latest actual index
        latest = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.desc())
            .first()
        )
        current_value = latest.index_value if latest else None

        # Get cached forecasts for 3/6/12 months
        fc_3 = db.query(ForecastResult).filter(
            ForecastResult.target_type == "country_index",
            ForecastResult.target_code == country.code,
            ForecastResult.horizon_months == 3,
        ).order_by(ForecastResult.period_date.asc()).first()

        fc_6 = db.query(ForecastResult).filter(
            ForecastResult.target_type == "country_index",
            ForecastResult.target_code == country.code,
            ForecastResult.horizon_months == 6,
        ).order_by(ForecastResult.period_date.asc()).first()

        fc_12 = db.query(ForecastResult).filter(
            ForecastResult.target_type == "country_index",
            ForecastResult.target_code == country.code,
            ForecastResult.horizon_months == 12,
        ).order_by(ForecastResult.period_date.asc()).first()

        # Determine trend from 6-month forecast vs current
        trend = "flat"
        if current_value and fc_6:
            diff = fc_6.forecast_value - current_value
            if diff > 2:
                trend = "up"
            elif diff < -2:
                trend = "down"

        confidence = latest.confidence if latest and latest.confidence else 0.0
        if confidence >= 0.8:
            quality = "green"
        elif confidence >= 0.5:
            quality = "yellow"
        elif confidence >= 0.3:
            quality = "red"
        else:
            quality = "grey"

        items.append(ForecastSummaryItem(
            country_code=country.code,
            country_name=country.name,
            current_value=round(current_value, 2) if current_value else None,
            forecast_3m=round(fc_3.forecast_value, 2) if fc_3 else None,
            forecast_6m=round(fc_6.forecast_value, 2) if fc_6 else None,
            forecast_12m=round(fc_12.forecast_value, 2) if fc_12 else None,
            trend=trend,
            confidence=round(confidence, 2),
            data_quality=quality,
        ))

    # Composite forecast
    composite_fc = _get_cached_forecast(db, "composite_index", "WASI_COMPOSITE", 6)

    return ForecastSummaryResponse(
        composite_forecast=composite_fc,
        countries=items,
        total_countries=len(items),
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/refresh", response_model=ForecastRefreshResponse)
@limiter.limit("10/minute")
async def refresh_forecasts(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger full forecast recalculation. Costs 20 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/refresh", cost_multiplier=20.0)

    result = await run_forecast_update(db=db)

    return ForecastRefreshResponse(
        status=result.get("status", "unknown"),
        country_forecasts_computed=result.get("country_forecasts_computed", 0),
        composite_computed=result.get("composite_computed", False),
        commodities_computed=result.get("commodities_computed", 0),
        macro_computed=result.get("macro_computed", 0),
        duration_seconds=result.get("duration_seconds", 0.0),
        computed_at=result.get("computed_at", datetime.now(timezone.utc)),
    )


@router.get("/commodity/{commodity_code}", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_commodity(
    request: Request,
    commodity_code: str,
    horizon: int = Query(default=6, description="Forecast horizon in months (3, 6, or 12)"),
    quarter: Optional[str] = Query(default=None, description="Filter forecast periods by quarter: Q1-2026, T3-2025, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast a commodity price series. Costs 2 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/commodity/{commodity_code}", cost_multiplier=2.0)

    code = commodity_code.upper()
    if code not in VALID_COMMODITIES:
        raise HTTPException(status_code=400, detail=f"Invalid commodity. Valid: {sorted(VALID_COMMODITIES)}")

    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=400, detail=f"horizon must be one of {sorted(VALID_HORIZONS)}")

    cached = _get_cached_forecast(db, "commodity_price", code, horizon, quarter)
    if cached:
        return cached

    rows = (
        db.query(CommodityPrice)
        .filter(CommodityPrice.commodity_code == code)
        .order_by(CommodityPrice.period_date.asc())
        .all()
    )
    if len(rows) < 3:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {code}")

    values = [r.price_usd for r in rows if r.price_usd is not None]
    dates = [r.period_date for r in rows if r.price_usd is not None]
    if len(values) < 3:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {code}")

    result = _engine.forecast_commodity(code, values, dates, horizon)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)


@router.get("/{country_code}/index", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_country_index(
    request: Request,
    country_code: str,
    horizon: int = Query(default=6, description="Forecast horizon in months (3, 6, or 12)"),
    quarter: Optional[str] = Query(default=None, description="Filter forecast periods by quarter: Q1-2026, T3-2025, etc."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast a country's WASI index. Costs 3 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/{country_code}/index", cost_multiplier=3.0)

    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=400, detail=f"horizon must be one of {sorted(VALID_HORIZONS)}")

    cc = country_code.upper()
    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    cached = _get_cached_forecast(db, "country_index", cc, horizon, quarter)
    if cached:
        return cached

    rows = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.asc())
        .all()
    )
    values = [r.index_value for r in rows if r.index_value is not None]
    dates = [r.period_date for r in rows if r.index_value is not None]
    if len(values) < 3:
        raise HTTPException(status_code=404, detail="Insufficient data for forecasting")

    avg_confidence = sum(r.confidence or 1.0 for r in rows) / len(rows)
    result = _engine.forecast_country_index(cc, values, dates, horizon, avg_confidence)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)


@router.get("/{country_code}/macro", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_macro(
    request: Request,
    country_code: str,
    indicator: str = Query(default="gdp_growth", description="gdp_growth or inflation"),
    horizon: int = Query(default=2, description="Forecast horizon in years (1 or 2)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast macro indicators (GDP growth, inflation). Costs 3 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/{country_code}/macro", cost_multiplier=3.0)

    if indicator not in VALID_INDICATORS:
        raise HTTPException(status_code=400, detail=f"indicator must be one of {sorted(VALID_INDICATORS)}")

    if horizon not in {1, 2}:
        raise HTTPException(status_code=400, detail="horizon must be 1 or 2 (years)")

    cc = country_code.upper()
    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    target_type = f"macro_{indicator}"
    cached = _get_cached_forecast(db, target_type, cc, horizon)
    if cached:
        return cached

    column = INDICATOR_COLUMNS[indicator]
    rows = (
        db.query(MacroIndicator)
        .filter(
            MacroIndicator.country_id == country.id,
            MacroIndicator.is_projection == False,
        )
        .order_by(MacroIndicator.year.asc())
        .all()
    )
    values = [getattr(r, column) for r in rows if getattr(r, column) is not None]
    years = [r.year for r in rows if getattr(r, column) is not None]
    if len(values) < 3:
        raise HTTPException(status_code=404, detail="Insufficient macro data for forecasting")

    confidence = rows[-1].confidence or 0.85 if rows else 0.85
    result = _engine.forecast_macro(cc, indicator, values, years, horizon, confidence)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)


@router.get("/stock/{exchange_code}", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_stock_market(
    request: Request,
    exchange_code: str,
    horizon: int = Query(default=6, description="Forecast horizon in months (3, 6, or 12)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast a West African stock exchange index (NGX/GSE/BRVM). Costs 3 credits."""
    deduct_credits(current_user, db, "/api/v3/forecast/stock", cost_multiplier=3.0)

    code = exchange_code.upper()
    if code not in VALID_EXCHANGES:
        raise HTTPException(status_code=400, detail=f"Invalid exchange. Valid: {sorted(VALID_EXCHANGES)}")
    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=400, detail=f"horizon must be one of {sorted(VALID_HORIZONS)}")

    cached = _get_cached_forecast(db, "stock_market", code, horizon)
    if cached:
        return cached

    try:
        from src.database.models import StockMarketData
        rows = (
            db.query(StockMarketData)
            .filter(StockMarketData.exchange_code == code)
            .order_by(StockMarketData.period_date.asc())
            .all()
        )
    except ImportError:
        raise HTTPException(status_code=404, detail="Stock market data not available")
    except Exception as exc:
        logger.error("Stock market query failed for %s: %s", code, exc)
        raise HTTPException(status_code=500, detail="Stock market data query failed")

    if len(rows) < 3:
        raise HTTPException(status_code=404, detail=f"Insufficient stock data for {code}")

    values = [r.index_value for r in rows if r.index_value is not None]
    dates = [r.period_date for r in rows if r.index_value is not None]
    if len(values) < 3:
        raise HTTPException(status_code=404, detail=f"Insufficient data for {code}")

    avg_conf = sum(r.confidence or 0.85 for r in rows) / len(rows)
    result = _engine.forecast_stock_market(code, values, dates, horizon, avg_conf)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)


@router.get("/ecfa/{country_code}/{aggregate}", response_model=ForecastResponse)
@limiter.limit("20/minute")
async def forecast_ecfa_monetary(
    request: Request,
    country_code: str,
    aggregate: str,
    horizon: int = Query(default=6, description="Forecast horizon in months (3, 6, or 12)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast eCFA monetary aggregate for a WAEMU country. Costs 3 credits.

    Aggregates: circulation, m0, m1, m2, velocity.
    """
    deduct_credits(current_user, db, "/api/v3/forecast/ecfa", cost_multiplier=3.0)

    agg = aggregate.lower()
    if agg not in VALID_ECFA_AGGREGATES:
        raise HTTPException(status_code=400, detail=f"Invalid aggregate. Valid: {sorted(VALID_ECFA_AGGREGATES)}")
    if horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=400, detail=f"horizon must be one of {sorted(VALID_HORIZONS)}")

    cc = country_code.upper()
    target_type = f"ecfa_{agg}"
    cached = _get_cached_forecast(db, target_type, cc, horizon)
    if cached:
        return cached

    AGGREGATE_COLUMN = {
        "circulation": "total_ecfa_circulation",
        "m0": "m0_base_money_ecfa",
        "m1": "m1_narrow_money_ecfa",
        "m2": "m2_broad_money_ecfa",
        "velocity": "velocity",
    }

    try:
        from src.database.cbdc_models import CbdcMonetaryAggregate
        rows = (
            db.query(CbdcMonetaryAggregate)
            .filter(CbdcMonetaryAggregate.country_code == cc)
            .order_by(CbdcMonetaryAggregate.snapshot_date.asc())
            .all()
        )
    except ImportError:
        raise HTTPException(status_code=404, detail="eCFA monetary data not available")
    except Exception as exc:
        logger.error("eCFA monetary query failed for %s/%s: %s", cc, agg, exc)
        raise HTTPException(status_code=500, detail="eCFA monetary data query failed")

    col = AGGREGATE_COLUMN[agg]
    values = [getattr(r, col) for r in rows if getattr(r, col, None) is not None]
    dates = [r.snapshot_date for r in rows if getattr(r, col, None) is not None]
    if len(values) < 3:
        raise HTTPException(status_code=404, detail=f"Insufficient eCFA data for {cc}/{agg}")

    result = _engine.forecast_ecfa_supply(cc, agg, values, dates, horizon, 0.90)
    _persist_forecast(db, result, horizon)
    db.commit()
    return _build_response(result)
