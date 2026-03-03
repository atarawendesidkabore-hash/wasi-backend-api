"""
DCF Valuation models — ValuationTarget, FinancialStatement, ValuationResult.

Supports three entity types: COMPANY, COUNTRY, INFRASTRUCTURE.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, UniqueConstraint, Numeric,
)
from sqlalchemy.orm import relationship
from src.database.models import Base


class ValuationTarget(Base):
    """Entity being valued — company, country economy, or infrastructure project."""
    __tablename__ = "valuation_targets"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    entity_type = Column(String(20), nullable=False, index=True)  # COMPANY|COUNTRY|INFRASTRUCTURE
    name = Column(String(200), nullable=False)
    ticker = Column(String(20), index=True)
    exchange_code = Column(String(10))              # NGX|GSE|BRVM
    country_code = Column(String(2), nullable=False, index=True)
    sector = Column(String(50))
    currency = Column(String(5), default="XOF")

    # Company-specific
    shares_outstanding = Column(Numeric(18, 0, asdecimal=False))
    current_share_price = Column(Float)
    market_cap_usd = Column(Numeric(18, 2, asdecimal=False))
    net_debt_usd = Column(Numeric(18, 2, asdecimal=False))

    # Infrastructure-specific
    project_start_date = Column(Date)
    project_end_date = Column(Date)
    total_project_cost_usd = Column(Numeric(18, 2, asdecimal=False))

    status = Column(String(20), default="active")   # active|archived
    notes = Column(Text)
    confidence = Column(Float, default=0.70)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    financials = relationship("FinancialStatement", back_populates="target",
                              order_by="FinancialStatement.fiscal_year")
    valuations = relationship("ValuationResult", back_populates="target",
                              order_by="ValuationResult.calculated_at.desc()")


class FinancialStatement(Base):
    """Annual financial data for a valuation target (manual input or scraped)."""
    __tablename__ = "financial_statements"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(String(36), ForeignKey("valuation_targets.target_id"),
                       nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False)
    statement_type = Column(String(20), default="ACTUAL")  # ACTUAL|PROJECTED|ESTIMATE

    # Income statement
    revenue_usd = Column(Numeric(18, 2, asdecimal=False))
    revenue_growth_pct = Column(Float)
    cogs_usd = Column(Numeric(18, 2, asdecimal=False))
    gross_profit_usd = Column(Numeric(18, 2, asdecimal=False))
    gross_margin_pct = Column(Float)
    operating_expenses_usd = Column(Numeric(18, 2, asdecimal=False))
    ebit_usd = Column(Numeric(18, 2, asdecimal=False))
    ebit_margin_pct = Column(Float)
    ebitda_usd = Column(Numeric(18, 2, asdecimal=False))
    ebitda_margin_pct = Column(Float)
    depreciation_amortization_usd = Column(Numeric(18, 2, asdecimal=False))
    interest_expense_usd = Column(Numeric(18, 2, asdecimal=False))
    net_income_usd = Column(Numeric(18, 2, asdecimal=False))
    tax_rate_pct = Column(Float)

    # Balance sheet
    total_debt_usd = Column(Numeric(18, 2, asdecimal=False))
    cash_equivalents_usd = Column(Numeric(18, 2, asdecimal=False))
    net_working_capital_usd = Column(Numeric(18, 2, asdecimal=False))
    total_assets_usd = Column(Numeric(18, 2, asdecimal=False))
    total_equity_usd = Column(Numeric(18, 2, asdecimal=False))

    # Cash flow
    capex_usd = Column(Numeric(18, 2, asdecimal=False))
    change_in_nwc_usd = Column(Numeric(18, 2, asdecimal=False))

    # Country economy proxies
    gdp_usd = Column(Numeric(18, 2, asdecimal=False))
    gov_spending_usd = Column(Numeric(18, 2, asdecimal=False))
    tax_revenue_usd = Column(Numeric(18, 2, asdecimal=False))
    trade_surplus_usd = Column(Numeric(18, 2, asdecimal=False))

    # Infrastructure proxies
    project_revenue_usd = Column(Numeric(18, 2, asdecimal=False))
    construction_cost_usd = Column(Numeric(18, 2, asdecimal=False))
    maintenance_cost_usd = Column(Numeric(18, 2, asdecimal=False))

    data_source = Column(String(50), default="manual_input")
    confidence = Column(Float, default=0.80)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    target = relationship("ValuationTarget", back_populates="financials")

    __table_args__ = (
        UniqueConstraint("target_id", "fiscal_year", "statement_type"),
    )


class ValuationResult(Base):
    """Cached DCF valuation output — one row per scenario per run."""
    __tablename__ = "valuation_results"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(String(36), unique=True, nullable=False, index=True)
    target_id = Column(String(36), ForeignKey("valuation_targets.target_id"),
                       nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    scenario = Column(String(10), nullable=False, default="BASE")  # BULL|BASE|BEAR|BLENDED

    # WACC inputs
    wacc_pct = Column(Float, nullable=False)
    cost_of_equity_pct = Column(Float)
    cost_of_debt_pct = Column(Float)
    country_risk_premium_pct = Column(Float)
    beta = Column(Float)

    # DCF core
    projection_years = Column(Integer, default=5)
    projected_fcfs_json = Column(Text)           # JSON array of per-year projections
    pv_fcfs_total_usd = Column(Numeric(18, 2, asdecimal=False))

    # Terminal value
    terminal_growth_rate_pct = Column(Float)
    terminal_value_gordon_usd = Column(Numeric(18, 2, asdecimal=False))
    terminal_value_exit_usd = Column(Numeric(18, 2, asdecimal=False))
    exit_multiple = Column(Float)
    pv_terminal_gordon_usd = Column(Numeric(18, 2, asdecimal=False))
    pv_terminal_exit_usd = Column(Numeric(18, 2, asdecimal=False))
    terminal_blend_weight_gordon = Column(Float, default=0.50)

    # Enterprise & equity
    enterprise_value_usd = Column(Numeric(18, 2, asdecimal=False))
    net_debt_usd = Column(Numeric(18, 2, asdecimal=False))
    equity_value_usd = Column(Numeric(18, 2, asdecimal=False))
    implied_share_price = Column(Float)
    current_share_price = Column(Float)
    upside_pct = Column(Float)

    # Sensitivity (JSON grid)
    sensitivity_wacc_growth_json = Column(Text)

    # Quality & metadata
    confidence = Column(Float, default=0.70)
    risk_score = Column(Float)
    data_quality = Column(String(10), default="medium")
    narrative = Column(Text)
    analyst_review_required = Column(Boolean, default=True)

    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    engine_version = Column(String(10), default="1.0")

    target = relationship("ValuationTarget", back_populates="valuations")
    user = relationship("User")
