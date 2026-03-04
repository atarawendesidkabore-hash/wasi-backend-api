"""
Forecast Methods v2.0 — 8 time-series forecasting algorithms.

All methods are stateless, use numpy only, and return a consistent tuple:
    (forecasts: np.ndarray, residuals: np.ndarray, params: dict)

Methods:
  1. Linear Trend     — np.polyfit degree 1
  2. SES              — grid-search optimal alpha
  3. Holt             — grid-search optimal alpha/beta
  4. Damped Holt      — trend damping to prevent overshoot
  5. Croston          — for intermittent/sparse data
  6. Theta            — theta-line decomposition
  7. AR(p)            — autoregressive with differencing
  8. Seasonal         — STL decomposition + method forecasts (delegated to seasonal.py)
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ForecastMethods:
    """Collection of individual forecasting algorithms."""

    # Minimum data points per method
    MIN_POINTS = {
        "linear": 3,
        "ses": 3,
        "holt": 5,
        "damped_holt": 5,
        "croston": 6,
        "theta": 6,
        "ar": 8,
        "seasonal": 24,
    }

    # ── Method 1: Linear Trend Extrapolation ───────────────────────

    def forecast_linear(
        self,
        values: np.ndarray,
        horizon: int,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """Fit degree-1 polynomial and extrapolate."""
        n = len(values)
        t = np.arange(n, dtype=float)
        coeffs = np.polyfit(t, values, deg=1)
        fitted = np.polyval(coeffs, t)
        residuals = values - fitted

        future_t = np.arange(n, n + horizon, dtype=float)
        forecasts = np.polyval(coeffs, future_t)

        params = {"slope": float(coeffs[0]), "intercept": float(coeffs[1])}
        return forecasts, residuals, params

    # ── Method 2: Simple Exponential Smoothing (SES) ───────────────

    def _ses_fit(
        self,
        values: np.ndarray,
        alpha: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Fit SES with given alpha, return (smoothed, residuals)."""
        n = len(values)
        smoothed = np.zeros(n)
        smoothed[0] = values[0]
        for i in range(1, n):
            smoothed[i] = alpha * values[i] + (1 - alpha) * smoothed[i - 1]
        residuals = values - smoothed
        return smoothed, residuals

    def forecast_ses(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """SES with optional grid-search for optimal alpha."""
        if alpha is None:
            alpha = self._optimize_ses_alpha(values)

        smoothed, residuals = self._ses_fit(values, alpha)
        last_level = float(smoothed[-1])
        forecasts = np.full(horizon, last_level)

        params = {"alpha": alpha}
        return forecasts, residuals, params

    def _optimize_ses_alpha(self, values: np.ndarray) -> float:
        """Grid search alpha in [0.05, 0.95] minimizing in-sample MSE."""
        best_alpha = 0.3
        best_mse = float("inf")
        for a_int in range(5, 100, 5):
            a = a_int / 100.0
            _, residuals = self._ses_fit(values, a)
            mse = float(np.mean(residuals[1:] ** 2))
            if mse < best_mse:
                best_mse = mse
                best_alpha = a
        return best_alpha

    # ── Method 3: Double Exponential Smoothing (Holt) ──────────────

    def _holt_fit(
        self,
        values: np.ndarray,
        alpha: float,
        beta: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Fit Holt, return (level, trend, fitted, residuals)."""
        n = len(values)
        level = np.zeros(n)
        trend = np.zeros(n)
        level[0] = values[0]
        trend[0] = values[1] - values[0] if n > 1 else 0.0

        for i in range(1, n):
            level[i] = alpha * values[i] + (1 - alpha) * (level[i - 1] + trend[i - 1])
            trend[i] = beta * (level[i] - level[i - 1]) + (1 - beta) * trend[i - 1]

        fitted = np.zeros(n)
        fitted[0] = level[0]
        for i in range(1, n):
            fitted[i] = level[i - 1] + trend[i - 1]
        residuals = values - fitted

        return level, trend, fitted, residuals

    def forecast_holt(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """Holt with optional grid-search for alpha/beta."""
        if alpha is None or beta is None:
            alpha, beta = self._optimize_holt_params(values)

        level, trend, fitted, residuals = self._holt_fit(values, alpha, beta)
        last_level = level[-1]
        last_trend = trend[-1]
        forecasts = np.array([last_level + (h + 1) * last_trend for h in range(horizon)])

        params = {"alpha": alpha, "beta": beta}
        return forecasts, residuals, params

    def _optimize_holt_params(self, values: np.ndarray) -> Tuple[float, float]:
        """Grid search alpha in [0.1..0.9], beta in [0.01..0.3]."""
        best_alpha, best_beta = 0.3, 0.1
        best_mse = float("inf")
        for a_int in range(10, 100, 10):
            a = a_int / 100.0
            for b_int in [1, 5, 10, 15, 20, 30]:
                b = b_int / 100.0
                _, _, _, residuals = self._holt_fit(values, a, b)
                mse = float(np.mean(residuals[2:] ** 2))
                if mse < best_mse:
                    best_mse = mse
                    best_alpha, best_beta = a, b
        return best_alpha, best_beta

    # ── Method 4: Damped Trend Holt ────────────────────────────────

    def forecast_damped_holt(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        phi: Optional[float] = None,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Holt with damping parameter phi in [0.80, 0.98].
        Forecast: level + (phi + phi^2 + ... + phi^h) * trend
        Converges as h grows, preventing trend overshoot.
        """
        if alpha is None or beta is None or phi is None:
            alpha, beta, phi = self._optimize_damped_holt_params(values)

        n = len(values)
        level = np.zeros(n)
        trend = np.zeros(n)
        level[0] = values[0]
        trend[0] = values[1] - values[0] if n > 1 else 0.0

        for i in range(1, n):
            level[i] = alpha * values[i] + (1 - alpha) * (level[i - 1] + phi * trend[i - 1])
            trend[i] = beta * (level[i] - level[i - 1]) + (1 - beta) * phi * trend[i - 1]

        # One-step-ahead fitted values
        fitted = np.zeros(n)
        fitted[0] = level[0]
        for i in range(1, n):
            fitted[i] = level[i - 1] + phi * trend[i - 1]
        residuals = values - fitted

        # Forecast with cumulative damping
        last_level = level[-1]
        last_trend = trend[-1]
        forecasts = np.zeros(horizon)
        for h in range(horizon):
            cumulative_phi = sum(phi ** j for j in range(1, h + 2))
            forecasts[h] = last_level + cumulative_phi * last_trend

        params = {"alpha": alpha, "beta": beta, "phi": phi}
        return forecasts, residuals, params

    def _optimize_damped_holt_params(
        self, values: np.ndarray
    ) -> Tuple[float, float, float]:
        """Grid search for alpha, beta, phi."""
        best = (0.3, 0.1, 0.90)
        best_mse = float("inf")
        for a_int in range(10, 100, 20):
            a = a_int / 100.0
            for b_int in [1, 5, 10, 20]:
                b = b_int / 100.0
                for p_int in [80, 85, 90, 95, 98]:
                    p = p_int / 100.0
                    n = len(values)
                    level = np.zeros(n)
                    trend = np.zeros(n)
                    level[0] = values[0]
                    trend[0] = values[1] - values[0] if n > 1 else 0.0
                    for i in range(1, n):
                        level[i] = a * values[i] + (1 - a) * (level[i - 1] + p * trend[i - 1])
                        trend[i] = b * (level[i] - level[i - 1]) + (1 - b) * p * trend[i - 1]
                    fitted = np.zeros(n)
                    fitted[0] = level[0]
                    for i in range(1, n):
                        fitted[i] = level[i - 1] + p * trend[i - 1]
                    residuals = values - fitted
                    mse = float(np.mean(residuals[2:] ** 2))
                    if mse < best_mse:
                        best_mse = mse
                        best = (a, b, p)
        return best

    # ── Method 5: Croston's Method ─────────────────────────────────

    def forecast_croston(
        self,
        values: np.ndarray,
        horizon: int,
        alpha: float = 0.3,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        For intermittent/sparse data (tertiary countries with gaps).
        Decomposes into demand size + inter-arrival intervals.
        """
        n = len(values)
        # Find non-zero observations
        nonzero_indices = np.where(values != 0.0)[0]

        if len(nonzero_indices) < 2:
            # Not enough non-zero data, return mean as flat forecast
            mean_val = float(np.mean(values))
            forecasts = np.full(horizon, mean_val)
            residuals = values - mean_val
            return forecasts, residuals, {"method": "croston_fallback_mean"}

        # Demand sizes at non-zero points
        demands = values[nonzero_indices]
        # Intervals between non-zero points
        intervals = np.diff(nonzero_indices).astype(float)

        # Smooth demand sizes
        z_smooth = demands[0]
        p_smooth = intervals[0] if len(intervals) > 0 else 1.0

        for i in range(1, len(demands)):
            z_smooth = alpha * demands[i] + (1 - alpha) * z_smooth
            if i - 1 < len(intervals):
                p_smooth = alpha * intervals[i - 1] + (1 - alpha) * p_smooth

        # Forecast rate = smoothed demand / smoothed interval
        forecast_rate = z_smooth / max(p_smooth, 1e-6)
        forecasts = np.full(horizon, float(forecast_rate))

        # Residuals: difference between actuals and the running forecast rate
        fitted = np.full(n, float(forecast_rate))
        residuals = values - fitted

        params = {
            "alpha": alpha,
            "z_smooth": float(z_smooth),
            "p_smooth": float(p_smooth),
            "forecast_rate": float(forecast_rate),
            "nonzero_count": len(nonzero_indices),
        }
        return forecasts, residuals, params

    # ── Method 6: Theta Method ─────────────────────────────────────

    def forecast_theta(
        self,
        values: np.ndarray,
        horizon: int,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Assimakopoulos & Nikolopoulos (2000).
        Decompose into theta=0 (linear) and theta=2 (amplified curvature),
        forecast each, then average.
        """
        n = len(values)
        t = np.arange(n, dtype=float)

        # Theta=0 line: linear trend
        coeffs = np.polyfit(t, values, deg=1)
        trend_fitted = np.polyval(coeffs, t)

        # Theta=2 line: amplified local curvature
        theta2_values = 2.0 * values - trend_fitted

        # Forecast theta=0: extrapolate linear trend
        future_t = np.arange(n, n + horizon, dtype=float)
        fc_theta0 = np.polyval(coeffs, future_t)

        # Forecast theta=2: apply SES to theta2 values
        ses_alpha = self._optimize_ses_alpha(theta2_values)
        smoothed, _ = self._ses_fit(theta2_values, ses_alpha)
        fc_theta2_base = np.full(horizon, float(smoothed[-1]))

        # Add drift back (trend contribution to theta=2 forecast)
        drift = np.polyval(coeffs, future_t) - np.polyval(coeffs, np.array([n - 1]))
        fc_theta2 = fc_theta2_base + drift

        # Combine: simple average
        forecasts = (fc_theta0 + fc_theta2) / 2.0

        # Residuals from in-sample
        in_sample_fc0 = trend_fitted
        in_sample_fc2 = theta2_values  # identity for in-sample
        in_sample_combined = (in_sample_fc0 + in_sample_fc2) / 2.0
        residuals = values - in_sample_combined

        params = {
            "slope": float(coeffs[0]),
            "intercept": float(coeffs[1]),
            "ses_alpha": ses_alpha,
        }
        return forecasts, residuals, params

    # ── Method 7: AR(p) with Differencing ──────────────────────────

    def forecast_ar(
        self,
        values: np.ndarray,
        horizon: int,
        max_p: int = 4,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Autoregressive model with optional first-differencing.
        Uses Yule-Walker equations solved via numpy.
        Selects p using BIC.
        """
        n = len(values)

        # Check stationarity: compare std of diffs vs std of levels
        diffs = np.diff(values)
        differenced = np.std(diffs) < np.std(values)

        work_values = diffs if differenced else values
        work_n = len(work_values)

        if work_n < max_p + 2:
            max_p = max(1, work_n - 2)

        # Select best p using BIC
        best_p = 1
        best_bic = float("inf")
        best_phi = None

        for p in range(1, max_p + 1):
            phi, residuals, bic = self._fit_ar(work_values, p)
            if phi is not None and bic < best_bic:
                best_bic = bic
                best_p = p
                best_phi = phi

        if best_phi is None:
            # Fallback to simple mean forecast
            mean_val = float(np.mean(values))
            return np.full(horizon, mean_val), values - mean_val, {"method": "ar_fallback"}

        # Compute in-sample residuals
        _, residuals_full, _ = self._fit_ar(work_values, best_p)

        # Recursive h-step forecast on working values
        recent = list(work_values[-best_p:])
        fc_work = []
        for _ in range(horizon):
            pred = sum(best_phi[j] * recent[-(j + 1)] for j in range(best_p))
            fc_work.append(pred)
            recent.append(pred)

        fc_work = np.array(fc_work)

        # Un-difference if needed
        if differenced:
            forecasts = np.zeros(horizon)
            forecasts[0] = values[-1] + fc_work[0]
            for h in range(1, horizon):
                forecasts[h] = forecasts[h - 1] + fc_work[h]
            # Pad residuals to match original length
            residuals_padded = np.zeros(n)
            residuals_padded[0] = 0.0
            if residuals_full is not None:
                usable = min(len(residuals_full), n - 1)
                residuals_padded[1 : 1 + usable] = residuals_full[:usable]
        else:
            forecasts = fc_work
            residuals_padded = np.zeros(n)
            if residuals_full is not None:
                usable = min(len(residuals_full), n)
                residuals_padded[:usable] = residuals_full[:usable]

        params = {
            "p": best_p,
            "phi": [float(x) for x in best_phi],
            "differenced": differenced,
            "bic": float(best_bic),
        }
        return forecasts, residuals_padded, params

    def _fit_ar(
        self,
        values: np.ndarray,
        p: int,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
        """Fit AR(p) via Yule-Walker, return (phi, residuals, BIC)."""
        n = len(values)
        if n <= p + 1:
            return None, None, float("inf")

        # Compute autocorrelation
        mean_val = np.mean(values)
        centered = values - mean_val
        var = np.dot(centered, centered) / n

        if var < 1e-12:
            return None, None, float("inf")

        acf = np.zeros(p + 1)
        for k in range(p + 1):
            acf[k] = np.dot(centered[: n - k], centered[k:]) / n

        # Toeplitz matrix R and vector r
        R = np.zeros((p, p))
        for i in range(p):
            for j in range(p):
                R[i, j] = acf[abs(i - j)]

        r = acf[1 : p + 1]

        try:
            phi = np.linalg.solve(R, r)
        except np.linalg.LinAlgError:
            return None, None, float("inf")

        # Compute residuals
        residuals = np.zeros(n - p)
        for t in range(p, n):
            pred = sum(phi[j] * values[t - j - 1] for j in range(p))
            residuals[t - p] = values[t] - pred

        res_var = np.var(residuals) if len(residuals) > 0 else 1e-12
        res_var = max(res_var, 1e-12)
        bic = n * math.log(res_var) + p * math.log(n)

        return phi, residuals, bic

    # ── Autocorrelation helper ─────────────────────────────────────

    @staticmethod
    def autocorrelation(values: np.ndarray, lag: int = 1) -> float:
        """Compute autocorrelation at given lag."""
        n = len(values)
        if n <= lag:
            return 0.0
        mean_val = np.mean(values)
        centered = values - mean_val
        var = np.dot(centered, centered)
        if var < 1e-12:
            return 0.0
        cov = np.dot(centered[: n - lag], centered[lag:])
        return float(cov / var)

    # ── Method registry ────────────────────────────────────────────

    def get_method(self, name: str):
        """Return method function by name."""
        methods = {
            "linear": self.forecast_linear,
            "ses": self.forecast_ses,
            "holt": self.forecast_holt,
            "damped_holt": self.forecast_damped_holt,
            "croston": self.forecast_croston,
            "theta": self.forecast_theta,
            "ar": self.forecast_ar,
        }
        return methods.get(name)
