"""
USSD Integration Routes for WASI Backend.

Endpoints:
  PUBLIC (MNO gateway callbacks — authenticated by provider API key):
    POST /api/v2/ussd/callback              — Main USSD session handler
    POST /api/v2/ussd/mobile-money/push     — MNO bulk daily aggregate push

  AUTHENTICATED (WASI API users):
    GET  /api/v2/ussd/status                — Pipeline overview
    GET  /api/v2/ussd/aggregate/{cc}        — Country daily USSD aggregate
    GET  /api/v2/ussd/aggregate/all         — All countries aggregate
    POST /api/v2/ussd/aggregate/calculate   — Trigger aggregation
    GET  /api/v2/ussd/commodity/{cc}        — Commodity price reports
    GET  /api/v2/ussd/trade/{cc}            — Trade declarations
    GET  /api/v2/ussd/port/{cc}             — Port clearance reports
    GET  /api/v2/ussd/mobile-money/{cc}     — Mobile money flows
    POST /api/v2/ussd/providers             — Register MNO provider
    GET  /api/v2/ussd/providers             — List providers
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User, Country
from src.database.ussd_models import (
    USSDProvider, USSDSession, USSDMobileMoneyFlow,
    USSDCommodityReport, USSDTradeDeclaration,
    USSDPortClearance, USSDDailyAggregate,
    USSDRouteReport,
)
from src.schemas.ussd import (
    USSDCallbackRequest, USSDCallbackResponse,
    USSDProviderCreate, USSDProviderResponse,
    MobileMoneyFlowCreate, MobileMoneyFlowResponse,
    CommodityReportResponse, TradeDeclarationResponse,
    PortClearanceResponse, USSDDailyAggregateResponse,
    USSDStatusResponse, RouteReportResponse,
)
from src.utils.periods import parse_quarter
from src.engines.ussd_engine import USSDMenuEngine, USSDDataAggregator, _to_usd
from src.utils.security import get_current_user, require_admin
from src.utils.credits import deduct_credits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/ussd", tags=["USSD Integration"])
limiter = Limiter(key_func=get_remote_address)


# ── Helper: authenticate MNO provider by API key ─────────────────────

def _verify_provider(api_key: str, db: Session) -> USSDProvider:
    """Verify MNO provider API key. Returns provider or raises 403."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    provider = (
        db.query(USSDProvider)
        .filter(USSDProvider.api_key_hash == key_hash, USSDProvider.is_active == True)
        .first()
    )
    if not provider:
        raise HTTPException(status_code=403, detail="Invalid USSD provider API key")
    return provider


# ══════════════════════════════════════════════════════════════════════
# PUBLIC — MNO Gateway Callbacks
# ══════════════════════════════════════════════════════════════════════

@router.post("/callback", response_model=USSDCallbackResponse)
@limiter.limit("120/minute")
async def ussd_callback(
    request: Request,
    payload: USSDCallbackRequest,
    x_provider_key: str = Header(..., alias="X-Provider-Key"),
    db: Session = Depends(get_db),
):
    """
    Main USSD callback endpoint.

    Called by MNO gateway (Africa's Talking, Infobip, or direct operator API)
    on every user interaction. The `text` field contains the full input chain
    separated by `*` (e.g., "1*3*500" means: selected menu 1, then 3, then entered 500).

    No credit cost — this is a data INGESTION endpoint, not a query.
    Authenticated by X-Provider-Key header (MNO partner API key).
    """
    provider = _verify_provider(x_provider_key, db)
    provider_code = provider.provider_code

    engine = USSDMenuEngine(db)
    response_text, session_type = engine.process_callback(
        session_id=payload.sessionId,
        service_code=payload.serviceCode,
        phone_number=payload.phoneNumber,
        text=payload.text,
        provider_code=provider_code,
    )

    return USSDCallbackResponse(
        response=response_text,
        session_type=session_type,
    )


@router.post("/mobile-money/push")
async def push_mobile_money(
    payload: MobileMoneyFlowCreate,
    x_provider_key: str = Header(..., alias="X-Provider-Key"),
    db: Session = Depends(get_db),
):
    """
    Bulk push: MNO sends daily aggregated mobile money transaction data.

    This is the highest-volume, highest-value USSD data source.
    Orange Money alone processes ~$2B/month across WAEMU countries.
    MNO partners push daily aggregates (not individual transactions).

    Authenticated by X-Provider-Key header.
    """
    provider = _verify_provider(x_provider_key, db)

    country = db.query(Country).filter(Country.code == payload.country_code).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {payload.country_code} not found")

    total_usd = payload.total_value_local / payload.fx_rate_usd
    avg_usd = total_usd / max(payload.transaction_count, 1)

    existing = (
        db.query(USSDMobileMoneyFlow)
        .filter(
            USSDMobileMoneyFlow.country_id == country.id,
            USSDMobileMoneyFlow.provider_code == payload.provider_code,
            USSDMobileMoneyFlow.period_date == payload.period_date,
        )
        .first()
    )

    if existing:
        existing.transaction_count = payload.transaction_count
        existing.total_value_local = payload.total_value_local
        existing.total_value_usd = total_usd
        existing.avg_transaction_local = payload.total_value_local / max(payload.transaction_count, 1)
        existing.avg_transaction_usd = avg_usd
        existing.p2p_count = payload.p2p_count or 0
        existing.merchant_count = payload.merchant_count or 0
        existing.bill_pay_count = payload.bill_pay_count or 0
        existing.cash_in_count = payload.cash_in_count or 0
        existing.cash_out_count = payload.cash_out_count or 0
        existing.cross_border_count = payload.cross_border_count or 0
        existing.fx_rate_usd = payload.fx_rate_usd
    else:
        flow = USSDMobileMoneyFlow(
            country_id=country.id,
            provider_code=payload.provider_code,
            period_date=payload.period_date,
            transaction_count=payload.transaction_count,
            total_value_local=payload.total_value_local,
            total_value_usd=total_usd,
            avg_transaction_local=payload.total_value_local / max(payload.transaction_count, 1),
            avg_transaction_usd=avg_usd,
            p2p_count=payload.p2p_count or 0,
            merchant_count=payload.merchant_count or 0,
            bill_pay_count=payload.bill_pay_count or 0,
            cash_in_count=payload.cash_in_count or 0,
            cash_out_count=payload.cash_out_count or 0,
            cross_border_count=payload.cross_border_count or 0,
            local_currency=payload.local_currency,
            fx_rate_usd=payload.fx_rate_usd,
            confidence=0.85,
        )
        db.add(flow)

    db.commit()

    logger.info(
        "Mobile money push: %s/%s %s — %d txns, %.2f USD",
        payload.country_code, payload.provider_code,
        payload.period_date, payload.transaction_count, total_usd,
    )

    return {
        "status": "accepted",
        "country_code": payload.country_code,
        "provider_code": payload.provider_code,
        "period_date": str(payload.period_date),
        "transaction_count": payload.transaction_count,
        "total_value_usd": round(total_usd, 2),
    }


# ══════════════════════════════════════════════════════════════════════
# AUTHENTICATED — WASI API Queries
# ══════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=USSDStatusResponse)
async def get_ussd_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """USSD data pipeline status overview. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v2/ussd/status")

    today = date.today()
    total_providers = db.query(USSDProvider).count()
    active_providers = db.query(USSDProvider).filter(USSDProvider.is_active == True).count()
    sessions_today = (
        db.query(USSDSession)
        .filter(USSDSession.started_at >= datetime.combine(today, datetime.min.time()))
        .count()
    )
    sessions_all = db.query(USSDSession).count()

    # Countries with any USSD data
    countries_money = db.query(func.count(func.distinct(USSDMobileMoneyFlow.country_id))).scalar() or 0
    countries_commodity = db.query(func.count(func.distinct(USSDCommodityReport.country_id))).scalar() or 0
    countries_trade = db.query(func.count(func.distinct(USSDTradeDeclaration.country_id))).scalar() or 0
    countries_port = db.query(func.count(func.distinct(USSDPortClearance.country_id))).scalar() or 0

    unique_countries = set()
    for model in [USSDMobileMoneyFlow, USSDCommodityReport, USSDTradeDeclaration, USSDPortClearance, USSDRouteReport]:
        ids = db.query(func.distinct(model.country_id)).all()
        unique_countries.update(r[0] for r in ids)

    latest_agg = db.query(func.max(USSDDailyAggregate.period_date)).scalar()

    return USSDStatusResponse(
        total_providers=total_providers,
        active_providers=active_providers,
        total_sessions_today=sessions_today,
        total_sessions_all=sessions_all,
        countries_with_data=len(unique_countries),
        data_sources={
            "mobile_money": db.query(USSDMobileMoneyFlow).count(),
            "commodity_reports": db.query(USSDCommodityReport).count(),
            "trade_declarations": db.query(USSDTradeDeclaration).count(),
            "port_clearances": db.query(USSDPortClearance).count(),
            "route_reports": db.query(USSDRouteReport).count(),
        },
        latest_aggregate_date=latest_agg,
    )


@router.get("/aggregate/all")
async def get_all_aggregates(
    period_date: Optional[date] = Query(default=None),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides period_date."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get USSD daily aggregate for all countries. Costs 2 credits."""
    deduct_credits(current_user, db, "/api/v2/ussd/aggregate/all", cost_multiplier=2.0)

    agg_query = (
        db.query(USSDDailyAggregate, Country)
        .join(Country, Country.id == USSDDailyAggregate.country_id)
    )
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        agg_query = agg_query.filter(USSDDailyAggregate.period_date.between(q_start, q_end))
    else:
        target = period_date or date.today()
        agg_query = agg_query.filter(USSDDailyAggregate.period_date == target)

    rows = agg_query.all()

    results = []
    for agg, country in rows:
        results.append({
            "country_code": country.code,
            "country_name": country.name,
            "period_date": str(agg.period_date),
            "mobile_money_score": agg.mobile_money_score,
            "commodity_price_score": agg.commodity_price_score,
            "informal_trade_score": agg.informal_trade_score,
            "port_efficiency_score": agg.port_efficiency_score,
            "ussd_composite_score": agg.ussd_composite_score,
            "data_points": agg.data_points_count,
            "providers_reporting": agg.providers_reporting,
            "confidence": agg.confidence,
        })

    label = quarter if quarter else str(period_date or date.today())
    return {"period_date": label, "aggregates": results}


@router.get("/aggregate/summary")
async def get_aggregate_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """USSD data summary across all countries — latest scores. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v2/ussd/aggregate/summary")

    # Get latest aggregate per country with actual scores (most recent period_date with non-null composite)
    subq = (
        db.query(
            USSDDailyAggregate.country_id,
            func.max(USSDDailyAggregate.period_date).label("latest_date"),
        )
        .filter(USSDDailyAggregate.ussd_composite_score.isnot(None))
        .group_by(USSDDailyAggregate.country_id)
        .subquery()
    )
    rows = (
        db.query(USSDDailyAggregate, Country)
        .join(Country, Country.id == USSDDailyAggregate.country_id)
        .join(subq, (USSDDailyAggregate.country_id == subq.c.country_id) & (USSDDailyAggregate.period_date == subq.c.latest_date))
        .all()
    )

    # Get date range + total record count
    date_stats = db.query(
        func.min(USSDDailyAggregate.period_date),
        func.max(USSDDailyAggregate.period_date),
        func.sum(USSDDailyAggregate.data_points_count),
    ).first()

    countries = []
    for agg, country in rows:
        countries.append({
            "country_code": country.code,
            "country_name": country.name,
            "composite_score": agg.ussd_composite_score,
            "mobile_money_score": agg.mobile_money_score,
            "commodity_score": agg.commodity_price_score,
            "trade_score": agg.informal_trade_score,
            "port_score": agg.port_efficiency_score,
            "records": agg.data_points_count,
            "dates": 1,
            "confidence": agg.confidence,
            "period_date": str(agg.period_date),
        })

    return {
        "countries": sorted(countries, key=lambda c: c["composite_score"] or 0, reverse=True),
        "total_records": int(date_stats[2] or 0) if date_stats else 0,
        "date_range": {
            "from": str(date_stats[0]) if date_stats and date_stats[0] else None,
            "to": str(date_stats[1]) if date_stats and date_stats[1] else None,
        },
    }


@router.get("/aggregate/{country_code}")
async def get_country_aggregate(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=400, ge=1, le=730),
    quarter: Optional[str] = Query(default=None, description="Filter by quarter: Q1-2026, T3-2025, etc. Overrides days."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get USSD aggregate history for a country. Costs 1 credit. Default shows last 400 days."""
    deduct_credits(current_user, db, f"/api/v2/ussd/aggregate/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    q = db.query(USSDDailyAggregate).filter(USSDDailyAggregate.country_id == country.id)
    if quarter:
        q_start, q_end = parse_quarter(quarter)
        q = q.filter(USSDDailyAggregate.period_date.between(q_start, q_end))
    else:
        cutoff = date.today() - timedelta(days=days)
        q = q.filter(USSDDailyAggregate.period_date >= cutoff)

    rows = q.order_by(USSDDailyAggregate.period_date.desc()).all()

    return {
        "country_code": country.code,
        "country_name": country.name,
        "history": [
            {
                "period_date": str(r.period_date),
                "mobile_money_score": r.mobile_money_score,
                "commodity_price_score": r.commodity_price_score,
                "informal_trade_score": r.informal_trade_score,
                "port_efficiency_score": r.port_efficiency_score,
                "ussd_composite_score": r.ussd_composite_score,
                "data_points": r.data_points_count,
                "confidence": r.confidence,
            }
            for r in rows
        ],
    }


@router.post("/aggregate/calculate")
async def trigger_aggregation(
    period_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger USSD data aggregation for all countries. Costs 5 credits.

    If period_date is provided, aggregates that specific date.
    If omitted, discovers ALL dates with data and aggregates each one.
    """
    deduct_credits(current_user, db, "/api/v2/ussd/aggregate/calculate", cost_multiplier=5.0)

    if period_date:
        # Aggregate a specific date
        aggregator = USSDDataAggregator(db)
        results = aggregator.aggregate_all(period_date)
        return {
            "status": "completed",
            "period_date": str(period_date),
            "countries_processed": len(results),
            "results": results,
        }

    # No date specified — aggregate ALL dates with data
    from src.tasks.ussd_aggregation import run_ussd_aggregation
    return run_ussd_aggregation(db)


@router.get("/commodity/{country_code}", response_model=list[CommodityReportResponse])
async def get_commodity_reports(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get USSD commodity price reports for a country. Costs 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/ussd/commodity/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(USSDCommodityReport)
        .filter(
            USSDCommodityReport.country_id == country.id,
            USSDCommodityReport.period_date >= cutoff,
        )
        .order_by(USSDCommodityReport.period_date.desc())
        .all()
    )


@router.get("/trade/{country_code}", response_model=list[TradeDeclarationResponse])
async def get_trade_declarations(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get USSD cross-border trade declarations. Costs 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/ussd/trade/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(USSDTradeDeclaration)
        .filter(
            USSDTradeDeclaration.country_id == country.id,
            USSDTradeDeclaration.period_date >= cutoff,
        )
        .order_by(USSDTradeDeclaration.period_date.desc())
        .all()
    )


@router.get("/port/{country_code}", response_model=list[PortClearanceResponse])
async def get_port_clearances(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get USSD port clearance reports. Costs 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/ussd/port/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(USSDPortClearance)
        .filter(
            USSDPortClearance.country_id == country.id,
            USSDPortClearance.period_date >= cutoff,
        )
        .order_by(USSDPortClearance.period_date.desc())
        .all()
    )


@router.get("/mobile-money/{country_code}", response_model=list[MobileMoneyFlowResponse])
async def get_mobile_money_flows(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get mobile money transaction flows. Costs 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/ussd/mobile-money/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(USSDMobileMoneyFlow)
        .filter(
            USSDMobileMoneyFlow.country_id == country.id,
            USSDMobileMoneyFlow.period_date >= cutoff,
        )
        .order_by(USSDMobileMoneyFlow.period_date.desc())
        .all()
    )


# ── Provider management ───────────────────────────────────────────────

@router.post("/providers", response_model=USSDProviderResponse)
async def register_provider(
    payload: USSDProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Register a new USSD MNO provider. Admin only."""
    deduct_credits(current_user, db, "/api/v2/ussd/providers", cost_multiplier=10.0)

    existing = (
        db.query(USSDProvider)
        .filter(USSDProvider.provider_code == payload.provider_code)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Provider already registered")

    # Generate API key and hash it
    import secrets
    api_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    provider = USSDProvider(
        provider_code=payload.provider_code,
        provider_name=payload.provider_name,
        gateway_url=payload.gateway_url,
        api_key_hash=key_hash,
        country_codes=payload.country_codes,
        ussd_shortcode=payload.ussd_shortcode,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)

    logger.info("Registered USSD provider: %s (%s)", payload.provider_code, payload.provider_name)

    # Return the API key ONCE (it's hashed in DB)
    return {
        **USSDProviderResponse.model_validate(provider).model_dump(),
        "api_key": api_key,  # Only shown at creation time
    }


@router.get("/providers", response_model=list[USSDProviderResponse])
async def list_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List registered USSD providers. Costs 1 credit."""
    deduct_credits(current_user, db, "/api/v2/ussd/providers")
    return db.query(USSDProvider).all()


# ── Route report endpoints ───────────────────────────────────────────

@router.get("/routes/{country_code}")
async def get_route_reports(
    country_code: str = Path(pattern="^[A-Za-z]{2}$"),
    days: int = Query(default=7, ge=1, le=90),
    corridor: Optional[str] = Query(default=None, description="Filter by corridor code"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get crowdsourced route condition reports for a country. Costs 1 credit."""
    deduct_credits(current_user, db, f"/api/v2/ussd/routes/{country_code}")

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country {country_code} not found")

    cutoff = date.today() - timedelta(days=days)
    query = (
        db.query(USSDRouteReport)
        .filter(
            USSDRouteReport.country_id == country.id,
            USSDRouteReport.period_date >= cutoff,
        )
    )
    if corridor:
        query = query.filter(USSDRouteReport.corridor_code == corridor.upper())
    rows = query.order_by(USSDRouteReport.period_date.desc()).all()

    return {
        "country_code": country.code,
        "country_name": country.name,
        "reports": [
            {
                "period_date": str(r.period_date),
                "corridor_code": r.corridor_code,
                "corridor_name": r.corridor_name,
                "report_type": r.report_type,
                "road_surface": r.road_surface,
                "condition_score": r.condition_score,
                "wait_hours": r.wait_hours,
                "fuel_type": r.fuel_type,
                "fuel_price_local": r.fuel_price_local,
                "fuel_price_usd": r.fuel_price_usd,
                "transit_hours": r.transit_hours,
                "reporter_count": r.reporter_count,
                "reporter_type": r.reporter_type,
                "confidence": r.confidence,
            }
            for r in rows
        ],
    }


@router.get("/routes/corridor/{corridor_code}")
async def get_corridor_reports(
    corridor_code: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all route reports for a specific corridor across countries. Costs 2 credits."""
    deduct_credits(current_user, db, f"/api/v2/ussd/routes/corridor/{corridor_code}", cost_multiplier=2.0)

    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(USSDRouteReport, Country)
        .join(Country, Country.id == USSDRouteReport.country_id)
        .filter(
            USSDRouteReport.corridor_code == corridor_code.upper(),
            USSDRouteReport.period_date >= cutoff,
        )
        .order_by(USSDRouteReport.period_date.desc())
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail=f"No reports for corridor '{corridor_code}'")

    return {
        "corridor_code": corridor_code.upper(),
        "corridor_name": rows[0][0].corridor_name if rows else corridor_code,
        "reports": [
            {
                "period_date": str(r.period_date),
                "country_code": c.code,
                "report_type": r.report_type,
                "road_surface": r.road_surface,
                "condition_score": r.condition_score,
                "wait_hours": r.wait_hours,
                "fuel_type": r.fuel_type,
                "fuel_price_local": r.fuel_price_local,
                "transit_hours": r.transit_hours,
                "reporter_count": r.reporter_count,
                "confidence": r.confidence,
            }
            for r, c in rows
        ],
    }


@router.post("/routes/bridge")
async def trigger_route_bridge(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Manually trigger route-to-RoadCorridor bridge. Admin only, 5 credits."""
    deduct_credits(current_user, db, "/api/v2/ussd/routes/bridge", cost_multiplier=5.0)
    from src.tasks.ussd_aggregation import bridge_route_to_road_corridors
    return bridge_route_to_road_corridors(db)
