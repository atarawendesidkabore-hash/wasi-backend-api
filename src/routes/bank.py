"""
Bank Integration Module — /api/v2/bank/

Rule-based credit scoring using WASI indices, trade balance, procurement,
and volatility. Designed for compatibility with COBOL legacy systems and REST clients.

Endpoint credit costs:
  GET  /credit-context/{country_code}  — 3 credits
  POST /loan-advisory                  — 5 credits
  POST /score-dossier                  — 10 credits
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import timezone, date, datetime
from typing import Optional
import json
import math

from src.database.connection import get_db
from src.database.models import (
    User, Country, CountryIndex, WASIComposite, WASIProcurementRecord,
    BilateralTrade, BankDossierScore, RoadCorridor, NewsEvent,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.wacc_params import (
    POLITICAL_RISK, VALID_WASI_COUNTRIES, COUNTRY_WACC_PARAMS,
    _DEFAULT_WACC_PARAMS, _RF, _ERP,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v2/bank", tags=["Bank"])
limiter = Limiter(key_func=get_remote_address)


def _validate_wasi_country(country_code: str) -> str:
    """Validate and normalize country code. Raises 422 if not in WASI v3.0 set."""
    code = country_code.upper()
    if code not in VALID_WASI_COUNTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"Country '{country_code}' is not in the WASI v3.0 ECOWAS set. "
                   f"Valid codes: {', '.join(sorted(VALID_WASI_COUNTRIES))}",
        )
    return code

# Risk rating thresholds
RATING_THRESHOLDS = [
    (90, "AAA"), (80, "AA"), (70, "A"),
    (60, "BBB"), (50, "BB"), (40, "B"), (0, "CCC"),
]


def _get_rating(score: float) -> str:
    for threshold, rating in RATING_THRESHOLDS:
        if score >= threshold:
            return rating
    return "CCC"


def _rate_premium_bps(rating: str) -> int:
    """Basis points above base rate per risk rating."""
    return {
        "AAA": 50, "AA": 100, "A": 150,
        "BBB": 250, "BB": 400, "B": 600, "CCC": 1000,
    }.get(rating, 1000)


def _max_recommended_usd(score: float, loan_amount: float) -> float:
    """Cap recommended loan at score% of requested amount, minimum 10%."""
    pct = max(0.10, score / 100.0)
    return round(loan_amount * pct, 2)


def _calculate_wacc(
    country_code: str,
    political_risk: float,
    wasi_index: float | None,
    rate_premium_bps: int,
) -> dict:
    """
    Country WACC via CAPM + sovereign risk premium.

    Re  = Rf + β × ERP + CRP
    Rd  = Rf + sovereign_spread
    CRP = f(political_risk, wasi_index)
    WACC = (E/V × Re) + (D/V × Rd × (1 − Tax))
    """
    p = COUNTRY_WACC_PARAMS.get(country_code, _DEFAULT_WACC_PARAMS)
    wasi = wasi_index if wasi_index is not None else 50.0

    # Country Risk Premium: political risk drives 60%, low WASI drives 40%
    crp = (political_risk / 10.0) * 0.072 + (1.0 - wasi / 100.0) * 0.048

    re = _RF + p["beta"] * _ERP + crp                    # cost of equity
    rd = _RF + rate_premium_bps / 10_000.0               # cost of debt
    eq = p["eq_ratio"]
    dt = 1.0 - eq
    tax = p["tax"]

    wacc = eq * re + dt * rd * (1.0 - tax)

    return {
        "wacc_pct":                  round(wacc * 100, 2),
        "cost_of_equity_pct":        round(re   * 100, 2),
        "cost_of_debt_pct":          round(rd   * 100, 2),
        "risk_free_rate_pct":        round(_RF  * 100, 2),
        "equity_risk_premium_pct":   round(_ERP * 100, 2),
        "country_risk_premium_pct":  round(crp  * 100, 2),
        "beta":                      p["beta"],
        "equity_ratio_pct":          round(eq   * 100, 1),
        "debt_ratio_pct":            round(dt   * 100, 1),
        "corporate_tax_rate_pct":    round(tax  * 100, 1),
        "sovereign_spread_bps":      rate_premium_bps,
        "interpretation": (
            "Très attractif — coût du capital comparable aux marchés développés" if wacc < 0.12 else
            "Attractif — rendement minimal requis raisonnable pour la région"    if wacc < 0.16 else
            "Modéré — prime de risque significative, projets à fort rendement"   if wacc < 0.20 else
            "Élevé — risque souverain élevé, rentabilité minimale très haute"    if wacc < 0.25 else
            "Très élevé — coût du capital dissuasif, risques majeurs à surveiller"
        ),
    }


def _score_dossier(
    country: Country,
    db: Session,
    sector: str,
    loan_amount_usd: float,
    loan_term_months: int,
    collateral_type: Optional[str],
) -> dict:
    """
    Core scoring logic. Returns score dict with components.

    Components (total 100 points):
      WASI Index Component   : 40 pts
      Trade Balance Component: 20 pts
      Procurement Activity   : 15 pts
      Volatility Penalty     : -15 pts max
      Political Risk Penalty : -10 pts max
    """
    components = {}

    # 1. WASI Index Component (40 pts)
    latest_idx = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    if latest_idx and latest_idx.index_value is not None:
        wasi_pts = (latest_idx.index_value / 100.0) * 40.0
    else:
        wasi_pts = 30.0  # ECOWAS median (~75/100 WASI) when no data
    components["wasi_component"] = round(wasi_pts, 2)

    # 2. Trade Balance Component (20 pts)
    trade_rows = (
        db.query(BilateralTrade)
        .filter(BilateralTrade.country_id == country.id)
        .all()
    )
    if trade_rows:
        total_balance = sum(r.trade_balance_usd for r in trade_rows if r.trade_balance_usd)
        # Positive surplus → full 20 pts; negative deficit → 0 pts; scaled
        max_balance = 100_000_000_000  # $100B reference (scaled for ECOWAS, NG alone ~$200B)
        trade_pts = max(0.0, min(20.0, (total_balance / max_balance) * 20.0 + 10.0))
    else:
        trade_pts = 12.0  # ECOWAS median (slight deficit) when no trade data
    components["trade_component"] = round(trade_pts, 2)

    # 3. Procurement Activity (15 pts)
    proc_row = (
        db.query(WASIProcurementRecord)
        .filter(WASIProcurementRecord.country_id == country.id)
        .order_by(WASIProcurementRecord.period_date.desc())
        .first()
    )
    if proc_row and proc_row.tender_count and proc_row.tender_count > 0:
        awarded_ratio = (proc_row.awarded_count or 0) / proc_row.tender_count
        proc_pts = awarded_ratio * 15.0
    else:
        proc_pts = 10.0  # ECOWAS median procurement when no data
    components["procurement_component"] = round(proc_pts, 2)

    # 4. Volatility Penalty (max -15 pts)
    composite = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )
    vol_penalty = 0.0
    if composite:
        if composite.coefficient_of_variation and composite.coefficient_of_variation > 0:
            vol_penalty += min(7.5, composite.coefficient_of_variation * 50.0)
        if composite.max_drawdown and composite.max_drawdown > 0:
            vol_penalty += min(7.5, composite.max_drawdown * 30.0)
    components["volatility_penalty"] = round(-vol_penalty, 2)

    # 5. Political Risk Penalty (max -10 pts)
    risk_score = POLITICAL_RISK.get(country.code, 5.0)   # 0–10
    pol_penalty = (risk_score / 10.0) * 10.0
    components["political_risk_penalty"] = round(-pol_penalty, 2)

    overall = max(0.0, min(100.0,
        wasi_pts + trade_pts + proc_pts - vol_penalty - pol_penalty
    ))
    rating = _get_rating(overall)

    # Build narrative
    direction = "surplus" if trade_pts >= 10 else "deficit"
    narrative = (
        f"{country.name} ({country.code}) scores {overall:.1f}/100 for the "
        f"{sector} sector. WASI index contribution: {wasi_pts:.1f}/40. "
        f"Trade balance shows a {direction} (score {trade_pts:.1f}/20). "
        f"Political risk penalty: {pol_penalty:.1f}/10. "
        f"Risk rating: {rating}. "
        f"Recommended maximum loan: ${_max_recommended_usd(overall, loan_amount_usd):,.0f} USD "
        f"at +{_rate_premium_bps(rating)} bps above base rate. "
        f"This dossier requires human bank officer review before disbursement."
    )

    wacc_data = _calculate_wacc(
        country_code=country.code,
        political_risk=risk_score,
        wasi_index=latest_idx.index_value if latest_idx and latest_idx.index_value else None,
        rate_premium_bps=_rate_premium_bps(rating),
    )

    return {
        "overall_score": round(overall, 2),
        "risk_rating": rating,
        "max_recommended_usd": _max_recommended_usd(overall, loan_amount_usd),
        "rate_premium_bps": _rate_premium_bps(rating),
        "component_scores": components,
        "wacc": wacc_data,
        "narrative": narrative,
        "bank_review_required": True,
        # COBOL-compatible record (fixed-width numeric fields, YYYYMMDD dates)
        "cobol_record": {
            "SCORE_9V2":     f"{min(int(overall * 100), 999_999_999):09d}",      # PIC 9(7)V99
            "RATING_X5":     f"{rating:<5}",                                      # PIC X(5)
            "MAX_LOAN_15V2": f"{min(int(_max_recommended_usd(overall, loan_amount_usd)), 999_999_999_999_999):015d}",
            "PREMIUM_4":     f"{_rate_premium_bps(rating):04d}",                  # PIC 9(4)
            "WACC_6V2":      f"{min(int(wacc_data['wacc_pct'] * 100), 999_999):06d}",  # PIC 9(4)V99
            "CALC_DATE_8":   date.today().strftime("%Y%m%d"),                     # PIC 9(8)
            "REVIEW_FLAG_1": "Y",                                                 # PIC X(1)
        },
    }


# ── Pydantic request schemas ──────────────────────────────────────────────────

class DossierRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO-2 country code")
    sector: str = Field(..., max_length=50, description="e.g. agriculture, logistics, mining, manufacturing")
    loan_amount_usd: float = Field(..., gt=0, le=1_000_000_000, description="Requested loan amount in USD (max $1B)")
    loan_term_months: int = Field(..., ge=1, le=360, description="Loan term in months")
    collateral_type: Optional[str] = Field(None, description="e.g. real_estate, receivables, inventory")


class LoanAdvisoryRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    sector: str = Field(..., max_length=50)
    loan_amount_usd: float = Field(..., gt=0, le=1_000_000_000)
    loan_term_months: int = Field(..., ge=1, le=360)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/credit-context/{country_code}")
@limiter.limit("20/minute")
async def get_credit_context(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Credit context for a country: WASI score, trade balance, procurement metrics,
    top bilateral trade partners. 3 credits.
    """
    cc = _validate_wasi_country(country_code)
    deduct_credits(current_user, db, f"/api/v2/bank/credit-context/{cc}", cost_multiplier=3.0)

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    latest_idx = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    trade_rows = (
        db.query(BilateralTrade)
        .filter(BilateralTrade.country_id == country.id)
        .order_by(BilateralTrade.total_trade_usd.desc())
        .limit(5)
        .all()
    )
    proc_row = (
        db.query(WASIProcurementRecord)
        .filter(WASIProcurementRecord.country_id == country.id)
        .order_by(WASIProcurementRecord.period_date.desc())
        .first()
    )

    total_export = sum(r.export_value_usd for r in
                       db.query(BilateralTrade).filter(BilateralTrade.country_id == country.id).all()
                       if r.export_value_usd)
    total_import = sum(r.import_value_usd for r in
                       db.query(BilateralTrade).filter(BilateralTrade.country_id == country.id).all()
                       if r.import_value_usd)

    # Compute indicative score server-side (same formula as score-dossier)
    _quick = _score_dossier(
        country=country,
        db=db,
        sector="general",
        loan_amount_usd=1_000_000,
        loan_term_months=12,
        collateral_type=None,
    )

    return {
        "country_code": country.code,
        "country_name": country.name,
        "tier": country.tier,
        "composite_weight_pct": round(country.weight * 100, 1),
        "political_risk_score": POLITICAL_RISK.get(country.code, 5.0),
        "indicative_score": _quick["overall_score"],
        "indicative_rating": _quick["risk_rating"],
        "wasi_index": {
            "value": latest_idx.index_value if latest_idx else None,
            "period_date": str(latest_idx.period_date) if latest_idx else None,
            "confidence": latest_idx.confidence if latest_idx else None,
            "data_quality": latest_idx.data_quality if latest_idx else None,
        },
        "trade_summary": {
            "total_exports_usd": total_export,
            "total_imports_usd": total_import,
            "trade_balance_usd": total_export - total_import,
            "top_partners": [
                {
                    "partner": r.partner_name,
                    "partner_code": r.partner_code,
                    "total_trade_usd": r.total_trade_usd,
                    "trade_balance_usd": r.trade_balance_usd,
                    "top_exports": r.top_exports,
                }
                for r in trade_rows
            ],
        },
        "procurement": {
            "tender_count": proc_row.tender_count if proc_row else None,
            "awarded_count": proc_row.awarded_count if proc_row else None,
            "total_value_usd": proc_row.total_value_usd if proc_row else None,
            "infrastructure_pct": proc_row.infrastructure_pct if proc_row else None,
        } if proc_row else None,
        "wacc": _calculate_wacc(
            country_code=country.code,
            political_risk=POLITICAL_RISK.get(country.code, 5.0),
            wasi_index=latest_idx.index_value if latest_idx else None,
            rate_premium_bps=_quick["rate_premium_bps"],
        ),
    }


@router.post("/loan-advisory")
@limiter.limit("10/minute")
async def get_loan_advisory(
    request: Request,
    req: LoanAdvisoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Loan advisory narrative without full dossier scoring. 5 credits.
    Returns risk factors, regional comparison, and indicative rate premium.
    """
    cc = _validate_wasi_country(req.country_code)
    deduct_credits(current_user, db, "/api/v2/bank/loan-advisory", cost_multiplier=5.0)

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{req.country_code}' not found")

    result = _score_dossier(
        country=country,
        db=db,
        sector=req.sector,
        loan_amount_usd=req.loan_amount_usd,
        loan_term_months=req.loan_term_months,
        collateral_type=None,
    )

    risk_factors = []
    pol = POLITICAL_RISK.get(country.code, 5.0)
    if pol >= 7.0:
        risk_factors.append(f"High political risk score ({pol}/10) — elevated sovereign risk")
    if result["overall_score"] < 50:
        risk_factors.append("Below-average WASI composite score — monitor closely")
    if result["component_scores"].get("trade_component", 10) < 8:
        risk_factors.append("Negative trade balance — import-dependent economy")
    if not risk_factors:
        risk_factors.append("No critical risk factors identified at this time")

    return {
        "country_code": country.code,
        "country_name": country.name,
        "sector": req.sector,
        "loan_amount_usd": req.loan_amount_usd,
        "loan_term_months": req.loan_term_months,
        "indicative_score": result["overall_score"],
        "indicative_rating": result["risk_rating"],
        "indicative_rate_premium_bps": result["rate_premium_bps"],
        "risk_factors": risk_factors,
        "advisory_narrative": result["narrative"],
        "bank_review_required": True,
        "disclaimer": (
            "This advisory is generated from WASI composite data and publicly available "
            "trade statistics. It is indicative only and does not constitute a binding "
            "credit decision. All loan approvals require human bank officer review."
        ),
    }


@router.post("/score-dossier")
@limiter.limit("5/minute")
async def score_dossier(
    request: Request,
    req: DossierRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full credit dossier scoring with COBOL-compatible output. 10 credits.
    Stores result in bank_dossier_scores table.
    """
    cc = _validate_wasi_country(req.country_code)
    deduct_credits(current_user, db, "/api/v2/bank/score-dossier", cost_multiplier=10.0)

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{req.country_code}' not found")

    result = _score_dossier(
        country=country,
        db=db,
        sector=req.sector,
        loan_amount_usd=req.loan_amount_usd,
        loan_term_months=req.loan_term_months,
        collateral_type=req.collateral_type,
    )

    # Persist to DB
    record = BankDossierScore(
        user_id=current_user.id,
        country_id=country.id,
        period_date=date.today().replace(day=1),
        sector=req.sector,
        loan_amount_usd=req.loan_amount_usd,
        loan_term_months=req.loan_term_months,
        collateral_type=req.collateral_type,
        overall_score=result["overall_score"],
        risk_rating=result["risk_rating"],
        max_recommended_usd=result["max_recommended_usd"],
        rate_premium_bps=result["rate_premium_bps"],
        component_scores=json.dumps(result["component_scores"]),
        narrative=result["narrative"],
        bank_review_required=True,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "dossier_id": record.id,
        "country_code": country.code,
        "country_name": country.name,
        "sector": req.sector,
        "loan_amount_usd": req.loan_amount_usd,
        "loan_term_months": req.loan_term_months,
        "collateral_type": req.collateral_type,
        "overall_score": result["overall_score"],
        "risk_rating": result["risk_rating"],
        "max_recommended_usd": result["max_recommended_usd"],
        "rate_premium_bps": result["rate_premium_bps"],
        "component_scores": result["component_scores"],
        "narrative": result["narrative"],
        "cobol_record": result["cobol_record"],
        "bank_review_required": True,
        "scored_at": str(record.created_at),
    }


# ── New v3.0 endpoints ────────────────────────────────────────────────────────

# CFA franc peg: 1 EUR = 655.957 XOF (fixed). Convert via EUR/USD rate.
# EUR/USD ≈ 1.045 (Feb 2026) → 1 USD ≈ 655.957 / 1.045 ≈ 627.71 XOF
_EUR_USD = 1.045   # ECB reference rate, Feb 2026
_XOF_TO_USD = 1.0 / (655.957 / _EUR_USD)  # XOF → USD via EUR parity

_SEVERITY = {
    "POLITICAL_RISK": "CRITICAL", "ROAD_CORRIDOR_BLOCKED": "CRITICAL",
    "PORT_DISRUPTION": "HIGH",    "STRIKE": "HIGH",
    "CURRENCY_CRISIS": "HIGH",    "DROUGHT_FOOD": "MEDIUM",
    "COMMODITY_SURGE": "MEDIUM",  "POLICY_CHANGE": "LOW",
    "TRADE_POSITIVE_SIGNAL": "LOW", "RAIL_OPERATIONAL_CHANGE": "LOW",
    "INFRASTRUCTURE_UPGRADE": "LOW", "NEW_GOVERNMENT_DOCUMENT": "INFO",
}

_SECTOR_ALERTS = {
    "PORT_DISRUPTION":       ["logistics", "import_export", "manufacturing"],
    "ROAD_CORRIDOR_BLOCKED": ["logistics", "agriculture", "mining"],
    "POLITICAL_RISK":        ["all sectors"],
    "STRIKE":                ["logistics", "port_services"],
    "DROUGHT_FOOD":          ["agriculture", "food_processing"],
    "CURRENCY_CRISIS":       ["import_export", "finance"],
    "COMMODITY_SURGE":       ["mining", "agriculture", "energy"],
}


@router.get("/loan-rate-advisory/{amount_xof}/{sector}/{country_code}")
async def get_loan_rate_advisory(
    amount_xof: float,
    sector: str,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    GET version of loan advisory. Amount in XOF, sector and country in URL. 3 credits.
    Returns indicative rate range (min/max %) based on country risk scoring.
    """
    deduct_credits(current_user, db,
                   f"/api/v2/bank/loan-rate-advisory/{amount_xof}/{sector}/{country_code}",
                   cost_multiplier=3.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    amount_usd = round(amount_xof * _XOF_TO_USD, 2)
    result = _score_dossier(
        country=country, db=db, sector=sector,
        loan_amount_usd=max(amount_usd, 1000.0),
        loan_term_months=12, collateral_type=None,
    )

    bps = result["rate_premium_bps"]
    base_rate = 8.0   # ECOWAS regional base rate %
    rate_min = round(base_rate + bps / 100 * 0.60, 2)
    rate_max = round(base_rate + bps / 100 * 1.00, 2)

    return {
        "country_code": country.code,
        "country_name": country.name,
        "sector": sector,
        "amount_xof": amount_xof,
        "amount_usd": amount_usd,
        "indicative_score": result["overall_score"],
        "indicative_rating": result["risk_rating"],
        "rate_min_pct": rate_min,
        "rate_max_pct": rate_max,
        "market_rate_benchmark_pct": {"min": 18.0, "max": 22.0},
        "rate_premium_bps": bps,
        "rationale": result["narrative"],
        "data_quality": "B" if result["overall_score"] > 40 else "C",
        "bank_review_required": True,
        "disclaimer": (
            "Indicative only. Rate derived from WASI macroeconomic data. "
            "Final rates require bank officer review and full credit assessment."
        ),
    }


@router.get("/corridor-status/{corridor_id}")
async def get_corridor_status(
    corridor_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Road corridor status: latest transport metrics + active news alerts. 1 credit.
    corridor_id is a partial name match (e.g. 'LAGOS', 'DAKAR', 'LOME').
    """
    deduct_credits(current_user, db,
                   f"/api/v2/bank/corridor-status/{corridor_id}", cost_multiplier=1.0)

    from sqlalchemy import func as sqlfunc
    name_filter = f"%{corridor_id.upper()}%"
    corridors = (
        db.query(RoadCorridor)
        .filter(sqlfunc.upper(RoadCorridor.corridor_name).like(name_filter))
        .order_by(RoadCorridor.period_date.desc())
        .limit(3)
        .all()
    )
    if not corridors:
        raise HTTPException(status_code=404,
                            detail=f"No corridor found matching '{corridor_id}'")

    latest = corridors[0]
    road_index = latest.road_index

    # Collect active alerts for countries along this corridor
    now = datetime.now(timezone.utc)
    corridor_country = db.query(Country).filter(Country.id == latest.country_id).first()
    active_alerts = []
    if corridor_country:
        events = (
            db.query(NewsEvent)
            .filter(
                NewsEvent.country_id == corridor_country.id,
                NewsEvent.is_active == True,
                NewsEvent.expires_at > now,
            )
            .order_by(NewsEvent.detected_at.desc())
            .limit(5)
            .all()
        )
        active_alerts = [
            {
                "event_type": e.event_type,
                "headline": e.headline[:150],
                "magnitude": e.magnitude,
                "severity": _SEVERITY.get(e.event_type, "MEDIUM"),
                "detected_at": str(e.detected_at),
                "expires_at": str(e.expires_at),
            }
            for e in events
        ]

    # Determine status
    has_critical = any(
        a["severity"] == "CRITICAL" or a["event_type"] == "ROAD_CORRIDOR_BLOCKED"
        for a in active_alerts
    )
    if (road_index is not None and road_index < 40) or has_critical:
        status = "RED"
    elif (road_index is not None and road_index < 60) or active_alerts:
        status = "AMBER"
    else:
        status = "GREEN"

    return {
        "corridor_name": latest.corridor_name,
        "corridor_id": corridor_id.upper(),
        "status": status,
        "latest_road_index": road_index,
        "avg_transit_days": latest.avg_transit_days,
        "border_wait_hours": latest.border_wait_hours,
        "road_quality_score": latest.road_quality_score if hasattr(latest, "road_quality_score") else None,
        "period_date": str(latest.period_date),
        "active_alerts": active_alerts,
        "last_updated": str(latest.period_date),
    }


@router.get("/sector-alert/{country_code}")
async def get_sector_alert(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Active news-driven alerts for a country grouped by event type. 1 credit.
    Returns severity, affected sectors, and recommended action.
    """
    deduct_credits(current_user, db,
                   f"/api/v2/bank/sector-alert/{country_code}", cost_multiplier=1.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    now = datetime.now(timezone.utc)
    events = (
        db.query(NewsEvent)
        .filter(
            NewsEvent.country_id == country.id,
            NewsEvent.is_active == True,
            NewsEvent.expires_at > now,
        )
        .order_by(NewsEvent.detected_at.desc())
        .all()
    )

    alerts = [
        {
            "event_type": e.event_type,
            "headline": e.headline[:200],
            "magnitude": e.magnitude,
            "severity": _SEVERITY.get(e.event_type, "MEDIUM"),
            "affected_sectors": _SECTOR_ALERTS.get(e.event_type, ["general"]),
            "detected_at": str(e.detected_at),
            "expires_at": str(e.expires_at),
        }
        for e in events
    ]

    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    highest = max(
        (a["severity"] for a in alerts),
        key=lambda s: severity_order.get(s, 0),
        default="NONE",
    )

    affected = list({s for a in alerts for s in a["affected_sectors"]})

    if highest == "CRITICAL":
        action = "Suspend new credit exposure. Immediate risk committee review required."
    elif highest == "HIGH":
        action = "Increase monitoring frequency. Apply additional risk premium."
    elif highest == "MEDIUM":
        action = "Standard monitoring. Review at next scheduled credit committee."
    else:
        action = "No critical alerts. Standard due diligence applies."

    return {
        "country_code": country.code,
        "country_name": country.name,
        "active_alerts": alerts,
        "total_active": len(alerts),
        "highest_severity": highest,
        "affected_sectors": affected,
        "recommended_action": action,
        "political_risk_score": POLITICAL_RISK.get(country.code, 5.0),
        "data_as_of": str(now.date()),
        "bank_review_required": True,
    }
