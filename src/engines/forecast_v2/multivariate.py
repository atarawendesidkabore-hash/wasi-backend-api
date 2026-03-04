"""
Multivariate Forecasting — cross-correlation models and VAR(1).

Models leading indicator relationships between ECOWAS economic variables:
  - Commodity prices -> country WASI indices
  - Stock market indices -> WASI indices
  - News event magnitudes -> country WASI indices

Also provides a simple VAR(1) model for the Big 4 countries
(NG, CI, GH, SN = 75% of WASI composite weight).
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CrossCorrelationModel:
    """
    Models leading indicator relationships between data series.
    Uses lagged cross-correlation to identify optimal lead/lag,
    then regression-based forecast adjustment.
    """

    # Known commodity-country sensitivity map (domain knowledge)
    COMMODITY_COUNTRY_MAP = {
        "COCOA": [("CI", 0.6), ("GH", 0.3)],
        "BRENT": [("NG", 0.7), ("GH", 0.15)],
        "GOLD": [("ML", 0.4), ("BF", 0.3), ("GN", 0.2)],
        "COTTON": [("BF", 0.3), ("ML", 0.2), ("BJ", 0.2)],
        "COFFEE": [("CI", 0.15), ("GN", 0.1)],
        "IRON_ORE": [("SL", 0.3), ("GN", 0.2), ("LR", 0.2)],
    }

    # Stock exchange to country mapping
    STOCK_COUNTRY_MAP = {
        "NGX": [("NG", 0.5)],
        "GSE": [("GH", 0.4)],
        "BRVM": [("CI", 0.3), ("SN", 0.25), ("BJ", 0.15), ("TG", 0.1)],
    }

    def compute_cross_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray,
        max_lag: int = 6,
    ) -> dict:
        """
        Compute cross-correlation at different lags.

        Positive lag means x leads y (x is the leading indicator).

        Returns:
            {
                "lag_correlations": {lag: correlation},
                "optimal_lag": int,
                "optimal_correlation": float,
            }
        """
        n = min(len(x), len(y))
        if n < 4:
            return {"lag_correlations": {}, "optimal_lag": 0, "optimal_correlation": 0.0}

        x_use = x[:n]
        y_use = y[:n]

        # Normalize
        x_mean, x_std = np.mean(x_use), np.std(x_use)
        y_mean, y_std = np.mean(y_use), np.std(y_use)

        if x_std < 1e-12 or y_std < 1e-12:
            return {"lag_correlations": {}, "optimal_lag": 0, "optimal_correlation": 0.0}

        x_norm = (x_use - x_mean) / x_std
        y_norm = (y_use - y_mean) / y_std

        lag_corr = {}
        for lag in range(0, min(max_lag + 1, n - 2)):
            if lag == 0:
                ccf = float(np.dot(x_norm, y_norm) / n)
            else:
                ccf = float(np.dot(x_norm[:-lag], y_norm[lag:]) / (n - lag))
            lag_corr[lag] = round(ccf, 4)

        if not lag_corr:
            return {"lag_correlations": {}, "optimal_lag": 0, "optimal_correlation": 0.0}

        optimal_lag = max(lag_corr, key=lambda k: abs(lag_corr[k]))
        return {
            "lag_correlations": lag_corr,
            "optimal_lag": optimal_lag,
            "optimal_correlation": lag_corr[optimal_lag],
        }

    def compute_leading_indicator_adjustment(
        self,
        target_values: np.ndarray,
        indicator_values: np.ndarray,
        indicator_forecast: np.ndarray,
        optimal_lag: int,
        sensitivity: float,
    ) -> np.ndarray:
        """
        Compute forecast adjustment from a leading indicator.

        Uses simple regression: delta_target = beta * delta_indicator(lagged) + eps

        Args:
            target_values: historical WASI index for a country
            indicator_values: historical commodity/stock values
            indicator_forecast: forecasted indicator values
            optimal_lag: optimal lead time (months)
            sensitivity: commodity-country sensitivity coefficient

        Returns:
            Adjustment array to add to baseline forecast.
        """
        min_len = min(len(target_values), len(indicator_values))
        if min_len < 4:
            return np.zeros(len(indicator_forecast))

        target = target_values[:min_len]
        indicator = indicator_values[:min_len]

        # Compute differences
        delta_target = np.diff(target)
        delta_indicator = np.diff(indicator)

        # Align with lag
        if optimal_lag > 0 and optimal_lag < len(delta_indicator):
            x = delta_indicator[: -optimal_lag] if optimal_lag > 0 else delta_indicator
            y = delta_target[optimal_lag:]
        else:
            x = delta_indicator
            y = delta_target[: len(x)]

        min_xy = min(len(x), len(y))
        if min_xy < 2:
            return np.zeros(len(indicator_forecast))

        x = x[:min_xy]
        y = y[:min_xy]

        # Simple regression: y = beta * x
        x_var = float(np.dot(x, x))
        if x_var < 1e-12:
            return np.zeros(len(indicator_forecast))

        beta = float(np.dot(x, y)) / x_var

        # Apply to indicator forecast
        if len(indicator_forecast) > 1:
            delta_fc = np.diff(indicator_forecast)
            adjustment = beta * sensitivity * delta_fc
            # Pad to match forecast length (first period has zero adjustment)
            adjustment = np.concatenate([[0.0], adjustment])
        else:
            adjustment = np.zeros(len(indicator_forecast))

        # Cumulative adjustment (changes compound)
        adjustment = np.cumsum(adjustment)

        return adjustment

    def get_country_indicators(self, country_code: str) -> List[dict]:
        """
        Return list of relevant leading indicators for a country.
        Uses domain knowledge maps.
        """
        indicators = []

        for commodity, countries in self.COMMODITY_COUNTRY_MAP.items():
            for cc, sensitivity in countries:
                if cc == country_code:
                    indicators.append({
                        "type": "commodity",
                        "code": commodity,
                        "sensitivity": sensitivity,
                    })

        for exchange, countries in self.STOCK_COUNTRY_MAP.items():
            for cc, sensitivity in countries:
                if cc == country_code:
                    indicators.append({
                        "type": "stock",
                        "code": exchange,
                        "sensitivity": sensitivity,
                    })

        return indicators

    def compute_total_adjustment(
        self,
        country_code: str,
        target_values: np.ndarray,
        exogenous: Dict[str, dict],
        horizon: int,
    ) -> Tuple[np.ndarray, List[dict]]:
        """
        Compute total multivariate adjustment for a country forecast.

        Args:
            country_code: ECOWAS country code
            target_values: historical WASI index
            exogenous: {indicator_code: {"values": np.ndarray, "forecast": np.ndarray}}
            horizon: forecast horizon

        Returns:
            (total_adjustment_array, list of indicator details used)
        """
        total_adjustment = np.zeros(horizon)
        indicators_used = []

        relevant = self.get_country_indicators(country_code)
        for ind in relevant:
            code = ind["code"]
            sensitivity = ind["sensitivity"]

            if code not in exogenous:
                continue

            ind_data = exogenous[code]
            ind_values = ind_data.get("values")
            ind_forecast = ind_data.get("forecast")

            if ind_values is None or ind_forecast is None:
                continue
            if len(ind_values) < 4 or len(ind_forecast) < 1:
                continue

            # Compute cross-correlation to find optimal lag
            cc_result = self.compute_cross_correlation(
                ind_values, target_values, max_lag=6,
            )
            optimal_lag = cc_result["optimal_lag"]
            correlation = cc_result["optimal_correlation"]

            # Only use if correlation is meaningful (|r| > 0.2)
            if abs(correlation) < 0.2:
                continue

            adjustment = self.compute_leading_indicator_adjustment(
                target_values, ind_values, ind_forecast[:horizon],
                optimal_lag, sensitivity,
            )

            total_adjustment[:len(adjustment)] += adjustment[:horizon]
            indicators_used.append({
                "code": code,
                "type": ind["type"],
                "sensitivity": sensitivity,
                "lag": optimal_lag,
                "correlation": correlation,
                "adjustment_mean": round(float(np.mean(adjustment[:horizon])), 4),
            })

        return total_adjustment, indicators_used


class SimpleVAR:
    """
    Vector Autoregression for the Big 4 countries (NG, CI, GH, SN = 75% of WASI).

    Models interdependence: NG trade affects CI port activity, etc.

    VAR(1): Y_t = c + A * Y_{t-1} + epsilon
    where Y_t = [NG_index_t, CI_index_t, GH_index_t, SN_index_t]
    """

    BIG_4 = ["NG", "CI", "GH", "SN"]

    def fit(
        self,
        data: Dict[str, np.ndarray],
    ) -> Optional[dict]:
        """
        Fit VAR(1) model via OLS.

        Args:
            data: {country_code: time_series_array} for each of the Big 4

        Returns:
            {
                "A": 4x4 coefficient matrix,
                "intercept": 4-vector,
                "residuals": dict of residual arrays,
                "countries": list of country codes,
            }
            or None if insufficient data.
        """
        # Ensure all Big 4 present with same length
        series = []
        countries = []
        min_len = float("inf")
        for cc in self.BIG_4:
            if cc not in data or len(data[cc]) < 4:
                logger.warning("VAR: Missing or short data for %s", cc)
                return None
            series.append(data[cc])
            countries.append(cc)
            min_len = min(min_len, len(data[cc]))

        min_len = int(min_len)
        k = len(countries)  # should be 4

        # Build matrix Y (k x T)
        Y = np.zeros((k, min_len))
        for i, s in enumerate(series):
            Y[i, :] = s[:min_len]

        # X = [1; Y_{t-1}] (augmented for intercept)
        T = min_len - 1
        if T < k + 2:
            return None

        # Y_next = Y[:, 1:]
        Y_next = Y[:, 1:]  # k x T

        # X = [ones; Y[:, :-1]]  -> (k+1) x T
        X = np.vstack([np.ones((1, T)), Y[:, :-1]])

        # OLS: B = Y_next @ X.T @ inv(X @ X.T)
        try:
            XXT_inv = np.linalg.inv(X @ X.T)
            B = Y_next @ X.T @ XXT_inv
        except np.linalg.LinAlgError:
            logger.warning("VAR: Singular matrix, cannot fit")
            return None

        intercept = B[:, 0]  # first column is intercept
        A = B[:, 1:]  # remaining columns are VAR coefficients

        # Compute residuals
        Y_pred = B @ X
        residuals_matrix = Y_next - Y_pred

        residuals = {}
        for i, cc in enumerate(countries):
            residuals[cc] = residuals_matrix[i, :]

        return {
            "A": A,
            "intercept": intercept,
            "residuals": residuals,
            "countries": countries,
        }

    def forecast(
        self,
        fitted: dict,
        horizon: int,
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Recursive h-step VAR forecast.

        y_{t+1} = c + A * y_t

        Returns {country_code: forecast_array} or None.
        """
        if fitted is None:
            return None

        A = fitted["A"]
        intercept = fitted["intercept"]
        countries = fitted["countries"]

        # Last known values (from the residuals, the last column of the data)
        # We need the last actual values — reconstruct from fitted
        # Use intercept + A @ last_residual_column
        # Actually, we need the raw last values
        # Better: pass last_values separately or store in fitted
        # For now, use residuals to infer (but this is approximate)
        # In practice, the orchestrator passes last_values

        return None  # Must be called via forecast_from_last

    def forecast_from_last(
        self,
        fitted: dict,
        last_values: Dict[str, float],
        horizon: int,
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Forecast from known last values.

        Args:
            fitted: output of fit()
            last_values: {country_code: last_index_value}
            horizon: number of steps ahead

        Returns:
            {country_code: np.ndarray of forecasts}
        """
        if fitted is None:
            return None

        A = fitted["A"]
        intercept = fitted["intercept"]
        countries = fitted["countries"]
        k = len(countries)

        # Build last Y vector
        y_t = np.array([last_values.get(cc, 50.0) for cc in countries])

        forecasts = {cc: [] for cc in countries}
        for h in range(horizon):
            y_next = intercept + A @ y_t
            for i, cc in enumerate(countries):
                forecasts[cc].append(float(y_next[i]))
            y_t = y_next

        for cc in countries:
            forecasts[cc] = np.array(forecasts[cc])

        return forecasts
