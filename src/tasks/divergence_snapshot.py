"""
W6: Daily divergence snapshot task.

Computes divergence for all tracked exchanges and writes a DivergenceSnapshot
record per index per day. Enables historical trend queries:
  - "Has NGX been consistently overvalued for 6+ months?"
  - "Is GSE divergence worsening or improving?"

Called from wasi_data_scheduler.py after stock market data is fetched.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex, DivergenceSnapshot, StockMarketData
from src.engines.divergence_engine import EXCHANGE_COUNTRY_MAP, compute_divergence

logger = logging.getLogger(__name__)


def save_divergence_snapshot(db: Session | None = None) -> int:
    """
    Compute and persist today's divergence snapshot for every tracked exchange/index.

    Returns the number of new snapshots written.
    """
    close_db = db is None
    if db is None:
        db = SessionLocal()

    inserted = 0
    today = date.today()

    try:
        # Latest stock data per (exchange, index)
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
            logger.info("DivergenceSnapshot: no stock data — skipping")
            return 0

        # Latest and prior WASI country scores (30-day lookback for change)
        from datetime import timedelta
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

            prev_ci_date = latest_ci_date - timedelta(days=90)
            for row in (
                db.query(CountryIndex, Country)
                .join(Country, Country.id == CountryIndex.country_id)
                .filter(CountryIndex.period_date >= prev_ci_date)
                .order_by(CountryIndex.period_date.asc())
                .all()
            ):
                if row.Country.code not in country_prev:
                    country_prev[row.Country.code] = row.CountryIndex.index_value

        # Prior stock data for change_pct (90-day lookback)
        from datetime import timedelta as td
        cutoff = today - td(days=90)
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

        for stock in latest_stocks:
            key = (stock.exchange_code, stock.index_name)

            # Skip if snapshot already exists for today
            exists = (
                db.query(DivergenceSnapshot)
                .filter(
                    DivergenceSnapshot.exchange_code == stock.exchange_code,
                    DivergenceSnapshot.index_name == stock.index_name,
                    DivergenceSnapshot.snapshot_date == today,
                )
                .first()
            )
            if exists:
                continue

            prior = prior_map.get(key)
            stock_change: float | None = None
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

            db.add(DivergenceSnapshot(
                exchange_code=div.exchange_code,
                index_name=div.index_name,
                snapshot_date=today,
                stock_index_value=div.stock_index_value,
                stock_change_pct=div.stock_change_pct,
                avg_wasi_score=div.avg_wasi_score,
                fundamentals_change_pct=div.fundamentals_change_pct,
                divergence_pct=div.divergence_pct,
                signal=div.signal,
                liquidity_flag=div.liquidity_flag,
                volume_usd=div.volume_usd,
                computed_at=datetime.utcnow(),
            ))
            inserted += 1

        if inserted:
            db.commit()
        logger.info("DivergenceSnapshot: %d new snapshots saved for %s", inserted, today)

    except Exception as exc:
        logger.error("DivergenceSnapshot failed: %s", exc, exc_info=True)
        db.rollback()
    finally:
        if close_db:
            db.close()

    return inserted
