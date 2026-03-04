"""
WASI Forecast Engine v2.0 — Adaptive Ensemble with Multivariate Support.

Drop-in replacement for ForecastEngine with enhanced capabilities:
  - 8 forecasting methods (vs 3 in v1)
  - Adaptive ensemble weights from backtesting (vs fixed 25/35/40)
  - Multivariate cross-correlation adjustments
  - Monte Carlo confidence bands (fan charts)
  - Regime change detection
  - Scenario analysis
  - Backtesting framework

API compatibility: all existing methods (forecast_country_index, forecast_composite,
forecast_commodity, forecast_macro, forecast_stock_market, forecast_ecfa_supply)
return the same dict structure as v1, with additional fields.
"""
import logging
import math
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.engines.forecast_v2.methods import ForecastMethods
from src.engines.forecast_v2.ensemble import AdaptiveEnsemble
from src.engines.forecast_v2.seasonal import SeasonalDecomposer
from src.engines.forecast_v2.multivariate import CrossCorrelationModel, SimpleVAR
from src.engines.forecast_v2.scenarios import ScenarioEngine
from src.engines.forecast_v2.backtesting import WalkForwardBacktester
from src.engines.forecast_v2.montecarlo import MonteCarloSimulator
from src.engines.forecast_v2.regime import RegimeDetector
from src.engines.forecast_v2.diagnostics import ModelDiagnostics

logger = logging.getLogger(__name__)


class ForecastEngineV2:
    """
    WASI Forecast Engine v2.0 — production forecasting with adaptive ensemble.
    """

    ENGINE_VERSION = "2.0"

    def __init__(self):
        self.methods = ForecastMethods()
        self.ensemble = AdaptiveEnsemble()
        self.decomposer = SeasonalDecomposer()
        self.cross_corr = CrossCorrelationModel()
        self.var_model = SimpleVAR()
        self.scenarios = ScenarioEngine()
        self.backtester = WalkForwardBacktester()
        self.montecarlo = MonteCarloSimulator()
        self.regime = RegimeDetector()
        self.diagnostics = ModelDiagnostics()

    # ── Core ensemble forecast ─────────────────────────────────────

    def forecast_ensemble(
        self,
        values: List[float],
        horizon: int,
        confidence_score: float = 1.0,
        exogenous: Optional[Dict[str, dict]] = None,
        use_adaptive_weights: bool = True,
        include_montecarlo: bool = True,
        include_backtesting: bool = False,
    ) -> Dict:
        """
        Main forecast method. Returns v1-compatible dict with v2 extensions.

        Flow:
          1. Profile data series
          2. Detect regime changes, trim to current regime
          3. Select applicable methods
          4. Run each method
          5. Compute adaptive weights (or fallback to equal)
          6. Combine forecasts
          7. Apply multivariate adjustments
          8. Run Monte Carlo for fan chart
          9. Build result
        """
        arr = np.array(values, dtype=float)
        n = len(arr)

        if n < ForecastMethods.MIN_POINTS["linear"]:
            return self._insufficient_data_result(n, horizon)

        # Step 1: Profile the data
        data_profile = self.diagnostics.profile_series(arr)

        # Step 2: Regime detection — optionally trim to current regime
        regime_info = self.regime.get_regime_info(arr)
        if regime_info["change_point_detected"]:
            regime_values = self.regime.get_regime_window(arr)
            if len(regime_values) >= ForecastMethods.MIN_POINTS["linear"]:
                working_values = regime_values
            else:
                working_values = arr
        else:
            working_values = arr

        working_n = len(working_values)

        # Step 3: Select methods based on data profile
        selected_methods = self.ensemble.select_methods(working_values, data_profile)
        if not selected_methods:
            selected_methods = ["linear", "ses"]

        # Step 4: Run each method
        method_forecasts = {}
        method_residuals = {}
        method_params = {}
        all_residuals = []

        for method_name in selected_methods:
            try:
                if method_name == "seasonal":
                    fc, res, params = self.decomposer.forecast_seasonal(
                        working_values, horizon,
                    )
                else:
                    fn = self.methods.get_method(method_name)
                    if fn is None:
                        continue
                    fc, res, params = fn(working_values, horizon)

                method_forecasts[method_name] = fc
                method_residuals[method_name] = res
                method_params[method_name] = params
                all_residuals.append(res)
            except Exception:
                logger.debug("Method %s failed", method_name, exc_info=True)
                continue

        if not method_forecasts:
            return self._insufficient_data_result(n, horizon)

        methods_used = list(method_forecasts.keys())

        # Step 5: Compute weights
        if use_adaptive_weights and working_n >= 8:
            method_fns = {}
            for name in methods_used:
                if name == "seasonal":
                    method_fns[name] = lambda v, h: self.decomposer.forecast_seasonal(v, h)
                else:
                    fn = self.methods.get_method(name)
                    if fn:
                        method_fns[name] = fn

            weights = self.ensemble.quick_cv_weights(
                working_values, method_fns, test_fraction=0.25, horizon=min(horizon, 3),
            )
        else:
            # Equal weights fallback
            weights = {name: 1.0 / len(methods_used) for name in methods_used}

        # Step 6: Combine forecasts
        ensemble_fc = self.ensemble.combine_forecasts(method_forecasts, weights)

        # Pooled residuals for standard deviation
        pooled = np.concatenate(all_residuals) if all_residuals else np.array([0.0])
        residual_std = float(np.std(pooled, ddof=1)) if len(pooled) > 1 else 0.0

        # Step 7: Multivariate adjustment
        multivariate_info = {
            "applied": False,
            "indicators_used": [],
            "total_adjustment": [0.0] * horizon,
        }
        if exogenous:
            # Exogenous is expected as {code: {"values": np.ndarray, "forecast": np.ndarray}}
            # We need to know the country code — this is set by higher-level methods
            pass  # Applied in target-specific methods below

        # Step 8: Monte Carlo fan chart
        fan_chart = None
        if include_montecarlo and len(pooled) > 2:
            mc_result = self.montecarlo.residual_bootstrap(
                ensemble_fc, pooled,
                n_simulations=500,
                horizon=horizon,
                confidence_score=confidence_score,
            )
            fan_chart = self.montecarlo.fan_chart_data(mc_result)

        # Step 9: Build v1-compatible result
        confidence_multiplier = 1.0 / max(confidence_score, 0.1)
        periods = []
        for h in range(horizon):
            fc_val = float(ensemble_fc[h]) if h < len(ensemble_fc) else 0.0
            spread = residual_std * math.sqrt(h + 1) * confidence_multiplier
            period = {
                "period_offset": h + 1,
                "forecast_value": round(fc_val, 4),
                "lower_1sigma": round(fc_val - spread, 4),
                "upper_1sigma": round(fc_val + spread, 4),
                "lower_2sigma": round(fc_val - 2 * spread, 4),
                "upper_2sigma": round(fc_val + 2 * spread, 4),
            }
            # Add fan chart percentiles if available
            if fan_chart and h < len(fan_chart):
                period["p10"] = fan_chart[h]["p10"]
                period["p25"] = fan_chart[h]["p25"]
                period["p75"] = fan_chart[h]["p75"]
                period["p90"] = fan_chart[h]["p90"]
            periods.append(period)

        method_details = {}
        for name, fc in method_forecasts.items():
            method_details[name] = [round(float(v), 4) for v in fc]

        result = {
            # v1-compatible fields
            "data_points_used": n,
            "horizon": horizon,
            "methods_used": methods_used,
            "ensemble_weights": {m: round(w, 4) for m, w in weights.items()},
            "residual_std": round(residual_std, 4),
            "confidence_score": confidence_score,
            "periods": periods,
            "method_forecasts": method_details,
            # v2 extension fields
            "engine_version": self.ENGINE_VERSION,
            "data_profile": data_profile,
            "regime_info": regime_info,
            "fan_chart": fan_chart,
            "multivariate_adjustment": multivariate_info,
            "method_params": {
                name: {k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in params.items()}
                for name, params in method_params.items()
            },
        }

        # Optional backtesting
        if include_backtesting and working_n >= 12:
            method_fns = {}
            for name in methods_used:
                if name == "seasonal":
                    method_fns[name] = lambda v, h: self.decomposer.forecast_seasonal(v, h)
                else:
                    fn = self.methods.get_method(name)
                    if fn:
                        method_fns[name] = fn
            bt = self.backtester.run_all_methods_backtest(
                working_values, method_fns,
                min_train_size=max(6, working_n // 3),
                test_horizon=min(horizon, 3),
            )
            result["backtesting_summary"] = {
                "best_method": bt.get("best_method"),
                "ranking": bt.get("ranking", []),
            }

        return result

    def _insufficient_data_result(self, n: int, horizon: int) -> Dict:
        """Return result dict when data is insufficient."""
        return {
            "data_points_used": n,
            "horizon": horizon,
            "methods_used": [],
            "ensemble_weights": {},
            "residual_std": None,
            "confidence_score": 0.0,
            "periods": [],
            "method_forecasts": {},
            "engine_version": self.ENGINE_VERSION,
            "data_profile": None,
            "regime_info": None,
            "fan_chart": None,
            "multivariate_adjustment": None,
            "error": f"Insufficient data: {n} points, minimum 3 required",
        }

    # ── High-level forecast methods (v1-compatible interface) ──────

    def forecast_country_index(
        self,
        country_code: str,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 1.0,
        commodity_data: Optional[Dict] = None,
        stock_data: Optional[Dict] = None,
        news_data: Optional[Dict] = None,
    ) -> Dict:
        """Forecast country WASI index with optional multivariate inputs."""
        exogenous = self._build_country_exogenous(
            country_code, commodity_data, stock_data, news_data,
        )
        result = self.forecast_ensemble(
            values, horizon_months, confidence, exogenous=exogenous,
        )

        # Apply multivariate adjustment if we have exogenous data
        if exogenous and len(values) >= 6:
            arr = np.array(values, dtype=float)
            adj, indicators = self.cross_corr.compute_total_adjustment(
                country_code, arr, exogenous, horizon_months,
            )
            if np.any(adj != 0.0):
                # Adjust the forecast periods
                for i, period in enumerate(result.get("periods", [])):
                    if i < len(adj):
                        period["forecast_value"] = round(
                            period["forecast_value"] + adj[i], 4,
                        )
                result["multivariate_adjustment"] = {
                    "applied": True,
                    "indicators_used": indicators,
                    "total_adjustment": [round(float(a), 4) for a in adj],
                }

        result["target_type"] = "country_index"
        result["target_code"] = country_code
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    def forecast_composite(
        self,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 1.0,
    ) -> Dict:
        """Forecast WASI composite index."""
        result = self.forecast_ensemble(values, horizon_months, confidence)
        result["target_type"] = "composite_index"
        result["target_code"] = "WASI_COMPOSITE"
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    def forecast_commodity(
        self,
        commodity_code: str,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 1.0,
    ) -> Dict:
        """Forecast commodity price."""
        result = self.forecast_ensemble(values, horizon_months, confidence)
        result["target_type"] = "commodity_price"
        result["target_code"] = commodity_code
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    def forecast_macro(
        self,
        country_code: str,
        indicator: str,
        values: List[float],
        years: List[int],
        horizon_years: int = 2,
        confidence: float = 1.0,
    ) -> Dict:
        """Forecast macro indicator (GDP growth, inflation)."""
        result = self.forecast_ensemble(values, horizon_years, confidence)
        result["target_type"] = f"macro_{indicator}"
        result["target_code"] = country_code
        result["indicator"] = indicator
        result["last_actual_year"] = years[-1] if years else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    def forecast_stock_market(
        self,
        exchange_code: str,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 0.85,
    ) -> Dict:
        """Forecast stock market index."""
        result = self.forecast_ensemble(values, horizon_months, confidence)
        result["target_type"] = "stock_market"
        result["target_code"] = exchange_code
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    def forecast_ecfa_supply(
        self,
        country_code: str,
        aggregate: str,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 0.90,
    ) -> Dict:
        """Forecast eCFA monetary aggregate."""
        result = self.forecast_ensemble(values, horizon_months, confidence)
        result["target_type"] = f"ecfa_{aggregate}"
        result["target_code"] = country_code
        result["aggregate"] = aggregate
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result

    # ── VAR forecast for Big 4 ─────────────────────────────────────

    def forecast_var_big4(
        self,
        country_data: Dict[str, List[float]],
        horizon: int = 6,
    ) -> Optional[Dict]:
        """
        Run VAR(1) forecast for the Big 4 countries.

        Args:
            country_data: {"NG": [values], "CI": [values], "GH": [values], "SN": [values]}
            horizon: forecast steps

        Returns:
            {country_code: {"forecast": [...], "last_value": float}}
        """
        np_data = {cc: np.array(v, dtype=float) for cc, v in country_data.items()}
        fitted = self.var_model.fit(np_data)
        if fitted is None:
            return None

        last_values = {cc: float(v[-1]) for cc, v in np_data.items()}
        forecasts = self.var_model.forecast_from_last(fitted, last_values, horizon)
        if forecasts is None:
            return None

        result = {}
        for cc in self.var_model.BIG_4:
            if cc in forecasts:
                result[cc] = {
                    "forecast": [round(float(v), 4) for v in forecasts[cc]],
                    "last_value": round(last_values.get(cc, 0.0), 4),
                }
        return result

    # ── Internal helpers ───────────────────────────────────────────

    def _build_country_exogenous(
        self,
        country_code: str,
        commodity_data: Optional[Dict] = None,
        stock_data: Optional[Dict] = None,
        news_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Build exogenous variable dict for a country's forecast."""
        if not commodity_data and not stock_data:
            return None

        exogenous = {}

        # Add relevant commodity data
        if commodity_data:
            indicators = self.cross_corr.get_country_indicators(country_code)
            for ind in indicators:
                if ind["type"] == "commodity" and ind["code"] in commodity_data:
                    exogenous[ind["code"]] = commodity_data[ind["code"]]

        # Add stock market data
        if stock_data:
            for exchange, countries in self.cross_corr.STOCK_COUNTRY_MAP.items():
                for cc, _ in countries:
                    if cc == country_code and exchange in stock_data:
                        exogenous[exchange] = stock_data[exchange]

        return exogenous if exogenous else None
