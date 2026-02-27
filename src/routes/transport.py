"""
Transport Layer routes — /api/v2/transport/

Multi-modal transport composite index (Maritime + Air + Rail + Road).
Endpoint credit costs:
  GET  /latest/{country_code}        — 2 credits
  GET  /history/{country_code}       — 3 credits
  GET  /composite                    — 3 credits
  POST /calculate                    — 5 credits
  GET  /rail/sitarail                — 0 credits (public)
  GET  /airport/{iata_code}          — 1 credit
  GET  /corridor/{corridor_name}     — 1 credit
  GET  /mode-comparison/{country_code} — 2 credits
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date
from typing import Optional, List
import json

from src.database.connection import get_db
from src.database.models import (
    User, Country, CountryIndex, AirTraffic, RailTraffic,
    RoadCorridor, TransportComposite,
)
from src.engines.transport_engine import TransportEngine, PROFILE_WEIGHTS, AIR_BENCHMARKS, SITARAIL_BASELINE_MONTHLY, SITARAIL_2024_MONTHLY
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/v2/transport", tags=["Transport"])

engine = TransportEngine()


def _latest_air(db: Session, country_id: int):
    return (
        db.query(AirTraffic)
        .filter(AirTraffic.country_id == country_id)
        .order_by(AirTraffic.period_date.desc())
        .first()
    )


def _latest_rail(db: Session, country_id: int):
    return (
        db.query(RailTraffic)
        .filter(RailTraffic.country_id == country_id)
        .order_by(RailTraffic.period_date.desc())
        .first()
    )


def _latest_road(db: Session, country_id: int):
    return (
        db.query(RoadCorridor)
        .filter(RoadCorridor.country_id == country_id)
        .order_by(RoadCorridor.period_date.desc())
        .first()
    )


def _latest_maritime(db: Session, country_id: int):
    """Use shipping_score from CountryIndex as maritime proxy."""
    return (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country_id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )


def _compute_transport(db: Session, country: Country) -> dict:
    air_row = _latest_air(db, country.id)
    rail_row = _latest_rail(db, country.id)
    road_row = _latest_road(db, country.id)
    maritime_row = _latest_maritime(db, country.id)

    maritime_idx = maritime_row.shipping_score if maritime_row and maritime_row.shipping_score else None
    air_idx = air_row.air_index if air_row else None
    rail_idx = rail_row.rail_index if rail_row else None
    road_idx = road_row.road_index if road_row else None

    period_date = date.today().replace(day=1)
    result = engine.calculate_transport_composite(
        country_code=country.code,
        period_date=period_date,
        maritime_index=maritime_idx,
        air_index=air_idx,
        rail_index=rail_idx,
        road_index=road_idx,
    )
    result["country_code"] = country.code
    result["country_name"] = country.name
    return result


@router.get("/latest/{country_code}")
async def get_transport_latest(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Latest multi-modal transport composite for a single country.
    Returns live-computed result (not stored). 2 credits.
    """
    deduct_credits(current_user, db, f"/api/v2/transport/latest/{country_code}", cost_multiplier=2.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    return _compute_transport(db, country)


@router.get("/history/{country_code}")
async def get_transport_history(
    country_code: str,
    months: int = 6,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stored transport composite history for a country (last N months). 3 credits.
    """
    deduct_credits(current_user, db, f"/api/v2/transport/history/{country_code}", cost_multiplier=3.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    history = (
        db.query(TransportComposite)
        .filter(TransportComposite.country_id == country.id)
        .order_by(TransportComposite.period_date.desc())
        .limit(months)
        .all()
    )

    return {
        "country_code": country.code,
        "country_name": country.name,
        "country_profile": engine.get_profile(country.code),
        "months_requested": months,
        "records": [
            {
                "period_date": str(r.period_date),
                "transport_composite": r.transport_composite,
                "maritime_index": r.maritime_index,
                "air_index": r.air_index,
                "rail_index": r.rail_index,
                "road_index": r.road_index,
                "w_maritime": r.w_maritime,
                "w_air": r.w_air,
                "w_rail": r.w_rail,
                "w_road": r.w_road,
                "country_profile": r.country_profile,
                "calculated_at": str(r.calculated_at),
            }
            for r in history
        ],
    }


@router.get("/composite")
async def get_transport_composite_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Live-computed transport composite for all 16 WASI countries. 3 credits.
    """
    deduct_credits(current_user, db, "/api/v2/transport/composite", cost_multiplier=3.0)

    countries = db.query(Country).filter(Country.is_active == True).all()
    results = []
    for country in countries:
        r = _compute_transport(db, country)
        results.append(r)

    results.sort(key=lambda x: x["transport_composite"], reverse=True)
    return {
        "total_countries": len(results),
        "composites": results,
    }


@router.post("/calculate")
async def calculate_and_store_transport(
    period_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Compute and persist transport composites for all countries for a given period.
    Defaults to current month. 5 credits.
    """
    deduct_credits(current_user, db, "/api/v2/transport/calculate", cost_multiplier=5.0)

    if period_date:
        try:
            pd_ = date.fromisoformat(period_date).replace(day=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="period_date must be YYYY-MM-DD")
    else:
        pd_ = date.today().replace(day=1)

    countries = db.query(Country).filter(Country.is_active == True).all()
    stored = []

    for country in countries:
        result = _compute_transport(db, country)

        existing = (
            db.query(TransportComposite)
            .filter(TransportComposite.country_id == country.id,
                    TransportComposite.period_date == pd_)
            .first()
        )
        if existing:
            existing.transport_composite = result["transport_composite"]
            existing.maritime_index = result["maritime_index"]
            existing.air_index = result["air_index"]
            existing.rail_index = result["rail_index"]
            existing.road_index = result["road_index"]
            existing.w_maritime = result["w_maritime"]
            existing.w_air = result["w_air"]
            existing.w_rail = result["w_rail"]
            existing.w_road = result["w_road"]
            existing.country_profile = result["country_profile"]
        else:
            db.add(TransportComposite(
                country_id=country.id,
                period_date=pd_,
                country_profile=result["country_profile"],
                maritime_index=result["maritime_index"],
                air_index=result["air_index"],
                rail_index=result["rail_index"],
                road_index=result["road_index"],
                w_maritime=result["w_maritime"],
                w_air=result["w_air"],
                w_rail=result["w_rail"],
                w_road=result["w_road"],
                transport_composite=result["transport_composite"],
            ))
        stored.append({
            "country_code": country.code,
            "transport_composite": result["transport_composite"],
            "country_profile": result["country_profile"],
        })

    db.commit()
    return {
        "period_date": str(pd_),
        "countries_calculated": len(stored),
        "results": stored,
    }


@router.get("/rail/sitarail")
async def get_sitarail_metrics(
    db: Session = Depends(get_db),
):
    """
    Public endpoint — SITARAIL Abidjan–Ouagadougou corridor metrics.
    Returns latest records for CI and BF. No auth required, 0 credits.
    """
    records = []
    for cc in ("CI", "BF"):
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue
        rows = (
            db.query(RailTraffic)
            .filter(RailTraffic.country_id == country.id)
            .order_by(RailTraffic.period_date.desc())
            .limit(6)
            .all()
        )
        for r in rows:
            records.append({
                "country_code": cc,
                "period_date": str(r.period_date),
                "freight_tonnes": r.freight_tonnes,
                "passengers": r.passenger_count,
                "avg_transit_days": r.avg_transit_days,
                "on_time_pct": r.on_time_pct,
                "rail_index": r.rail_index,
            })

    actual_avg = SITARAIL_2024_MONTHLY
    performance_pct = round((actual_avg / SITARAIL_BASELINE_MONTHLY) * 100, 1) if SITARAIL_BASELINE_MONTHLY else None

    return {
        "line": "Abidjan–Ouagadougou SITARAIL",
        "baseline_monthly_tonnes": SITARAIL_BASELINE_MONTHLY,
        "actual_2024_monthly_avg": actual_avg,
        "performance_pct": performance_pct,
        "countries": ["CI", "BF"],
        "records": sorted(records, key=lambda x: x["period_date"], reverse=True),
    }


@router.get("/airport/{iata_code}")
async def get_airport_metrics(
    iata_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Latest 6 months of traffic data for a specific airport (by IATA code). 1 credit.
    """
    deduct_credits(current_user, db, f"/api/v2/transport/airport/{iata_code}", cost_multiplier=1.0)

    code = iata_code.upper()
    rows = (
        db.query(AirTraffic)
        .filter(AirTraffic.airport_code == code)
        .order_by(AirTraffic.period_date.desc())
        .limit(6)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data found for airport '{code}'")

    country_code = None
    if rows[0].country_id:
        c = db.query(Country).filter(Country.id == rows[0].country_id).first()
        if c:
            country_code = c.code

    benchmark = AIR_BENCHMARKS.get(country_code, 50_000) if country_code else None

    return {
        "airport_code": code,
        "airport_name": rows[0].airport_name,
        "country_code": country_code,
        "benchmark_monthly_pax": benchmark,
        "records": [
            {
                "period_date": str(r.period_date),
                "passengers": r.passengers_total,
                "cargo_tonnes": r.cargo_tonnes,
                "aircraft_movements": r.aircraft_movements,
                "on_time_pct": r.on_time_pct,
                "air_index": r.air_index,
            }
            for r in rows
        ],
    }


@router.get("/corridor/{corridor_name}")
async def get_corridor_metrics(
    corridor_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Latest 6 months of road corridor data (case-insensitive partial match). 1 credit.
    """
    deduct_credits(current_user, db, f"/api/v2/transport/corridor/{corridor_name}", cost_multiplier=1.0)

    search = corridor_name.upper()
    rows = (
        db.query(RoadCorridor)
        .filter(RoadCorridor.corridor_name.ilike(f"%{search}%"))
        .order_by(RoadCorridor.period_date.desc())
        .limit(6)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No corridor data matching '{corridor_name}'")

    return {
        "corridor_name": rows[0].corridor_name,
        "records": [
            {
                "period_date": str(r.period_date),
                "truck_count": r.truck_count,
                "avg_transit_days": r.avg_transit_days,
                "border_wait_hours": r.border_wait_hours,
                "road_quality_score": r.road_quality_score,
                "road_index": r.road_index,
            }
            for r in rows
        ],
    }


@router.get("/mode-comparison/{country_code}")
async def get_mode_comparison(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    All 4 transport mode indices for a country in one response. 2 credits.
    Shows which modes have data and the effective weights used.
    """
    deduct_credits(current_user, db, f"/api/v2/transport/mode-comparison/{country_code}", cost_multiplier=2.0)

    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail=f"Country '{country_code}' not found")

    profile = engine.get_profile(country.code)
    weights = PROFILE_WEIGHTS.get(profile, {})

    # Maritime — from CountryIndex.shipping_score
    maritime_row = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    maritime_data = None
    if maritime_row and maritime_row.shipping_score is not None:
        maritime_data = {
            "index": round(maritime_row.shipping_score, 2),
            "source": "CountryIndex.shipping_score",
            "period_date": str(maritime_row.period_date),
        }

    # Air — from AirTraffic
    air_row = (
        db.query(AirTraffic)
        .filter(AirTraffic.country_id == country.id)
        .order_by(AirTraffic.period_date.desc())
        .first()
    )
    air_data = None
    if air_row and air_row.air_index is not None:
        air_data = {
            "index": round(air_row.air_index, 2),
            "source": "AirTraffic",
            "period_date": str(air_row.period_date),
        }

    # Rail — from RailTraffic
    rail_row = (
        db.query(RailTraffic)
        .filter(RailTraffic.country_id == country.id)
        .order_by(RailTraffic.period_date.desc())
        .first()
    )
    rail_data = None
    if rail_row and rail_row.rail_index is not None:
        rail_data = {
            "index": round(rail_row.rail_index, 2),
            "source": "RailTraffic",
            "period_date": str(rail_row.period_date),
        }
    else:
        rail_data = {"index": None, "source": None, "note": "No rail data for this country"}

    # Road — from RoadCorridor
    road_row = (
        db.query(RoadCorridor)
        .filter(RoadCorridor.country_id == country.id)
        .order_by(RoadCorridor.period_date.desc())
        .first()
    )
    road_data = None
    if road_row and road_row.road_index is not None:
        road_data = {
            "index": round(road_row.road_index, 2),
            "source": "RoadCorridor",
            "period_date": str(road_row.period_date),
        }
    else:
        road_data = {"index": None, "source": None, "note": "No road corridor data for this country"}

    # Compute composite using engine (re-normalizes missing modes)
    composite_result = engine.calculate_transport_composite(
        country_code=country.code,
        period_date=date.today().replace(day=1),
        maritime_index=maritime_data["index"] if maritime_data else None,
        air_index=air_data["index"] if air_data else None,
        rail_index=rail_data.get("index"),
        road_index=road_data.get("index"),
    )

    return {
        "country_code": country.code,
        "country_name": country.name,
        "country_profile": profile,
        "profile_weights": weights,
        "modes": {
            "maritime": maritime_data,
            "air": air_data,
            "rail": rail_data,
            "road": road_data,
        },
        "transport_composite": composite_result["transport_composite"],
        "effective_weights": {
            "w_maritime": composite_result["w_maritime"],
            "w_air": composite_result["w_air"],
            "w_rail": composite_result["w_rail"],
            "w_road": composite_result["w_road"],
        },
    }
