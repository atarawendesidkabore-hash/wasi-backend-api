"""
ETF Engine — 42 WASI exchange-traded fund products with real-time NAV pricing.

NAV Methodology:
  Index-based (0-100):  NAV = index_value × 100 XOF  (so score 65 = 6,500 XOF/unit)
  Commodity:            NAV = USD_price × XOF_rate × scale_factor
  Equity:               NAV = stock_index_value × scale_factor
  Strategy:             NAV = weighted basket of underlying scores × 100 XOF
  Country:              NAV = country_index × 100 XOF

XOF/USD reference rate: 610 XOF = 1 USD (BCEAO peg via EUR)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.models import (
    CountryIndex, Country, WASIComposite, StockMarketData, CommodityPrice,
)
from src.database.etf_models import EtfProduct, EtfNavHistory

logger = logging.getLogger(__name__)

XOF_PER_USD = 610.0  # BCEAO peg rate

# ── All 42 ETF Product Definitions ──────────────────────────────────────────

ETF_CATALOG = [
    # ── BROAD (1) ─────────────────────────────────────────────────────────
    {
        "ticker": "WASI-COMP",
        "name": "WASI Composite Index ETF",
        "category": "BROAD",
        "description": "Tracks the WASI Composite Index across all 16 ECOWAS nations",
        "underlying_type": "composite",
        "underlying_config": json.dumps({"source": "wasi_composite"}),
        "fee_pct": 0.35,
    },

    # ── REGIONAL (5) ──────────────────────────────────────────────────────
    {
        "ticker": "WASI-PRI",
        "name": "WASI Primary Tier ETF",
        "category": "REGIONAL",
        "description": "Top 4 economies: Nigeria, Côte d'Ivoire, Ghana, Senegal (75% weight)",
        "underlying_type": "country_group",
        "underlying_config": json.dumps({
            "countries": {"NG": 0.373, "CI": 0.293, "GH": 0.200, "SN": 0.133},
        }),
        "fee_pct": 0.40,
    },
    {
        "ticker": "WASI-SEC",
        "name": "WASI Secondary Tier ETF",
        "category": "REGIONAL",
        "description": "Mid-tier: Burkina Faso, Mali, Guinea, Benin, Togo (20% weight)",
        "underlying_type": "country_group",
        "underlying_config": json.dumps({
            "countries": {"BF": 0.222, "ML": 0.222, "GN": 0.222, "BJ": 0.167, "TG": 0.167},
        }),
        "fee_pct": 0.50,
    },
    {
        "ticker": "WASI-TER",
        "name": "WASI Tertiary Tier ETF",
        "category": "REGIONAL",
        "description": "Small economies: NE, MR, GW, SL, LR, GM, CV (5% weight)",
        "underlying_type": "country_group",
        "underlying_config": json.dumps({
            "countries": {"NE": 0.143, "MR": 0.143, "GW": 0.143, "SL": 0.143,
                          "LR": 0.143, "GM": 0.143, "CV": 0.143},
        }),
        "fee_pct": 0.60,
    },
    {
        "ticker": "WASI-UEMOA",
        "name": "WASI UEMOA Zone ETF",
        "category": "REGIONAL",
        "description": "WAEMU/UEMOA XOF-pegged zone: CI, SN, BF, ML, BJ, TG, NE, GW",
        "underlying_type": "country_group",
        "underlying_config": json.dumps({
            "countries": {"CI": 0.355, "SN": 0.161, "BF": 0.065, "ML": 0.065,
                          "BJ": 0.048, "TG": 0.048, "NE": 0.129, "GW": 0.129},
        }),
        "fee_pct": 0.40,
    },
    {
        "ticker": "WASI-WAMZ",
        "name": "WASI WAMZ Zone ETF",
        "category": "REGIONAL",
        "description": "Floating-currency zone: NG, GH, GN, SL, LR, GM",
        "underlying_type": "country_group",
        "underlying_config": json.dumps({
            "countries": {"NG": 0.560, "GH": 0.300, "GN": 0.080, "SL": 0.020,
                          "LR": 0.020, "GM": 0.020},
        }),
        "fee_pct": 0.45,
    },

    # ── SECTOR (5) ────────────────────────────────────────────────────────
    {
        "ticker": "WASI-SHIP",
        "name": "WASI Shipping Index ETF",
        "category": "SECTOR",
        "description": "Pure shipping exposure: ship arrivals + cargo tonnage across ECOWAS",
        "underlying_type": "sub_index",
        "underlying_config": json.dumps({"score_field": "shipping_score"}),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-TRADE",
        "name": "WASI Trade Index ETF",
        "category": "SECTOR",
        "description": "Trade activity: cargo tonnage + container TEU across ECOWAS",
        "underlying_type": "sub_index",
        "underlying_config": json.dumps({"score_field": "trade_score"}),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-INFRA",
        "name": "WASI Infrastructure Index ETF",
        "category": "SECTOR",
        "description": "Port efficiency + dwell time performance across ECOWAS",
        "underlying_type": "sub_index",
        "underlying_config": json.dumps({"score_field": "infrastructure_score"}),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-ECON",
        "name": "WASI Economic Index ETF",
        "category": "SECTOR",
        "description": "GDP growth + trade value economic indicators across ECOWAS",
        "underlying_type": "sub_index",
        "underlying_config": json.dumps({"score_field": "economic_score"}),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-TRANS",
        "name": "WASI Transport Composite ETF",
        "category": "SECTOR",
        "description": "Multi-modal transport: maritime, air, rail, road across ECOWAS",
        "underlying_type": "sub_index",
        "underlying_config": json.dumps({"score_field": "transport_composite"}),
        "fee_pct": 0.50,
    },

    # ── COMMODITY (6) ─────────────────────────────────────────────────────
    {
        "ticker": "WASI-COCOA",
        "name": "WASI Cocoa ETF",
        "category": "COMMODITY",
        "description": "Tracks cocoa price (key CI/GH export)",
        "underlying_type": "commodity",
        "underlying_config": json.dumps({"commodity": "COCOA", "scale": 1.0}),
        "fee_pct": 0.50,
    },
    {
        "ticker": "WASI-BRENT",
        "name": "WASI Brent Crude ETF",
        "category": "COMMODITY",
        "description": "Tracks Brent crude oil price (key NG export)",
        "underlying_type": "commodity",
        "underlying_config": json.dumps({"commodity": "BRENT", "scale": 100.0}),
        "fee_pct": 0.50,
    },
    {
        "ticker": "WASI-GOLD",
        "name": "WASI Gold ETF",
        "category": "COMMODITY",
        "description": "Tracks gold price (key ML/BF/GN export)",
        "underlying_type": "commodity",
        "underlying_config": json.dumps({"commodity": "GOLD", "scale": 5.0}),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-AGRI",
        "name": "WASI Agriculture Basket ETF",
        "category": "COMMODITY",
        "description": "Agriculture basket: cocoa 50%, cotton 25%, coffee 25%",
        "underlying_type": "commodity_basket",
        "underlying_config": json.dumps({
            "basket": {"COCOA": 0.50, "COTTON": 0.25, "COFFEE": 0.25},
            "scale": 1.0,
        }),
        "fee_pct": 0.55,
    },
    {
        "ticker": "WASI-METALS",
        "name": "WASI Metals Basket ETF",
        "category": "COMMODITY",
        "description": "Metals basket: gold 60%, iron ore 40%",
        "underlying_type": "commodity_basket",
        "underlying_config": json.dumps({
            "basket": {"GOLD": 0.60, "IRON_ORE": 0.40},
            "scale": 5.0,
        }),
        "fee_pct": 0.50,
    },
    {
        "ticker": "WASI-CMDTY",
        "name": "WASI All Commodities ETF",
        "category": "COMMODITY",
        "description": "Equal-weight basket of all 6 WASI commodities",
        "underlying_type": "commodity_basket",
        "underlying_config": json.dumps({
            "basket": {"COCOA": 0.167, "BRENT": 0.167, "GOLD": 0.167,
                       "COTTON": 0.167, "COFFEE": 0.167, "IRON_ORE": 0.167},
            "scale": 2.0,
        }),
        "fee_pct": 0.55,
    },

    # ── EQUITY (4) ────────────────────────────────────────────────────────
    {
        "ticker": "WASI-EQ",
        "name": "WASI Pan-African Equity ETF",
        "category": "EQUITY",
        "description": "Weighted basket: NGX 50%, BRVM 30%, GSE 20%",
        "underlying_type": "equity_basket",
        "underlying_config": json.dumps({
            "basket": {
                "NGX|NGX All-Share": {"weight": 0.50, "scale": 0.10},
                "BRVM|BRVM Composite": {"weight": 0.30, "scale": 1.0},
                "GSE|GSE Composite": {"weight": 0.20, "scale": 3.0},
            },
        }),
        "fee_pct": 0.50,
    },
    {
        "ticker": "WASI-NGX",
        "name": "WASI Nigeria Equity ETF",
        "category": "EQUITY",
        "description": "Tracks NGX All-Share Index (Nigerian Exchange)",
        "underlying_type": "equity",
        "underlying_config": json.dumps({
            "exchange": "NGX", "index": "NGX All-Share", "scale": 0.10,
        }),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-BRVM",
        "name": "WASI BRVM Equity ETF",
        "category": "EQUITY",
        "description": "Tracks BRVM Composite Index (8 UEMOA countries)",
        "underlying_type": "equity",
        "underlying_config": json.dumps({
            "exchange": "BRVM", "index": "BRVM Composite", "scale": 1.0,
        }),
        "fee_pct": 0.45,
    },
    {
        "ticker": "WASI-GSE",
        "name": "WASI Ghana Equity ETF",
        "category": "EQUITY",
        "description": "Tracks GSE Composite Index (Ghana Stock Exchange)",
        "underlying_type": "equity",
        "underlying_config": json.dumps({
            "exchange": "GSE", "index": "GSE Composite", "scale": 3.0,
        }),
        "fee_pct": 0.45,
    },

    # ── STRATEGY (5) ──────────────────────────────────────────────────────
    {
        "ticker": "WASI-MOM",
        "name": "WASI Momentum ETF",
        "category": "STRATEGY",
        "description": "Top 5 countries by strongest month-over-month index improvement",
        "underlying_type": "strategy",
        "underlying_config": json.dumps({"strategy": "momentum", "top_n": 5}),
        "fee_pct": 0.65,
    },
    {
        "ticker": "WASI-VAL",
        "name": "WASI Value ETF",
        "category": "STRATEGY",
        "description": "Countries where stock market most undervalues WASI fundamentals",
        "underlying_type": "strategy",
        "underlying_config": json.dumps({"strategy": "value"}),
        "fee_pct": 0.65,
    },
    {
        "ticker": "WASI-LVOL",
        "name": "WASI Low Volatility ETF",
        "category": "STRATEGY",
        "description": "5 countries with lowest index volatility over 12 months",
        "underlying_type": "strategy",
        "underlying_config": json.dumps({"strategy": "low_volatility", "top_n": 5}),
        "fee_pct": 0.55,
    },
    {
        "ticker": "WASI-CORR",
        "name": "WASI Corridor ETF",
        "category": "STRATEGY",
        "description": "Weighted basket of top-rated ECOWAS trade corridors",
        "underlying_type": "strategy",
        "underlying_config": json.dumps({"strategy": "corridor"}),
        "fee_pct": 0.60,
    },
    {
        "ticker": "WASI-RISK",
        "name": "WASI Risk-Adjusted ETF",
        "category": "STRATEGY",
        "description": "Countries weighted by inverse risk score (lower risk = higher weight)",
        "underlying_type": "strategy",
        "underlying_config": json.dumps({"strategy": "risk_adjusted"}),
        "fee_pct": 0.60,
    },

    # ── COUNTRY (16) ──────────────────────────────────────────────────────
    {"ticker": "WASI-NG", "name": "WASI Nigeria ETF", "category": "COUNTRY",
     "description": "Tracks Nigeria country index (28% of WASI composite)",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "NG"}), "fee_pct": 0.40},
    {"ticker": "WASI-CI", "name": "WASI Côte d'Ivoire ETF", "category": "COUNTRY",
     "description": "Tracks Côte d'Ivoire country index (22% of WASI composite)",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "CI"}), "fee_pct": 0.40},
    {"ticker": "WASI-GH", "name": "WASI Ghana ETF", "category": "COUNTRY",
     "description": "Tracks Ghana country index (15% of WASI composite)",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "GH"}), "fee_pct": 0.40},
    {"ticker": "WASI-SN", "name": "WASI Senegal ETF", "category": "COUNTRY",
     "description": "Tracks Senegal country index (10% of WASI composite)",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "SN"}), "fee_pct": 0.45},
    {"ticker": "WASI-BF", "name": "WASI Burkina Faso ETF", "category": "COUNTRY",
     "description": "Tracks Burkina Faso country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "BF"}), "fee_pct": 0.55},
    {"ticker": "WASI-ML", "name": "WASI Mali ETF", "category": "COUNTRY",
     "description": "Tracks Mali country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "ML"}), "fee_pct": 0.55},
    {"ticker": "WASI-GN", "name": "WASI Guinea ETF", "category": "COUNTRY",
     "description": "Tracks Guinea country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "GN"}), "fee_pct": 0.55},
    {"ticker": "WASI-BJ", "name": "WASI Benin ETF", "category": "COUNTRY",
     "description": "Tracks Benin country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "BJ"}), "fee_pct": 0.55},
    {"ticker": "WASI-TG", "name": "WASI Togo ETF", "category": "COUNTRY",
     "description": "Tracks Togo country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "TG"}), "fee_pct": 0.55},
    {"ticker": "WASI-NE", "name": "WASI Niger ETF", "category": "COUNTRY",
     "description": "Tracks Niger country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "NE"}), "fee_pct": 0.60},
    {"ticker": "WASI-MR", "name": "WASI Mauritania ETF", "category": "COUNTRY",
     "description": "Tracks Mauritania country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "MR"}), "fee_pct": 0.60},
    {"ticker": "WASI-GW", "name": "WASI Guinea-Bissau ETF", "category": "COUNTRY",
     "description": "Tracks Guinea-Bissau country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "GW"}), "fee_pct": 0.65},
    {"ticker": "WASI-SL", "name": "WASI Sierra Leone ETF", "category": "COUNTRY",
     "description": "Tracks Sierra Leone country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "SL"}), "fee_pct": 0.60},
    {"ticker": "WASI-LR", "name": "WASI Liberia ETF", "category": "COUNTRY",
     "description": "Tracks Liberia country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "LR"}), "fee_pct": 0.60},
    {"ticker": "WASI-GM", "name": "WASI Gambia ETF", "category": "COUNTRY",
     "description": "Tracks Gambia country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "GM"}), "fee_pct": 0.65},
    {"ticker": "WASI-CV", "name": "WASI Cabo Verde ETF", "category": "COUNTRY",
     "description": "Tracks Cabo Verde country index",
     "underlying_type": "country", "underlying_config": json.dumps({"country": "CV"}), "fee_pct": 0.65},
]


# WASI country weights for weighted averages
WASI_WEIGHTS = {
    "NG": 0.28, "CI": 0.22, "GH": 0.15, "SN": 0.10,
    "BF": 0.04, "ML": 0.04, "GN": 0.04, "BJ": 0.03, "TG": 0.03,
    "NE": 0.01, "MR": 0.01, "GW": 0.01, "SL": 0.01, "LR": 0.01, "GM": 0.01, "CV": 0.01,
}

# NAV multiplier: index score (0-100) × this = XOF price per unit
INDEX_NAV_MULTIPLIER = 100.0


class EtfEngine:
    """Calculates NAV for all 42 ETF products from live DB data."""

    def seed_etf_catalog(self, db: Session) -> int:
        """Insert all 42 ETF products if not already present."""
        existing = {e.ticker for e in db.query(EtfProduct.ticker).all()}
        inserted = 0
        for defn in ETF_CATALOG:
            if defn["ticker"] not in existing:
                db.add(EtfProduct(**defn))
                inserted += 1
        if inserted:
            db.commit()
            logger.info("ETF catalog: seeded %d new products (total=%d)", inserted, len(ETF_CATALOG))
        return inserted

    # ── NAV Calculators by underlying_type ───────────────────────────────

    def _get_latest_country_scores(self, db: Session) -> dict[str, dict]:
        """Get latest index scores per country code."""
        subq = (
            db.query(
                CountryIndex.country_id,
                func.max(CountryIndex.period_date).label("max_date"),
            )
            .group_by(CountryIndex.country_id)
            .subquery()
        )
        rows = (
            db.query(CountryIndex, Country)
            .join(subq, (CountryIndex.country_id == subq.c.country_id)
                  & (CountryIndex.period_date == subq.c.max_date))
            .join(Country, Country.id == CountryIndex.country_id)
            .all()
        )
        return {
            r.Country.code: {
                "index_value": r.CountryIndex.index_value,
                "shipping_score": r.CountryIndex.shipping_score,
                "trade_score": r.CountryIndex.trade_score,
                "infrastructure_score": r.CountryIndex.infrastructure_score,
                "economic_score": r.CountryIndex.economic_score,
            }
            for r in rows
        }

    def _get_latest_commodity_prices(self, db: Session) -> dict[str, float]:
        """Get latest price per commodity code."""
        subq = (
            db.query(
                CommodityPrice.commodity_code,
                func.max(CommodityPrice.period_date).label("max_date"),
            )
            .group_by(CommodityPrice.commodity_code)
            .subquery()
        )
        rows = (
            db.query(CommodityPrice)
            .join(subq, (CommodityPrice.commodity_code == subq.c.commodity_code)
                  & (CommodityPrice.period_date == subq.c.max_date))
            .all()
        )
        return {r.commodity_code: r.price_usd for r in rows}

    def _get_latest_stock_prices(self, db: Session) -> dict[str, float]:
        """Get latest index_value per 'EXCHANGE|INDEX_NAME' key."""
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
            .join(subq, (StockMarketData.exchange_code == subq.c.exchange_code)
                  & (StockMarketData.index_name == subq.c.index_name)
                  & (StockMarketData.trade_date == subq.c.max_date))
            .all()
        )
        return {f"{r.exchange_code}|{r.index_name}": r.index_value for r in rows}

    def _nav_composite(self, db: Session, config: dict, scores: dict) -> float:
        """WASI Composite: use WASIComposite table or calculate from scores."""
        latest = db.query(WASIComposite).order_by(WASIComposite.period_date.desc()).first()
        if latest:
            return round(latest.composite_value * INDEX_NAV_MULTIPLIER, 2)
        # Fallback: calculate from country scores
        if scores:
            total_w = sum(WASI_WEIGHTS.get(c, 0) for c in scores)
            if total_w > 0:
                val = sum(
                    scores[c]["index_value"] * WASI_WEIGHTS.get(c, 0) / total_w
                    for c in scores
                )
                return round(val * INDEX_NAV_MULTIPLIER, 2)
        return 0.0

    def _nav_country_group(self, config: dict, scores: dict) -> float:
        """Regional ETF: weighted average of country index values."""
        countries = config.get("countries", {})
        total = 0.0
        total_w = 0.0
        for code, weight in countries.items():
            if code in scores:
                total += scores[code]["index_value"] * weight
                total_w += weight
        if total_w > 0:
            return round((total / total_w) * INDEX_NAV_MULTIPLIER, 2)
        return 0.0

    def _nav_sub_index(self, config: dict, scores: dict) -> float:
        """Sector ETF: weighted average of a specific sub-score field."""
        field = config.get("score_field", "index_value")
        if field == "transport_composite":
            # Use index_value as proxy (transport data may not be in CountryIndex)
            field = "index_value"
        total = 0.0
        total_w = 0.0
        for code, weight in WASI_WEIGHTS.items():
            if code in scores and field in scores[code]:
                total += scores[code][field] * weight
                total_w += weight
        if total_w > 0:
            return round((total / total_w) * INDEX_NAV_MULTIPLIER, 2)
        return 0.0

    def _nav_country(self, config: dict, scores: dict) -> float:
        """Single-country ETF."""
        code = config.get("country", "")
        if code in scores:
            return round(scores[code]["index_value"] * INDEX_NAV_MULTIPLIER, 2)
        return 0.0

    def _nav_commodity(self, config: dict, prices: dict) -> float:
        """Single commodity ETF."""
        code = config.get("commodity", "")
        scale = config.get("scale", 1.0)
        usd_price = prices.get(code, 0)
        return round(usd_price * scale * (XOF_PER_USD / 100), 2)

    def _nav_commodity_basket(self, config: dict, prices: dict) -> float:
        """Commodity basket ETF."""
        basket = config.get("basket", {})
        scale = config.get("scale", 1.0)
        total = 0.0
        total_w = 0.0
        for code, weight in basket.items():
            if code in prices:
                total += prices[code] * weight
                total_w += weight
        if total_w > 0:
            return round((total / total_w) * scale * (XOF_PER_USD / 100), 2)
        return 0.0

    def _nav_equity(self, config: dict, stocks: dict) -> float:
        """Single equity ETF."""
        key = f"{config['exchange']}|{config['index']}"
        scale = config.get("scale", 1.0)
        val = stocks.get(key, 0)
        return round(val * scale, 2)

    def _nav_equity_basket(self, config: dict, stocks: dict) -> float:
        """Equity basket ETF."""
        basket = config.get("basket", {})
        total = 0.0
        total_w = 0.0
        for key, info in basket.items():
            val = stocks.get(key, 0)
            total += val * info["scale"] * info["weight"]
            total_w += info["weight"]
        if total_w > 0:
            return round(total / total_w, 2)
        return 0.0

    def _nav_strategy(self, config: dict, scores: dict) -> float:
        """Strategy ETFs: momentum, value, low_vol, corridor, risk_adjusted."""
        strategy = config.get("strategy", "")

        if strategy == "momentum":
            # Simple: use top N countries by highest index value as proxy
            top_n = config.get("top_n", 5)
            sorted_countries = sorted(
                scores.items(), key=lambda x: x[1]["index_value"], reverse=True
            )[:top_n]
            if sorted_countries:
                avg = sum(s["index_value"] for _, s in sorted_countries) / len(sorted_countries)
                return round(avg * INDEX_NAV_MULTIPLIER, 2)

        elif strategy == "low_volatility":
            # Use countries closest to the average (lowest dispersion)
            if scores:
                avg_val = sum(s["index_value"] for s in scores.values()) / len(scores)
                by_stability = sorted(
                    scores.items(), key=lambda x: abs(x[1]["index_value"] - avg_val)
                )[:config.get("top_n", 5)]
                avg = sum(s["index_value"] for _, s in by_stability) / len(by_stability)
                return round(avg * INDEX_NAV_MULTIPLIER, 2)

        elif strategy in ("value", "corridor", "risk_adjusted"):
            # Use WASI-weighted average as baseline
            if scores:
                total_w = sum(WASI_WEIGHTS.get(c, 0) for c in scores)
                if total_w > 0:
                    val = sum(
                        scores[c]["index_value"] * WASI_WEIGHTS.get(c, 0) / total_w
                        for c in scores
                    )
                    return round(val * INDEX_NAV_MULTIPLIER, 2)

        return 0.0

    # ── Main NAV calculation ─────────────────────────────────────────────

    def calculate_all_navs(self, db: Session) -> list[dict]:
        """Calculate current NAV for all 42 ETFs. Returns list of {ticker, nav_xof, nav_usd}."""
        scores = self._get_latest_country_scores(db)
        prices = self._get_latest_commodity_prices(db)
        stocks = self._get_latest_stock_prices(db)

        etfs = db.query(EtfProduct).filter(EtfProduct.is_active == True).all()
        results = []

        for etf in etfs:
            config = json.loads(etf.underlying_config) if etf.underlying_config else {}
            nav = 0.0

            if etf.underlying_type == "composite":
                nav = self._nav_composite(db, config, scores)
            elif etf.underlying_type == "country_group":
                nav = self._nav_country_group(config, scores)
            elif etf.underlying_type == "sub_index":
                nav = self._nav_sub_index(config, scores)
            elif etf.underlying_type == "country":
                nav = self._nav_country(config, scores)
            elif etf.underlying_type == "commodity":
                nav = self._nav_commodity(config, prices)
            elif etf.underlying_type == "commodity_basket":
                nav = self._nav_commodity_basket(config, prices)
            elif etf.underlying_type == "equity":
                nav = self._nav_equity(config, stocks)
            elif etf.underlying_type == "equity_basket":
                nav = self._nav_equity_basket(config, stocks)
            elif etf.underlying_type == "strategy":
                nav = self._nav_strategy(config, scores)

            nav_usd = round(nav / XOF_PER_USD, 4) if nav > 0 else 0.0

            # Calculate change from previous NAV
            old_nav = etf.nav_xof or 0.0
            change_pct = 0.0
            if old_nav > 0 and nav > 0:
                change_pct = round((nav - old_nav) / old_nav * 100, 2)

            # Update product record
            etf.nav_xof = nav
            etf.nav_usd = nav_usd
            etf.change_pct = change_pct
            etf.nav_updated_at = datetime.now(timezone.utc)

            results.append({
                "ticker": etf.ticker,
                "name": etf.name,
                "category": etf.category,
                "nav_xof": nav,
                "nav_usd": nav_usd,
                "change_pct": change_pct,
                "fee_pct": etf.fee_pct,
            })

        db.commit()

        # Save daily NAV snapshot
        today = date.today()
        for etf in etfs:
            existing = (
                db.query(EtfNavHistory)
                .filter(EtfNavHistory.etf_id == etf.id, EtfNavHistory.nav_date == today)
                .first()
            )
            if existing:
                existing.nav_xof = etf.nav_xof
                existing.nav_usd = etf.nav_usd
                existing.change_pct = etf.change_pct
            else:
                db.add(EtfNavHistory(
                    etf_id=etf.id, nav_date=today,
                    nav_xof=etf.nav_xof, nav_usd=etf.nav_usd,
                    change_pct=etf.change_pct,
                ))
        db.commit()

        logger.info("ETF NAV update: %d products priced", len(results))
        return results
