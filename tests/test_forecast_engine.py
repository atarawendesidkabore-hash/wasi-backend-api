"""
Pure unit tests for the ForecastEngine — no database dependency.
"""
import pytest
from datetime import date
from src.engines.forecast_engine import ForecastEngine


@pytest.fixture
def engine():
    return ForecastEngine()


# ── Weight Invariants ────────────────────────────────────────────

def test_ensemble_weights_sum_to_one(engine):
    total = sum(engine.ENSEMBLE_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9


# ── Linear Trend ─────────────────────────────────────────────────

def test_linear_constant_series(engine):
    result = engine.forecast_ensemble([50, 50, 50, 50, 50], horizon=3)
    for p in result["periods"]:
        assert abs(p["forecast_value"] - 50.0) < 2.0


def test_linear_upward_trend(engine):
    result = engine.forecast_ensemble([10, 20, 30, 40, 50], horizon=3)
    assert result["periods"][0]["forecast_value"] > 50.0


def test_linear_downward_trend(engine):
    result = engine.forecast_ensemble([50, 40, 30, 20, 10], horizon=3)
    assert result["periods"][0]["forecast_value"] < 10.0


# ── SES ──────────────────────────────────────────────────────────

def test_ses_constant_series(engine):
    _, residuals = engine._forecast_ses(
        __import__("numpy").array([50.0, 50.0, 50.0, 50.0, 50.0]),
        horizon=3,
    )
    assert all(abs(r) < 1e-9 for r in residuals)


# ── Holt ─────────────────────────────────────────────────────────

def test_holt_upward_trend(engine):
    import numpy as np
    fc, _ = engine._forecast_holt(np.array([10.0, 20.0, 30.0, 40.0, 50.0]), horizon=3)
    assert fc[0] > 50.0
    assert fc[1] > fc[0]


def test_holt_requires_minimum_points(engine):
    result = engine.forecast_ensemble([10, 20, 30], horizon=3)
    assert "holt" not in result["methods_used"]
    assert "linear" in result["methods_used"]
    assert "ses" in result["methods_used"]


# ── Ensemble ─────────────────────────────────────────────────────

def test_ensemble_all_methods_used(engine):
    result = engine.forecast_ensemble([10, 20, 30, 40, 50], horizon=3)
    assert "linear" in result["methods_used"]
    assert "ses" in result["methods_used"]
    assert "holt" in result["methods_used"]


def test_ensemble_two_methods_short_series(engine):
    result = engine.forecast_ensemble([10, 20, 30, 40], horizon=3)
    assert len(result["methods_used"]) == 2
    assert "holt" not in result["methods_used"]


# ── Insufficient Data ────────────────────────────────────────────

def test_insufficient_data_returns_error(engine):
    result = engine.forecast_ensemble([10, 20], horizon=3)
    assert result["periods"] == []
    assert "error" in result
    assert result["data_points_used"] == 2


def test_insufficient_data_single_point(engine):
    result = engine.forecast_ensemble([42], horizon=3)
    assert result["periods"] == []
    assert "error" in result


# ── Confidence Bands ─────────────────────────────────────────────

def test_confidence_bands_widen_with_horizon(engine):
    result = engine.forecast_ensemble([10, 20, 30, 40, 50], horizon=6)
    spread_1 = result["periods"][0]["upper_1sigma"] - result["periods"][0]["lower_1sigma"]
    spread_6 = result["periods"][5]["upper_1sigma"] - result["periods"][5]["lower_1sigma"]
    assert spread_6 > spread_1


def test_confidence_score_affects_bands(engine):
    result_high = engine.forecast_ensemble([10, 20, 30, 40, 50], horizon=3, confidence_score=0.9)
    result_low = engine.forecast_ensemble([10, 20, 30, 40, 50], horizon=3, confidence_score=0.3)
    spread_high = result_high["periods"][0]["upper_1sigma"] - result_high["periods"][0]["lower_1sigma"]
    spread_low = result_low["periods"][0]["upper_1sigma"] - result_low["periods"][0]["lower_1sigma"]
    assert spread_low > spread_high


# ── Metadata ─────────────────────────────────────────────────────

def test_forecast_country_index_includes_metadata(engine):
    dates = [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1),
             date(2024, 4, 1), date(2024, 5, 1)]
    result = engine.forecast_country_index("NG", [40, 45, 50, 48, 52], dates, 6)
    assert result["target_type"] == "country_index"
    assert result["target_code"] == "NG"
    assert result["last_actual_date"] == "2024-05-01"
    assert result["last_actual_value"] == 52.0


def test_forecast_commodity_includes_metadata(engine):
    dates = [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1),
             date(2024, 4, 1), date(2024, 5, 1)]
    result = engine.forecast_commodity("COCOA", [3200, 3400, 3600, 3500, 3700], dates, 3)
    assert result["target_type"] == "commodity_price"
    assert result["target_code"] == "COCOA"


def test_forecast_macro_includes_indicator(engine):
    result = engine.forecast_macro("NG", "gdp_growth", [3.0, 3.5, 2.8, 3.2, 3.6], [2020, 2021, 2022, 2023, 2024], 2)
    assert result["target_type"] == "macro_gdp_growth"
    assert result["indicator"] == "gdp_growth"
    assert result["last_actual_year"] == 2024
