"""
Forecast v4 routes — /api/v4/forecast/

Enhanced forecasting with adaptive ensemble, multivariate cross-correlation,
Monte Carlo fan charts, backtesting, scenario analysis, and model zoo.

v3 endpoints remain unchanged; v4 adds richer diagnostics.
"""
import json
import logging
import math
import uuid
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
    CommodityPrice, MacroIndicator, StockMarketData,
)
from src.database.forecast_models import ForecastResult
from src.database.forecast_v2_models import (
    ForecastModel, BacktestResult, ForecastScenario, ForecastAccuracyLog,
)
from src.engines.forecast_v2 import ForecastEngineV2
from src.schemas.forecast_v2 import (
    ForecastV4Response, ForecastV4Period, DataProfile, RegimeInfo,
    MultivariateAdjustment, FanChartBand,
    ScenarioRequest, ScenarioResponse,
    BacktestResponse, BacktestMethodResult,
    ModelZooResponse, ModelZooEntry,
    AccuracyResponse,
    VARResponse, VARCountryForecast,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v4/forecast", tags=["Forecast v4"])
limiter = Limiter(key_func=get_remote_address)

_engine = ForecastEngineV2()

VALID_HORIZONS = {1, 3, 6, 12, 24}
VALID_COMMODITIES = {"COCOA", "BRENT", "GOLD", "COTTON", "COFFEE", "IRON_ORE"}
COMMODITY_CODES = list(VALID_COMMODITIES)


# ── Helpers ──────────────────────────────────────────────────────

def _sanitize_numpy(obj):
    """Recursively convert numpy types to Python native types for Pydantic."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _sanitize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_numpy(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def _build_v4_response(result: dict) -> ForecastV4Response:
    result = _sanitize_numpy(result)
    """Convert engine result dict into ForecastV4Response."""
    periods = []
    for p in result.get("periods", []):
        periods.append(ForecastV4Period(**p))

    # Build data profile
    dp = result.get("data_profile")
    data_profile = DataProfile(**dp) if dp and isinstance(dp, dict) and "n" in dp else None

    # Build regime info
    ri = result.get("regime_info")
    regime_info = RegimeInfo(**ri) if ri and isinstance(ri, dict) else None

    # Build multivariate adjustment
    ma = result.get("multivariate_adjustment")
    multivariate = MultivariateAdjustment(**ma) if ma and isinstance(ma, dict) else None

    # Build fan chart
    fc_data = result.get("fan_chart")
    fan_chart = [FanChartBand(**b) for b in fc_data] if fc_data else None

    return ForecastV4Response(
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
        engine_version=result.get("engine_version", "2.0"),
        data_profile=data_profile,
        regime_info=regime_info,
        multivariate_adjustment=multivariate,
        fan_chart=fan_chart,
        backtesting_summary=result.get("backtesting_summary"),
        method_params=result.get("method_params"),
    )


def _load_commodity_data(db: Session) -> dict:
    """Load commodity data for multivariate forecasting."""
    import numpy as np
    cache = {}
    for code in COMMODITY_CODES:
        rows = (
            db.query(CommodityPrice)
            .filter(CommodityPrice.commodity_code == code)
            .order_by(CommodityPrice.period_date.asc())
            .all()
        )
        if len(rows) >= 3:
            values = np.array([r.price_usd for r in rows if r.price_usd is not None])
            if len(values) >= 3:
                fc_result = _engine.forecast_ensemble(list(values), 12)
                fc_values = np.array([p["forecast_value"] for p in fc_result.get("periods", [])])
                cache[code] = {"values": values, "forecast": fc_values}
    return cache


def _load_stock_data(db: Session) -> dict:
    """Load stock market data for multivariate forecasting."""
    import numpy as np
    cache = {}
    for exchange in ["NGX", "GSE", "BRVM"]:
        rows = (
            db.query(StockMarketData)
            .filter(StockMarketData.exchange_code == exchange)
            .order_by(StockMarketData.trade_date.asc())
            .all()
        )
        if len(rows) >= 3:
            values = np.array([r.index_value for r in rows if r.index_value is not None])
            if len(values) >= 3:
                fc_result = _engine.forecast_ensemble(list(values), 12)
                fc_values = np.array([p["forecast_value"] for p in fc_result.get("periods", [])])
                cache[exchange] = {"values": values, "forecast": fc_values}
    return cache


# ── 1. Composite Forecast ────────────────────────────────────────

@router.get("/composite", response_model=ForecastV4Response)
@limiter.limit("20/minute")
async def forecast_composite_v4(
    request: Request,
    horizon: int = Query(6, description="Forecast horizon in months"),
    include_backtesting: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast WASI composite index with fan chart and diagnostics. 5 credits."""
    if horizon not in VALID_HORIZONS:
        raise HTTPException(400, f"Invalid horizon. Use: {sorted(VALID_HORIZONS)}")
    deduct_credits(current_user, db, "/api/v4/forecast/composite", cost_multiplier=5.0)

    composites = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )
    if len(composites) < 3:
        raise HTTPException(404, "Insufficient composite history for forecasting")

    values = [r.composite_value for r in composites]
    dates = [r.period_date for r in composites]

    result = _engine.forecast_composite(
        values, dates, horizon,
    )
    result["include_backtesting"] = include_backtesting
    return _build_v4_response(result)


# ── 2. Country Index Forecast ────────────────────────────────────

@router.get("/{country_code}/index", response_model=ForecastV4Response)
@limiter.limit("30/minute")
async def forecast_country_index_v4(
    request: Request,
    country_code: str,
    horizon: int = Query(6),
    include_multivariate: bool = Query(True),
    include_backtesting: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecast country WASI index with multivariate cross-correlations. 3 credits."""
    if horizon not in VALID_HORIZONS:
        raise HTTPException(400, f"Invalid horizon. Use: {sorted(VALID_HORIZONS)}")
    deduct_credits(current_user, db, f"/api/v4/forecast/{country_code}/index", cost_multiplier=3.0)

    country = db.query(Country).filter(
        Country.code == country_code.upper(), Country.is_active == True,
    ).first()
    if not country:
        raise HTTPException(404, f"Country {country_code} not found or inactive")

    rows = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.asc())
        .all()
    )
    if len(rows) < 3:
        raise HTTPException(404, "Insufficient data for country forecast")

    values = [r.index_value for r in rows if r.index_value is not None]
    dates = [r.period_date for r in rows if r.index_value is not None]
    avg_confidence = sum(r.confidence or 1.0 for r in rows) / len(rows)

    commodity_data = _load_commodity_data(db) if include_multivariate else None
    stock_data = _load_stock_data(db) if include_multivariate else None

    result = _engine.forecast_country_index(
        country.code, values, dates, horizon, avg_confidence,
        commodity_data=commodity_data,
        stock_data=stock_data,
    )
    return _build_v4_response(result)


# ── 3. Backtesting Results ───────────────────────────────────────

@router.get("/backtest/{target_type}/{target_code}", response_model=BacktestResponse)
@limiter.limit("10/minute")
async def get_backtest_results(
    request: Request,
    target_type: str,
    target_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cached backtesting results for a target. 5 credits."""
    deduct_credits(current_user, db, f"/api/v4/forecast/backtest/{target_type}/{target_code}", cost_multiplier=5.0)

    rows = (
        db.query(BacktestResult)
        .filter(
            BacktestResult.target_type == target_type,
            BacktestResult.target_code == target_code,
        )
        .order_by(BacktestResult.avg_rmse.asc())
        .all()
    )

    methods = []
    for r in rows:
        methods.append(BacktestMethodResult(
            method=r.method_name,
            n_splits=r.n_splits,
            window_type=r.window_type,
            avg_rmse=r.avg_rmse,
            avg_mae=r.avg_mae,
            avg_mape=r.avg_mape,
            avg_directional_accuracy=r.avg_directional_accuracy,
            avg_coverage_68=r.avg_coverage_68,
            avg_coverage_95=r.avg_coverage_95,
        ))

    best = rows[0].method_name if rows else None
    return BacktestResponse(
        target_type=target_type,
        target_code=target_code,
        methods=methods,
        best_method=best,
        computed_at=rows[0].computed_at if rows else None,
    )


# ── 4. On-demand Backtesting ─────────────────────────────────────

@router.post("/backtest/{target_type}/{target_code}/run", response_model=BacktestResponse)
@limiter.limit("5/minute")
async def run_backtest(
    request: Request,
    target_type: str,
    target_code: str,
    window_type: str = Query("expanding"),
    min_train_size: int = Query(12),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger on-demand backtesting. 10 credits."""
    deduct_credits(current_user, db, f"/api/v4/forecast/backtest/{target_type}/{target_code}/run", cost_multiplier=10.0)

    values = _load_target_values(db, target_type, target_code)
    if values is None or len(values) < min_train_size + 3:
        raise HTTPException(404, "Insufficient data for backtesting")

    import numpy as np
    arr = np.array(values, dtype=float)

    # Build method functions
    method_fns = {}
    for name in ["linear", "ses", "holt", "damped_holt", "theta"]:
        fn = _engine.methods.get_method(name)
        if fn and len(arr) >= _engine.methods.MIN_POINTS.get(name, 3):
            method_fns[name] = fn

    if not method_fns:
        raise HTTPException(400, "No applicable methods for this data")

    bt_result = _engine.backtester.run_all_methods_backtest(
        arr, method_fns,
        min_train_size=min_train_size,
        test_horizon=min(6, len(arr) // 4),
        window_type=window_type,
    )

    # Persist results
    for method_result in bt_result.get("methods", []):
        backtest_id = str(uuid.uuid4())
        existing = (
            db.query(BacktestResult)
            .filter(
                BacktestResult.target_type == target_type,
                BacktestResult.target_code == target_code,
                BacktestResult.method_name == method_result["method"],
            )
            .first()
        )
        if existing:
            existing.avg_rmse = method_result.get("avg_rmse")
            existing.avg_mae = method_result.get("avg_mae")
            existing.avg_mape = method_result.get("avg_mape")
            existing.avg_directional_accuracy = method_result.get("avg_directional_accuracy")
            existing.avg_coverage_68 = method_result.get("avg_coverage_68")
            existing.avg_coverage_95 = method_result.get("avg_coverage_95")
            existing.n_splits = method_result.get("n_splits", 0)
            existing.computed_at = datetime.now(timezone.utc)
        else:
            db.add(BacktestResult(
                backtest_id=backtest_id,
                target_type=target_type,
                target_code=target_code,
                method_name=method_result["method"],
                window_type=window_type,
                min_train_size=min_train_size,
                test_horizon=method_result.get("test_horizon", 6),
                n_splits=method_result.get("n_splits", 0),
                avg_rmse=method_result.get("avg_rmse"),
                avg_mae=method_result.get("avg_mae"),
                avg_mape=method_result.get("avg_mape"),
                avg_directional_accuracy=method_result.get("avg_directional_accuracy"),
                avg_coverage_68=method_result.get("avg_coverage_68"),
                avg_coverage_95=method_result.get("avg_coverage_95"),
                split_details=json.dumps(method_result.get("split_details", [])),
            ))
    db.commit()

    methods = [
        BacktestMethodResult(
            method=m["method"],
            n_splits=m.get("n_splits", 0),
            window_type=window_type,
            avg_rmse=m.get("avg_rmse"),
            avg_mae=m.get("avg_mae"),
            avg_mape=m.get("avg_mape"),
            avg_directional_accuracy=m.get("avg_directional_accuracy"),
            avg_coverage_68=m.get("avg_coverage_68"),
            avg_coverage_95=m.get("avg_coverage_95"),
        )
        for m in bt_result.get("methods", [])
    ]

    return BacktestResponse(
        target_type=target_type,
        target_code=target_code,
        methods=methods,
        best_method=bt_result.get("best_method"),
        ranking=bt_result.get("ranking", []),
        computed_at=datetime.now(timezone.utc),
    )


# ── 5. Scenario Analysis ─────────────────────────────────────────

@router.post("/scenario", response_model=ScenarioResponse)
@limiter.limit("10/minute")
async def run_scenario(
    request: Request,
    body: ScenarioRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run what-if scenario analysis. 10 credits."""
    deduct_credits(current_user, db, "/api/v4/forecast/scenario", cost_multiplier=10.0)

    # Get baseline forecast for composite
    composites = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.asc())
        .all()
    )
    if len(composites) < 3:
        raise HTTPException(404, "Insufficient data for scenario analysis")

    values = [r.composite_value for r in composites]
    dates = [r.period_date for r in composites]

    baseline = _engine.forecast_composite(values, dates, body.horizon_months)
    baseline_periods = baseline.get("periods", [])

    scenario_result = _engine.scenarios.run_scenario(
        baseline_periods,
        body.scenario_type,
        target_code=body.target_code,
        custom_shocks=body.custom_shocks,
        horizon_months=body.horizon_months,
    )

    # Persist scenario
    db.add(ForecastScenario(
        scenario_id=scenario_result["scenario_id"],
        user_id=current_user.id,
        scenario_name=scenario_result["scenario_name"],
        scenario_type=body.scenario_type,
        target_type="composite_index",
        target_code=body.target_code or "WASI_COMPOSITE",
        shocks=json.dumps(body.custom_shocks or {}),
        baseline_forecast=json.dumps(scenario_result["baseline_periods"]),
        scenario_forecast=json.dumps(scenario_result["scenario_periods"]),
        impact_delta=json.dumps(scenario_result["impact_delta"]),
        horizon_months=body.horizon_months,
    ))
    db.commit()

    return ScenarioResponse(**scenario_result)


# ── 6. Model Zoo ─────────────────────────────────────────────────

@router.get("/model-zoo", response_model=ModelZooResponse)
@limiter.limit("20/minute")
async def get_model_zoo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all fitted forecast models with performance metrics. 2 credits."""
    deduct_credits(current_user, db, "/api/v4/forecast/model-zoo", cost_multiplier=2.0)

    models = db.query(ForecastModel).filter(ForecastModel.is_active == True).all()

    entries = []
    method_weights = {}
    for m in models:
        target = f"{m.target_type}:{m.target_code}"
        entries.append(ModelZooEntry(
            method=m.method_name,
            target=target,
            weight=m.ensemble_weight or 0.0,
            data_points=m.data_points_used,
            trend_strength=m.trend_strength,
            seasonality_strength=m.seasonality_strength,
            rmse=m.rmse,
            fitted_at=m.fitted_at,
        ))
        method_weights.setdefault(m.method_name, []).append(m.ensemble_weight or 0.0)

    # Find best overall method by average weight
    best_method = None
    if method_weights:
        avg_weights = {m: sum(w) / len(w) for m, w in method_weights.items()}
        best_method = max(avg_weights, key=avg_weights.get)

    return ModelZooResponse(
        models=entries,
        total_models=len(entries),
        best_overall_method=best_method,
    )


# ── 7. Explain Forecast ──────────────────────────────────────────

@router.get("/explain/{target_type}/{target_code}")
@limiter.limit("10/minute")
async def explain_forecast(
    request: Request,
    target_type: str,
    target_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Feature importance / attribution for multivariate forecast. 5 credits."""
    deduct_credits(current_user, db, f"/api/v4/forecast/explain/{target_type}/{target_code}", cost_multiplier=5.0)

    import numpy as np

    if target_type != "country_index":
        raise HTTPException(400, "Explain is only available for country_index targets")

    country = db.query(Country).filter(
        Country.code == target_code.upper(), Country.is_active == True,
    ).first()
    if not country:
        raise HTTPException(404, f"Country {target_code} not found")

    rows = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.asc())
        .all()
    )
    if len(rows) < 6:
        raise HTTPException(404, "Insufficient data for feature importance analysis")

    values = np.array([r.index_value for r in rows if r.index_value is not None])
    n = len(values)

    # Build exogenous features
    exogenous = {}
    indicators = _engine.cross_corr.get_country_indicators(target_code.upper())
    for ind in indicators:
        if ind["type"] == "commodity":
            commodity_rows = (
                db.query(CommodityPrice)
                .filter(CommodityPrice.commodity_code == ind["code"])
                .order_by(CommodityPrice.period_date.asc())
                .limit(n)
                .all()
            )
            if len(commodity_rows) >= n:
                exogenous[ind["code"]] = np.array([
                    r.price_usd for r in commodity_rows[:n]
                ])

    importance = _engine.diagnostics.compute_feature_importance(values, exogenous)

    # Cross-correlations
    cross_correlations = {}
    for ind in indicators:
        if ind["code"] in exogenous:
            cc = _engine.cross_corr.compute_cross_correlation(
                exogenous[ind["code"]], values, max_lag=6,
            )
            cross_correlations[ind["code"]] = {
                "lag": cc["optimal_lag"],
                "correlation": cc["optimal_correlation"],
            }

    return {
        "target": f"{target_type}:{target_code}",
        "feature_importance": importance,
        "cross_correlations": cross_correlations,
        "data_points": n,
    }


# ── 8. Accuracy Report ───────────────────────────────────────────

@router.get("/accuracy", response_model=AccuracyResponse)
@limiter.limit("20/minute")
async def get_forecast_accuracy(
    request: Request,
    target_type: Optional[str] = Query(None),
    target_code: Optional[str] = Query(None),
    horizon_months: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historical forecast accuracy metrics. 3 credits."""
    deduct_credits(current_user, db, "/api/v4/forecast/accuracy", cost_multiplier=3.0)

    query = db.query(ForecastAccuracyLog)
    if target_type:
        query = query.filter(ForecastAccuracyLog.target_type == target_type)
    if target_code:
        query = query.filter(ForecastAccuracyLog.target_code == target_code)
    if horizon_months:
        query = query.filter(ForecastAccuracyLog.horizon_months == horizon_months)

    logs = query.all()
    if not logs:
        return AccuracyResponse(
            target_type=target_type,
            target_code=target_code,
            sample_size=0,
        )

    errors = [l.error for l in logs if l.error is not None]
    abs_errors = [l.abs_error for l in logs if l.abs_error is not None]
    pct_errors = [l.pct_error for l in logs if l.pct_error is not None]
    within_1s = sum(1 for l in logs if l.within_1sigma)
    within_2s = sum(1 for l in logs if l.within_2sigma)
    total = len(logs)

    rmse = math.sqrt(sum(e ** 2 for e in errors) / len(errors)) if errors else None
    mae = sum(abs_errors) / len(abs_errors) if abs_errors else None
    mape = sum(abs(p) for p in pct_errors) / len(pct_errors) if pct_errors else None

    # By horizon
    by_horizon = {}
    horizon_groups = {}
    for l in logs:
        h = l.horizon_months
        if h not in horizon_groups:
            horizon_groups[h] = []
        horizon_groups[h].append(l)

    for h, group in sorted(horizon_groups.items()):
        h_errors = [l.error for l in group if l.error is not None]
        if h_errors:
            by_horizon[str(h)] = {
                "rmse": round(math.sqrt(sum(e ** 2 for e in h_errors) / len(h_errors)), 4),
                "samples": len(h_errors),
            }

    return AccuracyResponse(
        target_type=target_type,
        target_code=target_code,
        overall_rmse=round(rmse, 4) if rmse else None,
        overall_mae=round(mae, 4) if mae else None,
        overall_mape=round(mape, 4) if mape else None,
        band_coverage_68=round(within_1s / total, 4) if total > 0 else None,
        band_coverage_95=round(within_2s / total, 4) if total > 0 else None,
        by_horizon=by_horizon,
        sample_size=total,
    )


# ── 9. VAR Big 4 ─────────────────────────────────────────────────

@router.get("/var/big4", response_model=VARResponse)
@limiter.limit("10/minute")
async def get_var_forecast(
    request: Request,
    horizon: int = Query(6),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """VAR(1) joint forecast for NG/CI/GH/SN (Big 4 = 75% of WASI). 10 credits."""
    deduct_credits(current_user, db, "/api/v4/forecast/var/big4", cost_multiplier=10.0)

    country_data = {}
    for cc in ["NG", "CI", "GH", "SN"]:
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            raise HTTPException(404, f"Country {cc} not found")

        rows = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.asc())
            .all()
        )
        values = [r.index_value for r in rows if r.index_value is not None]
        if len(values) < 4:
            raise HTTPException(404, f"Insufficient data for {cc}")
        country_data[cc] = values

    result = _engine.forecast_var_big4(country_data, horizon)
    if result is None:
        raise HTTPException(500, "VAR model fitting failed")

    countries = [
        VARCountryForecast(
            country_code=cc,
            last_value=result[cc]["last_value"],
            forecast=result[cc]["forecast"],
        )
        for cc in ["NG", "CI", "GH", "SN"]
        if cc in result
    ]

    return VARResponse(countries=countries, horizon=horizon)


# ── Scenario Presets ──────────────────────────────────────────────

@router.get("/scenario/presets")
@limiter.limit("30/minute")
async def list_scenario_presets(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """List available preset scenarios (no credit cost)."""
    return _engine.scenarios.list_presets()


# ── Helper: load target values ────────────────────────────────────

def _load_target_values(db: Session, target_type: str, target_code: str):
    """Load historical values for any target type."""
    if target_type == "country_index":
        country = db.query(Country).filter(Country.code == target_code.upper()).first()
        if not country:
            return None
        rows = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.asc())
            .all()
        )
        return [r.index_value for r in rows if r.index_value is not None]

    elif target_type == "composite_index":
        rows = (
            db.query(WASIComposite)
            .order_by(WASIComposite.period_date.asc())
            .all()
        )
        return [r.composite_value for r in rows]

    elif target_type == "commodity_price":
        rows = (
            db.query(CommodityPrice)
            .filter(CommodityPrice.commodity_code == target_code.upper())
            .order_by(CommodityPrice.period_date.asc())
            .all()
        )
        return [r.price_usd for r in rows if r.price_usd is not None]

    return None
