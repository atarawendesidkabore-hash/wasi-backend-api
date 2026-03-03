"""
Trade Corridor Intelligence API — /api/v3/corridors/

8 endpoints synthesizing transport, FX, trade, logistics, risk, and payment
data into unified corridor scores for 10 ECOWAS trade routes.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.corridor_engine import CorridorIntelligenceEngine
from src.database.corridor_models import TradeCorridor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/corridors", tags=["Corridors"])
limiter = Limiter(key_func=get_remote_address)

VALID_HISTORY_DAYS = {7, 14, 30, 60, 90}


# ── Static routes (before dynamic /{corridor_code}) ──────────────

@router.get("/")
@limiter.limit("30/minute")
def list_corridors(
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all corridors with latest assessment scores."""
    deduct_credits(db, user, 2)
    engine = CorridorIntelligenceEngine(db)
    result = engine.assess_all_corridors()
    db.commit()
    return {
        "as_of": datetime.now(timezone.utc).isoformat() + "Z",
        "corridors": result["results"],
        "count": result["corridors_assessed"],
    }


@router.get("/dashboard")
@limiter.limit("30/minute")
def corridor_dashboard(
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """ECOWAS corridor dashboard with aggregate statistics."""
    deduct_credits(db, user, 5)
    engine = CorridorIntelligenceEngine(db)
    # Ensure assessments exist
    engine.assess_all_corridors()
    db.commit()
    return engine.get_ecowas_corridor_dashboard()


@router.get("/ranking")
@limiter.limit("30/minute")
def corridor_ranking(
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Corridors ranked by composite score (best first)."""
    deduct_credits(db, user, 3)
    engine = CorridorIntelligenceEngine(db)
    # Ensure assessments exist
    engine.assess_all_corridors()
    db.commit()
    rankings = engine.get_corridor_ranking()
    return {
        "as_of": datetime.now(timezone.utc).isoformat() + "Z",
        "rankings": rankings,
    }


@router.get("/compare")
@limiter.limit("30/minute")
def corridor_comparison(
    codes: str = Query(..., description="Comma-separated corridor codes"),
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Side-by-side comparison of selected corridors."""
    deduct_credits(db, user, 3)
    code_list = [c.strip().upper() for c in codes.split(",") if c.strip()]
    if len(code_list) < 2:
        raise HTTPException(400, "Provide at least 2 corridor codes separated by commas")
    if len(code_list) > 5:
        raise HTTPException(400, "Maximum 5 corridors for comparison")

    engine = CorridorIntelligenceEngine(db)
    result = engine.get_corridor_comparison(code_list)
    db.commit()
    if result["count"] == 0:
        raise HTTPException(400, "No valid corridor codes found")
    return result


@router.post("/refresh")
@limiter.limit("5/minute")
def refresh_corridors(
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Trigger full reassessment of all corridors."""
    deduct_credits(db, user, 10)
    engine = CorridorIntelligenceEngine(db)
    result = engine.assess_all_corridors()
    db.commit()
    return {
        "corridors_assessed": result["corridors_assessed"],
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }


# ── Dynamic routes ────────────────────────────────────────────────

@router.get("/{corridor_code}")
@limiter.limit("30/minute")
def corridor_detail(
    corridor_code: str,
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Full corridor assessment with sub-score breakdown."""
    deduct_credits(db, user, 2)
    code = corridor_code.strip().upper()
    corridor = db.query(TradeCorridor).filter(TradeCorridor.corridor_code == code).first()
    if not corridor:
        raise HTTPException(404, f"Corridor '{code}' not found")

    engine = CorridorIntelligenceEngine(db)
    result = engine.assess_corridor(code)
    db.commit()
    return result


@router.get("/{corridor_code}/bottleneck")
@limiter.limit("30/minute")
def corridor_bottleneck(
    corridor_code: str,
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Bottleneck analysis with recommendations."""
    deduct_credits(db, user, 3)
    code = corridor_code.strip().upper()

    engine = CorridorIntelligenceEngine(db)
    # Ensure assessment exists
    engine.assess_corridor(code)
    db.commit()
    result = engine.get_bottleneck_analysis(code)
    if not result:
        raise HTTPException(404, f"Corridor '{code}' not found")
    return result


@router.get("/{corridor_code}/history")
@limiter.limit("30/minute")
def corridor_history(
    corridor_code: str,
    days: int = Query(default=30),
    request=None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Assessment history for a corridor."""
    deduct_credits(db, user, 3)
    if days not in VALID_HISTORY_DAYS:
        raise HTTPException(400, f"days must be one of {sorted(VALID_HISTORY_DAYS)}")

    code = corridor_code.strip().upper()
    engine = CorridorIntelligenceEngine(db)
    result = engine.get_corridor_history(code, days)
    if not result:
        raise HTTPException(404, f"Corridor '{code}' not found")
    return result
