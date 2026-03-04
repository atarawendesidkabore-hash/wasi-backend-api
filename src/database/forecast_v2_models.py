"""
Forecast Engine v2.0 Models — extended tables for adaptive ensemble forecasting.

New tables (additive, no changes to existing ForecastResult):
  1. ForecastModel      — fitted model registry with performance metrics
  2. BacktestResult     — walk-forward validation results
  3. ForecastScenario   — what-if scenario analysis results
  4. ForecastAccuracyLog — actual-vs-forecast tracking
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime

from src.database.models import Base


class ForecastModel(Base):
    """Registry of fitted forecast models with performance metrics."""
    __tablename__ = "forecast_models"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String(36), unique=True, nullable=False, index=True)

    # Target this model was fitted for
    target_type = Column(String(30), nullable=False, index=True)
    target_code = Column(String(20), nullable=False, index=True)

    # Model specification
    method_name = Column(String(30), nullable=False)
    parameters = Column(Text, default="{}")
    engine_version = Column(String(10), default="2.0")

    # Performance metrics (from backtesting)
    rmse = Column(Float)
    mae = Column(Float)
    mape = Column(Float)
    directional_accuracy = Column(Float)
    coverage_68 = Column(Float)
    coverage_95 = Column(Float)

    # Adaptive ensemble weight (dynamically computed)
    ensemble_weight = Column(Float, default=0.0)

    # Data characteristics this model was fitted on
    data_points_used = Column(Integer)
    trend_strength = Column(Float)
    seasonality_strength = Column(Float)
    series_length_class = Column(String(10))

    # Lifecycle
    is_active = Column(Boolean, default=True)
    fitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "target_type", "target_code", "method_name",
            name="uq_forecast_model",
        ),
    )


class BacktestResult(Base):
    """Walk-forward validation results for forecast methods."""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, index=True)
    backtest_id = Column(String(36), unique=True, nullable=False, index=True)

    target_type = Column(String(30), nullable=False, index=True)
    target_code = Column(String(20), nullable=False, index=True)

    # Configuration
    method_name = Column(String(30), nullable=False)
    window_type = Column(String(10), nullable=False)
    min_train_size = Column(Integer, nullable=False)
    test_horizon = Column(Integer, nullable=False)
    n_splits = Column(Integer, nullable=False)

    # Aggregate metrics across all splits
    avg_rmse = Column(Float)
    avg_mae = Column(Float)
    avg_mape = Column(Float)
    avg_directional_accuracy = Column(Float)
    avg_coverage_68 = Column(Float)
    avg_coverage_95 = Column(Float)

    # Per-split detail (JSON array)
    split_details = Column(Text, default="[]")

    # Forecast horizon analysis (JSON: {1: {rmse: ...}, 2: {rmse: ...}})
    horizon_degradation = Column(Text, default="{}")

    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    engine_version = Column(String(10), default="2.0")


class ForecastScenario(Base):
    """What-if scenario analysis results."""
    __tablename__ = "forecast_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Scenario definition
    scenario_name = Column(String(100), nullable=False)
    scenario_type = Column(String(30), nullable=False)
    target_type = Column(String(30), nullable=False)
    target_code = Column(String(20), nullable=False)

    # Input shocks (JSON)
    shocks = Column(Text, nullable=False)

    # Results (JSON arrays of periods)
    baseline_forecast = Column(Text, default="[]")
    scenario_forecast = Column(Text, default="[]")
    impact_delta = Column(Text, default="[]")

    horizon_months = Column(Integer, nullable=False)
    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")


class ForecastAccuracyLog(Base):
    """Tracks forecast accuracy when actual values arrive."""
    __tablename__ = "forecast_accuracy_log"

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(30), nullable=False, index=True)
    target_code = Column(String(20), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    forecast_value = Column(Float, nullable=False)
    actual_value = Column(Float, nullable=False)
    error = Column(Float)
    abs_error = Column(Float)
    pct_error = Column(Float)
    within_1sigma = Column(Boolean)
    within_2sigma = Column(Boolean)

    method = Column(String(20))
    horizon_months = Column(Integer)
    forecast_calculated_at = Column(DateTime)
    logged_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint(
            "target_type", "target_code", "period_date", "horizon_months",
            name="uq_accuracy_log",
        ),
    )
