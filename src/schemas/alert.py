"""Pydantic schemas for Alert/Webhook endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_EVENT_SOURCES = {
    "WASI_INDEX", "COMMODITY_PRICE", "NEWS_EVENT",
    "DIVERGENCE", "FORECAST_DEVIATION", "CONFIDENCE_DROP",
}

VALID_CONDITIONS = {
    "DROP_GT", "RISE_GT", "CHANGE_GT", "BELOW", "ABOVE", "ANY",
}


class AlertRuleCreateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    event_source: str
    country_code: Optional[str] = Field(None, min_length=2, max_length=2)
    commodity_code: Optional[str] = Field(None, max_length=20)
    event_type_filter: Optional[str] = Field(None, max_length=30)
    condition: str
    threshold_value: Optional[float] = None
    webhook_url: str = Field(..., max_length=500)
    webhook_secret: Optional[str] = Field(None, max_length=128)
    cooldown_seconds: int = Field(default=3600, ge=60, le=86400)
    credit_cost_per_delivery: float = Field(default=1.0, ge=0.0, le=10.0)

    @field_validator("event_source")
    @classmethod
    def validate_event_source(cls, v: str) -> str:
        v = v.upper()
        if v not in VALID_EVENT_SOURCES:
            raise ValueError(f"event_source must be one of {sorted(VALID_EVENT_SOURCES)}")
        return v

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str) -> str:
        v = v.upper()
        if v not in VALID_CONDITIONS:
            raise ValueError(f"condition must be one of {sorted(VALID_CONDITIONS)}")
        return v


class AlertRuleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    webhook_url: Optional[str] = Field(None, max_length=500)
    webhook_secret: Optional[str] = Field(None, max_length=128)
    condition: Optional[str] = None
    threshold_value: Optional[float] = None
    cooldown_seconds: Optional[int] = Field(None, ge=60, le=86400)
    is_active: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: int
    name: Optional[str] = None
    event_source: str
    country_code: Optional[str] = None
    commodity_code: Optional[str] = None
    event_type_filter: Optional[str] = None
    condition: str
    threshold_value: Optional[float] = None
    webhook_url: str
    cooldown_seconds: int
    credit_cost_per_delivery: float
    is_active: bool
    last_evaluated_at: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertRuleCreateResponse(AlertRuleResponse):
    """Returned only on creation — includes the webhook_secret once."""
    webhook_secret: str


class AlertDeliveryResponse(BaseModel):
    id: int
    rule_id: int
    event_source: str
    status: str
    http_status_code: Optional[int] = None
    error_message: Optional[str] = None
    attempt_count: int
    credits_charged: float
    created_at: datetime
    delivered_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertDeliveryDetailResponse(AlertDeliveryResponse):
    """Single delivery view — includes the full payload."""
    payload_json: str


class AlertStatusResponse(BaseModel):
    total_rules: int
    active_rules: int
    total_deliveries: int
    deliveries_last_24h: int
    credits_spent_last_24h: float
    failed_deliveries_last_24h: int
