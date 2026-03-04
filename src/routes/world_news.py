"""
World News Intelligence routes — /api/v3/news/

Provides access to worldwide news events, their impact on ECOWAS countries,
and daily intelligence briefings.

Endpoint credit costs:
  GET  /worldwide                    — 2 credits
  GET  /daily-briefing               — 5 credits
  GET  /impact/{event_id}            — 3 credits
  GET  /country/{cc}/exposure        — 2 credits
  POST /refresh                      — 20 credits (manual trigger)
"""
import json
from datetime import datetime, date, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User, Country
from src.database.world_news_models import (
    WorldNewsEvent, NewsImpactAssessment, DailyNewsBriefing,
)
from src.engines.world_news_engine import (
    RELEVANCE_THRESHOLD_HIGH,
    generate_daily_briefing,
)
from src.schemas.world_news import (
    WorldNewsEventResponse,
    ImpactCascadeResponse,
    ImpactAssessmentResponse,
    CountryExposureResponse,
    CountryExposureItem,
    DailyBriefingResponse,
    DailyBriefingTopEvent,
    DailyBriefingCountryImpact,
    WorldNewsSweepResponse,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.pagination import PaginationParams, paginate

ECOWAS_CODES = {
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
    "NE", "MR", "GW", "SL", "LR", "GM", "CV",
}

router = APIRouter(prefix="/api/v3/news", tags=["World News Intelligence"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/worldwide")
@limiter.limit("20/minute")
async def get_worldwide_news(
    request: Request,
    event_type: str = None,
    min_relevance: float = Query(default=0.0, ge=0.0, le=1.0),
    active_only: bool = Query(default=True),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated global news feed with relevance scores. 2 credits."""
    deduct_credits(current_user, db, "/api/v3/news/worldwide", cost_multiplier=2.0)

    now = datetime.now(timezone.utc)
    q = db.query(WorldNewsEvent)

    if active_only:
        q = q.filter(WorldNewsEvent.is_active.is_(True), WorldNewsEvent.expires_at > now)
    if event_type:
        q = q.filter(WorldNewsEvent.event_type == event_type.upper())
    if min_relevance > 0.0:
        q = q.filter(WorldNewsEvent.relevance_score >= min_relevance)

    q = q.order_by(WorldNewsEvent.relevance_score.desc(), WorldNewsEvent.detected_at.desc())
    result = paginate(q, pagination)

    result["items"] = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "headline": e.headline,
            "summary": e.summary or "",
            "source_url": e.source_url,
            "source_name": e.source_name,
            "source_region": e.source_region,
            "relevance_score": e.relevance_score,
            "relevance_layer1_keyword": e.relevance_layer1_keyword,
            "relevance_layer2_supply_chain": e.relevance_layer2_supply_chain,
            "relevance_layer3_transmission": e.relevance_layer3_transmission,
            "keywords_matched": json.loads(e.keywords_matched) if e.keywords_matched else [],
            "global_magnitude": e.global_magnitude,
            "detected_at": str(e.detected_at),
            "expires_at": str(e.expires_at),
            "is_active": e.is_active,
            "cascaded": e.cascaded,
        }
        for e in result["items"]
    ]
    return result


@router.get("/daily-briefing")
@limiter.limit("20/minute")
async def get_daily_briefing(
    request: Request,
    briefing_date: date = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Today's intelligence digest. 5 credits. Cached daily."""
    deduct_credits(current_user, db, "/api/v3/news/daily-briefing", cost_multiplier=5.0)

    target_date = briefing_date or date.today()

    # Check cache
    briefing = (
        db.query(DailyNewsBriefing)
        .filter(DailyNewsBriefing.briefing_date == target_date)
        .first()
    )

    if not briefing:
        # Generate on-demand
        data = generate_daily_briefing(db, target_date)
        briefing = DailyNewsBriefing(**data)
        db.add(briefing)
        db.commit()
        db.refresh(briefing)

    top_events_raw = json.loads(briefing.top_events_json)
    country_exposure_raw = json.loads(briefing.country_exposure_json)
    trend_raw = json.loads(briefing.trend_indicators_json)
    watchlist_raw = json.loads(briefing.watchlist_json)

    top_events = [DailyBriefingTopEvent(**e) for e in top_events_raw]
    country_impacts = [
        DailyBriefingCountryImpact(
            country_code=cc,
            net_global_impact=data["net_impact"],
            active_global_events=data["event_count"],
            trend=trend_raw.get(cc, "stable"),
        )
        for cc, data in country_exposure_raw.items()
    ]

    return DailyBriefingResponse(
        briefing_date=briefing.briefing_date,
        total_global_events=briefing.total_global_events,
        high_relevance_events=briefing.high_relevance_events,
        countries_affected=briefing.countries_affected,
        top_events=top_events,
        country_impacts=country_impacts,
        watchlist=watchlist_raw,
        generated_at=briefing.generated_at,
    )


@router.get("/impact/{event_id}")
@limiter.limit("20/minute")
async def get_impact_cascade(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cascade analysis for a specific global event. 3 credits."""
    deduct_credits(current_user, db, "/api/v3/news/impact", cost_multiplier=3.0)

    event = db.query(WorldNewsEvent).filter(WorldNewsEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"World news event {event_id} not found")

    assessments = (
        db.query(NewsImpactAssessment)
        .filter(NewsImpactAssessment.world_news_event_id == event_id)
        .order_by(NewsImpactAssessment.country_magnitude.asc())
        .all()
    )

    most_affected = assessments[0].country_code if assessments else None
    cascaded_count = sum(1 for a in assessments if a.news_event_created)

    return ImpactCascadeResponse(
        world_event=WorldNewsEventResponse(
            id=event.id,
            event_type=event.event_type,
            headline=event.headline,
            summary=event.summary or "",
            source_url=event.source_url,
            source_name=event.source_name,
            source_region=event.source_region,
            relevance_score=event.relevance_score,
            relevance_layer1_keyword=event.relevance_layer1_keyword,
            relevance_layer2_supply_chain=event.relevance_layer2_supply_chain,
            relevance_layer3_transmission=event.relevance_layer3_transmission,
            keywords_matched=json.loads(event.keywords_matched) if event.keywords_matched else [],
            global_magnitude=event.global_magnitude,
            detected_at=event.detected_at,
            expires_at=event.expires_at,
            is_active=event.is_active,
            cascaded=event.cascaded,
        ),
        assessments=[
            ImpactAssessmentResponse(
                id=a.id,
                world_news_event_id=a.world_news_event_id,
                country_code=a.country_code,
                direct_impact=a.direct_impact,
                indirect_impact=a.indirect_impact,
                systemic_impact=a.systemic_impact,
                country_magnitude=a.country_magnitude,
                transmission_channel=a.transmission_channel,
                explanation=a.explanation,
                news_event_created=a.news_event_created,
                assessed_at=a.assessed_at,
            )
            for a in assessments
        ],
        countries_affected=len(assessments),
        most_affected_country=most_affected,
        total_cascaded_events=cascaded_count,
    )


@router.get("/country/{country_code}/exposure")
@limiter.limit("20/minute")
async def get_country_exposure(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Country's exposure to active global events. 2 credits."""
    deduct_credits(current_user, db, "/api/v3/news/country/exposure", cost_multiplier=2.0)

    cc = country_code.upper()
    if cc not in ECOWAS_CODES:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not in ECOWAS")

    country = db.query(Country).filter(Country.code == cc).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    now = datetime.now(timezone.utc)
    assessments = (
        db.query(NewsImpactAssessment, WorldNewsEvent)
        .join(WorldNewsEvent, WorldNewsEvent.id == NewsImpactAssessment.world_news_event_id)
        .filter(
            NewsImpactAssessment.country_code == cc,
            WorldNewsEvent.is_active.is_(True),
            WorldNewsEvent.expires_at > now,
        )
        .order_by(NewsImpactAssessment.country_magnitude.asc())
        .all()
    )

    net_adjustment = sum(row.NewsImpactAssessment.country_magnitude for row in assessments)

    items = [
        CountryExposureItem(
            event_id=row.WorldNewsEvent.id,
            event_type=row.WorldNewsEvent.event_type,
            headline=row.WorldNewsEvent.headline,
            country_magnitude=row.NewsImpactAssessment.country_magnitude,
            transmission_channel=row.NewsImpactAssessment.transmission_channel,
            detected_at=row.WorldNewsEvent.detected_at,
        )
        for row in assessments
    ]

    return CountryExposureResponse(
        country_code=cc,
        country_name=country.name,
        total_active_global_events=len(items),
        net_global_adjustment=round(net_adjustment, 4),
        exposure_items=items,
    )


@router.post("/refresh")
@limiter.limit("5/minute")
async def trigger_world_news_sweep(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger manual worldwide news sweep. 20 credits."""
    deduct_credits(current_user, db, "/api/v3/news/refresh", cost_multiplier=20.0)

    from src.tasks.world_news_sweep import sweep_world_news
    result = sweep_world_news(db)
    return result
