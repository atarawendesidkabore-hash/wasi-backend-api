"""
/api/markets — West African stock market data endpoints.

Exchanges:
  NGX  — Nigerian Exchange Group     (NG,  28% WASI weight)
  GSE  — Ghana Stock Exchange        (GH,  15% WASI weight)
  BRVM — Bourse Régionale des Valeurs (CI/SN/BJ/TG, 34% WASI weight)

Credit costs:
  GET /api/markets/latest     — 1 credit
  GET /api/markets/history    — 2 credits
  GET /api/markets/summary    — 1 credit
  GET /api/markets/divergence — 2 credits
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import Country, CountryIndex, DivergenceSnapshot, StockMarketData, User
from src.engines.divergence_engine import (
    EXCHANGE_COUNTRY_MAP,
    EXCHANGE_WASI_WEIGHT,
    compute_divergence,
)
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user
from src.utils.pagination import PaginationParams, paginate

router = APIRouter(prefix="/api/markets", tags=["Markets"])

limiter = Limiter(key_func=get_remote_address)


# ── Response schemas ──────────────────────────────────────────────────────────

class StockIndexResponse(BaseModel):
    exchange_code:       str
    index_name:          str
    country_codes:       str
    trade_date:          date
    index_value:         float
    change_pct:          Optional[float] = None
    ytd_change_pct:      Optional[float] = None
    market_cap_usd:      Optional[float] = None
    volume_usd:          Optional[float] = None
    data_source:         str
    confidence:          float
    wasi_weight:         float
    data_age_days:       int             # W4: how old the data is
    freshness_warning:   Optional[str] = None  # W4: stale/delayed/None


class MarketSummaryResponse(BaseModel):
    generated_at:     str
    exchanges:        list[StockIndexResponse]
    total_market_cap_usd:   Optional[float]
    wasi_coverage_pct: float   # % of WASI weight covered by these exchanges


class DivergenceResponse(BaseModel):
    exchange_code:           str
    index_name:              str
    country_codes:           list[str]
    wasi_weight:             float
    stock_index_value:       float
    stock_change_pct:        Optional[float]
    stock_market_cap_usd:    Optional[float]
    volume_usd:              Optional[float]
    avg_wasi_score:          Optional[float]
    fundamentals_change_pct: Optional[float]
    divergence_pct:          Optional[float]
    signal:                  str
    liquidity_flag:          bool
    narrative:               str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wasi_weight(exchange_code: str) -> float:
    return EXCHANGE_WASI_WEIGHT.get(exchange_code, 0.0)


def _freshness(trade_date: date) -> tuple[int, Optional[str]]:
    """W4: compute data age and return (age_days, warning_string | None)."""
    age = (date.today() - trade_date).days
    if age > 30:
        warn = f"STALE: data is {age} days old — treat with caution."
    elif age > 3:
        warn = f"DELAYED: data is {age} days old (T+{age})."
    else:
        warn = None
    return age, warn


def _to_response(row: StockMarketData) -> StockIndexResponse:
    age, warn = _freshness(row.trade_date)
    return StockIndexResponse(
        exchange_code=row.exchange_code,
        index_name=row.index_name,
        country_codes=row.country_codes,
        trade_date=row.trade_date,
        index_value=row.index_value,
        change_pct=row.change_pct,
        ytd_change_pct=row.ytd_change_pct,
        market_cap_usd=row.market_cap_usd,
        volume_usd=row.volume_usd,
        data_source=row.data_source,
        confidence=row.confidence,
        wasi_weight=_wasi_weight(row.exchange_code),
        data_age_days=age,
        freshness_warning=warn,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/latest", response_model=list[StockIndexResponse])
@limiter.limit("30/minute")
async def get_latest_indices(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Latest value for each tracked stock index (NGX All-Share, GSE Composite,
    BRVM Composite, BRVM 10). Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/markets/latest")

    # For each (exchange, index_name) pair, get the most recent row
    subq = (
        db.query(
            StockMarketData.exchange_code,
            StockMarketData.index_name,
            func.max(StockMarketData.trade_date).label("max_date"),
        )
        .group_by(StockMarketData.exchange_code, StockMarketData.index_name)
        .subquery()
    )

    rows = (
        db.query(StockMarketData)
        .join(
            subq,
            (StockMarketData.exchange_code == subq.c.exchange_code)
            & (StockMarketData.index_name == subq.c.index_name)
            & (StockMarketData.trade_date == subq.c.max_date),
        )
        .order_by(StockMarketData.exchange_code, StockMarketData.index_name)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No stock market data found.")

    return [_to_response(r) for r in rows]


@router.get("/history")
@limiter.limit("30/minute")
async def get_index_history(
    request: Request,
    exchange_code: str = Query(..., description="NGX | GSE | BRVM"),
    index_name: Optional[str] = Query(None, description="Filter by specific index name"),
    months: int = Query(12, ge=1, le=60, description="Number of months of history"),
    pagination=Depends(PaginationParams),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Historical monthly data for a specific exchange. Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/markets/history", cost_multiplier=2.0)

    cutoff = date.today() - timedelta(days=months * 31)
    q = (
        db.query(StockMarketData)
        .filter(
            StockMarketData.exchange_code == exchange_code.upper(),
            StockMarketData.trade_date >= cutoff,
        )
    )
    if index_name:
        q = q.filter(StockMarketData.index_name == index_name)

    result = paginate(q.order_by(StockMarketData.trade_date.asc()), pagination)
    result["items"] = [_to_response(r) for r in result["items"]]
    return result


@router.get("/summary", response_model=MarketSummaryResponse)
@limiter.limit("30/minute")
async def get_market_summary(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregated market summary: latest values for all exchanges + combined market cap.
    Costs 1 credit.
    """
    from datetime import datetime as dt
    deduct_credits(current_user, db, "/api/markets/summary")

    subq = (
        db.query(
            StockMarketData.exchange_code,
            StockMarketData.index_name,
            func.max(StockMarketData.trade_date).label("max_date"),
        )
        .group_by(StockMarketData.exchange_code, StockMarketData.index_name)
        .subquery()
    )
    rows = (
        db.query(StockMarketData)
        .join(
            subq,
            (StockMarketData.exchange_code == subq.c.exchange_code)
            & (StockMarketData.index_name == subq.c.index_name)
            & (StockMarketData.trade_date == subq.c.max_date),
        )
        .order_by(StockMarketData.exchange_code)
        .all()
    )

    exchanges = [_to_response(r) for r in rows]
    total_mcap = sum(
        e.market_cap_usd for e in exchanges if e.market_cap_usd is not None
    ) or None
    wasi_cov = sum(set(_wasi_weight(e.exchange_code) for e in exchanges)) * 100

    return MarketSummaryResponse(
        generated_at=dt.utcnow().isoformat(),
        exchanges=exchanges,
        total_market_cap_usd=round(total_mcap, 2) if total_mcap else None,
        wasi_coverage_pct=round(wasi_cov, 1),
    )


@router.get("/divergence", response_model=list[DivergenceResponse])
@limiter.limit("30/minute")
async def get_divergence(
    request: Request,
    lookback_months: int = Query(
        3, ge=1, le=24,
        description="Number of months to compute stock vs fundamentals change",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cross-reference each exchange's recent performance against WASI fundamentals.

    Returns divergence analysis per exchange:
    - Positive divergence → market outrunning fundamentals (overvaluation risk)
    - Negative divergence → market lagging fundamentals (undervaluation opportunity)

    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/markets/divergence", cost_multiplier=2.0)

    # ── Latest stock data per (exchange, index) ────────────────────────────
    subq = (
        db.query(
            StockMarketData.exchange_code,
            StockMarketData.index_name,
            func.max(StockMarketData.trade_date).label("max_date"),
        )
        .group_by(StockMarketData.exchange_code, StockMarketData.index_name)
        .subquery()
    )
    latest_stocks = (
        db.query(StockMarketData)
        .join(
            subq,
            (StockMarketData.exchange_code == subq.c.exchange_code)
            & (StockMarketData.index_name == subq.c.index_name)
            & (StockMarketData.trade_date == subq.c.max_date),
        )
        .all()
    )

    if not latest_stocks:
        raise HTTPException(status_code=404, detail="No stock market data found.")

    # ── Prior period stock data (lookback_months ago) ──────────────────────
    cutoff = date.today() - timedelta(days=lookback_months * 31)
    prior_stocks: dict[tuple, StockMarketData] = {}
    for s in (
        db.query(StockMarketData)
        .filter(StockMarketData.trade_date <= cutoff)
        .order_by(StockMarketData.trade_date.desc())
        .all()
    ):
        key = (s.exchange_code, s.index_name)
        if key not in prior_stocks:
            prior_stocks[key] = s

    # ── Latest WASI country index values ──────────────────────────────────
    latest_ci_date = db.query(func.max(CountryIndex.period_date)).scalar()

    country_latest: dict[str, float] = {}
    country_prev:   dict[str, float] = {}

    if latest_ci_date:
        for row in (
            db.query(CountryIndex, Country)
            .join(Country, Country.id == CountryIndex.country_id)
            .filter(CountryIndex.period_date == latest_ci_date)
            .all()
        ):
            country_latest[row.Country.code] = row.CountryIndex.index_value

        prev_ci_date = latest_ci_date - timedelta(days=lookback_months * 31)
        for row in (
            db.query(CountryIndex, Country)
            .join(Country, Country.id == CountryIndex.country_id)
            .filter(CountryIndex.period_date >= prev_ci_date)
            .order_by(CountryIndex.period_date.asc())
            .all()
        ):
            if row.Country.code not in country_prev:
                country_prev[row.Country.code] = row.CountryIndex.index_value

    # ── Compute divergence per stock index ────────────────────────────────
    results: list[DivergenceResponse] = []
    seen: set[tuple] = set()

    for stock in latest_stocks:
        key = (stock.exchange_code, stock.index_name)
        if key in seen:
            continue
        seen.add(key)

        prior = prior_stocks.get(key)
        stock_change: Optional[float] = None
        if prior and prior.index_value and prior.index_value != 0:
            stock_change = round(
                (stock.index_value - prior.index_value) / prior.index_value * 100, 2
            )

        div = compute_divergence(
            exchange_code=stock.exchange_code,
            index_name=stock.index_name,
            stock_index_value=stock.index_value,
            stock_change_pct=stock_change,
            stock_market_cap_usd=stock.market_cap_usd,
            country_index_values=country_latest,
            prev_country_index_values=country_prev,
            volume_usd=stock.volume_usd,
        )

        results.append(
            DivergenceResponse(
                exchange_code=div.exchange_code,
                index_name=div.index_name,
                country_codes=div.country_codes,
                wasi_weight=div.wasi_weight,
                stock_index_value=div.stock_index_value,
                stock_change_pct=div.stock_change_pct,
                stock_market_cap_usd=div.stock_market_cap_usd,
                volume_usd=div.volume_usd,
                avg_wasi_score=div.avg_wasi_score,
                fundamentals_change_pct=div.fundamentals_change_pct,
                divergence_pct=div.divergence_pct,
                signal=div.signal,
                liquidity_flag=div.liquidity_flag,
                narrative=div.narrative,
            )
        )

    # Sort by absolute divergence descending (biggest opportunity first)
    results.sort(
        key=lambda r: abs(r.divergence_pct) if r.divergence_pct is not None else 0,
        reverse=True,
    )
    return results


# ── W6: Divergence history endpoint ──────────────────────────────────────────

class DivergenceSnapshotResponse(BaseModel):
    snapshot_date:           date
    exchange_code:           str
    index_name:              str
    stock_index_value:       float
    stock_change_pct:        Optional[float]
    avg_wasi_score:          Optional[float]
    fundamentals_change_pct: Optional[float]
    divergence_pct:          Optional[float]
    signal:                  str
    liquidity_flag:          bool


@router.get("/divergence/history")
@limiter.limit("30/minute")
async def get_divergence_history(
    request: Request,
    exchange_code: str = Query(..., description="NGX | GSE | BRVM"),
    index_name: Optional[str] = Query(None),
    months: int = Query(6, ge=1, le=24),
    pagination=Depends(PaginationParams),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    W6: Historical divergence trend for a specific exchange.

    Answers: "Has NGX been consistently overvalued vs WASI fundamentals?"
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/markets/divergence/history", cost_multiplier=2.0)

    cutoff = date.today() - timedelta(days=months * 31)
    q = (
        db.query(DivergenceSnapshot)
        .filter(
            DivergenceSnapshot.exchange_code == exchange_code.upper(),
            DivergenceSnapshot.snapshot_date >= cutoff,
        )
    )
    if index_name:
        q = q.filter(DivergenceSnapshot.index_name == index_name)

    result = paginate(q.order_by(DivergenceSnapshot.snapshot_date.asc()), pagination)
    result["items"] = [
        DivergenceSnapshotResponse(
            snapshot_date=r.snapshot_date,
            exchange_code=r.exchange_code,
            index_name=r.index_name,
            stock_index_value=r.stock_index_value,
            stock_change_pct=r.stock_change_pct,
            avg_wasi_score=r.avg_wasi_score,
            fundamentals_change_pct=r.fundamentals_change_pct,
            divergence_pct=r.divergence_pct,
            signal=r.signal,
            liquidity_flag=r.liquidity_flag,
        )
        for r in result["items"]
    ]
    return result
