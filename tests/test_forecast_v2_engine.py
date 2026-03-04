"""
Unit tests for Forecast Engine v2.0 — all components.

Tests run without database, using synthetic data only.
"""
import math
import numpy as np
import pytest

from src.engines.forecast_v2.methods import ForecastMethods
from src.engines.forecast_v2.seasonal import SeasonalDecomposer
from src.engines.forecast_v2.ensemble import AdaptiveEnsemble
from src.engines.forecast_v2.regime import RegimeDetector
from src.engines.forecast_v2.multivariate import CrossCorrelationModel, SimpleVAR
from src.engines.forecast_v2.scenarios import ScenarioEngine
from src.engines.forecast_v2.backtesting import WalkForwardBacktester
from src.engines.forecast_v2.montecarlo import MonteCarloSimulator
from src.engines.forecast_v2.diagnostics import ModelDiagnostics
from src.engines.forecast_v2 import ForecastEngineV2


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def methods():
    return ForecastMethods()


@pytest.fixture
def upward_trend():
    """Upward trending series: 10, 12, 14, ..., 30 (11 points)."""
    return np.array([10 + 2 * i for i in range(11)], dtype=float)


@pytest.fixture
def constant_series():
    """Constant series of 50s (12 points)."""
    return np.full(12, 50.0)


@pytest.fixture
def seasonal_series():
    """36 months with trend + seasonality."""
    t = np.arange(36)
    trend = 50.0 + 0.5 * t
    seasonal = 5.0 * np.sin(2 * np.pi * t / 12)
    return trend + seasonal


@pytest.fixture
def intermittent_series():
    """Sparse data with many zeros (Croston's test case)."""
    return np.array([0, 0, 5, 0, 0, 0, 8, 0, 0, 3, 0, 0, 6, 0, 0], dtype=float)


# ── Method Tests ──────────────────────────────────────────────────

class TestForecastMethods:

    def test_linear_upward_trend(self, methods, upward_trend):
        fc, res, params = methods.forecast_linear(upward_trend, 3)
        assert len(fc) == 3
        assert fc[0] > upward_trend[-1]  # continues upward
        assert params["slope"] > 0

    def test_ses_constant_series(self, methods, constant_series):
        fc, res, params = methods.forecast_ses(constant_series, 6)
        assert len(fc) == 6
        # SES on constant should forecast ~50
        for v in fc:
            assert abs(v - 50.0) < 2.0

    def test_holt_upward_trend(self, methods, upward_trend):
        fc, res, params = methods.forecast_holt(upward_trend, 3)
        assert len(fc) == 3
        assert fc[0] > upward_trend[-1]

    def test_damped_holt_convergence(self, methods, upward_trend):
        fc, res, params = methods.forecast_damped_holt(upward_trend, 20)
        # Damped holt should converge (later values flatten)
        assert len(fc) == 20
        diffs = np.diff(fc)
        # Later diffs should be smaller than earlier diffs (damping effect)
        assert abs(diffs[-1]) < abs(diffs[0]) + 0.01

    def test_croston_intermittent(self, methods, intermittent_series):
        fc, res, params = methods.forecast_croston(intermittent_series, 6)
        assert len(fc) == 6
        # Should produce a positive flat forecast
        assert fc[0] > 0
        assert all(v == fc[0] for v in fc)  # Croston gives flat forecast

    def test_theta_method(self, methods, upward_trend):
        fc, res, params = methods.forecast_theta(upward_trend, 3)
        assert len(fc) == 3
        assert fc[0] > upward_trend[-1]  # continues upward

    def test_ar_with_autocorrelation(self, methods):
        # Create AR(1) process: y_t = 0.8 * y_{t-1} + noise
        rng = np.random.RandomState(42)
        n = 30
        y = np.zeros(n)
        y[0] = 50.0
        for i in range(1, n):
            y[i] = 0.8 * y[i - 1] + rng.randn() * 2.0
        fc, res, params = methods.forecast_ar(y, 3)
        assert len(fc) == 3
        assert params.get("p") is not None


# ── Seasonal Tests ────────────────────────────────────────────────

class TestSeasonalDecomposer:

    def test_decomposition_reconstruction(self, seasonal_series):
        decomposer = SeasonalDecomposer()
        decomp = decomposer.decompose(seasonal_series, period=12)
        # Reconstruction: trend + seasonal + residual ≈ original
        reconstructed = decomp["trend"] + decomp["seasonal"] + decomp["residual"]
        np.testing.assert_allclose(reconstructed, seasonal_series, atol=1e-6)

    def test_seasonal_strength(self, seasonal_series):
        decomposer = SeasonalDecomposer()
        strength = decomposer.seasonal_strength(seasonal_series, period=12)
        assert 0.0 <= strength <= 1.0
        assert strength > 0.3  # Our synthetic series has clear seasonality

    def test_trend_strength(self, seasonal_series):
        decomposer = SeasonalDecomposer()
        strength = decomposer.trend_strength(seasonal_series, period=12)
        assert 0.0 <= strength <= 1.0
        assert strength > 0.3  # Our synthetic series has clear trend


# ── Ensemble Tests ────────────────────────────────────────────────

class TestAdaptiveEnsemble:

    def test_inverse_error_weights(self):
        ensemble = AdaptiveEnsemble()
        errors = {
            "good_method": [0.1, 0.2, 0.15],    # low errors
            "bad_method": [1.0, 1.5, 2.0],       # high errors
        }
        weights = ensemble.compute_adaptive_weights(errors, strategy="inverse_error")
        assert weights["good_method"] > weights["bad_method"]
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_trimmed_mean_drops_worst(self):
        ensemble = AdaptiveEnsemble()
        errors = {
            "a": [0.5], "b": [1.0], "c": [10.0],  # c is worst
        }
        weights = ensemble.compute_adaptive_weights(errors, strategy="trimmed_mean")
        assert "c" not in weights
        assert "a" in weights and "b" in weights

    def test_method_selection(self):
        ensemble = AdaptiveEnsemble()
        profile = {
            "n": 30,
            "trend_strength": 0.5,
            "seasonality_strength": 0.1,
            "autocorrelation_lag1": 0.6,
            "zero_fraction": 0.0,
        }
        values = np.arange(30, dtype=float)
        methods = ensemble.select_methods(values, profile)
        assert "linear" in methods
        assert "ses" in methods
        assert "ar" in methods  # high autocorrelation


# ── Regime Tests ──────────────────────────────────────────────────

class TestRegimeDetector:

    def test_cusum_detects_mean_shift(self):
        detector = RegimeDetector()
        # Series with mean shift at index 20
        values = np.concatenate([
            np.full(20, 50.0) + np.random.RandomState(42).randn(20) * 1.0,
            np.full(20, 70.0) + np.random.RandomState(43).randn(20) * 1.0,
        ])
        change_points = detector.detect_cusum(values, threshold=3.0)
        assert len(change_points) > 0
        # Should detect near index 20
        assert any(15 <= cp <= 30 for cp in change_points)

    def test_no_false_positive_on_stable(self):
        detector = RegimeDetector()
        values = np.full(40, 50.0) + np.random.RandomState(42).randn(40) * 0.5
        change_points = detector.detect_cusum(values, threshold=5.0)
        # Stable series should have few or no change points
        assert len(change_points) <= 1


# ── Multivariate Tests ────────────────────────────────────────────

class TestCrossCorrelation:

    def test_identifies_known_lag(self):
        model = CrossCorrelationModel()
        # x leads y by 2 periods
        rng = np.random.RandomState(42)
        x = rng.randn(30).cumsum()
        y = np.zeros(30)
        y[2:] = x[:-2] * 0.8  # y follows x with lag 2

        result = model.compute_cross_correlation(x, y, max_lag=6)
        assert result["optimal_lag"] == 2
        assert result["optimal_correlation"] > 0.5

    def test_country_indicators(self):
        model = CrossCorrelationModel()
        indicators = model.get_country_indicators("CI")
        codes = [i["code"] for i in indicators]
        assert "COCOA" in codes  # CI is major cocoa exporter


class TestSimpleVAR:

    def test_var_fit_and_forecast(self):
        var = SimpleVAR()
        rng = np.random.RandomState(42)
        data = {
            "NG": 50 + rng.randn(20).cumsum(),
            "CI": 45 + rng.randn(20).cumsum(),
            "GH": 40 + rng.randn(20).cumsum(),
            "SN": 35 + rng.randn(20).cumsum(),
        }
        fitted = var.fit(data)
        assert fitted is not None
        assert fitted["A"].shape == (4, 4)

        last_values = {cc: float(v[-1]) for cc, v in data.items()}
        forecasts = var.forecast_from_last(fitted, last_values, horizon=6)
        assert forecasts is not None
        for cc in ["NG", "CI", "GH", "SN"]:
            assert len(forecasts[cc]) == 6


# ── Scenario Tests ────────────────────────────────────────────────

class TestScenarioEngine:

    def test_oil_shock_negative_impact(self):
        engine = ScenarioEngine()
        baseline = [
            {"period_offset": i + 1, "forecast_value": 50.0 + i * 0.5}
            for i in range(12)
        ]
        result = engine.run_scenario(
            baseline, "oil_shock", target_code="NG",
        )
        assert result["scenario_type"] == "oil_shock"
        # NG should be negatively impacted
        assert result["impact_summary"]["max_negative_impact"] < 0

    def test_list_presets(self):
        engine = ScenarioEngine()
        presets = engine.list_presets()
        assert len(presets) >= 4
        types = [p["scenario_type"] for p in presets]
        assert "oil_shock" in types
        assert "cocoa_boom" in types


# ── Backtesting Tests ─────────────────────────────────────────────

class TestBacktesting:

    def test_expanding_window_splits(self):
        bt = WalkForwardBacktester()
        methods = ForecastMethods()
        values = np.arange(30, dtype=float) + 10
        result = bt.run_backtest(
            values, "linear", methods.forecast_linear,
            min_train_size=10, test_horizon=3,
        )
        assert result["n_splits"] > 0
        assert result["avg_rmse"] is not None

    def test_all_methods_comparison(self):
        bt = WalkForwardBacktester()
        methods = ForecastMethods()
        values = np.array([10 + 2 * i + np.sin(i) for i in range(30)])
        method_fns = {
            "linear": methods.forecast_linear,
            "ses": methods.forecast_ses,
        }
        result = bt.run_all_methods_backtest(
            values, method_fns, min_train_size=8, test_horizon=3,
        )
        assert result["best_method"] is not None
        assert len(result["ranking"]) == 2


# ── Monte Carlo Tests ─────────────────────────────────────────────

class TestMonteCarlo:

    def test_percentile_ordering(self):
        mc = MonteCarloSimulator()
        base = np.array([50.0, 51.0, 52.0, 53.0])
        residuals = np.random.RandomState(42).randn(20) * 2.0
        result = mc.residual_bootstrap(base, residuals, n_simulations=500)
        # p10 < p25 < p50 < p75 < p90 at each horizon
        for h in range(4):
            assert result["p10"][h] <= result["p25"][h]
            assert result["p25"][h] <= result["p50"][h]
            assert result["p50"][h] <= result["p75"][h]
            assert result["p75"][h] <= result["p90"][h]

    def test_fan_chart_format(self):
        mc = MonteCarloSimulator()
        base = np.array([50.0, 52.0, 54.0])
        residuals = np.random.RandomState(42).randn(15) * 3.0
        result = mc.residual_bootstrap(base, residuals)
        chart = mc.fan_chart_data(result)
        assert len(chart) == 3
        assert chart[0]["period_offset"] == 1
        assert "p10" in chart[0]


# ── Diagnostics Tests ─────────────────────────────────────────────

class TestDiagnostics:

    def test_profile_series(self, upward_trend):
        diag = ModelDiagnostics()
        profile = diag.profile_series(upward_trend)
        assert profile["n"] == 11
        assert profile["trend_strength"] > 0.5  # clear trend
        assert "linear" in profile["recommended_methods"]
        assert profile["series_class"] == "short"

    def test_profile_seasonal(self, seasonal_series):
        diag = ModelDiagnostics()
        profile = diag.profile_series(seasonal_series)
        assert profile["n"] == 36
        assert profile["series_class"] == "long"


# ── Full Engine Tests ─────────────────────────────────────────────

class TestForecastEngineV2:

    def test_backward_compatible_output(self, upward_trend):
        """v2 engine returns all v1 required fields."""
        engine = ForecastEngineV2()
        result = engine.forecast_ensemble(list(upward_trend), horizon=6)

        # v1 required fields
        assert "data_points_used" in result
        assert "horizon" in result
        assert "methods_used" in result
        assert "ensemble_weights" in result
        assert "residual_std" in result
        assert "confidence_score" in result
        assert "periods" in result
        assert "method_forecasts" in result

        # v2 extension fields
        assert "engine_version" in result
        assert result["engine_version"] == "2.0"
        assert "data_profile" in result
        assert "regime_info" in result
        assert "fan_chart" in result

    def test_ensemble_produces_forecasts(self, upward_trend):
        engine = ForecastEngineV2()
        result = engine.forecast_ensemble(list(upward_trend), horizon=6)
        assert len(result["periods"]) == 6
        assert result["periods"][0]["forecast_value"] > 0
        assert len(result["methods_used"]) >= 2

    def test_insufficient_data(self):
        engine = ForecastEngineV2()
        result = engine.forecast_ensemble([10.0, 20.0], horizon=3)
        assert "error" in result
        assert result["methods_used"] == []

    def test_country_index_method(self, upward_trend):
        engine = ForecastEngineV2()
        from datetime import date
        dates = [date(2024, i + 1, 1) for i in range(len(upward_trend))]
        result = engine.forecast_country_index(
            "NG", list(upward_trend), dates, horizon_months=6,
        )
        assert result["target_type"] == "country_index"
        assert result["target_code"] == "NG"
        assert len(result["periods"]) == 6

    def test_fan_chart_in_periods(self, upward_trend):
        engine = ForecastEngineV2()
        result = engine.forecast_ensemble(
            list(upward_trend), horizon=6, include_montecarlo=True,
        )
        # Fan chart should have percentiles
        if result.get("fan_chart"):
            assert len(result["fan_chart"]) == 6
            assert "p10" in result["fan_chart"][0]
