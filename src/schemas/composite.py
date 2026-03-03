from pydantic import BaseModel, ConfigDict, computed_field
from datetime import date, datetime
from typing import Optional

from src.utils.periods import quarter_label


class CompositeResponse(BaseModel):
    id: int
    period_date: date
    composite_value: float
    trend_direction: Optional[str] = None
    mom_change: Optional[float] = None
    yoy_change: Optional[float] = None
    std_dev: Optional[float] = None
    annualized_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    coefficient_of_variation: Optional[float] = None
    countries_included: Optional[int] = None
    calculated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def quarter(self) -> str:
        """Quarter label derived from period_date, e.g. 'Q2-2026'."""
        return quarter_label(self.period_date)


class CompositeReport(BaseModel):
    latest: CompositeResponse
    history_12m: list[CompositeResponse]
    country_contributions: dict[str, float]
    generated_at: datetime
    concentration_warning: Optional[str] = None  # T6: single-country distortion alert
