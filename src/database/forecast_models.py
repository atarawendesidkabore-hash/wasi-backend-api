"""
Forecast Result Model — cached forecast projections.

Stores pre-computed forecasts so API queries return cached results
without re-running engine calculations on every request.
Refreshed daily at 04:00 UTC by the forecast scheduler task.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Date,
    UniqueConstraint,
)
from datetime import timezone, datetime
from src.database.models import Base


class ForecastResult(Base):
    __tablename__ = "forecast_results"

    id = Column(Integer, primary_key=True, index=True)

    # What is being forecast
    target_type = Column(String(30), nullable=False, index=True)
    target_code = Column(String(20), nullable=False, index=True)

    # The forecasted period
    period_date = Column(Date, nullable=False, index=True)
    horizon_months = Column(Integer, nullable=False)

    # Forecast output
    forecast_value = Column(Numeric(18, 4, asdecimal=False), nullable=False)
    lower_1sigma = Column(Numeric(18, 4, asdecimal=False))
    upper_1sigma = Column(Numeric(18, 4, asdecimal=False))
    lower_2sigma = Column(Numeric(18, 4, asdecimal=False))
    upper_2sigma = Column(Numeric(18, 4, asdecimal=False))

    # Method metadata
    method = Column(String(20), nullable=False, default="ensemble")
    methods_used = Column(String(100))
    data_points_used = Column(Integer)
    residual_std = Column(Float)

    # Source data quality
    confidence = Column(Float, default=1.0)
    last_actual_date = Column(Date)
    last_actual_value = Column(Float)

    # Metadata
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    engine_version = Column(String(10), default="1.0")

    __table_args__ = (
        UniqueConstraint(
            "target_type", "target_code", "period_date", "horizon_months",
            name="uq_forecast_target_period_horizon",
        ),
    )
