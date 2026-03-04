"""
Monte Carlo Simulation — residual bootstrapping and parametric simulation.

Generates fan chart confidence bands via:
  1. Residual bootstrap: sample historical residuals with replacement
  2. Parametric simulation: assume residuals follow normal or t-distribution

Output: percentile bands (p10, p25, p50, p75, p90) for each forecast period.
"""
import logging
import math
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class MonteCarloSimulator:
    """Monte Carlo simulation for forecast uncertainty quantification."""

    DEFAULT_SIMULATIONS = 1000
    RANDOM_SEED = 42  # For reproducibility in production

    def residual_bootstrap(
        self,
        base_forecast: np.ndarray,
        residuals: np.ndarray,
        n_simulations: int = 1000,
        horizon: Optional[int] = None,
        confidence_score: float = 1.0,
    ) -> dict:
        """
        Non-parametric bootstrap: sample residuals with replacement.

        Accounts for autocorrelation via AR(1) filtering of sampled residuals.

        Args:
            base_forecast: point forecast array
            residuals: historical residuals from model fit
            n_simulations: number of simulation paths
            horizon: forecast horizon (defaults to len(base_forecast))
            confidence_score: data quality score (0-1), wider bands at low confidence

        Returns:
            {
                "p10": np.ndarray, "p25": np.ndarray, "p50": np.ndarray,
                "p75": np.ndarray, "p90": np.ndarray,
                "mean": np.ndarray, "std": np.ndarray,
            }
        """
        if horizon is None:
            horizon = len(base_forecast)

        fc = base_forecast[:horizon]
        n_res = len(residuals)

        if n_res < 2:
            # Not enough residuals, return base forecast as all percentiles
            return self._flat_result(fc, horizon)

        # Compute autocorrelation of residuals (for AR(1) filter)
        res_mean = np.mean(residuals)
        centered = residuals - res_mean
        var = float(np.dot(centered, centered))
        if var < 1e-12:
            rho = 0.0
        else:
            cov = float(np.dot(centered[:-1], centered[1:]))
            rho = cov / var
        rho = max(-0.95, min(0.95, rho))  # Clamp for stability

        # Confidence adjustment: widen residuals at low confidence
        conf_mult = 1.0 / max(confidence_score, 0.1)

        rng = np.random.RandomState(self.RANDOM_SEED)
        paths = np.zeros((n_simulations, horizon))

        for sim in range(n_simulations):
            sampled = rng.choice(residuals, size=horizon, replace=True)

            # Apply AR(1) filter to preserve autocorrelation structure
            filtered = np.zeros(horizon)
            filtered[0] = sampled[0]
            sqrt_factor = math.sqrt(max(1.0 - rho ** 2, 0.01))
            for h in range(1, horizon):
                filtered[h] = rho * filtered[h - 1] + sampled[h] * sqrt_factor

            # Scale by confidence and horizon (uncertainty grows with sqrt(h))
            for h in range(horizon):
                horizon_scale = math.sqrt(h + 1)
                filtered[h] *= conf_mult * horizon_scale

            paths[sim] = fc + filtered

        return self._compute_percentiles(paths, fc, horizon)

    def parametric_simulation(
        self,
        base_forecast: np.ndarray,
        residual_std: float,
        horizon: Optional[int] = None,
        n_simulations: int = 1000,
        distribution: str = "normal",
        confidence_score: float = 1.0,
    ) -> dict:
        """
        Parametric simulation: assume residuals follow a distribution.

        Args:
            base_forecast: point forecast array
            residual_std: standard deviation of residuals
            horizon: forecast horizon
            n_simulations: number of paths
            distribution: "normal" or "t" (heavier tails for economic data)
            confidence_score: data quality score

        Returns: same as residual_bootstrap
        """
        if horizon is None:
            horizon = len(base_forecast)

        fc = base_forecast[:horizon]
        conf_mult = 1.0 / max(confidence_score, 0.1)

        rng = np.random.RandomState(self.RANDOM_SEED + 1)
        paths = np.zeros((n_simulations, horizon))

        for sim in range(n_simulations):
            if distribution == "t":
                # Student-t with df=5 (heavier tails than normal)
                noise = rng.standard_t(df=5, size=horizon)
            else:
                noise = rng.randn(horizon)

            for h in range(horizon):
                spread = residual_std * math.sqrt(h + 1) * conf_mult
                paths[sim, h] = fc[h] + noise[h] * spread

        return self._compute_percentiles(paths, fc, horizon)

    def fan_chart_data(self, mc_result: dict) -> List[dict]:
        """
        Convert Monte Carlo output to fan chart format for API response.

        Returns:
            [
                {"period_offset": 1, "p10": ..., "p25": ..., "p50": ..., "p75": ..., "p90": ...},
                ...
            ]
        """
        horizon = len(mc_result.get("p50", []))
        chart = []
        for h in range(horizon):
            chart.append({
                "period_offset": h + 1,
                "p10": round(float(mc_result["p10"][h]), 4),
                "p25": round(float(mc_result["p25"][h]), 4),
                "p50": round(float(mc_result["p50"][h]), 4),
                "p75": round(float(mc_result["p75"][h]), 4),
                "p90": round(float(mc_result["p90"][h]), 4),
            })
        return chart

    def _compute_percentiles(
        self,
        paths: np.ndarray,
        base_forecast: np.ndarray,
        horizon: int,
    ) -> dict:
        """Compute percentile bands from simulation paths."""
        return {
            "p10": np.percentile(paths, 10, axis=0),
            "p25": np.percentile(paths, 25, axis=0),
            "p50": np.percentile(paths, 50, axis=0),
            "p75": np.percentile(paths, 75, axis=0),
            "p90": np.percentile(paths, 90, axis=0),
            "mean": np.mean(paths, axis=0),
            "std": np.std(paths, axis=0),
        }

    def _flat_result(self, fc: np.ndarray, horizon: int) -> dict:
        """Return flat result when insufficient data for simulation."""
        return {
            "p10": fc.copy(),
            "p25": fc.copy(),
            "p50": fc.copy(),
            "p75": fc.copy(),
            "p90": fc.copy(),
            "mean": fc.copy(),
            "std": np.zeros(horizon),
        }
