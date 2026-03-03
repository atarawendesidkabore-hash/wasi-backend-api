"""Pydantic v2 schemas for FX Analytics API responses."""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class FxRateItem(BaseModel):
    currency_code: str
    rate_to_usd: float
    rate_to_eur: Optional[float] = None
    rate_to_xof: Optional[float] = None
    pct_change_1d: Optional[float] = None
    pct_change_7d: Optional[float] = None
    pct_change_30d: Optional[float] = None
    regime: str
    rate_date: date
    data_source: str = "unknown"
    confidence: float = 1.0


class FxRatesResponse(BaseModel):
    as_of: datetime
    currencies: list[FxRateItem]
    count: int
    xof_eur_peg: float = 655.957
    cve_eur_peg: float = 110.265


class FxRateHistoryItem(BaseModel):
    rate_date: date
    rate_to_usd: float
    rate_to_eur: Optional[float] = None
    rate_to_xof: Optional[float] = None
    pct_change_1d: Optional[float] = None


class FxRateHistoryResponse(BaseModel):
    currency_code: str
    regime: str
    days: int
    history: list[FxRateHistoryItem]


class FxCurrencyProfile(BaseModel):
    currency_code: str
    regime: str
    trend: str
    latest_rate_usd: float
    latest_rate_eur: Optional[float] = None
    latest_rate_xof: Optional[float] = None
    rate_date: date
    volatility_7d: Optional[float] = None
    volatility_30d: Optional[float] = None
    volatility_90d: Optional[float] = None
    annualized_vol: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    pct_change_1d: Optional[float] = None
    pct_change_7d: Optional[float] = None
    pct_change_30d: Optional[float] = None
    countries: list[str]


class FxVolatilityItem(BaseModel):
    currency_code: str
    regime: str
    volatility_7d: Optional[float] = None
    volatility_30d: Optional[float] = None
    volatility_90d: Optional[float] = None
    annualized_vol: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    trend: str = "STABLE"


class FxVolatilityResponse(BaseModel):
    as_of: datetime
    currencies: list[FxVolatilityItem]
    avg_floating_vol: Optional[float] = None
    avg_pegged_vol: Optional[float] = None


class TradeCostResponse(BaseModel):
    from_country: str
    to_country: str
    from_currency: str
    to_currency: str
    amount_usd: float
    spread_cost_usd: float
    volatility_premium_usd: float
    total_fx_cost_usd: float
    fx_cost_pct: float
    same_currency_zone: bool
    settlement_risk: str


class RegimeZoneStats(BaseModel):
    zone_name: str
    currencies: list[str]
    countries: list[str]
    avg_annualized_vol: Optional[float] = None
    avg_30d_vol: Optional[float] = None


class RegimeDivergenceResponse(BaseModel):
    as_of: datetime
    cfa_zone: RegimeZoneStats
    floating_zone: RegimeZoneStats
    special_zone: RegimeZoneStats
    divergence_ratio: Optional[float] = None
    interpretation: str


class FxDashboardCountry(BaseModel):
    country_code: str
    currency: str
    regime: str
    wasi_weight: float
    rate_to_usd: Optional[float] = None
    pct_change_1d: Optional[float] = None
    annualized_vol: Optional[float] = None
    fx_risk_score: float


class FxDashboardResponse(BaseModel):
    as_of: datetime
    total_countries: int
    weighted_fx_risk: float
    countries: list[FxDashboardCountry]
    regime_summary: dict


class FxRefreshResponse(BaseModel):
    status: str
    currencies_updated: int
    errors: int
    data_source: str
    refreshed_at: datetime
