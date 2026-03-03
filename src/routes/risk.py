"""
Risk Scoring & Anomaly Detection Routes — /api/v3/risk/

Credit costs:
  GET  /country/{cc}           — 3 credits  (single country risk profile)
  GET  /regional               — 10 credits (all 16 ECOWAS countries)
  GET  /anomalies/{cc}         — 2 credits  (anomaly detection)
  GET  /correlation/{a}/{b}    — 2 credits  (country pair correlation)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.risk_engine import RiskEngine
from src.schemas.risk import (
    CountryRiskResponse,
    RegionalRiskResponse,
    AnomalyResponse,
    CorrelationResponse,
)

router = APIRouter(prefix="/api/v3/risk", tags=["Risk & Anomaly Detection"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/country/{country_code}", response_model=CountryRiskResponse)
@limiter.limit("20/minute")
async def get_country_risk(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get multi-dimensional risk profile for a single ECOWAS country.

    Combines trade (30%), macro (25%), political (20%),
    logistics (15%), and market (10%) risk dimensions.
    """
    deduct_credits(current_user, db, "/api/v3/risk/country", "GET", 3.0)

    engine = RiskEngine(db)
    result = engine.score_country(country_code)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return CountryRiskResponse(**result)


@router.get("/regional", response_model=RegionalRiskResponse)
@limiter.limit("5/minute")
async def get_regional_risk(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get risk scores for all 16 ECOWAS countries plus regional aggregate."""
    deduct_credits(current_user, db, "/api/v3/risk/regional", "GET", 10.0)

    engine = RiskEngine(db)
    result = engine.score_all_countries()
    return RegionalRiskResponse(**result)


@router.get("/anomalies/{country_code}", response_model=AnomalyResponse)
@limiter.limit("20/minute")
async def detect_anomalies(
    request: Request,
    country_code: str,
    lookback_days: int = Query(30, ge=7, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Detect anomalies in recent WASI data for a country.

    Checks for: index outliers (>2σ), sudden changes (>15%),
    negative event accumulation, and data staleness.
    """
    deduct_credits(current_user, db, "/api/v3/risk/anomalies", "GET", 2.0)

    engine = RiskEngine(db)
    result = engine.detect_anomalies(country_code, lookback_days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return AnomalyResponse(**result)


@router.get("/correlation/{country_a}/{country_b}", response_model=CorrelationResponse)
@limiter.limit("20/minute")
async def get_country_correlation(
    request: Request,
    country_a: str,
    country_b: str,
    lookback_days: int = Query(90, ge=30, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compute Pearson correlation between two countries' WASI indices.

    Returns correlation coefficient (-1 to +1), data point count,
    and human-readable interpretation.
    """
    deduct_credits(current_user, db, "/api/v3/risk/correlation", "GET", 2.0)

    engine = RiskEngine(db)
    result = engine.correlate_countries(country_a, country_b, lookback_days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return CorrelationResponse(**result)
