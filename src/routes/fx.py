"""
FX Analytics routes — /api/v3/fx/

ECOWAS currency market analytics: rates, volatility, trade costs, regime divergence.

  GET  /rates                        — 1 credit
  GET  /volatility                   — 3 credits
  GET  /dashboard                    — 5 credits
  GET  /regime-divergence            — 3 credits
  POST /refresh                      — 10 credits
  GET  /rates/{currency}             — 1 credit
  GET  /rates/{currency}/history     — 2 credits
  GET  /trade-cost/{from_cc}/{to_cc} — 3 credits
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.fx_analytics_engine import (
    FxAnalyticsEngine, REGIME_MAP, COUNTRY_CURRENCY, ALL_CURRENCIES,
)
from src.schemas.fx import (
    FxRateItem, FxRatesResponse, FxRateHistoryItem, FxRateHistoryResponse,
    FxCurrencyProfile, FxVolatilityItem, FxVolatilityResponse,
    TradeCostResponse, RegimeZoneStats, RegimeDivergenceResponse,
    FxDashboardCountry, FxDashboardResponse, FxRefreshResponse,
)

router = APIRouter(prefix="/api/v3/fx", tags=["FX Analytics"])
limiter = Limiter(key_func=get_remote_address)

VALID_CURRENCIES = set(ALL_CURRENCIES)
VALID_HISTORY_DAYS = {30, 90, 365}


# ── Static routes (before dynamic) ──────────────────────────────────────

@router.get("/rates", response_model=FxRatesResponse)
@limiter.limit("30/minute")
async def get_all_rates(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current FX rates for all ECOWAS currencies. 1 credit."""
    deduct_credits(current_user, db, "/api/v3/fx/rates", method="GET", cost_multiplier=1.0)
    engine = FxAnalyticsEngine(db)
    rates = engine.get_current_rates()
    return FxRatesResponse(
        as_of=datetime.now(timezone.utc),
        currencies=[FxRateItem(**r) for r in rates],
        count=len(rates),
    )


@router.get("/volatility", response_model=FxVolatilityResponse)
@limiter.limit("20/minute")
async def get_volatility_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Volatility dashboard for all ECOWAS currencies. 3 credits."""
    deduct_credits(current_user, db, "/api/v3/fx/volatility", method="GET", cost_multiplier=3.0)
    engine = FxAnalyticsEngine(db)

    items = []
    floating_vols = []
    pegged_vols = []

    for cc in ALL_CURRENCIES:
        vol = engine.compute_volatility(cc)
        items.append(FxVolatilityItem(**vol))
        ann = vol.get("annualized_vol")
        if ann is not None:
            if vol["regime"] == "PEGGED":
                pegged_vols.append(ann)
            elif vol["regime"] == "FLOATING":
                floating_vols.append(ann)

    db.commit()

    return FxVolatilityResponse(
        as_of=datetime.now(timezone.utc),
        currencies=items,
        avg_floating_vol=round(sum(floating_vols) / len(floating_vols), 6) if floating_vols else None,
        avg_pegged_vol=round(sum(pegged_vols) / len(pegged_vols), 6) if pegged_vols else None,
    )


@router.get("/dashboard", response_model=FxDashboardResponse)
@limiter.limit("10/minute")
async def get_fx_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """16-country ECOWAS FX analytics dashboard. 5 credits."""
    deduct_credits(current_user, db, "/api/v3/fx/dashboard", method="GET", cost_multiplier=5.0)
    engine = FxAnalyticsEngine(db)
    result = engine.get_ecowas_fx_dashboard()
    return FxDashboardResponse(
        as_of=datetime.now(timezone.utc),
        **result,
    )


@router.get("/regime-divergence", response_model=RegimeDivergenceResponse)
@limiter.limit("20/minute")
async def get_regime_divergence(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CFA zone vs floating currency regime comparison. 3 credits."""
    deduct_credits(current_user, db, "/api/v3/fx/regime-divergence", method="GET", cost_multiplier=3.0)
    engine = FxAnalyticsEngine(db)
    result = engine.get_regime_divergence()
    return RegimeDivergenceResponse(
        as_of=datetime.now(timezone.utc),
        cfa_zone=RegimeZoneStats(**result["cfa_zone"]),
        floating_zone=RegimeZoneStats(**result["floating_zone"]),
        special_zone=RegimeZoneStats(**result["special_zone"]),
        divergence_ratio=result["divergence_ratio"],
        interpretation=result["interpretation"],
    )


@router.post("/refresh", response_model=FxRefreshResponse)
@limiter.limit("5/minute")
async def refresh_fx_rates(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger FX rate refresh from live APIs. 10 credits."""
    deduct_credits(current_user, db, "/api/v3/fx/refresh", method="POST", cost_multiplier=10.0)

    from src.pipelines.scrapers.fx_scraper import run_fx_scraper
    result = run_fx_scraper(db=db)

    # Also recompute volatility
    engine = FxAnalyticsEngine(db)
    engine.recompute_all_volatility()
    db.commit()

    return FxRefreshResponse(
        status="completed",
        currencies_updated=result.get("updated", 0),
        errors=result.get("errors", 0),
        data_source=result.get("data_source", "unknown"),
        refreshed_at=datetime.now(timezone.utc),
    )


# ── Dynamic routes (after static) ───────────────────────────────────────

@router.get("/rates/{currency}", response_model=FxCurrencyProfile)
@limiter.limit("30/minute")
async def get_currency_profile(
    request: Request,
    currency: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Single currency deep profile. 1 credit."""
    cc = currency.upper()
    if cc not in VALID_CURRENCIES:
        raise HTTPException(400, f"Invalid currency '{currency}'. Valid: {sorted(VALID_CURRENCIES)}")

    deduct_credits(current_user, db, f"/api/v3/fx/rates/{cc}", method="GET", cost_multiplier=1.0)
    engine = FxAnalyticsEngine(db)
    result = engine.get_currency_profile(cc)
    if not result:
        raise HTTPException(404, f"No rate data available for {cc}")
    return FxCurrencyProfile(**result)


@router.get("/rates/{currency}/history", response_model=FxRateHistoryResponse)
@limiter.limit("20/minute")
async def get_rate_history(
    request: Request,
    currency: str,
    days: int = Query(30, description="History window in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historical rate data for a currency. 2 credits."""
    cc = currency.upper()
    if cc not in VALID_CURRENCIES:
        raise HTTPException(400, f"Invalid currency '{currency}'. Valid: {sorted(VALID_CURRENCIES)}")
    if days not in VALID_HISTORY_DAYS:
        raise HTTPException(400, f"Invalid days '{days}'. Valid: {sorted(VALID_HISTORY_DAYS)}")

    deduct_credits(current_user, db, f"/api/v3/fx/rates/{cc}/history", method="GET", cost_multiplier=2.0)
    engine = FxAnalyticsEngine(db)
    history = engine.get_rate_history(cc, days)
    return FxRateHistoryResponse(
        currency_code=cc,
        regime=REGIME_MAP.get(cc, "FLOATING"),
        days=days,
        history=[FxRateHistoryItem(**h) for h in history],
    )


@router.get("/trade-cost/{from_cc}/{to_cc}", response_model=TradeCostResponse)
@limiter.limit("20/minute")
async def get_trade_cost(
    request: Request,
    from_cc: str,
    to_cc: str,
    amount: float = Query(100_000.0, ge=1.0, le=1_000_000_000.0,
                          description="Trade amount in USD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """FX cost analysis for bilateral trade between ECOWAS countries. 3 credits."""
    from_cc = from_cc.upper()
    to_cc = to_cc.upper()
    valid_countries = set(COUNTRY_CURRENCY.keys())

    if from_cc not in valid_countries:
        raise HTTPException(400, f"Invalid country '{from_cc}'. Valid: {sorted(valid_countries)}")
    if to_cc not in valid_countries:
        raise HTTPException(400, f"Invalid country '{to_cc}'. Valid: {sorted(valid_countries)}")

    deduct_credits(current_user, db, f"/api/v3/fx/trade-cost/{from_cc}/{to_cc}", method="GET", cost_multiplier=3.0)
    engine = FxAnalyticsEngine(db)
    result = engine.compute_trade_cost(from_cc, to_cc, amount)
    return TradeCostResponse(**result)
