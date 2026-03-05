"""
Personalized Data Intelligence Routes — Spotify Wrapped for data producers.

7 GET endpoints under /api/v3/intelligence/, all FREE (0 credits).
"""
import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.engines.intelligence_engine import ContributorIntelligenceEngine
from src.schemas.intelligence import (
    ProfileCardResponse, SpecializationResponse, QualityTrendsResponse,
    EarningProjectionResponse, CoverageOpportunitiesResponse,
    NudgeResponse, WrappedSummaryResponse,
)
from src.utils.security import get_current_user
from src.utils.phone_hash import phone_hash_from_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v3/intelligence", tags=["Intelligence (Spotify Wrapped)"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/profile", response_model=ProfileCardResponse)
@limiter.limit("30/minute")
async def get_profile(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Reputation breakdown + tier progress + weakest factor advice."""
    return ContributorIntelligenceEngine.get_profile_card(db, phone_hash_from_user(user))


@router.get("/specialization", response_model=SpecializationResponse)
@limiter.limit("20/minute")
async def get_specialization(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Token type expertise analysis + country comparison."""
    return ContributorIntelligenceEngine.get_data_specialization(db, phone_hash_from_user(user))


@router.get("/quality", response_model=QualityTrendsResponse)
@limiter.limit("20/minute")
async def get_quality(
    request: Request,
    months: int = Query(6, ge=1, le=12),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confidence trends + cross-validation rate + peer comparison."""
    return ContributorIntelligenceEngine.get_quality_trends(db, phone_hash_from_user(user), months)


@router.get("/earnings", response_model=EarningProjectionResponse)
@limiter.limit("20/minute")
async def get_earnings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Earning projections + what-if scenarios."""
    return ContributorIntelligenceEngine.get_earning_projection(db, phone_hash_from_user(user))


@router.get("/opportunities", response_model=CoverageOpportunitiesResponse)
@limiter.limit("10/minute")
async def get_opportunities(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Coverage gaps + underserved token types + matching challenges."""
    return ContributorIntelligenceEngine.get_coverage_opportunities(db, phone_hash_from_user(user))


@router.get("/nudges", response_model=list[NudgeResponse])
@limiter.limit("30/minute")
async def get_nudges(
    request: Request,
    locale: str = Query("fr", pattern="^(en|fr)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """3-5 personalized, prioritized action items."""
    return ContributorIntelligenceEngine.get_nudges(db, phone_hash_from_user(user), locale)


@router.get("/wrapped", response_model=WrappedSummaryResponse)
@limiter.limit("10/minute")
async def get_wrapped(
    request: Request,
    year: int = Query(2026, ge=2025, le=2030),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Annual 'Spotify Wrapped' style summary."""
    return ContributorIntelligenceEngine.get_wrapped_summary(db, phone_hash_from_user(user), year)
