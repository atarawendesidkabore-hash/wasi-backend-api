"""
Adaptive Ensemble — dynamic weight computation from cross-validation errors.

Replaces fixed weights (25/35/40) with performance-driven weights.
Strategies:
  - inverse_error: weight_i = (1/RMSE_i) / sum(1/RMSE_j)
  - trimmed_mean: drop worst method, equal weights for remaining
"""
import logging
import math
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class AdaptiveEnsemble:
    """
    Dynamic ensemble that replaces fixed weights with performance-driven weights.
    """

    ALL_METHODS = [
        "linear", "ses", "holt", "damped_holt",
        "croston", "theta", "ar", "seasonal",
    ]

    MIN_POINTS = {
        "linear": 3, "ses": 3, "holt": 5, "damped_holt": 5,
        "croston": 6, "theta": 6, "ar": 8, "seasonal": 24,
    }

    # Fallback fixed weights (v1-compatible)
    FALLBACK_WEIGHTS = {
        "linear": 0.25,
        "ses": 0.35,
        "holt": 0.40,
    }

    def select_methods(
        self,
        values: np.ndarray,
        data_profile: dict,
    ) -> List[str]:
        """
        Auto-select which methods to include based on data characteristics.

        Args:
            values: the time series
            data_profile: dict from ModelDiagnostics.profile_series()
        """
        n = len(values)
        methods = []

        # Always include basic methods if enough data
        if n >= self.MIN_POINTS["linear"]:
            methods.append("linear")
        if n >= self.MIN_POINTS["ses"]:
            methods.append("ses")

        # Trend methods
        if n >= self.MIN_POINTS["holt"]:
            methods.append("holt")
            ts = data_profile.get("trend_strength", 0.0)
            if ts > 0.3:
                methods.append("damped_holt")

        # Intermittent data
        zf = data_profile.get("zero_fraction", 0.0)
        if zf > 0.15 and n >= self.MIN_POINTS["croston"]:
            methods.append("croston")

        # Theta — good general method
        if n >= self.MIN_POINTS["theta"]:
            methods.append("theta")

        # AR — needs autocorrelation
        ac1 = data_profile.get("autocorrelation_lag1", 0.0)
        if n >= self.MIN_POINTS["ar"] and abs(ac1) > 0.3:
            methods.append("ar")

        # Seasonal — needs long series with seasonality
        ss = data_profile.get("seasonality_strength", 0.0)
        if n >= self.MIN_POINTS["seasonal"] and ss > 0.3:
            methods.append("seasonal")

        return methods

    def compute_adaptive_weights(
        self,
        method_errors: Dict[str, List[float]],
        strategy: str = "inverse_error",
    ) -> Dict[str, float]:
        """
        Compute ensemble weights from cross-validation errors.

        Args:
            method_errors: {method_name: [error_per_split, ...]}
            strategy: "inverse_error" or "trimmed_mean"

        Returns:
            {method_name: weight} summing to 1.0
        """
        if not method_errors:
            return {}

        if strategy == "trimmed_mean":
            return self._trimmed_mean_weights(method_errors)

        return self._inverse_error_weights(method_errors)

    def _inverse_error_weights(
        self,
        method_errors: Dict[str, List[float]],
    ) -> Dict[str, float]:
        """Weight = (1/RMSE) / sum(1/RMSE) for each method."""
        rmse_map = {}
        for name, errors in method_errors.items():
            if errors:
                rmse = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
                rmse_map[name] = max(rmse, 1e-6)

        if not rmse_map:
            return {}

        inv_sum = sum(1.0 / r for r in rmse_map.values())
        if inv_sum < 1e-12:
            # Equal weights fallback
            n = len(rmse_map)
            return {name: 1.0 / n for name in rmse_map}

        weights = {name: (1.0 / r) / inv_sum for name, r in rmse_map.items()}
        return weights

    def _trimmed_mean_weights(
        self,
        method_errors: Dict[str, List[float]],
    ) -> Dict[str, float]:
        """Drop worst method, equal weights for remaining."""
        rmse_map = {}
        for name, errors in method_errors.items():
            if errors:
                rmse = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
                rmse_map[name] = rmse

        if len(rmse_map) <= 1:
            return {name: 1.0 for name in rmse_map}

        # Drop worst
        worst = max(rmse_map, key=rmse_map.get)
        remaining = [name for name in rmse_map if name != worst]
        w = 1.0 / len(remaining)
        return {name: w for name in remaining}

    def combine_forecasts(
        self,
        method_forecasts: Dict[str, np.ndarray],
        weights: Dict[str, float],
    ) -> np.ndarray:
        """Weighted average combination of forecasts."""
        if not method_forecasts or not weights:
            return np.array([])

        # Normalize weights for available methods
        available = {k: v for k, v in weights.items() if k in method_forecasts}
        if not available:
            available = {k: 1.0 / len(method_forecasts) for k in method_forecasts}

        w_total = sum(available.values())
        if w_total < 1e-12:
            w_total = 1.0

        horizon = max(len(fc) for fc in method_forecasts.values())
        combined = np.zeros(horizon)
        for name, fc in method_forecasts.items():
            w = available.get(name, 0.0) / w_total
            combined[: len(fc)] += fc * w

        return combined

    def quick_cv_weights(
        self,
        values: np.ndarray,
        method_fns: Dict[str, Callable],
        test_fraction: float = 0.25,
        horizon: int = 3,
    ) -> Dict[str, float]:
        """
        Quick cross-validation to compute adaptive weights.
        Holds out last test_fraction of data, forecasts from the rest.

        Args:
            values: full time series
            method_fns: {name: callable(values, horizon) -> (forecasts, residuals, params)}
            test_fraction: fraction of data to hold out
            horizon: forecast horizon for CV

        Returns:
            {method_name: weight}
        """
        n = len(values)
        test_size = max(1, int(n * test_fraction))
        if test_size > horizon:
            test_size = horizon
        train_end = n - test_size

        if train_end < 3:
            # Not enough training data, return equal weights
            return {name: 1.0 / len(method_fns) for name in method_fns}

        train = values[:train_end]
        actual = values[train_end : train_end + test_size]

        method_errors = {}
        for name, fn in method_fns.items():
            try:
                fc, _, _ = fn(train, test_size)
                errors = list(fc[:len(actual)] - actual)
                method_errors[name] = errors
            except Exception:
                logger.debug("CV failed for method %s", name, exc_info=True)
                continue

        if not method_errors:
            return {name: 1.0 / len(method_fns) for name in method_fns}

        return self.compute_adaptive_weights(method_errors, strategy="inverse_error")
