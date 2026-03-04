"""
Live Signals routes — /api/v2/signals/

Provides access to Layer B (hourly news-derived) live adjustments and news events.

Endpoint credit costs:
  GET  /live                       — 1 credit
  GET  /{country_code}/live        — 1 credit
  GET  /events                     — 1 credit
  POST /sweep                      — 5 credits (admin trigger)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from datetime import datetime, timezone

from fastapi import Query as FQuery
from src.database.connection import get_db
from src.database.models import User, Country, LiveSignal, NewsEvent
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.utils.pagination import PaginationParams, paginate
from src.tasks.news_sweep import sweep_news

# ECOWAS v3.0 country codes — only these should appear in signals
ECOWAS_CODES = {"NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV"}

router = APIRouter(prefix="/api/v2/signals", tags=["Live Signals"])

limiter = Limiter(key_func=get_remote_address)


@router.get("/live")
@limiter.limit("20/minute")
async def get_all_live_signals(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All countries' latest live signals (base + adjustment + adjusted index). 1 credit."""
    deduct_credits(current_user, db, "/api/v2/signals/live", cost_multiplier=1.0)

    signals = (
        db.query(LiveSignal, Country)
        .join(Country, Country.id == LiveSignal.country_id)
        .filter(Country.code.in_(ECOWAS_CODES))
        .order_by(LiveSignal.adjusted_index.desc())
        .all()
    )

    return {
        "total": len(signals),
        "computed_at": str(signals[0].LiveSignal.computed_at) if signals else None,
        "signals": [
            {
                "country_code": row.Country.code,
                "country_name": row.Country.name,
                "period_date": str(row.LiveSignal.period_date),
                "base_index": row.LiveSignal.base_index,
                "live_adjustment": row.LiveSignal.live_adjustment,
                "adjusted_index": row.LiveSignal.adjusted_index,
                "computed_at": str(row.LiveSignal.computed_at),
            }
            for row in signals
        ],
    }


@router.get("/{country_code}/live")
@limiter.limit("20/minute")
async def get_country_live_signal(
    request: Request,
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Live signal for a single country with active event breakdown. 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/signals/{country_code}/live", cost_multiplier=1.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    signal = (
        db.query(LiveSignal)
        .filter(LiveSignal.country_id == country.id)
        .order_by(LiveSignal.period_date.desc())
        .first()
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active_events = (
        db.query(NewsEvent)
        .filter(
            NewsEvent.country_id == country.id,
            NewsEvent.is_active == True,
            NewsEvent.expires_at > now,
        )
        .order_by(NewsEvent.detected_at.desc())
        .all()
    )

    return {
        "country_code": country.code,
        "country_name": country.name,
        "signal": {
            "base_index": signal.base_index if signal else None,
            "live_adjustment": signal.live_adjustment if signal else 0.0,
            "adjusted_index": signal.adjusted_index if signal else None,
            "period_date": str(signal.period_date) if signal else None,
            "computed_at": str(signal.computed_at) if signal else None,
        },
        "active_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "headline": e.headline,
                "magnitude": e.magnitude,
                "detected_at": str(e.detected_at),
                "expires_at": str(e.expires_at),
            }
            for e in active_events
        ],
    }


@router.get("/events")
@limiter.limit("20/minute")
async def get_active_events(
    request: Request,
    event_type: str = None,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """All active news events, optionally filtered by event_type. 1 credit."""
    deduct_credits(current_user, db, "/api/v2/signals/events", cost_multiplier=1.0)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    q = (
        db.query(NewsEvent, Country)
        .join(Country, Country.id == NewsEvent.country_id)
        .filter(NewsEvent.is_active == True, NewsEvent.expires_at > now)
    )
    if event_type:
        q = q.filter(NewsEvent.event_type == event_type.upper())
    q = q.order_by(NewsEvent.detected_at.desc())

    result = paginate(q, pagination)
    result["items"] = [
        {
            "id": row.NewsEvent.id,
            "country_code": row.Country.code,
            "country_name": row.Country.name,
            "event_type": row.NewsEvent.event_type,
            "headline": row.NewsEvent.headline,
            "magnitude": row.NewsEvent.magnitude,
            "source_name": row.NewsEvent.source_name,
            "detected_at": str(row.NewsEvent.detected_at),
            "expires_at": str(row.NewsEvent.expires_at),
        }
        for row in result["items"]
    ]
    return result


@router.post("/sweep")
@limiter.limit("10/minute")
async def trigger_news_sweep(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger an RSS news sweep and live signal update. 5 credits.
    Normally runs hourly via scheduler.
    """
    deduct_credits(current_user, db, "/api/v2/signals/sweep", cost_multiplier=5.0)

    result = sweep_news(db)
    return result
