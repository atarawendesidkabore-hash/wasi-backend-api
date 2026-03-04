"""
Regime Detection — change-point detection for forecasting regime switching.

Two methods:
  1. CUSUM (Cumulative Sum Control Chart)
  2. Moving-window variance ratio

When a regime change is detected, the forecast engine can focus on data
from the current regime only, avoiding contamination from old patterns.
"""
import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class RegimeDetector:
    """Simple change-point detection for time-series regime switching."""

    def detect_cusum(
        self,
        values: np.ndarray,
        threshold: float = 4.0,
    ) -> List[int]:
        """
        CUSUM change-point detection.

        S_t = max(0, S_{t-1} + (x_t - target) - allowance)
        Change point when S_t > threshold * sigma.

        Returns list of change-point indices.
        """
        n = len(values)
        if n < 6:
            return []

        target = float(np.mean(values))
        sigma = float(np.std(values, ddof=1))
        if sigma < 1e-12:
            return []

        allowance = 0.5 * sigma
        detection_threshold = threshold * sigma

        change_points = []
        s_pos = 0.0  # Upward shift detector
        s_neg = 0.0  # Downward shift detector

        for t in range(n):
            s_pos = max(0.0, s_pos + (values[t] - target) - allowance)
            s_neg = max(0.0, s_neg - (values[t] - target) - allowance)

            if s_pos > detection_threshold or s_neg > detection_threshold:
                change_points.append(t)
                # Reset after detection
                s_pos = 0.0
                s_neg = 0.0

        return change_points

    def detect_variance_shift(
        self,
        values: np.ndarray,
        window: int = 12,
        ratio_threshold: float = 2.0,
    ) -> List[int]:
        """
        Moving-window variance ratio change-point detection.

        Compare variance of recent window vs historical window.
        Flag when ratio > threshold or ratio < 1/threshold.

        Returns list of indices where variance shifts occur.
        """
        n = len(values)
        if n < 2 * window:
            return []

        change_points = []
        for t in range(window, n - window + 1):
            hist_var = float(np.var(values[t - window : t], ddof=1))
            recent_var = float(np.var(values[t : t + window], ddof=1))

            if hist_var < 1e-12:
                continue

            ratio = recent_var / hist_var
            if ratio > ratio_threshold or ratio < 1.0 / ratio_threshold:
                # Avoid duplicates close together
                if not change_points or t - change_points[-1] >= window // 2:
                    change_points.append(t)

        return change_points

    def get_regime_window(
        self,
        values: np.ndarray,
        min_regime_size: int = 6,
    ) -> np.ndarray:
        """
        Return the subset of values from the last detected change point onward.
        If no change point detected, returns all values.
        Uses both CUSUM and variance shift, takes the latest detection.

        Args:
            values: full time series
            min_regime_size: minimum data points to keep

        Returns:
            Subset of values in the current regime
        """
        cusum_pts = self.detect_cusum(values)
        var_pts = self.detect_variance_shift(values)

        all_pts = sorted(set(cusum_pts + var_pts))

        if not all_pts:
            return values

        # Take the latest change point
        last_cp = all_pts[-1]

        # Ensure minimum regime size
        remaining = len(values) - last_cp
        if remaining < min_regime_size:
            # Try earlier change points
            for cp in reversed(all_pts):
                if len(values) - cp >= min_regime_size:
                    last_cp = cp
                    break
            else:
                return values

        logger.info(
            "Regime change detected at index %d, using %d points from current regime",
            last_cp, len(values) - last_cp,
        )
        return values[last_cp:]

    def get_regime_info(self, values: np.ndarray) -> dict:
        """
        Return regime detection summary for API response.
        """
        cusum_pts = self.detect_cusum(values)
        var_pts = self.detect_variance_shift(values)
        all_pts = sorted(set(cusum_pts + var_pts))

        if not all_pts:
            return {
                "change_point_detected": False,
                "regime_start_index": 0,
                "effective_data_points": len(values),
                "change_points": [],
            }

        regime_window = self.get_regime_window(values)
        regime_start = len(values) - len(regime_window)

        return {
            "change_point_detected": True,
            "regime_start_index": regime_start,
            "effective_data_points": len(regime_window),
            "change_points": all_pts,
        }
