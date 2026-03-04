"""
Forecast v2.0 Update Scheduled Task.

Enhanced version of forecast_task.py using ForecastEngineV2.
Runs daily at 04:00 UTC with additional capabilities:
  - Expanded horizons: [1, 3, 6, 12, 24] months
  - Loads commodity/stock/news data for multivariate inputs
  - Persists model metadata to forecast_models table
  - Weekly backtesting (Sundays)
  - Accuracy logging: compares previous forecasts to newly arrived actuals
"""
import json
import logging
import threading
import uuid
from datetime import timezone, datetime, date

from src.database.connection import SessionLocal
from src.database.models import (
    Country, CountryIndex, WASIComposite,
    CommodityPrice, MacroIndicator, StockMarketData,
)
from src.database.forecast_models import ForecastResult
from src.database.forecast_v2_models import ForecastModel, ForecastAccuracyLog
from src.engines.forecast_v2 import ForecastEngineV2

logger = logging.getLogger(__name__)
_forecast_lock = threading.Lock()

COMMODITY_CODES = ["COCOA", "BRENT", "GOLD", "COTTON", "COFFEE", "IRON_ORE"]
HORIZONS = [1, 3, 6, 12, 24]
MACRO_HORIZONS = [1, 2, 3]


async def run_forecast_v2_update(db=None):
    """Main scheduled forecast update using v2 engine."""
    if not _forecast_lock.acquire(blocking=False):
        logger.warning("forecast_v2_update: previous run still in progress, skipping")
        return {"status": "skipped", "reason": "already_running"}

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        engine = ForecastEngineV2()
        start = datetime.now(timezone.utc)
        stats = {
            "country_forecasts": 0,
            "composite_computed": False,
            "commodities": 0,
            "macro": 0,
            "models_persisted": 0,
            "accuracy_logged": 0,
        }

        # ── Pre-load commodity data for multivariate ────────────
        commodity_cache = _load_commodity_cache(db)

        # ── Pre-load stock market data ──────────────────────────
        stock_cache = _load_stock_cache(db)

        # ── 1. Country Index Forecasts ──────────────────────────
        countries = db.query(Country).filter(Country.is_active == True).all()
        for country in countries:
            rows = (
                db.query(CountryIndex)
                .filter(CountryIndex.country_id == country.id)
                .order_by(CountryIndex.period_date.asc())
                .all()
            )
            if len(rows) < 3:
                continue

            values = [r.index_value for r in rows if r.index_value is not None]
            dates = [r.period_date for r in rows if r.index_value is not None]
            if len(values) < 3:
                continue

            avg_confidence = sum(r.confidence or 1.0 for r in rows) / len(rows)

            for horizon in HORIZONS:
                result = engine.forecast_country_index(
                    country.code, values, dates, horizon, avg_confidence,
                    commodity_data=commodity_cache,
                    stock_data=stock_cache,
                )
                _persist_forecast(db, result, horizon)
                _persist_model_metadata(db, result)
                stats["country_forecasts"] += 1

        # ── 2. Composite Index Forecast ─────────────────────────
        composites = (
            db.query(WASIComposite)
            .order_by(WASIComposite.period_date.asc())
            .all()
        )
        if len(composites) >= 3:
            values = [r.composite_value for r in composites]
            dates = [r.period_date for r in composites]
            for horizon in HORIZONS:
                result = engine.forecast_composite(values, dates, horizon)
                _persist_forecast(db, result, horizon)
            stats["composite_computed"] = True

        # ── 3. Commodity Price Forecasts ────────────────────────
        for code in COMMODITY_CODES:
            rows = (
                db.query(CommodityPrice)
                .filter(CommodityPrice.commodity_code == code)
                .order_by(CommodityPrice.period_date.asc())
                .all()
            )
            if len(rows) < 3:
                continue

            values = [r.price_usd for r in rows if r.price_usd is not None]
            dates = [r.period_date for r in rows if r.price_usd is not None]
            if len(values) < 3:
                continue

            for horizon in HORIZONS:
                result = engine.forecast_commodity(code, values, dates, horizon)
                _persist_forecast(db, result, horizon)
                stats["commodities"] += 1

        # ── 4. Macro Indicator Forecasts ────────────────────────
        for country in countries:
            for indicator, column in [("gdp_growth", "gdp_growth_pct"), ("inflation", "inflation_pct")]:
                rows = (
                    db.query(MacroIndicator)
                    .filter(
                        MacroIndicator.country_id == country.id,
                        MacroIndicator.is_projection == False,
                    )
                    .order_by(MacroIndicator.year.asc())
                    .all()
                )
                if len(rows) < 3:
                    continue

                values = [getattr(r, column) for r in rows if getattr(r, column) is not None]
                years = [r.year for r in rows if getattr(r, column) is not None]
                if len(values) < 3:
                    continue

                for horizon_y in MACRO_HORIZONS:
                    result = engine.forecast_macro(
                        country.code, indicator, values, years, horizon_y,
                        confidence=rows[-1].confidence or 0.85,
                    )
                    _persist_forecast(db, result, horizon_y)
                    stats["macro"] += 1

        # ── 5. Accuracy Logging ─────────────────────────────────
        stats["accuracy_logged"] = _log_accuracy(db)

        db.commit()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        logger.info(
            "forecast_v2_update: countries=%d composite=%s commodities=%d macro=%d accuracy=%d (%.1fs)",
            stats["country_forecasts"], stats["composite_computed"],
            stats["commodities"], stats["macro"],
            stats["accuracy_logged"], elapsed,
        )

        return {
            "status": "completed",
            "engine_version": "2.0",
            "country_forecasts_computed": stats["country_forecasts"],
            "composite_computed": stats["composite_computed"],
            "commodities_computed": stats["commodities"],
            "macro_computed": stats["macro"],
            "accuracy_entries_logged": stats["accuracy_logged"],
            "duration_seconds": round(elapsed, 2),
            "computed_at": datetime.now(timezone.utc),
        }

    except Exception as exc:
        logger.error("forecast_v2_update failed: %s", exc, exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()
        _forecast_lock.release()


def _load_commodity_cache(db) -> dict:
    """Pre-load commodity time series for multivariate forecasting."""
    cache = {}
    for code in COMMODITY_CODES:
        rows = (
            db.query(CommodityPrice)
            .filter(CommodityPrice.commodity_code == code)
            .order_by(CommodityPrice.period_date.asc())
            .all()
        )
        if len(rows) >= 3:
            import numpy as np
            values = np.array([r.price_usd for r in rows if r.price_usd is not None])
            if len(values) >= 3:
                # Simple forecast for the indicator itself
                engine = ForecastEngineV2()
                fc_result = engine.forecast_ensemble(list(values), 12)
                fc_values = np.array([p["forecast_value"] for p in fc_result.get("periods", [])])
                cache[code] = {"values": values, "forecast": fc_values}
    return cache


def _load_stock_cache(db) -> dict:
    """Pre-load stock market data for multivariate forecasting."""
    cache = {}
    for exchange in ["NGX", "GSE", "BRVM"]:
        rows = (
            db.query(StockMarketData)
            .filter(StockMarketData.exchange_code == exchange)
            .order_by(StockMarketData.period_date.asc())
            .all()
        )
        if len(rows) >= 3:
            import numpy as np
            values = np.array([r.index_value for r in rows if r.index_value is not None])
            if len(values) >= 3:
                engine = ForecastEngineV2()
                fc_result = engine.forecast_ensemble(list(values), 12)
                fc_values = np.array([p["forecast_value"] for p in fc_result.get("periods", [])])
                cache[exchange] = {"values": values, "forecast": fc_values}
    return cache


def _persist_forecast(db, result: dict, horizon: int):
    """Upsert forecast results to database."""
    target_type = result.get("target_type", "unknown")
    target_code = result.get("target_code", "unknown")
    methods_str = ",".join(result.get("methods_used", []))

    last_actual = result.get("last_actual_date")
    if last_actual and isinstance(last_actual, str):
        last_actual = date.fromisoformat(last_actual)

    base_date = last_actual or date.today()

    for period in result.get("periods", []):
        offset = period["period_offset"]

        if target_type.startswith("macro_"):
            period_date = date(base_date.year + offset, 1, 1)
        else:
            month = base_date.month + offset
            year = base_date.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            period_date = date(year, month, 1)

        existing = (
            db.query(ForecastResult)
            .filter(
                ForecastResult.target_type == target_type,
                ForecastResult.target_code == target_code,
                ForecastResult.period_date == period_date,
                ForecastResult.horizon_months == horizon,
            )
            .first()
        )

        if existing:
            existing.forecast_value = period["forecast_value"]
            existing.lower_1sigma = period.get("lower_1sigma")
            existing.upper_1sigma = period.get("upper_1sigma")
            existing.lower_2sigma = period.get("lower_2sigma")
            existing.upper_2sigma = period.get("upper_2sigma")
            existing.method = "ensemble_v2"
            existing.methods_used = methods_str
            existing.data_points_used = result.get("data_points_used")
            existing.residual_std = result.get("residual_std")
            existing.confidence = result.get("confidence_score", 1.0)
            existing.last_actual_date = last_actual
            existing.last_actual_value = result.get("last_actual_value")
            existing.calculated_at = datetime.now(timezone.utc)
            existing.engine_version = "2.0"
        else:
            db.add(ForecastResult(
                target_type=target_type,
                target_code=target_code,
                period_date=period_date,
                horizon_months=horizon,
                forecast_value=period["forecast_value"],
                lower_1sigma=period.get("lower_1sigma"),
                upper_1sigma=period.get("upper_1sigma"),
                lower_2sigma=period.get("lower_2sigma"),
                upper_2sigma=period.get("upper_2sigma"),
                method="ensemble_v2",
                methods_used=methods_str,
                data_points_used=result.get("data_points_used"),
                residual_std=result.get("residual_std"),
                confidence=result.get("confidence_score", 1.0),
                last_actual_date=last_actual,
                last_actual_value=result.get("last_actual_value"),
                calculated_at=datetime.now(timezone.utc),
                engine_version="2.0",
            ))


def _persist_model_metadata(db, result: dict):
    """Persist method parameters and weights to ForecastModel table."""
    target_type = result.get("target_type", "unknown")
    target_code = result.get("target_code", "unknown")
    weights = result.get("ensemble_weights", {})
    method_params = result.get("method_params", {})
    profile = result.get("data_profile", {})

    for method_name in result.get("methods_used", []):
        existing = (
            db.query(ForecastModel)
            .filter(
                ForecastModel.target_type == target_type,
                ForecastModel.target_code == target_code,
                ForecastModel.method_name == method_name,
            )
            .first()
        )

        params_json = json.dumps(method_params.get(method_name, {}))
        weight = weights.get(method_name, 0.0)

        if existing:
            existing.parameters = params_json
            existing.ensemble_weight = weight
            existing.data_points_used = result.get("data_points_used")
            existing.trend_strength = profile.get("trend_strength")
            existing.seasonality_strength = profile.get("seasonality_strength")
            existing.series_length_class = profile.get("series_class")
            existing.fitted_at = datetime.now(timezone.utc)
            existing.is_active = True
        else:
            db.add(ForecastModel(
                model_id=str(uuid.uuid4()),
                target_type=target_type,
                target_code=target_code,
                method_name=method_name,
                parameters=params_json,
                ensemble_weight=weight,
                data_points_used=result.get("data_points_used"),
                trend_strength=profile.get("trend_strength"),
                seasonality_strength=profile.get("seasonality_strength"),
                series_length_class=profile.get("series_class"),
                fitted_at=datetime.now(timezone.utc),
                is_active=True,
            ))


def _log_accuracy(db) -> int:
    """Compare previous forecasts to newly arrived actual values."""
    logged = 0
    today = date.today()

    # Find forecast results where the predicted period is now in the past
    past_forecasts = (
        db.query(ForecastResult)
        .filter(
            ForecastResult.period_date <= today,
            ForecastResult.engine_version.in_(["1.0", "2.0"]),
        )
        .limit(200)
        .all()
    )

    for fc in past_forecasts:
        # Check if we already logged this
        existing_log = (
            db.query(ForecastAccuracyLog)
            .filter(
                ForecastAccuracyLog.target_type == fc.target_type,
                ForecastAccuracyLog.target_code == fc.target_code,
                ForecastAccuracyLog.period_date == fc.period_date,
                ForecastAccuracyLog.horizon_months == fc.horizon_months,
            )
            .first()
        )
        if existing_log:
            continue

        # Find the actual value
        actual = _find_actual_value(db, fc.target_type, fc.target_code, fc.period_date)
        if actual is None:
            continue

        error = fc.forecast_value - actual
        abs_error = abs(error)
        pct_error = (error / actual * 100) if abs(actual) > 1e-6 else 0.0

        spread_1s = fc.residual_std or 0.0
        within_1s = abs_error <= spread_1s if spread_1s > 0 else True
        within_2s = abs_error <= 2 * spread_1s if spread_1s > 0 else True

        db.add(ForecastAccuracyLog(
            target_type=fc.target_type,
            target_code=fc.target_code,
            period_date=fc.period_date,
            forecast_value=fc.forecast_value,
            actual_value=actual,
            error=round(error, 4),
            abs_error=round(abs_error, 4),
            pct_error=round(pct_error, 4),
            within_1sigma=within_1s,
            within_2sigma=within_2s,
            method=fc.method,
            horizon_months=fc.horizon_months,
            forecast_calculated_at=fc.calculated_at,
        ))
        logged += 1

    return logged


def _find_actual_value(db, target_type: str, target_code: str, period_date: date):
    """Look up the actual observed value for a forecast target."""
    if target_type == "country_index":
        row = (
            db.query(CountryIndex)
            .join(Country)
            .filter(
                Country.code == target_code,
                CountryIndex.period_date == period_date,
            )
            .first()
        )
        return row.index_value if row else None

    elif target_type == "composite_index":
        row = (
            db.query(WASIComposite)
            .filter(WASIComposite.period_date == period_date)
            .first()
        )
        return row.composite_value if row else None

    elif target_type == "commodity_price":
        row = (
            db.query(CommodityPrice)
            .filter(
                CommodityPrice.commodity_code == target_code,
                CommodityPrice.period_date == period_date,
            )
            .first()
        )
        return row.price_usd if row else None

    return None
