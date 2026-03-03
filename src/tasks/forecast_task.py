"""
Forecast Update Scheduled Task.

Runs daily at 04:00 UTC (after composite update and news sweep).
Computes and caches forecasts for all targets:
  - 16 country indices (3/6/12 month horizons)
  - 1 composite index (3/6/12 month horizons)
  - 6 commodities (3/6/12 month horizons)
  - 16 country macro indicators (1/2 year horizons)
"""
import logging
import threading
from datetime import timezone, datetime, date

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex, WASIComposite, CommodityPrice, MacroIndicator
from src.database.forecast_models import ForecastResult
from src.engines.forecast_engine import ForecastEngine

logger = logging.getLogger(__name__)
_forecast_lock = threading.Lock()

COMMODITY_CODES = ["COCOA", "BRENT", "GOLD", "COTTON", "COFFEE", "IRON_ORE"]


async def run_forecast_update(db=None):
    if not _forecast_lock.acquire(blocking=False):
        logger.warning("forecast_update: previous run still in progress, skipping")
        return {"status": "skipped", "reason": "already_running"}

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        engine = ForecastEngine()
        start = datetime.now(timezone.utc)
        stats = {
            "country_forecasts": 0,
            "composite_computed": False,
            "commodities": 0,
            "macro": 0,
        }

        # ── 1. Country Index Forecasts ────────────────────────
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

            for horizon in [3, 6, 12]:
                result = engine.forecast_country_index(
                    country.code, values, dates, horizon, avg_confidence,
                )
                _persist_forecast(db, result, horizon)
                stats["country_forecasts"] += 1

        # ── 2. Composite Index Forecast ───────────────────────
        composites = (
            db.query(WASIComposite)
            .order_by(WASIComposite.period_date.asc())
            .all()
        )
        if len(composites) >= 3:
            values = [r.composite_value for r in composites]
            dates = [r.period_date for r in composites]
            for horizon in [3, 6, 12]:
                result = engine.forecast_composite(values, dates, horizon)
                _persist_forecast(db, result, horizon)
            stats["composite_computed"] = True

        # ── 3. Commodity Price Forecasts ──────────────────────
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

            for horizon in [3, 6, 12]:
                result = engine.forecast_commodity(code, values, dates, horizon)
                _persist_forecast(db, result, horizon)
                stats["commodities"] += 1

        # ── 4. Macro Indicator Forecasts ──────────────────────
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

                for horizon_y in [1, 2]:
                    result = engine.forecast_macro(
                        country.code, indicator, values, years, horizon_y,
                        confidence=rows[-1].confidence or 0.85,
                    )
                    _persist_forecast(db, result, horizon_y)
                    stats["macro"] += 1

        db.commit()
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        logger.info(
            "forecast_update: countries=%d composite=%s commodities=%d macro=%d (%.1fs)",
            stats["country_forecasts"], stats["composite_computed"],
            stats["commodities"], stats["macro"], elapsed,
        )

        return {
            "status": "completed",
            "country_forecasts_computed": stats["country_forecasts"],
            "composite_computed": stats["composite_computed"],
            "commodities_computed": stats["commodities"],
            "macro_computed": stats["macro"],
            "duration_seconds": round(elapsed, 2),
            "computed_at": datetime.now(timezone.utc),
        }

    except Exception as exc:
        logger.error("forecast_update failed: %s", exc, exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()
        _forecast_lock.release()


def _persist_forecast(db, result: dict, horizon: int):
    target_type = result.get("target_type", "unknown")
    target_code = result.get("target_code", "unknown")
    methods_str = ",".join(result.get("methods_used", []))

    last_actual = result.get("last_actual_date")
    if last_actual and isinstance(last_actual, str):
        last_actual = date.fromisoformat(last_actual)

    base_date = last_actual or date.today()

    for period in result.get("periods", []):
        offset = period["period_offset"]

        # For macro (annual), offset = years; for others, offset = months
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
            existing.lower_1sigma = period["lower_1sigma"]
            existing.upper_1sigma = period["upper_1sigma"]
            existing.lower_2sigma = period["lower_2sigma"]
            existing.upper_2sigma = period["upper_2sigma"]
            existing.method = "ensemble"
            existing.methods_used = methods_str
            existing.data_points_used = result.get("data_points_used")
            existing.residual_std = result.get("residual_std")
            existing.confidence = result.get("confidence_score", 1.0)
            existing.last_actual_date = last_actual
            existing.last_actual_value = result.get("last_actual_value")
            existing.calculated_at = datetime.now(timezone.utc)
        else:
            db.add(ForecastResult(
                target_type=target_type,
                target_code=target_code,
                period_date=period_date,
                horizon_months=horizon,
                forecast_value=period["forecast_value"],
                lower_1sigma=period["lower_1sigma"],
                upper_1sigma=period["upper_1sigma"],
                lower_2sigma=period["lower_2sigma"],
                upper_2sigma=period["upper_2sigma"],
                method="ensemble",
                methods_used=methods_str,
                data_points_used=result.get("data_points_used"),
                residual_std=result.get("residual_std"),
                confidence=result.get("confidence_score", 1.0),
                last_actual_date=last_actual,
                last_actual_value=result.get("last_actual_value"),
                calculated_at=datetime.now(timezone.utc),
            ))
