"""
Backtesting Framework — walk-forward validation for forecast methods.

Supports:
  - Expanding window: train on [0..t], test on [t+1..t+h], increment t
  - Sliding window: train on [t-w..t], test on [t+1..t+h], increment t

Metrics:
  - RMSE, MAE, MAPE, directional accuracy
  - Coverage probability (do bands contain actuals?)
  - Horizon degradation analysis
"""
import logging
import math
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class WalkForwardBacktester:
    """Rigorous walk-forward validation framework."""

    def run_backtest(
        self,
        values: np.ndarray,
        method_name: str,
        method_fn: Callable,
        min_train_size: int = 12,
        test_horizon: int = 6,
        window_type: str = "expanding",
        sliding_window_size: Optional[int] = None,
    ) -> dict:
        """
        Walk-forward backtest for a single method.

        Args:
            values: full historical time series
            method_name: name for reporting
            method_fn: callable(values, horizon) -> (forecasts, residuals, params)
            min_train_size: minimum training window
            test_horizon: number of steps to forecast in each split
            window_type: "expanding" or "sliding"
            sliding_window_size: window size for sliding (defaults to min_train_size * 2)

        Returns:
            {
                "method": str,
                "n_splits": int,
                "window_type": str,
                "avg_rmse": float, "avg_mae": float, "avg_mape": float,
                "avg_directional_accuracy": float,
                "avg_coverage_68": float, "avg_coverage_95": float,
                "split_details": [...],
            }
        """
        n = len(values)
        if n < min_train_size + test_horizon:
            return self._insufficient_data(method_name, n)

        if sliding_window_size is None:
            sliding_window_size = min_train_size * 2

        splits = []
        for t in range(min_train_size, n - test_horizon + 1):
            if window_type == "sliding":
                start = max(0, t - sliding_window_size)
                train = values[start:t]
            else:
                train = values[:t]

            actual = values[t : t + test_horizon]

            try:
                forecast, residuals, params = method_fn(train, test_horizon)
            except Exception:
                continue

            fc = forecast[: len(actual)]
            errors = fc - actual

            # Metrics
            rmse = math.sqrt(float(np.mean(errors ** 2)))
            mae = float(np.mean(np.abs(errors)))
            mape = self._safe_mape(actual, fc)

            # Directional accuracy (for h > 1)
            if len(actual) > 1:
                actual_dir = np.sign(np.diff(actual))
                fc_dir = np.sign(np.diff(fc))
                dir_acc = float(np.mean(actual_dir == fc_dir))
            else:
                dir_acc = 0.0

            # Coverage: check if actuals fall within bands
            res_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 1.0
            within_1s = 0
            within_2s = 0
            for h in range(len(actual)):
                spread = res_std * math.sqrt(h + 1)
                if abs(errors[h]) <= spread:
                    within_1s += 1
                if abs(errors[h]) <= 2 * spread:
                    within_2s += 1
            coverage_68 = within_1s / len(actual) if actual.size > 0 else 0.0
            coverage_95 = within_2s / len(actual) if actual.size > 0 else 0.0

            splits.append({
                "split": len(splits),
                "train_size": len(train),
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "mape": round(mape, 4),
                "directional_accuracy": round(dir_acc, 4),
                "coverage_68": round(coverage_68, 4),
                "coverage_95": round(coverage_95, 4),
            })

        if not splits:
            return self._insufficient_data(method_name, n)

        # Aggregate metrics
        avg = lambda key: round(sum(s[key] for s in splits) / len(splits), 4)
        return {
            "method": method_name,
            "n_splits": len(splits),
            "window_type": window_type,
            "min_train_size": min_train_size,
            "test_horizon": test_horizon,
            "avg_rmse": avg("rmse"),
            "avg_mae": avg("mae"),
            "avg_mape": avg("mape"),
            "avg_directional_accuracy": avg("directional_accuracy"),
            "avg_coverage_68": avg("coverage_68"),
            "avg_coverage_95": avg("coverage_95"),
            "split_details": splits,
        }

    def run_all_methods_backtest(
        self,
        values: np.ndarray,
        methods: Dict[str, Callable],
        min_train_size: int = 12,
        test_horizon: int = 6,
        window_type: str = "expanding",
    ) -> dict:
        """
        Run backtest for all provided methods, return comparative results.

        Returns:
            {
                "methods": [backtest_result_per_method, ...],
                "best_method": str,
                "ranking": [{method, rmse, weight}, ...],
            }
        """
        results = []
        for name, fn in methods.items():
            result = self.run_backtest(
                values, name, fn, min_train_size, test_horizon, window_type,
            )
            results.append(result)

        # Rank by RMSE (lower is better)
        valid_results = [r for r in results if r.get("n_splits", 0) > 0]
        if not valid_results:
            return {"methods": results, "best_method": None, "ranking": []}

        valid_results.sort(key=lambda r: r.get("avg_rmse", float("inf")))
        best = valid_results[0]["method"]

        # Compute weights from inverse RMSE
        inv_sum = sum(
            1.0 / max(r["avg_rmse"], 1e-6) for r in valid_results
        )
        ranking = []
        for r in valid_results:
            rmse = r.get("avg_rmse", float("inf"))
            weight = (1.0 / max(rmse, 1e-6)) / inv_sum if inv_sum > 0 else 0.0
            ranking.append({
                "method": r["method"],
                "rmse": rmse,
                "mae": r.get("avg_mae"),
                "weight": round(weight, 4),
            })

        return {"methods": results, "best_method": best, "ranking": ranking}

    def compute_horizon_degradation(
        self,
        values: np.ndarray,
        method_fn: Callable,
        max_horizon: int = 12,
        min_train_size: int = 12,
    ) -> dict:
        """
        Analyze how accuracy degrades as forecast horizon increases.

        Returns {horizon: {rmse, mae, mape}} for h in 1..max_horizon.
        """
        n = len(values)
        horizon_metrics = {}

        for h in range(1, max_horizon + 1):
            errors_at_h = []

            for t in range(min_train_size, n - h):
                train = values[:t]
                actual_h = values[t + h - 1]

                try:
                    forecast, _, _ = method_fn(train, h)
                    if len(forecast) >= h:
                        error = float(forecast[h - 1] - actual_h)
                        errors_at_h.append(error)
                except Exception:
                    continue

            if errors_at_h:
                errors_arr = np.array(errors_at_h)
                horizon_metrics[h] = {
                    "rmse": round(math.sqrt(float(np.mean(errors_arr ** 2))), 4),
                    "mae": round(float(np.mean(np.abs(errors_arr))), 4),
                    "n_samples": len(errors_at_h),
                }

        return horizon_metrics

    def calibrate_confidence_bands(
        self,
        values: np.ndarray,
        method_fn: Callable,
        min_train_size: int = 12,
        test_horizon: int = 6,
    ) -> dict:
        """
        Check if confidence bands are well-calibrated.

        Checks:
          - Do ~68% of actuals fall within 1-sigma?
          - Do ~95% fall within 2-sigma?

        Returns:
            {
                "coverage_68": float (actual coverage at 1-sigma),
                "coverage_95": float (actual coverage at 2-sigma),
                "calibration_factor_68": float (multiply band width by this),
                "calibration_factor_95": float,
                "n_samples": int,
            }
        """
        n = len(values)
        within_1s = 0
        within_2s = 0
        total = 0

        for t in range(min_train_size, n - test_horizon + 1):
            train = values[:t]
            actual = values[t : t + test_horizon]

            try:
                forecast, residuals, _ = method_fn(train, test_horizon)
            except Exception:
                continue

            res_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 1.0

            for h in range(min(len(actual), len(forecast))):
                spread = res_std * math.sqrt(h + 1)
                error = abs(float(forecast[h] - actual[h]))
                if error <= spread:
                    within_1s += 1
                if error <= 2 * spread:
                    within_2s += 1
                total += 1

        if total == 0:
            return {
                "coverage_68": 0.0, "coverage_95": 0.0,
                "calibration_factor_68": 1.0, "calibration_factor_95": 1.0,
                "n_samples": 0,
            }

        cov_68 = within_1s / total
        cov_95 = within_2s / total

        # Calibration factors: if actual coverage is 50% but target is 68%,
        # we need to widen bands by factor = target / actual
        cal_68 = (0.6827 / max(cov_68, 0.01)) if cov_68 < 0.6827 else 1.0
        cal_95 = (0.9545 / max(cov_95, 0.01)) if cov_95 < 0.9545 else 1.0

        # Cap calibration factors to prevent unreasonable widening
        cal_68 = min(cal_68, 3.0)
        cal_95 = min(cal_95, 3.0)

        return {
            "coverage_68": round(cov_68, 4),
            "coverage_95": round(cov_95, 4),
            "calibration_factor_68": round(cal_68, 4),
            "calibration_factor_95": round(cal_95, 4),
            "n_samples": total,
        }

    @staticmethod
    def _safe_mape(actual: np.ndarray, forecast: np.ndarray) -> float:
        """MAPE with zero-protection."""
        mask = np.abs(actual) > 1e-6
        if not np.any(mask):
            return 0.0
        return float(np.mean(np.abs((actual[mask] - forecast[mask]) / actual[mask])) * 100)

    @staticmethod
    def _insufficient_data(method_name: str, n: int) -> dict:
        return {
            "method": method_name,
            "n_splits": 0,
            "window_type": "N/A",
            "avg_rmse": None,
            "avg_mae": None,
            "avg_mape": None,
            "avg_directional_accuracy": None,
            "avg_coverage_68": None,
            "avg_coverage_95": None,
            "split_details": [],
            "error": f"Insufficient data: {n} points",
        }
