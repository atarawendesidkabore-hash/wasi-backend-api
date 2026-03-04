"""
ML routes — /api/v2/ml/

IMF-style credit scoring using pre-fitted logistic regression.
Endpoint credit costs:
  GET  /credit-score/{country_code} — 3 credits
  GET  /credit-score/all            — 5 credits
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite
from src.engines.ml_engine import WASIMLEngine
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/v2/ml", tags=["ML"])

limiter = Limiter(key_func=get_remote_address)

_engine = WASIMLEngine()


def _get_latest_country_data(db: Session, country: Country) -> dict:
    """Fetch latest CountryIndex and WASI composite for a country."""
    idx = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    wasi = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )
    return {"index": idx, "wasi": wasi}


def _build_score(country: Country, data: dict) -> dict:
    idx = data["index"]
    wasi = data["wasi"]

    wasi_val = idx.index_value if idx else None
    gdp_val = idx.gdp_growth_pct if idx else None
    # Use shipping_score as a proxy for trade balance access
    trade_val = None
    if idx and idx.trade_score is not None:
        # trade_score is 0–100; map to approx trade balance pct (−30 to +10)
        trade_val = (idx.trade_score / 100.0) * 40.0 - 30.0

    return _engine.predict_credit_grade(
        country_code=country.code,
        wasi_index=wasi_val,
        gdp_growth_pct=gdp_val,
        trade_balance_pct=trade_val,
        inflation_rate=None,       # not stored in current schema; uses ECOWAS median
        debt_to_gdp_pct=None,      # not stored in current schema; uses ECOWAS median
        political_stability_score=None,  # not stored; uses ECOWAS median
    )


@router.get("/credit-score/all")
@limiter.limit("20/minute")
async def get_ml_credit_scores_all(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    IMF-style ML credit grades for all active WASI countries. 5 credits.
    Results sorted by probability descending (highest-rated first).
    """
    deduct_credits(current_user, db, "/api/v2/ml/credit-score/all", cost_multiplier=5.0)

    countries = db.query(Country).filter(Country.is_active == True).all()
    results = []
    for country in countries:
        data = _get_latest_country_data(db, country)
        score = _build_score(country, data)
        score["country_name"] = country.name
        results.append(score)

    results.sort(key=lambda x: x["probability"], reverse=True)

    return {
        "total_countries": len(results),
        "model": "logistic_regression_v1",
        "grades": results,
    }


@router.get("/credit-score/{country_code}")
@limiter.limit("20/minute")
async def get_ml_credit_score(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    IMF-style ML credit grade for a single country. 3 credits.

    Uses latest CountryIndex data + WASI composite as model inputs.
    Missing macro inputs (inflation, debt, political stability) fall back
    to ECOWAS median estimates embedded in the model.
    """
    deduct_credits(current_user, db, f"/api/v2/ml/credit-score/{country_code}", cost_multiplier=3.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    data = _get_latest_country_data(db, country)
    result = _build_score(country, data)
    result["country_name"] = country.name
    return result
