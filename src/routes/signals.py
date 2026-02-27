"""
Signals routes — bullish/bearish signals derived from composite, country indices,
and stock market divergence analysis.
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, ConfigDict

from src.database.connection import get_db
from src.database.models import User, Country, CountryIndex, WASIComposite, StockMarketData
from src.engines.divergence_engine import compute_divergence, EXCHANGE_WASI_WEIGHT
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

router = APIRouter(prefix="/api/signals", tags=["Signals"])


# ── Signal classification logic ───────────────────────────────────────────────

def _classify_composite_signal(composite: WASIComposite) -> dict:
    """Derive signal strength from composite metrics."""
    signal = "neutral"
    strength = 0.0
    reasons = []

    if composite.mom_change is not None:
        if composite.mom_change > 2.0:
            signal = "strong_bullish"
            strength += 2.0
            reasons.append(f"MoM change +{composite.mom_change:.2f}%")
        elif composite.mom_change > 0.5:
            signal = "bullish"
            strength += 1.0
            reasons.append(f"MoM change +{composite.mom_change:.2f}%")
        elif composite.mom_change < -2.0:
            signal = "strong_bearish"
            strength -= 2.0
            reasons.append(f"MoM change {composite.mom_change:.2f}%")
        elif composite.mom_change < -0.5:
            signal = "bearish"
            strength -= 1.0
            reasons.append(f"MoM change {composite.mom_change:.2f}%")

    if composite.sharpe_ratio is not None and composite.sharpe_ratio > 1.0:
        strength += 0.5
        reasons.append(f"Sharpe ratio {composite.sharpe_ratio:.2f} (risk-adjusted positive)")

    if composite.max_drawdown is not None and composite.max_drawdown > 0.15:
        strength -= 0.5
        reasons.append(f"Max drawdown {composite.max_drawdown * 100:.1f}% (elevated)")

    if composite.composite_value >= 70:
        strength += 0.5
        reasons.append(f"Composite value {composite.composite_value:.1f} (high zone)")
    elif composite.composite_value <= 30:
        strength -= 0.5
        reasons.append(f"Composite value {composite.composite_value:.1f} (low zone)")

    if strength > 1.5:
        signal = "strong_bullish"
    elif strength > 0.3:
        signal = "bullish"
    elif strength < -1.5:
        signal = "strong_bearish"
    elif strength < -0.3:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "signal": signal,
        "strength": round(strength, 2),
        "reasons": reasons,
    }


def _country_signal(index_value: float, prev_value: Optional[float]) -> str:
    if prev_value is None:
        return "neutral"
    change_pct = (index_value - prev_value) / prev_value * 100 if prev_value != 0 else 0
    if change_pct > 3:
        return "strong_bullish"
    elif change_pct > 0.5:
        return "bullish"
    elif change_pct < -3:
        return "strong_bearish"
    elif change_pct < -0.5:
        return "bearish"
    return "neutral"


# ── Response schemas ──────────────────────────────────────────────────────────

class CompositeSignal(BaseModel):
    period_date: date
    composite_value: float
    signal: str
    strength: float
    reasons: list[str]
    mom_change: Optional[float] = None
    yoy_change: Optional[float] = None
    trend_direction: Optional[str] = None


class CountrySignal(BaseModel):
    country_code: str
    country_name: str
    tier: str
    index_value: float
    signal: str
    mom_change_pct: Optional[float] = None
    period_date: date


class SignalSummary(BaseModel):
    generated_at: str
    composite: CompositeSignal
    country_signals: list[CountrySignal]
    bullish_count: int
    bearish_count: int
    neutral_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/composite", response_model=CompositeSignal)
async def get_composite_signal(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Current WASI composite market signal (bullish/bearish/neutral).
    Costs 1 credit.
    """
    deduct_credits(current_user, db, "/api/signals/composite")

    latest = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )
    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No composite data. Call POST /api/composite/calculate first.",
        )

    classification = _classify_composite_signal(latest)
    return CompositeSignal(
        period_date=latest.period_date,
        composite_value=latest.composite_value,
        signal=classification["signal"],
        strength=classification["strength"],
        reasons=classification["reasons"],
        mom_change=latest.mom_change,
        yoy_change=latest.yoy_change,
        trend_direction=latest.trend_direction,
    )


@router.get("/countries", response_model=list[CountrySignal])
async def get_country_signals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Per-country signals based on the latest vs prior month index value.
    Costs 2 credits.
    """
    deduct_credits(current_user, db, "/api/signals/countries", cost_multiplier=2.0)

    latest_date = db.query(func.max(CountryIndex.period_date)).scalar()
    if not latest_date:
        raise HTTPException(status_code=404, detail="No index data available.")

    prev_date = date(latest_date.year, latest_date.month, 1) - timedelta(days=1)
    prev_date = date(prev_date.year, prev_date.month, 1)

    latest_rows = (
        db.query(CountryIndex, Country)
        .join(Country, Country.id == CountryIndex.country_id)
        .filter(CountryIndex.period_date == latest_date)
        .all()
    )

    prev_map = {
        row.CountryIndex.country_id: row.CountryIndex.index_value
        for row in db.query(CountryIndex, Country)
        .join(Country, Country.id == CountryIndex.country_id)
        .filter(CountryIndex.period_date == prev_date)
        .all()
    }

    signals = []
    for row in sorted(latest_rows, key=lambda r: r.CountryIndex.index_value, reverse=True):
        prev = prev_map.get(row.CountryIndex.country_id)
        mom_pct = (
            round((row.CountryIndex.index_value - prev) / prev * 100, 2)
            if prev and prev != 0 else None
        )
        signals.append(
            CountrySignal(
                country_code=row.Country.code,
                country_name=row.Country.name,
                tier=row.Country.tier,
                index_value=row.CountryIndex.index_value,
                signal=_country_signal(row.CountryIndex.index_value, prev),
                mom_change_pct=mom_pct,
                period_date=latest_date,
            )
        )
    return signals


@router.get("/summary", response_model=SignalSummary)
async def get_signal_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Full signal summary: composite signal + all country signals + counts.
    Costs 3 credits.
    """
    from datetime import datetime as dt
    deduct_credits(current_user, db, "/api/signals/summary", cost_multiplier=3.0)

    latest = (
        db.query(WASIComposite)
        .order_by(WASIComposite.period_date.desc())
        .first()
    )
    if not latest:
        raise HTTPException(status_code=404, detail="No composite data available.")

    composite_cls = _classify_composite_signal(latest)
    composite_signal = CompositeSignal(
        period_date=latest.period_date,
        composite_value=latest.composite_value,
        signal=composite_cls["signal"],
        strength=composite_cls["strength"],
        reasons=composite_cls["reasons"],
        mom_change=latest.mom_change,
        yoy_change=latest.yoy_change,
        trend_direction=latest.trend_direction,
    )

    latest_date = db.query(func.max(CountryIndex.period_date)).scalar()
    prev_date = None
    if latest_date:
        pd = date(latest_date.year, latest_date.month, 1) - timedelta(days=1)
        prev_date = date(pd.year, pd.month, 1)

    latest_rows = (
        db.query(CountryIndex, Country)
        .join(Country, Country.id == CountryIndex.country_id)
        .filter(CountryIndex.period_date == latest_date)
        .all()
        if latest_date else []
    )
    prev_map = {}
    if prev_date:
        prev_map = {
            row.CountryIndex.country_id: row.CountryIndex.index_value
            for row in db.query(CountryIndex, Country)
            .join(Country, Country.id == CountryIndex.country_id)
            .filter(CountryIndex.period_date == prev_date)
            .all()
        }

    country_signals = []
    for row in sorted(latest_rows, key=lambda r: r.CountryIndex.index_value, reverse=True):
        prev = prev_map.get(row.CountryIndex.country_id)
        mom_pct = (
            round((row.CountryIndex.index_value - prev) / prev * 100, 2)
            if prev and prev != 0 else None
        )
        country_signals.append(
            CountrySignal(
                country_code=row.Country.code,
                country_name=row.Country.name,
                tier=row.Country.tier,
                index_value=row.CountryIndex.index_value,
                signal=_country_signal(row.CountryIndex.index_value, prev),
                mom_change_pct=mom_pct,
                period_date=latest_date,
            )
        )

    bullish = sum(1 for s in country_signals if "bullish" in s.signal)
    bearish = sum(1 for s in country_signals if "bearish" in s.signal)
    neutral = len(country_signals) - bullish - bearish

    return SignalSummary(
        generated_at=dt.utcnow().isoformat(),
        composite=composite_signal,
        country_signals=country_signals,
        bullish_count=bullish,
        bearish_count=bearish,
        neutral_count=neutral,
    )


# ── Market divergence signal ──────────────────────────────────────────────────

class MarketDivergenceSignal(BaseModel):
    exchange_code:           str
    index_name:              str
    country_codes:           list[str]
    wasi_weight:             float
    stock_index_value:       float
    stock_change_pct:        Optional[float]
    volume_usd:              Optional[float]
    avg_wasi_score:          Optional[float]
    fundamentals_change_pct: Optional[float]
    divergence_pct:          Optional[float]
    signal:                  str
    liquidity_flag:          bool
    narrative:               str


class MarketDivergenceSummary(BaseModel):
    generated_at:       str
    lookback_months:    int
    signals:            list[MarketDivergenceSignal]
    overvalued_count:   int
    undervalued_count:  int
    aligned_count:      int
    top_opportunity:    Optional[str]   # narrative of biggest divergence


@router.get("/market-divergence", response_model=MarketDivergenceSummary)
async def get_market_divergence(
    lookback_months: int = Query(3, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cross-reference each West African stock exchange against WASI fundamentals.

    Detects when equity markets are running ahead of (or behind) the real
    trade, port and economic data — actionable divergence signals for
    fund managers and analysts.

    Costs 2 credits.
    """
    from datetime import datetime as dt
    deduct_credits(current_user, db, "/api/signals/market-divergence", cost_multiplier=2.0)

    # Latest stock data per index
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
        raise HTTPException(status_code=404, detail="No stock market data available.")

    # Prior period stock data
    cutoff = date.today() - timedelta(days=lookback_months * 31)
    prior_map: dict[tuple, StockMarketData] = {}
    for s in (
        db.query(StockMarketData)
        .filter(StockMarketData.trade_date <= cutoff)
        .order_by(StockMarketData.trade_date.desc())
        .all()
    ):
        key = (s.exchange_code, s.index_name)
        if key not in prior_map:
            prior_map[key] = s

    # WASI country index values
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

    signals: list[MarketDivergenceSignal] = []
    seen: set[tuple] = set()

    for stock in latest_stocks:
        key = (stock.exchange_code, stock.index_name)
        if key in seen:
            continue
        seen.add(key)

        prior = prior_map.get(key)
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

        signals.append(MarketDivergenceSignal(
            exchange_code=div.exchange_code,
            index_name=div.index_name,
            country_codes=div.country_codes,
            wasi_weight=div.wasi_weight,
            stock_index_value=div.stock_index_value,
            stock_change_pct=div.stock_change_pct,
            volume_usd=div.volume_usd,
            avg_wasi_score=div.avg_wasi_score,
            fundamentals_change_pct=div.fundamentals_change_pct,
            divergence_pct=div.divergence_pct,
            signal=div.signal,
            liquidity_flag=div.liquidity_flag,
            narrative=div.narrative,
        ))

    signals.sort(
        key=lambda s: abs(s.divergence_pct) if s.divergence_pct is not None else 0,
        reverse=True,
    )

    overvalued  = sum(1 for s in signals if "overvalued"  in s.signal)
    undervalued = sum(1 for s in signals if "undervalued" in s.signal)
    aligned     = sum(1 for s in signals if s.signal == "aligned")
    top_opp     = signals[0].narrative if signals else None

    return MarketDivergenceSummary(
        generated_at=dt.utcnow().isoformat(),
        lookback_months=lookback_months,
        signals=signals,
        overvalued_count=overvalued,
        undervalued_count=undervalued,
        aligned_count=aligned,
        top_opportunity=top_opp,
    )
