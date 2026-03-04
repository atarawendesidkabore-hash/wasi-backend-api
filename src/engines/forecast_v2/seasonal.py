"""
Seasonal Decomposition — STL-like decomposition for monthly time-series.

Uses centered moving average for trend extraction, monthly averaging for
seasonal component, and remainder as residual. Pure numpy, zero dependencies.

For series >= 24 points: full seasonal decomposition (period=12).
For series < 24 points: falls back to simple 12-point moving average trend.
"""
import logging
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SeasonalDecomposer:
    """
    STL-like decomposition for monthly data.

    Steps:
        1. Centered 2x12 moving average to extract trend
        2. Detrend: seasonal_plus_residual = values - trend
        3. Average each month-of-year across years to get seasonal component
        4. Residual = values - trend - seasonal
    """

    def decompose(
        self,
        values: np.ndarray,
        period: int = 12,
    ) -> Dict[str, np.ndarray]:
        """
        Decompose time series into trend + seasonal + residual.

        Returns dict with keys: "trend", "seasonal", "residual".
        NaN values at edges where moving average cannot be computed.
        """
        n = len(values)

        if n < 2 * period:
            # Not enough data for full seasonal decomposition.
            # Return simple moving average as trend, no seasonal.
            trend = self._moving_average(values, min(period, n))
            seasonal = np.zeros(n)
            residual = values - trend
            return {"trend": trend, "seasonal": seasonal, "residual": residual}

        # Step 1: Centered 2xPeriod moving average for trend
        trend = self._centered_moving_average(values, period)

        # Step 2: Detrend
        detrended = values - trend

        # Step 3: Compute seasonal component (average each month-of-year)
        seasonal = self._compute_seasonal(detrended, period, n)

        # Step 4: Residual
        residual = values - trend - seasonal

        # Handle NaNs at edges (from centered MA): fill with 0
        nan_mask = np.isnan(trend)
        trend[nan_mask] = values[nan_mask]
        residual = values - trend - seasonal

        return {"trend": trend, "seasonal": seasonal, "residual": residual}

    def seasonal_strength(
        self,
        values: np.ndarray,
        period: int = 12,
    ) -> float:
        """
        Compute seasonal strength: 1 - Var(residual) / Var(seasonal + residual).
        Returns 0-1, where 1 means strong seasonality.
        """
        decomp = self.decompose(values, period)
        seasonal_plus_residual = decomp["seasonal"] + decomp["residual"]
        var_sr = float(np.var(seasonal_plus_residual))
        var_r = float(np.var(decomp["residual"]))

        if var_sr < 1e-12:
            return 0.0
        strength = max(0.0, 1.0 - var_r / var_sr)
        return round(strength, 4)

    def trend_strength(
        self,
        values: np.ndarray,
        period: int = 12,
    ) -> float:
        """
        Compute trend strength: 1 - Var(residual) / Var(trend + residual).
        Returns 0-1, where 1 means strong trend.
        """
        decomp = self.decompose(values, period)
        trend_plus_residual = decomp["trend"] + decomp["residual"]
        var_tr = float(np.var(trend_plus_residual))
        var_r = float(np.var(decomp["residual"]))

        if var_tr < 1e-12:
            return 0.0
        strength = max(0.0, 1.0 - var_r / var_tr)
        return round(strength, 4)

    def forecast_seasonal(
        self,
        values: np.ndarray,
        horizon: int,
        trend_method: str = "holt",
        period: int = 12,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Seasonal forecast: decompose, forecast each component, recombine.

        1. Decompose into trend + seasonal + residual
        2. Forecast trend using Holt (or linear)
        3. Replicate seasonal pattern forward
        4. Forecast residual using SES
        5. Combine: forecast = trend_fc + seasonal_fc + residual_fc

        Returns (forecasts, in_sample_residuals, params).
        """
        from src.engines.forecast_v2.methods import ForecastMethods

        decomp = self.decompose(values, period)
        trend = decomp["trend"]
        seasonal = decomp["seasonal"]
        residual = decomp["residual"]
        n = len(values)

        methods = ForecastMethods()

        # Forecast trend
        if trend_method == "holt" and n >= 5:
            trend_fc, _, trend_params = methods.forecast_holt(trend, horizon)
        else:
            trend_fc, _, trend_params = methods.forecast_linear(trend, horizon)

        # Replicate seasonal pattern forward
        seasonal_cycle = np.zeros(period)
        count = np.zeros(period)
        for i in range(n):
            month = i % period
            if not np.isnan(seasonal[i]):
                seasonal_cycle[month] += seasonal[i]
                count[month] += 1
        for m in range(period):
            if count[m] > 0:
                seasonal_cycle[m] /= count[m]

        seasonal_fc = np.array([seasonal_cycle[(n + h) % period] for h in range(horizon)])

        # Forecast residual with SES (should be near zero)
        residual_fc_val, _, _ = methods.forecast_ses(residual, horizon)

        # Combine
        forecasts = trend_fc + seasonal_fc + residual_fc_val

        # In-sample residuals (from original decomposition)
        in_sample_residuals = decomp["residual"]

        params = {
            "period": period,
            "trend_method": trend_method,
            "trend_params": trend_params,
            "seasonal_cycle": [round(float(x), 4) for x in seasonal_cycle],
        }
        return forecasts, in_sample_residuals, params

    # ── Internal helpers ───────────────────────────────────────────

    @staticmethod
    def _centered_moving_average(values: np.ndarray, period: int) -> np.ndarray:
        """Compute 2xPeriod centered moving average."""
        n = len(values)
        result = np.full(n, np.nan)

        # First pass: simple MA of 'period' length
        ma1 = np.full(n, np.nan)
        half = period // 2
        for i in range(half, n - half):
            ma1[i] = np.mean(values[i - half : i + half])

        # Second pass: center the MA (2-point average for even period)
        if period % 2 == 0:
            for i in range(1, n):
                if not np.isnan(ma1[i]) and not np.isnan(ma1[i - 1]):
                    result[i] = (ma1[i] + ma1[i - 1]) / 2.0
        else:
            result = ma1

        # Fill NaN edges with nearest valid value
        first_valid = None
        last_valid = None
        for i in range(n):
            if not np.isnan(result[i]):
                if first_valid is None:
                    first_valid = i
                last_valid = i

        if first_valid is not None:
            result[:first_valid] = result[first_valid]
        if last_valid is not None:
            result[last_valid + 1 :] = result[last_valid]

        return result

    @staticmethod
    def _compute_seasonal(
        detrended: np.ndarray,
        period: int,
        n: int,
    ) -> np.ndarray:
        """Average each month-of-year to get seasonal component."""
        seasonal_avg = np.zeros(period)
        count = np.zeros(period)

        for i in range(n):
            month = i % period
            val = detrended[i]
            if not np.isnan(val):
                seasonal_avg[month] += val
                count[month] += 1

        for m in range(period):
            if count[m] > 0:
                seasonal_avg[m] /= count[m]

        # Normalize: seasonal should sum to zero
        seasonal_avg -= np.mean(seasonal_avg)

        # Tile to full length
        seasonal = np.array([seasonal_avg[i % period] for i in range(n)])
        return seasonal

    @staticmethod
    def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
        """Simple moving average with edge padding."""
        n = len(values)
        if window >= n:
            return np.full(n, np.mean(values))

        result = np.zeros(n)
        cumsum = np.concatenate([np.array([0.0]), np.cumsum(values)])
        half = window // 2

        for i in range(n):
            lo = max(0, i - half)
            hi = min(n, i + half + 1)
            result[i] = (cumsum[hi] - cumsum[lo]) / (hi - lo)

        return result
