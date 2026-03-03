"""
Pydantic v2 schemas for the DCF Valuation Engine.
"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ── Request Schemas ──────────────────────────────────────────────

class CreateTargetRequest(BaseModel):
    entity_type: str = Field(..., pattern="^(COMPANY|COUNTRY|INFRASTRUCTURE)$")
    name: str = Field(..., min_length=2, max_length=200)
    ticker: Optional[str] = None
    exchange_code: Optional[str] = Field(None, pattern="^(NGX|GSE|BRVM)$")
    country_code: str = Field(..., min_length=2, max_length=2)
    sector: Optional[str] = None
    currency: str = Field(default="XOF", max_length=5)
    shares_outstanding: Optional[int] = Field(None, ge=0)
    current_share_price: Optional[float] = Field(None, ge=0)
    net_debt_usd: Optional[float] = None
    project_start_date: Optional[date] = None
    project_end_date: Optional[date] = None
    total_project_cost_usd: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class UpdateTargetRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    ticker: Optional[str] = None
    sector: Optional[str] = None
    shares_outstanding: Optional[int] = Field(None, ge=0)
    current_share_price: Optional[float] = Field(None, ge=0)
    net_debt_usd: Optional[float] = None
    notes: Optional[str] = None


class SubmitFinancialsRequest(BaseModel):
    fiscal_year: int = Field(..., ge=2000, le=2035)
    statement_type: str = Field(default="ACTUAL", pattern="^(ACTUAL|PROJECTED|ESTIMATE)$")

    # Income statement
    revenue_usd: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    cogs_usd: Optional[float] = None
    gross_profit_usd: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    operating_expenses_usd: Optional[float] = None
    ebit_usd: Optional[float] = None
    ebit_margin_pct: Optional[float] = None
    ebitda_usd: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None
    depreciation_amortization_usd: Optional[float] = None
    interest_expense_usd: Optional[float] = None
    net_income_usd: Optional[float] = None
    tax_rate_pct: Optional[float] = None

    # Balance sheet
    total_debt_usd: Optional[float] = None
    cash_equivalents_usd: Optional[float] = None
    net_working_capital_usd: Optional[float] = None
    total_assets_usd: Optional[float] = None
    total_equity_usd: Optional[float] = None

    # Cash flow
    capex_usd: Optional[float] = None
    change_in_nwc_usd: Optional[float] = None

    # Country economy proxies
    gdp_usd: Optional[float] = None
    gov_spending_usd: Optional[float] = None
    tax_revenue_usd: Optional[float] = None
    trade_surplus_usd: Optional[float] = None

    # Infrastructure proxies
    project_revenue_usd: Optional[float] = None
    construction_cost_usd: Optional[float] = None
    maintenance_cost_usd: Optional[float] = None


class RunValuationRequest(BaseModel):
    target_id: str
    projection_years: int = Field(default=5, ge=3, le=10)
    terminal_growth_pct: float = Field(default=2.5, ge=0.0, le=5.0)
    exit_multiple: float = Field(default=8.0, ge=3.0, le=25.0)
    gordon_weight: float = Field(default=0.50, ge=0.0, le=1.0)
    custom_wacc_pct: Optional[float] = None
    custom_beta: Optional[float] = None
    revenue_growth_overrides: Optional[list[float]] = None
    scenario_weights: Optional[dict[str, float]] = None
    include_sensitivity: bool = True


class RunCountryValuationRequest(BaseModel):
    projection_years: int = Field(default=5, ge=3, le=10)
    terminal_growth_pct: float = Field(default=2.5, ge=0.0, le=5.0)
    exit_multiple: float = Field(default=8.0, ge=3.0, le=25.0)
    gordon_weight: float = Field(default=0.50, ge=0.0, le=1.0)
    include_sensitivity: bool = True


# ── Response Schemas ─────────────────────────────────────────────

class FCFProjectionPeriod(BaseModel):
    year: int
    revenue_usd: float
    revenue_growth_pct: float
    ebit_usd: float
    ebit_margin_pct: float
    ebitda_usd: float
    nopat_usd: float
    da_usd: float
    capex_usd: float
    delta_nwc_usd: float
    fcf_usd: float
    discount_factor: float
    pv_fcf_usd: float


class TerminalValueResult(BaseModel):
    gordon_tv_usd: float
    gordon_pv_usd: float
    exit_tv_usd: float
    exit_pv_usd: float
    terminal_growth_pct: float
    exit_multiple: float
    tv_discount_factor: float


class WACCResult(BaseModel):
    wacc_pct: float
    cost_of_equity_pct: float
    cost_of_debt_pct: float
    risk_free_rate_pct: float
    equity_risk_premium_pct: float
    country_risk_premium_pct: float
    beta: float
    equity_ratio_pct: float
    debt_ratio_pct: float
    corporate_tax_rate_pct: float


class SensitivityCell(BaseModel):
    wacc_pct: float
    terminal_growth_pct: float
    enterprise_value_usd: Optional[float] = None
    equity_value_usd: Optional[float] = None
    implied_share_price: Optional[float] = None


class ScenarioResult(BaseModel):
    scenario: str
    weight: float
    wacc: WACCResult
    projections: Optional[list[FCFProjectionPeriod]] = None
    terminal_value: Optional[TerminalValueResult] = None
    pv_fcfs_total_usd: float
    enterprise_value_usd: float
    equity_value_usd: float
    implied_share_price: Optional[float] = None
    upside_pct: Optional[float] = None
    net_debt_usd: float = 0.0
    blended_pv_terminal_usd: Optional[float] = None
    gordon_weight: Optional[float] = None


class ValuationResponse(BaseModel):
    result_id: str
    target_id: str
    target_name: str
    entity_type: str
    country_code: str
    scenarios: list[ScenarioResult]
    blended: ScenarioResult
    sensitivity_table: Optional[list[SensitivityCell]] = None
    risk_score: Optional[float] = None
    narrative: str
    analyst_review_required: bool = True
    calculated_at: datetime
    engine_version: str = "1.0"

    model_config = ConfigDict(from_attributes=True)


class TargetResponse(BaseModel):
    target_id: str
    entity_type: str
    name: str
    ticker: Optional[str] = None
    exchange_code: Optional[str] = None
    country_code: str
    sector: Optional[str] = None
    currency: str = "XOF"
    shares_outstanding: Optional[int] = None
    current_share_price: Optional[float] = None
    net_debt_usd: Optional[float] = None
    project_start_date: Optional[date] = None
    project_end_date: Optional[date] = None
    total_project_cost_usd: Optional[float] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TargetListResponse(BaseModel):
    targets: list[TargetResponse]
    total: int


class FinancialStatementResponse(BaseModel):
    id: int
    target_id: str
    fiscal_year: int
    statement_type: str
    revenue_usd: Optional[float] = None
    ebit_usd: Optional[float] = None
    ebitda_usd: Optional[float] = None
    depreciation_amortization_usd: Optional[float] = None
    net_income_usd: Optional[float] = None
    tax_rate_pct: Optional[float] = None
    capex_usd: Optional[float] = None
    change_in_nwc_usd: Optional[float] = None
    total_debt_usd: Optional[float] = None
    cash_equivalents_usd: Optional[float] = None
    net_working_capital_usd: Optional[float] = None
    data_source: str
    confidence: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
