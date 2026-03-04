"""add_forecast_v2_tables

Revision ID: 5265dbdea763
Revises: 9c0a738cbe8a
Create Date: 2026-03-04 21:31:30.156449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5265dbdea763"
down_revision: Union[str, Sequence[str], None] = "9c0a738cbe8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 4 forecast v2 tables: models, backtests, scenarios, accuracy log."""
    op.create_table("forecast_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_code", sa.String(length=20), nullable=False),
        sa.Column("method_name", sa.String(length=30), nullable=False),
        sa.Column("parameters", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.String(length=10), nullable=True),
        sa.Column("rmse", sa.Float(), nullable=True),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("mape", sa.Float(), nullable=True),
        sa.Column("directional_accuracy", sa.Float(), nullable=True),
        sa.Column("coverage_68", sa.Float(), nullable=True),
        sa.Column("coverage_95", sa.Float(), nullable=True),
        sa.Column("ensemble_weight", sa.Float(), nullable=True),
        sa.Column("data_points_used", sa.Integer(), nullable=True),
        sa.Column("trend_strength", sa.Float(), nullable=True),
        sa.Column("seasonality_strength", sa.Float(), nullable=True),
        sa.Column("series_length_class", sa.String(length=10), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("fitted_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id"),
        sa.UniqueConstraint("target_type", "target_code", "method_name", name="uq_forecast_model"),
    )
    with op.batch_alter_table("forecast_models", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_forecast_models_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_models_model_id"), ["model_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_forecast_models_target_code"), ["target_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_models_target_type"), ["target_type"], unique=False)

    op.create_table("backtest_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_code", sa.String(length=20), nullable=False),
        sa.Column("method_name", sa.String(length=30), nullable=False),
        sa.Column("window_type", sa.String(length=10), nullable=False),
        sa.Column("min_train_size", sa.Integer(), nullable=False),
        sa.Column("test_horizon", sa.Integer(), nullable=False),
        sa.Column("n_splits", sa.Integer(), nullable=False),
        sa.Column("avg_rmse", sa.Float(), nullable=True),
        sa.Column("avg_mae", sa.Float(), nullable=True),
        sa.Column("avg_mape", sa.Float(), nullable=True),
        sa.Column("avg_directional_accuracy", sa.Float(), nullable=True),
        sa.Column("avg_coverage_68", sa.Float(), nullable=True),
        sa.Column("avg_coverage_95", sa.Float(), nullable=True),
        sa.Column("split_details", sa.Text(), nullable=True),
        sa.Column("horizon_degradation", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.Column("engine_version", sa.String(length=10), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("backtest_id"),
    )
    with op.batch_alter_table("backtest_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_backtest_results_backtest_id"), ["backtest_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_backtest_results_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_backtest_results_target_code"), ["target_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_backtest_results_target_type"), ["target_type"], unique=False)

    op.create_table("forecast_scenarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scenario_name", sa.String(length=100), nullable=False),
        sa.Column("scenario_type", sa.String(length=30), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_code", sa.String(length=20), nullable=False),
        sa.Column("shocks", sa.Text(), nullable=False),
        sa.Column("baseline_forecast", sa.Text(), nullable=True),
        sa.Column("scenario_forecast", sa.Text(), nullable=True),
        sa.Column("impact_delta", sa.Text(), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scenario_id"),
    )
    with op.batch_alter_table("forecast_scenarios", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_forecast_scenarios_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_scenarios_scenario_id"), ["scenario_id"], unique=True)
        batch_op.create_index(batch_op.f("ix_forecast_scenarios_user_id"), ["user_id"], unique=False)

    op.create_table("forecast_accuracy_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_code", sa.String(length=20), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("forecast_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=False),
        sa.Column("error", sa.Float(), nullable=True),
        sa.Column("abs_error", sa.Float(), nullable=True),
        sa.Column("pct_error", sa.Float(), nullable=True),
        sa.Column("within_1sigma", sa.Boolean(), nullable=True),
        sa.Column("within_2sigma", sa.Boolean(), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("horizon_months", sa.Integer(), nullable=True),
        sa.Column("forecast_calculated_at", sa.DateTime(), nullable=True),
        sa.Column("logged_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_type", "target_code", "period_date", "horizon_months", name="uq_accuracy_log"),
    )
    with op.batch_alter_table("forecast_accuracy_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_forecast_accuracy_log_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_accuracy_log_period_date"), ["period_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_accuracy_log_target_code"), ["target_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_forecast_accuracy_log_target_type"), ["target_type"], unique=False)


def downgrade() -> None:
    """Remove forecast v2 tables."""
    with op.batch_alter_table("forecast_accuracy_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_forecast_accuracy_log_target_type"))
        batch_op.drop_index(batch_op.f("ix_forecast_accuracy_log_target_code"))
        batch_op.drop_index(batch_op.f("ix_forecast_accuracy_log_period_date"))
        batch_op.drop_index(batch_op.f("ix_forecast_accuracy_log_id"))
    op.drop_table("forecast_accuracy_log")

    with op.batch_alter_table("forecast_scenarios", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_forecast_scenarios_user_id"))
        batch_op.drop_index(batch_op.f("ix_forecast_scenarios_scenario_id"))
        batch_op.drop_index(batch_op.f("ix_forecast_scenarios_id"))
    op.drop_table("forecast_scenarios")

    with op.batch_alter_table("backtest_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_backtest_results_target_type"))
        batch_op.drop_index(batch_op.f("ix_backtest_results_target_code"))
        batch_op.drop_index(batch_op.f("ix_backtest_results_id"))
        batch_op.drop_index(batch_op.f("ix_backtest_results_backtest_id"))
    op.drop_table("backtest_results")

    with op.batch_alter_table("forecast_models", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_forecast_models_target_type"))
        batch_op.drop_index(batch_op.f("ix_forecast_models_target_code"))
        batch_op.drop_index(batch_op.f("ix_forecast_models_model_id"))
        batch_op.drop_index(batch_op.f("ix_forecast_models_id"))
    op.drop_table("forecast_models")
