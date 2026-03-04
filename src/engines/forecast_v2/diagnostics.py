"""
Model Diagnostics — series profiling, method recommendation, feature importance.

Provides automated analysis of time series characteristics to guide
method selection and ensemble weighting decisions.
"""
import logging
import math
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class ModelDiagnostics:
    """Automated model selection and diagnostic reporting."""

    def profile_series(self, values: np.ndarray) -> dict:
        """
        Analyze a time series and return its characteristics.

        Returns:
            {
                "n": int,
                "mean": float,
                "std": float,
                "trend_strength": float (0-1),
                "seasonality_strength": float (0-1),
                "autocorrelation_lag1": float,
                "zero_fraction": float,
                "stationarity_score": float (0-1, higher = more stationary),
                "series_class": "short" | "medium" | "long",
                "recommended_methods": list[str],
                "regime_change_detected": bool,
                "last_change_point": int | None,
            }
        """
        n = len(values)
        if n < 2:
            return self._minimal_profile(values)

        mean_val = float(np.mean(values))
        std_val = float(np.std(values, ddof=1)) if n > 1 else 0.0

        # Trend strength (from linear fit R-squared)
        t = np.arange(n, dtype=float)
        if std_val > 1e-12:
            coeffs = np.polyfit(t, values, deg=1)
            fitted = np.polyval(coeffs, t)
            ss_res = float(np.sum((values - fitted) ** 2))
            ss_tot = float(np.sum((values - mean_val) ** 2))
            r_squared = 1.0 - (ss_res / max(ss_tot, 1e-12))
            trend_strength = max(0.0, min(1.0, r_squared))
        else:
            trend_strength = 0.0

        # Seasonality strength (if enough data)
        seasonality_strength = 0.0
        if n >= 24:
            from src.engines.forecast_v2.seasonal import SeasonalDecomposer
            decomposer = SeasonalDecomposer()
            seasonality_strength = decomposer.seasonal_strength(values, period=12)

        # Autocorrelation at lag 1
        from src.engines.forecast_v2.methods import ForecastMethods
        ac1 = ForecastMethods.autocorrelation(values, lag=1)

        # Zero fraction
        zero_fraction = float(np.sum(values == 0.0)) / n

        # Stationarity score (crude: variance ratio of first vs second half)
        if n >= 6:
            half = n // 2
            var1 = float(np.var(values[:half], ddof=1))
            var2 = float(np.var(values[half:], ddof=1))
            mean1 = float(np.mean(values[:half]))
            mean2 = float(np.mean(values[half:]))

            # Stationarity = low mean shift + low variance shift
            mean_shift = abs(mean2 - mean1) / max(std_val, 1e-12)
            var_ratio = max(var1, 1e-12) / max(var2, 1e-12)
            var_shift = abs(math.log(max(var_ratio, 1e-12)))

            stationarity_score = max(0.0, 1.0 - 0.3 * mean_shift - 0.2 * var_shift)
            stationarity_score = min(1.0, stationarity_score)
        else:
            stationarity_score = 0.5

        # Series class
        if n < 12:
            series_class = "short"
        elif n < 36:
            series_class = "medium"
        else:
            series_class = "long"

        # Regime detection
        from src.engines.forecast_v2.regime import RegimeDetector
        detector = RegimeDetector()
        regime_info = detector.get_regime_info(values)

        # Method recommendation
        profile = {
            "n": n,
            "mean": round(mean_val, 4),
            "std": round(std_val, 4),
            "trend_strength": round(trend_strength, 4),
            "seasonality_strength": round(seasonality_strength, 4),
            "autocorrelation_lag1": round(ac1, 4),
            "zero_fraction": round(zero_fraction, 4),
            "stationarity_score": round(stationarity_score, 4),
            "series_class": series_class,
            "regime_change_detected": regime_info["change_point_detected"],
            "last_change_point": regime_info["change_points"][-1]
                if regime_info["change_points"] else None,
        }

        profile["recommended_methods"] = self.recommend_methods(profile)
        return profile

    def recommend_methods(self, profile: dict) -> List[str]:
        """
        Based on data profile, return ordered list of recommended methods.
        """
        n = profile.get("n", 0)
        methods = []

        if n < 3:
            return []

        # Always include basic methods
        methods.append("linear")
        methods.append("ses")

        if n >= 5:
            methods.append("holt")
            ts = profile.get("trend_strength", 0.0)
            if ts > 0.3:
                methods.append("damped_holt")

        zf = profile.get("zero_fraction", 0.0)
        if zf > 0.15 and n >= 6:
            methods.append("croston")

        if n >= 6:
            methods.append("theta")

        ac1 = profile.get("autocorrelation_lag1", 0.0)
        if n >= 8 and abs(ac1) > 0.3:
            methods.append("ar")

        ss = profile.get("seasonality_strength", 0.0)
        if n >= 24 and ss > 0.3:
            methods.append("seasonal")

        return methods

    def compute_feature_importance(
        self,
        target_values: np.ndarray,
        exogenous: Dict[str, np.ndarray],
        n_permutations: int = 10,
    ) -> dict:
        """
        Permutation-based feature importance for multivariate forecasts.

        Shuffles each exogenous variable and measures increase in prediction error.
        Higher increase = more important feature.

        Always includes "historical_trend" as the baseline feature.

        Returns:
            {feature_name: importance_percentage} summing to ~100.
        """
        n = len(target_values)
        if n < 6 or not exogenous:
            return {"historical_trend": 100.0}

        # Baseline error: simple linear forecast from target only
        from src.engines.forecast_v2.methods import ForecastMethods
        methods = ForecastMethods()

        hold_out = max(1, n // 5)
        train = target_values[: n - hold_out]
        actual = target_values[n - hold_out :]

        try:
            base_fc, _, _ = methods.forecast_linear(train, hold_out)
            base_error = float(np.mean((base_fc[:len(actual)] - actual) ** 2))
        except Exception:
            return {"historical_trend": 100.0}

        if base_error < 1e-12:
            base_error = 1e-12

        importances = {"historical_trend": 1.0}  # Baseline importance

        rng = np.random.RandomState(42)
        for feature_name, feature_values in exogenous.items():
            if len(feature_values) != n:
                continue

            permuted_errors = []
            for _ in range(n_permutations):
                # Shuffle the feature
                shuffled = feature_values.copy()
                rng.shuffle(shuffled)

                # Compute error with shuffled feature
                # Use the change in feature as predictor of target changes
                delta_target = np.diff(target_values)
                delta_feature = np.diff(shuffled)

                min_len = min(len(delta_target), len(delta_feature))
                if min_len < 3:
                    continue

                x = delta_feature[:min_len]
                y = delta_target[:min_len]
                x_var = float(np.dot(x, x))
                if x_var < 1e-12:
                    continue

                beta = float(np.dot(x, y)) / x_var
                pred = beta * delta_feature[-hold_out:]
                actual_diff = np.diff(actual) if len(actual) > 1 else np.array([0.0])
                min_ph = min(len(pred), len(actual_diff))
                if min_ph > 0:
                    perm_error = float(np.mean((pred[:min_ph] - actual_diff[:min_ph]) ** 2))
                    permuted_errors.append(perm_error)

            if permuted_errors:
                avg_perm_error = sum(permuted_errors) / len(permuted_errors)
                # Importance = how much worse prediction gets when feature is shuffled
                importance = max(0.0, avg_perm_error / base_error - 1.0)
                importances[feature_name] = importance

        # Normalize to percentages
        total = sum(importances.values())
        if total < 1e-12:
            return {"historical_trend": 100.0}

        return {k: round(v / total * 100, 2) for k, v in importances.items()}
