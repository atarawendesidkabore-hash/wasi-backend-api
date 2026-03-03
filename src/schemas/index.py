from pydantic import BaseModel, ConfigDict, computed_field
from datetime import date, datetime
from typing import Optional

from src.utils.periods import quarter_label


def _confidence_indicator(confidence: Optional[float]) -> str:
    """Map a 0.0–1.0 confidence score to a color indicator."""
    if confidence is None:
        return "grey"
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"


class CountryIndexResponse(BaseModel):
    id: int
    country_id: int
    period_date: date
    index_value: float
    shipping_score: Optional[float] = None
    trade_score: Optional[float] = None
    infrastructure_score: Optional[float] = None
    economic_score: Optional[float] = None
    confidence: Optional[float] = None
    data_quality: Optional[str] = None
    data_source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def quarter(self) -> str:
        """Quarter label derived from period_date, e.g. 'Q1-2026'."""
        return quarter_label(self.period_date)

    @computed_field
    @property
    def confidence_indicator(self) -> str:
        """Colour indicator for UI: green / yellow / red / grey."""
        return _confidence_indicator(self.confidence)


class AllIndicesResponse(BaseModel):
    period_date: date
    indices: dict[str, float]
    confidence_indicators: dict[str, str] = {}   # {country_code: "green"|"yellow"|"red"|"grey"}
    generated_at: datetime
