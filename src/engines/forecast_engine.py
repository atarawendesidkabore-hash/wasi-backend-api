"""
WASI Forecasting Engine — Time-series projection for economic indicators.

Methods (numpy/pandas only, zero new dependencies):
  1. Linear Trend Extrapolation — np.polyfit degree 1
  2. Simple Exponential Smoothing (SES) — manual alpha-weighted
  3. Double Exponential Smoothing (Holt) — level + trend decomposition
  4. Ensemble — weighted average with confidence intervals from residuals

Forecast targets:
  - Country WASI Index (per-country, 3/6/12 month horizons)
  - WASI Composite Index (aggregate, 3/6/12 month horizons)
  - Commodity Prices (per commodity, 3/6/12 month horizons)
  - Macro Indicators (GDP growth, inflation, 1-2 year horizons)
"""
import logging
import math
from datetime import date
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ForecastEngine:
    """
    Stateless forecasting engine using ensemble of three methods.
    All computations use numpy only — no external forecasting libraries.
    """

    # Minimum data points required for each method
    MIN_POINTS_LINEAR = 3
    MIN_POINTS_SES = 3
    MIN_POINTS_HOLT = 5

    # Default smoothing parameters
    SES_ALPHA = 0.3
    HOLT_ALPHA = 0.3
    HOLT_BETA = 0.1

    # Ensemble weights (when all methods available)
    ENSEMBLE_WEIGHTS = {
        "linear": 0.25,
        "ses": 0.35,
        "holt": 0.40,
    }

    def __init__(self):
        total = sum(self.ENSEMBLE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Ensemble weights must sum to 1.0, got {total}"

    # ── Method 1: Linear Trend Extrapolation ─────────────────────────

    def _forecast_linear(
        self,
        values: np.ndarray,
        horizon: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        n = len(values)
        t = np.arange(n, dtype=float)
        coeffs = np.polyfit(t, values, deg=1)
        fitted = np.polyval(coeffs, t)
        residuals = values - fitted

        future_t = np.arange(n, n + horizon, dtype=float)
        forecasts = np.polyval(coeffs, future_t)
        return forecasts, residuals

    # ── Method 2: Simple Exponential Smoothing (SES) ─────────────────

    def _forecast_ses(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        a = alpha or self.SES_ALPHA
        n = len(values)
        smoothed = np.zeros(n)
        smoothed[0] = values[0]

        for i in range(1, n):
            smoothed[i] = a * values[i] + (1 - a) * smoothed[i - 1]

        residuals = values - smoothed
        last_level = smoothed[-1]
        forecasts = np.full(horizon, last_level)
        return forecasts, residuals

    # ── Method 3: Double Exponential Smoothing (Holt) ────────────────

    def _forecast_holt(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        a = alpha or self.HOLT_ALPHA
        b = beta or self.HOLT_BETA
        n = len(values)

        level = np.zeros(n)
        trend = np.zeros(n)

        level[0] = values[0]
        trend[0] = values[1] - values[0] if n > 1 else 0.0

        for i in range(1, n):
            level[i] = a * values[i] + (1 - a) * (level[i - 1] + trend[i - 1])
            trend[i] = b * (level[i] - level[i - 1]) + (1 - b) * trend[i - 1]

        # One-step-ahead fitted values
        fitted = np.zeros(n)
        fitted[0] = level[0]
        for i in range(1, n):
            fitted[i] = level[i - 1] + trend[i - 1]
        residuals = values - fitted

        last_level = level[-1]
        last_trend = trend[-1]
        forecasts = np.array([last_level + (h + 1) * last_trend for h in range(horizon)])
        return forecasts, residuals

    # ── Ensemble Forecast ────────────────────────────────────────────

    def forecast_ensemble(
        self,
        values: List[float],
        horizon: int,
        confidence_score: float = 1.0,
    ) -> Dict:
        arr = np.array(values, dtype=float)
        n = len(arr)

        if n < self.MIN_POINTS_LINEAR:
            return self._insufficient_data_result(n, horizon)

        methods_used = []
        all_forecasts = []
        all_residuals = []
        weights = []

        # Linear — available if n >= 3
        if n >= self.MIN_POINTS_LINEAR:
            fc_lin, res_lin = self._forecast_linear(arr, horizon)
            all_forecasts.append(fc_lin)
            all_residuals.append(res_lin)
            weights.append(self.ENSEMBLE_WEIGHTS["linear"])
            methods_used.append("linear")

        # SES — available if n >= 3
        if n >= self.MIN_POINTS_SES:
            fc_ses, res_ses = self._forecast_ses(arr, horizon)
            all_forecasts.append(fc_ses)
            all_residuals.append(res_ses)
            weights.append(self.ENSEMBLE_WEIGHTS["ses"])
            methods_used.append("ses")

        # Holt — available if n >= 5
        if n >= self.MIN_POINTS_HOLT:
            fc_holt, res_holt = self._forecast_holt(arr, horizon)
            all_forecasts.append(fc_holt)
            all_residuals.append(res_holt)
            weights.append(self.ENSEMBLE_WEIGHTS["holt"])
            methods_used.append("holt")

        # Re-normalize weights to sum to 1.0
        w_total = sum(weights)
        norm_weights = [w / w_total for w in weights]

        # Weighted ensemble forecast
        ensemble_fc = np.zeros(horizon)
        for fc, w in zip(all_forecasts, norm_weights):
            ensemble_fc += fc * w

        # Confidence bands from pooled residuals
        pooled_residuals = np.concatenate(all_residuals)
        residual_std = float(np.std(pooled_residuals, ddof=1)) if len(pooled_residuals) > 1 else 0.0

        # Widen bands with horizon: sigma * sqrt(h) * (1/confidence)
        confidence_multiplier = 1.0 / max(confidence_score, 0.1)
        periods = []
        for h in range(horizon):
            fc_val = float(ensemble_fc[h])
            spread = residual_std * math.sqrt(h + 1) * confidence_multiplier
            periods.append({
                "period_offset": h + 1,
                "forecast_value": round(fc_val, 4),
                "lower_1sigma": round(fc_val - spread, 4),
                "upper_1sigma": round(fc_val + spread, 4),
                "lower_2sigma": round(fc_val - 2 * spread, 4),
                "upper_2sigma": round(fc_val + 2 * spread, 4),
            })

        method_details = {}
        for name, fc in zip(methods_used, all_forecasts):
            method_details[name] = [round(float(v), 4) for v in fc]

        return {
            "data_points_used": n,
            "horizon": horizon,
            "methods_used": methods_used,
            "ensemble_weights": {m: round(w, 4) for m, w in zip(methods_used, norm_weights)},
            "residual_std": round(residual_std, 4),
            "confidence_score": confidence_score,
            "periods": periods,
            "method_forecasts": method_details,
        }

    def _insufficient_data_result(self, n: int, horizon: int) -> Dict:
        return {
            "data_points_used": n,
            "horizon": horizon,
            "methods_used": [],
            "ensemble_weights": {},
            "residual_std": None,
            "confidence_score": 0.0,
            "periods": [],
            "method_forecasts": {},
            "error": f"Insufficient data: {n} points available, minimum {self.MIN_POINTS_LINEAR} required",
        }

    # ── High-level forecast methods per target type ──────────────────

    def forecast_country_index(
        self,
        country_code: str,
        values: List[float],
        dates: List[date],
        horizon_months: int = 6,
        confidence: float = 1.0,
    ) -> Dict:
        result = self.forecast_ensemble(values, horizon_months, confidence)
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
        """Forecast stock market index for a West African exchange (NGX/GSE/BRVM)."""
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
        """Forecast eCFA monetary aggregate (M0/M1/M2/circulation/velocity)."""
        result = self.forecast_ensemble(values, horizon_months, confidence)
        result["target_type"] = f"ecfa_{aggregate}"
        result["target_code"] = country_code
        result["aggregate"] = aggregate
        result["last_actual_date"] = str(dates[-1]) if dates else None
        result["last_actual_value"] = round(values[-1], 4) if values else None
        return result
