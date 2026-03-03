"""
DCF Valuation Module — /api/v3/valuation/

12-step Discounted Cash Flow valuation engine supporting companies,
country economies, and infrastructure projects.

Endpoint credit costs:
  POST /targets                         — 2 credits
  GET  /targets                         — 1 credit
  GET  /targets/{target_id}             — 1 credit
  PUT  /targets/{target_id}             — 2 credits
  DELETE /targets/{target_id}           — 1 credit
  POST /targets/{target_id}/financials  — 3 credits
  GET  /targets/{target_id}/financials  — 1 credit
  POST /run                             — 15 credits
  GET  /results/{result_id}             — 2 credits
  GET  /targets/{target_id}/results     — 3 credits
  POST /country/{cc}                    — 10 credits
  GET  /sensitivity/{result_id}         — 3 credits
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, MacroIndicator, BilateralTrade
from src.database.valuation_models import ValuationTarget, FinancialStatement, ValuationResult
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.wacc_params import POLITICAL_RISK, VALID_WASI_COUNTRIES
from src.engines.valuation_engine import ValuationEngine
from src.schemas.valuation import (
    CreateTargetRequest, UpdateTargetRequest, SubmitFinancialsRequest,
    RunValuationRequest, RunCountryValuationRequest,
    ValuationResponse, TargetResponse, TargetListResponse,
    FinancialStatementResponse, ScenarioResult, WACCResult,
    FCFProjectionPeriod, TerminalValueResult, SensitivityCell,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v3/valuation", tags=["Valuation"])
limiter = Limiter(key_func=get_remote_address)
_engine = ValuationEngine()


# ── Helpers ──────────────────────────────────────────────────────

def _get_user_target(db: Session, target_id: str, user_id: int) -> ValuationTarget:
    target = db.query(ValuationTarget).filter(
        ValuationTarget.target_id == target_id,
        ValuationTarget.user_id == user_id,
        ValuationTarget.status == "active",
    ).first()
    if not target:
        raise HTTPException(404, "Valuation target not found")
    return target


def _extract_financials(target: ValuationTarget, statements: list[FinancialStatement]) -> dict:
    """Convert DB statements into the dict format expected by ValuationEngine."""
    sorted_stmts = sorted(statements, key=lambda s: s.fiscal_year)
    latest = sorted_stmts[-1]

    base_revenue = float(latest.revenue_usd or 0)
    if base_revenue <= 0 and latest.gdp_usd:
        base_revenue = float(latest.gdp_usd)
    if base_revenue <= 0 and latest.project_revenue_usd:
        base_revenue = float(latest.project_revenue_usd)
    if base_revenue <= 0:
        raise HTTPException(422, "Base revenue must be positive (provide revenue_usd, gdp_usd, or project_revenue_usd)")

    # Derive margins
    ebit_margin = 0.15
    if latest.ebit_usd and base_revenue > 0:
        ebit_margin = float(latest.ebit_usd) / base_revenue
    elif latest.ebit_margin_pct is not None:
        ebit_margin = latest.ebit_margin_pct / 100.0

    # D&A as % of revenue
    da_pct = 0.05
    if latest.depreciation_amortization_usd and base_revenue > 0:
        da_pct = float(latest.depreciation_amortization_usd) / base_revenue

    # CapEx as % of revenue
    capex_pct = 0.08
    if latest.capex_usd and base_revenue > 0:
        capex_pct = float(latest.capex_usd) / base_revenue

    # NWC change as % of revenue
    nwc_pct = 0.02
    if latest.change_in_nwc_usd and base_revenue > 0:
        nwc_pct = float(latest.change_in_nwc_usd) / base_revenue

    # Tax rate
    tax_rate = 0.28
    if latest.tax_rate_pct is not None:
        tax_rate = latest.tax_rate_pct / 100.0

    # Revenue growth rates from historical data
    growth_rates = []
    for i in range(1, len(sorted_stmts)):
        prev_rev = sorted_stmts[i - 1].revenue_usd or sorted_stmts[i - 1].gdp_usd or 0
        curr_rev = sorted_stmts[i].revenue_usd or sorted_stmts[i].gdp_usd or 0
        if prev_rev and prev_rev > 0 and curr_rev:
            growth_rates.append((float(curr_rev) - float(prev_rev)) / float(prev_rev))

    if not growth_rates:
        if latest.revenue_growth_pct is not None:
            growth_rates = [latest.revenue_growth_pct / 100.0]
        else:
            growth_rates = [0.05]

    # Project declining growth for forecast years
    recent_g = growth_rates[-1]
    projected_growth = []
    for i in range(10):
        decay = 0.85 ** i
        projected_growth.append(max(0.01, recent_g * decay))

    # Net debt
    net_debt = 0.0
    if target.net_debt_usd is not None:
        net_debt = float(target.net_debt_usd)
    elif latest.total_debt_usd is not None and latest.cash_equivalents_usd is not None:
        net_debt = float(latest.total_debt_usd) - float(latest.cash_equivalents_usd)

    return {
        "base_revenue": base_revenue,
        "base_ebit_margin": ebit_margin,
        "base_da_pct": da_pct,
        "base_capex_pct": capex_pct,
        "base_nwc_change_pct": nwc_pct,
        "tax_rate": tax_rate,
        "revenue_growth_rates": projected_growth,
        "net_debt": net_debt,
        "shares_outstanding": int(target.shares_outstanding) if target.shares_outstanding else None,
        "current_share_price": target.current_share_price,
    }


def _build_scenario_result(result: dict) -> ScenarioResult:
    """Convert engine output dict to ScenarioResult schema."""
    wacc_data = result["wacc"]
    wacc = WACCResult(
        wacc_pct=wacc_data["wacc_pct"],
        cost_of_equity_pct=wacc_data["cost_of_equity_pct"],
        cost_of_debt_pct=wacc_data["cost_of_debt_pct"],
        risk_free_rate_pct=wacc_data["risk_free_rate_pct"],
        equity_risk_premium_pct=wacc_data["equity_risk_premium_pct"],
        country_risk_premium_pct=wacc_data["country_risk_premium_pct"],
        beta=wacc_data["beta"],
        equity_ratio_pct=wacc_data["equity_ratio_pct"],
        debt_ratio_pct=wacc_data["debt_ratio_pct"],
        corporate_tax_rate_pct=wacc_data["corporate_tax_rate_pct"],
    )

    projections = None
    if "projections" in result and result["projections"]:
        projections = [FCFProjectionPeriod(**p) for p in result["projections"]]

    tv = None
    if "terminal_value" in result and result["terminal_value"]:
        tv = TerminalValueResult(**result["terminal_value"])

    return ScenarioResult(
        scenario=result["scenario"],
        weight=result.get("weight", 1.0),
        wacc=wacc,
        projections=projections,
        terminal_value=tv,
        pv_fcfs_total_usd=result.get("pv_fcfs_total_usd", 0),
        enterprise_value_usd=result.get("enterprise_value_usd", 0),
        equity_value_usd=result.get("equity_value_usd", 0),
        implied_share_price=result.get("implied_share_price"),
        upside_pct=result.get("upside_pct"),
        net_debt_usd=result.get("net_debt_usd", 0),
        blended_pv_terminal_usd=result.get("blended_pv_terminal_usd"),
        gordon_weight=result.get("gordon_weight"),
    )


def _persist_result(
    db: Session, target: ValuationTarget, user_id: int,
    scenario_data: dict, sensitivity: list[dict] | None,
    narrative: str, risk_score: float | None,
) -> str:
    """Save ValuationResult rows and return the blended result_id."""
    blended_id = str(uuid.uuid4())

    for scenario_name, data in scenario_data.get("scenarios", {}).items():
        rid = str(uuid.uuid4()) if scenario_name != "BLENDED" else blended_id
        record = ValuationResult(
            result_id=rid,
            target_id=target.target_id,
            user_id=user_id,
            scenario=scenario_name,
            wacc_pct=data["wacc"]["wacc_pct"],
            cost_of_equity_pct=data["wacc"]["cost_of_equity_pct"],
            cost_of_debt_pct=data["wacc"]["cost_of_debt_pct"],
            country_risk_premium_pct=data["wacc"]["country_risk_premium_pct"],
            beta=data["wacc"]["beta"],
            projection_years=data.get("projection_years", 5),
            projected_fcfs_json=json.dumps(data.get("projections", [])),
            pv_fcfs_total_usd=data.get("pv_fcfs_total_usd", 0),
            terminal_growth_rate_pct=data.get("terminal_value", {}).get("terminal_growth_pct"),
            terminal_value_gordon_usd=data.get("terminal_value", {}).get("gordon_tv_usd"),
            terminal_value_exit_usd=data.get("terminal_value", {}).get("exit_tv_usd"),
            exit_multiple=data.get("terminal_value", {}).get("exit_multiple"),
            pv_terminal_gordon_usd=data.get("terminal_value", {}).get("gordon_pv_usd"),
            pv_terminal_exit_usd=data.get("terminal_value", {}).get("exit_pv_usd"),
            terminal_blend_weight_gordon=data.get("gordon_weight", 0.50),
            enterprise_value_usd=data.get("enterprise_value_usd", 0),
            net_debt_usd=data.get("net_debt_usd", 0),
            equity_value_usd=data.get("equity_value_usd", 0),
            implied_share_price=data.get("implied_share_price"),
            current_share_price=target.current_share_price,
            upside_pct=data.get("upside_pct"),
            confidence=target.confidence,
            risk_score=risk_score,
            narrative=narrative if scenario_name == "BLENDED" else None,
        )
        db.add(record)

    # Save blended result
    blended = scenario_data.get("blended", {})
    blended_record = ValuationResult(
        result_id=blended_id,
        target_id=target.target_id,
        user_id=user_id,
        scenario="BLENDED",
        wacc_pct=blended["wacc"]["wacc_pct"],
        cost_of_equity_pct=blended["wacc"]["cost_of_equity_pct"],
        cost_of_debt_pct=blended["wacc"]["cost_of_debt_pct"],
        country_risk_premium_pct=blended["wacc"]["country_risk_premium_pct"],
        beta=blended["wacc"]["beta"],
        pv_fcfs_total_usd=blended.get("pv_fcfs_total_usd", 0),
        enterprise_value_usd=blended.get("enterprise_value_usd", 0),
        net_debt_usd=blended.get("net_debt_usd", 0),
        equity_value_usd=blended.get("equity_value_usd", 0),
        implied_share_price=blended.get("implied_share_price"),
        upside_pct=blended.get("upside_pct"),
        sensitivity_wacc_growth_json=json.dumps(sensitivity) if sensitivity else None,
        confidence=target.confidence,
        risk_score=risk_score,
        narrative=narrative,
        analyst_review_required=True,
    )
    db.add(blended_record)

    return blended_id


# ── Target CRUD ──────────────────────────────────────────────────

@router.post("/targets", response_model=TargetResponse, status_code=201)
@limiter.limit("20/minute")
async def create_target(
    request: Request,
    req: CreateTargetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new valuation target (company, country, or infrastructure project). 2 credits."""
    deduct_credits(current_user, db, "/api/v3/valuation/targets", cost_multiplier=2.0)

    target = ValuationTarget(
        target_id=str(uuid.uuid4()),
        user_id=current_user.id,
        entity_type=req.entity_type,
        name=req.name,
        ticker=req.ticker,
        exchange_code=req.exchange_code,
        country_code=req.country_code.upper(),
        sector=req.sector,
        currency=req.currency,
        shares_outstanding=req.shares_outstanding,
        current_share_price=req.current_share_price,
        net_debt_usd=req.net_debt_usd,
        project_start_date=req.project_start_date,
        project_end_date=req.project_end_date,
        total_project_cost_usd=req.total_project_cost_usd,
        notes=req.notes,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@router.get("/targets", response_model=TargetListResponse)
@limiter.limit("30/minute")
async def list_targets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all valuation targets for the current user. 1 credit."""
    deduct_credits(current_user, db, "/api/v3/valuation/targets", cost_multiplier=1.0)

    targets = (
        db.query(ValuationTarget)
        .filter(
            ValuationTarget.user_id == current_user.id,
            ValuationTarget.status == "active",
        )
        .order_by(ValuationTarget.created_at.desc())
        .all()
    )
    return TargetListResponse(targets=targets, total=len(targets))


@router.get("/targets/{target_id}", response_model=TargetResponse)
@limiter.limit("30/minute")
async def get_target(
    request: Request,
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific valuation target. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}", cost_multiplier=1.0)
    return _get_user_target(db, target_id, current_user.id)


@router.put("/targets/{target_id}", response_model=TargetResponse)
@limiter.limit("20/minute")
async def update_target(
    request: Request,
    target_id: str,
    req: UpdateTargetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a valuation target. 2 credits."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}", cost_multiplier=2.0)
    target = _get_user_target(db, target_id, current_user.id)

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(target, field, value)

    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/targets/{target_id}")
@limiter.limit("10/minute")
async def delete_target(
    request: Request,
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete (archive) a valuation target. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}", cost_multiplier=1.0)
    target = _get_user_target(db, target_id, current_user.id)
    target.status = "archived"
    target.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "archived", "target_id": target_id}


# ── Financial Statements ─────────────────────────────────────────

@router.post("/targets/{target_id}/financials", response_model=FinancialStatementResponse, status_code=201)
@limiter.limit("20/minute")
async def submit_financials(
    request: Request,
    target_id: str,
    req: SubmitFinancialsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a financial statement for a valuation target. 3 credits."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}/financials", cost_multiplier=3.0)
    target = _get_user_target(db, target_id, current_user.id)

    # Upsert: replace existing statement for same year + type
    existing = db.query(FinancialStatement).filter(
        FinancialStatement.target_id == target_id,
        FinancialStatement.fiscal_year == req.fiscal_year,
        FinancialStatement.statement_type == req.statement_type,
    ).first()

    if existing:
        for field, value in req.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    stmt = FinancialStatement(
        target_id=target_id,
        **req.model_dump(),
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)
    return stmt


@router.get("/targets/{target_id}/financials", response_model=list[FinancialStatementResponse])
@limiter.limit("30/minute")
async def get_financials(
    request: Request,
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all financial statements for a target. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}/financials", cost_multiplier=1.0)
    _get_user_target(db, target_id, current_user.id)

    return (
        db.query(FinancialStatement)
        .filter(FinancialStatement.target_id == target_id)
        .order_by(FinancialStatement.fiscal_year.asc())
        .all()
    )


# ── Run Valuation ────────────────────────────────────────────────

@router.post("/run", response_model=ValuationResponse)
@limiter.limit("10/minute")
async def run_valuation(
    request: Request,
    req: RunValuationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run a full 12-step DCF valuation with scenario analysis. 15 credits.

    Requires at least 2 years of financial statements submitted for the target.
    Returns BULL/BASE/BEAR scenarios with probability-weighted blended target,
    plus an optional sensitivity table (WACC × terminal growth grid).
    """
    deduct_credits(current_user, db, "/api/v3/valuation/run", cost_multiplier=15.0)

    target = _get_user_target(db, req.target_id, current_user.id)

    statements = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.target_id == req.target_id)
        .order_by(FinancialStatement.fiscal_year.asc())
        .all()
    )
    if len(statements) < 2:
        raise HTTPException(422, "At least 2 years of financial data required to run DCF")

    # Extract financials
    financials = _extract_financials(target, statements)

    # Calculate WACC
    cc = target.country_code.upper()
    pol_risk = POLITICAL_RISK.get(cc, 5.0)

    latest_idx = (
        db.query(CountryIndex)
        .join(Country)
        .filter(Country.code == cc)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    wasi_idx = latest_idx.index_value if latest_idx and latest_idx.index_value else None

    wacc_params = _engine.calculate_wacc(
        country_code=cc,
        political_risk=pol_risk,
        wasi_index=wasi_idx,
        custom_beta=req.custom_beta,
    )

    if req.custom_wacc_pct is not None:
        wacc_params["wacc"] = req.custom_wacc_pct / 100.0
        wacc_params["wacc_pct"] = req.custom_wacc_pct

    # Run scenario analysis
    result = _engine.run_scenario_analysis(
        financials=financials,
        wacc_params=wacc_params,
        scenario_weights=req.scenario_weights,
        projection_years=req.projection_years,
        terminal_growth=req.terminal_growth_pct / 100.0,
        exit_multiple=req.exit_multiple,
        gordon_weight=req.gordon_weight,
        revenue_growth_overrides=req.revenue_growth_overrides,
    )

    # Sensitivity table
    sensitivity = None
    sensitivity_cells = None
    if req.include_sensitivity:
        base_scenario = result["scenarios"]["BASE"]
        sensitivity = _engine.generate_sensitivity_table(base_scenario, financials)
        sensitivity_cells = [SensitivityCell(**c) for c in sensitivity]

    # Risk score (try to get from RiskEngine if available)
    risk_score = None
    try:
        from src.engines.risk_engine import RiskEngine
        risk_engine = RiskEngine(db)
        risk_result = risk_engine.score_country(cc)
        risk_score = risk_result.get("composite_score")
    except ImportError:
        pass  # RiskEngine not available — proceed without risk score
    except Exception as exc:
        logger.warning("Risk score calculation failed for %s: %s", cc, exc)

    # Narrative
    narrative = _engine.generate_narrative(
        entity_type=target.entity_type,
        name=target.name,
        country_code=cc,
        blended=result["blended"],
        scenarios=result["scenarios"],
        risk_score=risk_score,
    )

    # Persist
    blended_id = _persist_result(
        db, target, current_user.id,
        result, sensitivity, narrative, risk_score,
    )
    db.commit()

    # Build response
    scenario_results = [
        _build_scenario_result(result["scenarios"][s])
        for s in ["BULL", "BASE", "BEAR"]
    ]
    blended_result = _build_scenario_result(result["blended"])

    return ValuationResponse(
        result_id=blended_id,
        target_id=target.target_id,
        target_name=target.name,
        entity_type=target.entity_type,
        country_code=cc,
        scenarios=scenario_results,
        blended=blended_result,
        sensitivity_table=sensitivity_cells,
        risk_score=risk_score,
        narrative=narrative,
        analyst_review_required=True,
        calculated_at=datetime.now(timezone.utc),
    )


# ── Country-Level DCF ────────────────────────────────────────────

@router.post("/country/{country_code}", response_model=ValuationResponse)
@limiter.limit("10/minute")
async def run_country_valuation(
    request: Request,
    country_code: str,
    req: RunCountryValuationRequest = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run a country-level DCF using existing macro data. 10 credits.

    Auto-populates financials from MacroIndicator (GDP, growth, debt)
    and BilateralTrade (trade surplus). No manual financial input needed.
    """
    deduct_credits(current_user, db, f"/api/v3/valuation/country/{country_code}", cost_multiplier=10.0)

    cc = country_code.upper()
    if cc not in VALID_WASI_COUNTRIES:
        raise HTTPException(422, f"Country '{country_code}' not in WASI v3.0 ECOWAS set")

    if req is None:
        req = RunCountryValuationRequest()

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(404, f"Country '{country_code}' not found")

    # Fetch macro data
    macro_rows = (
        db.query(MacroIndicator)
        .filter(MacroIndicator.country_id == country.id)
        .order_by(MacroIndicator.year.asc())
        .all()
    )
    macro_data = [
        {
            "year": r.year,
            "gdp_usd_billions": float(r.gdp_usd_billions) if r.gdp_usd_billions else None,
            "gdp_growth_pct": r.gdp_growth_pct,
            "inflation_pct": r.inflation_pct,
            "debt_gdp_pct": r.debt_gdp_pct,
            "is_projection": r.is_projection,
        }
        for r in macro_rows
    ]

    # Trade surplus
    trade_rows = db.query(BilateralTrade).filter(BilateralTrade.country_id == country.id).all()
    trade_surplus = sum(
        float(r.trade_balance_usd) for r in trade_rows if r.trade_balance_usd
    )

    financials = _engine.prepare_country_financials(
        macro_data=macro_data,
        trade_surplus_usd=trade_surplus,
    )

    # WACC
    pol_risk = POLITICAL_RISK.get(cc, 5.0)
    latest_idx = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    wasi_idx = latest_idx.index_value if latest_idx and latest_idx.index_value else None

    wacc_params = _engine.calculate_wacc(
        country_code=cc,
        political_risk=pol_risk,
        wasi_index=wasi_idx,
    )

    # Create a temporary target for persistence
    target = ValuationTarget(
        target_id=str(uuid.uuid4()),
        user_id=current_user.id,
        entity_type="COUNTRY",
        name=country.name,
        country_code=cc,
        currency="USD",
        net_debt_usd=financials["net_debt"],
    )
    db.add(target)
    db.flush()

    # Run scenarios
    result = _engine.run_scenario_analysis(
        financials=financials,
        wacc_params=wacc_params,
        projection_years=req.projection_years,
        terminal_growth=req.terminal_growth_pct / 100.0,
        exit_multiple=req.exit_multiple,
        gordon_weight=req.gordon_weight,
    )

    sensitivity = None
    sensitivity_cells = None
    if req.include_sensitivity:
        sensitivity = _engine.generate_sensitivity_table(
            result["scenarios"]["BASE"], financials,
        )
        sensitivity_cells = [SensitivityCell(**c) for c in sensitivity]

    narrative = _engine.generate_narrative(
        entity_type="COUNTRY",
        name=country.name,
        country_code=cc,
        blended=result["blended"],
        scenarios=result["scenarios"],
    )

    blended_id = _persist_result(
        db, target, current_user.id,
        result, sensitivity, narrative, None,
    )
    db.commit()

    scenario_results = [
        _build_scenario_result(result["scenarios"][s])
        for s in ["BULL", "BASE", "BEAR"]
    ]
    blended_result = _build_scenario_result(result["blended"])

    return ValuationResponse(
        result_id=blended_id,
        target_id=target.target_id,
        target_name=country.name,
        entity_type="COUNTRY",
        country_code=cc,
        scenarios=scenario_results,
        blended=blended_result,
        sensitivity_table=sensitivity_cells,
        narrative=narrative,
        analyst_review_required=True,
        calculated_at=datetime.now(timezone.utc),
    )


# ── Retrieve Results ─────────────────────────────────────────────

@router.get("/results/{result_id}")
@limiter.limit("30/minute")
async def get_result(
    request: Request,
    result_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a cached valuation result by ID. 2 credits."""
    deduct_credits(current_user, db, f"/api/v3/valuation/results/{result_id}", cost_multiplier=2.0)

    result = db.query(ValuationResult).filter(
        ValuationResult.result_id == result_id,
        ValuationResult.user_id == current_user.id,
    ).first()
    if not result:
        raise HTTPException(404, "Valuation result not found")

    return {
        "result_id": result.result_id,
        "target_id": result.target_id,
        "scenario": result.scenario,
        "wacc_pct": result.wacc_pct,
        "enterprise_value_usd": result.enterprise_value_usd,
        "equity_value_usd": result.equity_value_usd,
        "implied_share_price": result.implied_share_price,
        "upside_pct": result.upside_pct,
        "terminal_growth_rate_pct": result.terminal_growth_rate_pct,
        "exit_multiple": result.exit_multiple,
        "pv_fcfs_total_usd": result.pv_fcfs_total_usd,
        "terminal_value_gordon_usd": result.terminal_value_gordon_usd,
        "terminal_value_exit_usd": result.terminal_value_exit_usd,
        "risk_score": result.risk_score,
        "narrative": result.narrative,
        "analyst_review_required": result.analyst_review_required,
        "calculated_at": str(result.calculated_at),
        "engine_version": result.engine_version,
    }


@router.get("/targets/{target_id}/results")
@limiter.limit("20/minute")
async def get_target_results(
    request: Request,
    target_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all valuation results for a target. 3 credits."""
    deduct_credits(current_user, db, f"/api/v3/valuation/targets/{target_id}/results", cost_multiplier=3.0)
    _get_user_target(db, target_id, current_user.id)

    results = (
        db.query(ValuationResult)
        .filter(
            ValuationResult.target_id == target_id,
            ValuationResult.user_id == current_user.id,
        )
        .order_by(ValuationResult.calculated_at.desc())
        .all()
    )

    return {
        "target_id": target_id,
        "total": len(results),
        "results": [
            {
                "result_id": r.result_id,
                "scenario": r.scenario,
                "wacc_pct": r.wacc_pct,
                "enterprise_value_usd": r.enterprise_value_usd,
                "equity_value_usd": r.equity_value_usd,
                "implied_share_price": r.implied_share_price,
                "upside_pct": r.upside_pct,
                "calculated_at": str(r.calculated_at),
            }
            for r in results
        ],
    }


# ── Sensitivity Table ────────────────────────────────────────────

@router.get("/sensitivity/{result_id}")
@limiter.limit("20/minute")
async def get_sensitivity(
    request: Request,
    result_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the sensitivity table for a valuation result. 3 credits."""
    deduct_credits(current_user, db, f"/api/v3/valuation/sensitivity/{result_id}", cost_multiplier=3.0)

    result = db.query(ValuationResult).filter(
        ValuationResult.result_id == result_id,
        ValuationResult.user_id == current_user.id,
    ).first()
    if not result:
        raise HTTPException(404, "Valuation result not found")

    if not result.sensitivity_wacc_growth_json:
        raise HTTPException(404, "No sensitivity table available for this result")

    cells = json.loads(result.sensitivity_wacc_growth_json)
    return {
        "result_id": result_id,
        "target_id": result.target_id,
        "base_wacc_pct": result.wacc_pct,
        "cells": cells,
        "total_cells": len(cells),
    }
