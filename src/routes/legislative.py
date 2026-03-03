"""
Legislative monitoring routes — /api/v3/legislative/

Tracks laws passed by ECOWAS country parliaments and their impact on WASI scores.
Data sources: Laws.Africa API, IPU Parline, RSS keyword detection.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User, Country
from src.database.legislative_models import LegislativeAct, ParliamentarySession
from src.engines.legislative_engine import LegislativeImpactEngine
from src.schemas.legislative import (
    LegislativeActResponse,
    CountryLegislativeResponse,
    LegislativeImpactResponse,
    ECOWASLegislativeSummary,
    LegislativeRefreshResponse,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/v3/legislative", tags=["Legislative Monitoring"])

ECOWAS_CODES = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ",
    "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]


def _confidence_indicator(conf: float | None) -> str:
    if conf is None:
        return "grey"
    if conf >= 0.70:
        return "green"
    if conf >= 0.40:
        return "yellow"
    return "red"


def _act_to_response(act: LegislativeAct, country_code: str, country_name: str) -> LegislativeActResponse:
    return LegislativeActResponse(
        id=act.id,
        country_code=country_code,
        country_name=country_name,
        title=act.title,
        description=act.description,
        act_number=act.act_number,
        act_date=act.act_date,
        category=act.category,
        status=act.status,
        impact_type=act.impact_type,
        estimated_magnitude=act.estimated_magnitude,
        source_url=act.source_url,
        source_name=act.source_name,
        confidence=act.confidence,
        data_quality=act.data_quality,
        data_source=act.data_source,
        is_active=act.is_active,
        detected_at=act.detected_at,
        confidence_indicator=_confidence_indicator(act.confidence),
    )


# ── GET /api/v3/legislative/latest ────────────────────────────────────────────
# Fixed route order: static paths (/latest, /summary, /refresh) BEFORE dynamic /{country_code}

@router.get("/latest", response_model=list[LegislativeActResponse])
def get_latest_legislation(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent legislation across all ECOWAS countries (2 credits)."""
    deduct_credits(current_user, db, "/api/v3/legislative/latest", "GET", cost_multiplier=2)

    acts = (
        db.query(LegislativeAct, Country)
        .join(Country, LegislativeAct.country_id == Country.id)
        .filter(LegislativeAct.is_active == True)
        .order_by(LegislativeAct.act_date.desc())
        .limit(limit)
        .all()
    )

    return [_act_to_response(act, country.code, country.name) for act, country in acts]


# ── GET /api/v3/legislative/summary ───────────────────────────────────────────

@router.get("/summary", response_model=ECOWASLegislativeSummary)
def get_ecowas_legislative_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get ECOWAS-wide legislative impact dashboard (5 credits)."""
    deduct_credits(current_user, db, "/api/v3/legislative/summary", "GET", cost_multiplier=5)

    engine = LegislativeImpactEngine(db)
    return ECOWASLegislativeSummary(**engine.get_ecowas_summary())


# ── POST /api/v3/legislative/refresh ──────────────────────────────────────────

@router.post("/refresh", response_model=LegislativeRefreshResponse)
def refresh_legislation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger legislative data refresh (10 credits)."""
    deduct_credits(current_user, db, "/api/v3/legislative/refresh", "POST", cost_multiplier=10)

    from src.pipelines.scrapers.legislative_scraper import run_legislative_scraper

    # Step 1: Scrape
    scraper_result = run_legislative_scraper(db)

    # Step 2: Score new acts
    engine = LegislativeImpactEngine(db)
    unscored = (
        db.query(LegislativeAct)
        .filter(
            LegislativeAct.estimated_magnitude == 0.0,
            LegislativeAct.is_active == True,
        )
        .all()
    )
    for act in unscored:
        engine.score_and_update_act(act)
        if abs(act.estimated_magnitude) > 5.0:
            engine.emit_news_event(act)

    return LegislativeRefreshResponse(**scraper_result)


# ── GET /api/v3/legislative/{country_code} ────────────────────────────────────

@router.get("/{country_code}", response_model=list[LegislativeActResponse])
def get_country_legislation(
    country_code: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get legislation for a specific ECOWAS country (1 credit)."""
    cc = country_code.upper()
    if cc not in ECOWAS_CODES:
        raise HTTPException(status_code=404, detail=f"Country {cc} not in ECOWAS set")

    deduct_credits(current_user, db, f"/api/v3/legislative/{cc}", "GET", cost_multiplier=1)

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {cc} not found")

    acts = (
        db.query(LegislativeAct)
        .filter(
            LegislativeAct.country_id == country.id,
            LegislativeAct.is_active == True,
        )
        .order_by(LegislativeAct.act_date.desc())
        .limit(limit)
        .all()
    )

    return [_act_to_response(act, cc, country.name) for act in acts]


# ── GET /api/v3/legislative/{country_code}/impact ─────────────────────────────

@router.get("/{country_code}/impact", response_model=LegislativeImpactResponse)
def get_country_legislative_impact(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get legislative impact assessment for a country (3 credits)."""
    cc = country_code.upper()
    if cc not in ECOWAS_CODES:
        raise HTTPException(status_code=404, detail=f"Country {cc} not in ECOWAS set")

    deduct_credits(current_user, db, f"/api/v3/legislative/{cc}/impact", "GET", cost_multiplier=3)

    engine = LegislativeImpactEngine(db)
    result = engine.get_legislative_impact(cc)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return LegislativeImpactResponse(**result)
