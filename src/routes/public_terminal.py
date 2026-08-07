from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import (
    CommodityPrice,
    Country,
    CountryIndex,
    LiveSignal,
    NewsEvent,
    StockMarketData,
    WASIComposite,
)

router = APIRouter(prefix="/api/public/terminal", tags=["Public Terminal"])
limiter = Limiter(key_func=get_remote_address)

ECOWAS_CODES = {"NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV"}
COMMODITY_PRIORITY = ["COCOA", "BRENT", "GOLD", "COTTON", "COFFEE", "IRON_ORE"]


def _confidence_indicator(confidence: float | None) -> str:
    if confidence is None:
        return "grey"
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "yellow"
    return "red"


def _rating(score: float) -> str:
    if score >= 90:
        return "AAA"
    if score >= 80:
        return "AA"
    if score >= 70:
        return "A"
    if score >= 60:
        return "BBB"
    if score >= 50:
        return "BB"
    if score >= 40:
        return "B"
    if score >= 30:
        return "CCC"
    return "D"


def _fmt_signed_pct(value: float | None) -> str:
    if value is None:
        return "0.00%"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _event_type(event_type: str) -> str:
    value = (event_type or "").upper()
    if value in {"POLITICAL_RISK", "PORT_DISRUPTION", "STRIKE"}:
        return "RISK"
    if value in {"COMMODITY_SURGE"}:
        return "TRADE"
    if value in {"POLICY_CHANGE"}:
        return "NEWS"
    return "DATA"


def _choose_market_symbol(exchange_code: str, index_name: str) -> str:
    upper_name = (index_name or "").upper()
    if exchange_code == "BRVM":
        return "BRVM-C"
    if exchange_code == "NGX":
        return "NGX-ASI"
    if exchange_code == "GSE":
        return "GSE-CI"
    if "BRVM" in upper_name:
        return "BRVM-C"
    if "NGX" in upper_name or "ALL" in upper_name:
        return "NGX-ASI"
    if "GSE" in upper_name:
        return "GSE-CI"
    return exchange_code


@router.get("/snapshot")
@limiter.limit("60/minute")
async def get_terminal_snapshot(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    # Latest official country indices per country.
    country_latest_subq = (
        db.query(
            CountryIndex.country_id,
            func.max(CountryIndex.period_date).label("max_date"),
        )
        .group_by(CountryIndex.country_id)
        .subquery()
    )
    country_rows = (
        db.query(Country, CountryIndex)
        .join(country_latest_subq, Country.id == country_latest_subq.c.country_id)
        .join(
            CountryIndex,
            and_(
                CountryIndex.country_id == country_latest_subq.c.country_id,
                CountryIndex.period_date == country_latest_subq.c.max_date,
            ),
        )
        .filter(Country.is_active.is_(True), Country.code.in_(ECOWAS_CODES))
        .all()
    )

    # Latest live signal per country (if available), used as displayed value.
    signal_latest_subq = (
        db.query(
            LiveSignal.country_id,
            func.max(LiveSignal.period_date).label("max_date"),
        )
        .group_by(LiveSignal.country_id)
        .subquery()
    )
    signal_rows = (
        db.query(LiveSignal)
        .join(signal_latest_subq, LiveSignal.country_id == signal_latest_subq.c.country_id)
        .filter(LiveSignal.period_date == signal_latest_subq.c.max_date)
        .all()
    )
    signal_by_country_id = {row.country_id: row for row in signal_rows}

    countries: list[dict[str, Any]] = []
    for country, latest in country_rows:
        signal = signal_by_country_id.get(country.id)
        displayed_value = float(signal.adjusted_index) if signal else float(latest.index_value)

        previous_row = (
            db.query(CountryIndex)
            .filter(
                CountryIndex.country_id == country.id,
                CountryIndex.period_date < latest.period_date,
            )
            .order_by(CountryIndex.period_date.desc())
            .first()
        )
        previous_value = float(previous_row.index_value) if previous_row else None
        change_points = round(displayed_value - previous_value, 1) if previous_value is not None else 0.0

        countries.append(
            {
                "code": country.code,
                "name": country.name,
                "index_value": round(displayed_value, 2),
                "change_points": change_points,
                "rating": _rating(displayed_value),
                "weight_pct": round(float(country.weight) * 100, 1),
                "confidence_indicator": _confidence_indicator(latest.confidence),
            }
        )

    countries.sort(key=lambda item: item["index_value"], reverse=True)
    for rank, item in enumerate(countries, start=1):
        item["rank"] = rank

    # Composite
    latest_composite = db.query(WASIComposite).order_by(WASIComposite.period_date.desc()).first()
    prev_composite = None
    if latest_composite:
        prev_composite = (
            db.query(WASIComposite)
            .filter(WASIComposite.period_date < latest_composite.period_date)
            .order_by(WASIComposite.period_date.desc())
            .first()
        )
    composite_change = 0.0
    if latest_composite and prev_composite:
        composite_change = round(float(latest_composite.composite_value) - float(prev_composite.composite_value), 1)

    # Markets latest per (exchange, index name)
    market_subq = (
        db.query(
            StockMarketData.exchange_code,
            StockMarketData.index_name,
            func.max(StockMarketData.trade_date).label("max_date"),
        )
        .group_by(StockMarketData.exchange_code, StockMarketData.index_name)
        .subquery()
    )
    market_rows = (
        db.query(StockMarketData)
        .join(
            market_subq,
            and_(
                StockMarketData.exchange_code == market_subq.c.exchange_code,
                StockMarketData.index_name == market_subq.c.index_name,
                StockMarketData.trade_date == market_subq.c.max_date,
            ),
        )
        .all()
    )

    def _pick_exchange_row(exchange_code: str) -> StockMarketData | None:
        options = [row for row in market_rows if row.exchange_code == exchange_code]
        if not options:
            return None
        preferred = [row for row in options if "COMP" in (row.index_name or "").upper() or "ALL" in (row.index_name or "").upper()]
        return preferred[0] if preferred else options[0]

    picked_market_rows = [
        row
        for row in [_pick_exchange_row("BRVM"), _pick_exchange_row("NGX"), _pick_exchange_row("GSE")]
        if row is not None
    ]

    market_indices: list[dict[str, Any]] = []
    for row in picked_market_rows:
        market_indices.append(
            {
                "symbol": _choose_market_symbol(row.exchange_code, row.index_name),
                "exchange_code": row.exchange_code,
                "index_name": row.index_name,
                "index_value": float(row.index_value),
                "change_pct": float(row.change_pct) if row.change_pct is not None else None,
                "trade_date": str(row.trade_date),
            }
        )

    # Latest commodities by code.
    commodity_rows = (
        db.query(CommodityPrice)
        .order_by(CommodityPrice.commodity_code, CommodityPrice.period_date.desc())
        .all()
    )
    commodity_by_code: dict[str, CommodityPrice] = {}
    for row in commodity_rows:
        if row.commodity_code not in commodity_by_code:
            commodity_by_code[row.commodity_code] = row

    commodities: list[dict[str, Any]] = []
    for code in COMMODITY_PRIORITY:
        row = commodity_by_code.get(code)
        if not row:
            continue
        commodities.append(
            {
                "code": row.commodity_code,
                "name": row.commodity_name,
                "price": float(row.price_usd),
                "unit": row.unit,
                "mom_pct": float(row.pct_change_mom) if row.pct_change_mom is not None else None,
                "yoy_pct": float(row.pct_change_yoy) if row.pct_change_yoy is not None else None,
                "period": str(row.period_date),
            }
        )

    # Active events used in alerts feed.
    now_naive_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    event_rows = (
        db.query(NewsEvent, Country)
        .join(Country, Country.id == NewsEvent.country_id)
        .filter(
            NewsEvent.is_active.is_(True),
            NewsEvent.expires_at > now_naive_utc,
            Country.code.in_(ECOWAS_CODES),
        )
        .order_by(NewsEvent.detected_at.desc())
        .limit(8)
        .all()
    )
    alerts: list[dict[str, Any]] = []
    for event, country in event_rows:
        alerts.append(
            {
                "time": event.detected_at.strftime("%H:%M") if event.detected_at else "--:--",
                "type": _event_type(event.event_type),
                "msg": f"{country.code}: {event.headline[:80]}",
                "country_code": country.code,
                "magnitude": float(event.magnitude),
            }
        )

    # Shared top ticker values.
    ticker: list[dict[str, Any]] = []
    market_symbol_map = {item["symbol"]: item for item in market_indices}
    for symbol in ("BRVM-C", "NGX-ASI", "GSE-CI"):
        item = market_symbol_map.get(symbol)
        if not item:
            continue
        change_pct = item.get("change_pct")
        ticker.append(
            {
                "sym": symbol,
                "val": f"{item['index_value']:.2f}",
                "chg": _fmt_signed_pct(change_pct),
                "up": (change_pct or 0) >= 0,
            }
        )

    commodity_symbol_map = {item["code"]: item for item in commodities}
    for symbol in ("COCOA", "BRENT", "GOLD"):
        item = commodity_symbol_map.get(symbol)
        if not item:
            continue
        mom_pct = item.get("mom_pct")
        ticker.append(
            {
                "sym": symbol,
                "val": f"{item['price']:.2f}",
                "chg": _fmt_signed_pct(mom_pct),
                "up": (mom_pct or 0) >= 0,
            }
        )

    ticker.append({"sym": "XOF/USD", "val": "0.00164", "chg": "+0.01%", "up": True})

    composite_value = float(latest_composite.composite_value) if latest_composite else None
    if composite_value is not None:
        ticker.append(
            {
                "sym": "WASI-IDX",
                "val": f"{composite_value:.1f}",
                "chg": f"{composite_change:+.1f}",
                "up": composite_change >= 0,
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "countries": countries,
        "composite": {
            "value": composite_value,
            "change_points": composite_change,
            "period_date": str(latest_composite.period_date) if latest_composite else None,
        },
        "market_indices": market_indices,
        "commodities": commodities,
        "alerts": alerts,
        "ticker": ticker,
    }
