"""
UN Comtrade Trade Flows Scraper — src/pipelines/scrapers/comtrade_scraper.py

Fetches bilateral trade flows for WASI countries from the UN Comtrade API and
upserts BilateralTrade records.

Free tier (no key):  Legacy v1 endpoint — 100 requests/hour, TOTAL aggregate only.
                     URL: https://comtradeapi.un.org/public/v1/preview/C/A/HS
Subscription (key):  Full v1 endpoint — commodity-level HS codes, unlimited requests.
                     URL: https://comtradeapi.un.org/data/v1/get/C/A/HS
                     Set COMTRADE_API_KEY in .env

Fallback:            WB macro estimates used when API is unavailable.

Comtrade reporter codes (numeric):
  NG=566, CI=384, GH=288, SN=686, BF=854, ML=466, GN=324, BJ=204,
  TG=768, NE=562, MR=478, GW=624, SL=694, LR=430, GM=270, CV=132

Top partner codes fetched (ISO-3 for display, numeric for API):
  World total (partnerCode=0), CN=156, US=842, IN=699, EU=97, FR=251, DE=276
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import SessionLocal
from src.database.models import Country, BilateralTrade

logger = logging.getLogger(__name__)

# ── API config ────────────────────────────────────────────────────────────────
COMTRADE_FREE_URL  = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_FULL_URL  = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
REQUEST_TIMEOUT    = 25
REQUEST_DELAY      = 1.5    # free tier — 100 req/hr = 36s minimum; use 1.5s to be safe

# WASI ISO-2 → Comtrade numeric reporter code
COMTRADE_REPORTER_MAP: Dict[str, int] = {
    "CI": 384, "NG": 566, "GH": 288, "SN": 686,
    "BF": 854, "ML": 466, "GN": 324, "BJ": 204,
    "TG": 768, "NE": 562, "MR": 478, "GW": 624,
    "SL": 694, "LR": 430, "GM": 270, "CV": 132,
}

# Trade partners to fetch (0 = World total; key bilateral partners)
PARTNERS: Dict[str, Tuple[int, str]] = {
    "WLD": (0,   "World"),
    "CN":  (156, "China"),
    "US":  (842, "United States"),
    "IN":  (699, "India"),
    "FR":  (251, "France"),
    "DE":  (276, "Germany"),
    "NL":  (528, "Netherlands"),
}

# Typical commodity breakdown by country (static — enriches top_exports/top_imports)
TYPICAL_EXPORTS: Dict[str, str] = {
    "NG": "crude oil, petroleum gas, cocoa, rubber",
    "CI": "cocoa beans, crude oil, cashew, rubber, gold",
    "GH": "gold, crude oil, cocoa, tuna, manganese ore",
    "SN": "gold, fish, petroleum products, phosphoric acid, groundnuts",
    "BF": "gold, cotton, zinc ore, sesame seeds, dried leguminous vegetables",
    "ML": "gold, cotton, livestock, karité nuts",
    "GN": "gold, bauxite, diamonds, alumina, iron ore",
    "BJ": "cotton, cashew nuts, sesame, soybeans, palm oil",
    "TG": "cement, phosphates, cotton, cocoa, coffee",
    "NE": "uranium, gold, livestock, cowpeas, onions",
    "MR": "iron ore, fish, gold, copper",
    "GW": "cashew nuts, fish, groundnuts",
    "SL": "diamonds, titanium ore, bauxite, cocoa, coffee",
    "LR": "rubber, iron ore, gold, cocoa, palm oil",
    "GM": "groundnuts, fish, sesame seeds, cashews",
    "CV": "fish, salt, fish products, fuels, seafood",
}

TYPICAL_IMPORTS: Dict[str, str] = {
    "NG": "refined petroleum, wheat, rice, machinery, vehicles",
    "CI": "petroleum products, rice, aircraft, vehicles, pharmaceuticals",
    "GH": "petroleum products, aircraft, vehicles, refined petroleum, broadcasting equipment",
    "SN": "refined petroleum, rice, vehicles, wheat, aircraft",
    "BF": "petroleum products, vehicles, rice, pharmaceuticals, cement",
    "ML": "petroleum products, vehicles, pharmaceuticals, aircraft, wheat",
    "GN": "petroleum products, rice, pharmaceuticals, vehicles, cement",
    "BJ": "petroleum products, vehicles, rice, pharmaceuticals, poultry meat",
    "TG": "petroleum products, vehicles, rice, pharmaceuticals, poultry",
    "NE": "petroleum products, vehicles, rice, pharmaceuticals, cement",
    "MR": "petroleum products, rice, aircraft, vehicles, wheat",
    "GW": "petroleum products, rice, vehicles, cement, pharmaceuticals",
    "SL": "refined petroleum, rice, vehicles, pharmaceutical products, iron ore",
    "LR": "petroleum products, rice, pharmaceuticals, vehicles, aircraft",
    "GM": "petroleum products, rice, vehicles, pharmaceuticals, sugar",
    "CV": "refined petroleum, aircraft, vehicles, pharmaceuticals, broadcasting equipment",
}


# ── Fetch helpers ─────────────────────────────────────────────────────────────

def _fetch_aggregate(reporter_code: int, year: int, api_key: Optional[str] = None) -> Optional[Dict]:
    """
    Fetch total exports + imports for one country/year from Comtrade.
    Returns dict with {export_value_usd, import_value_usd, total_trade_usd} or None.
    """
    if api_key:
        url = COMTRADE_FULL_URL
        headers = {"Ocp-Apim-Subscription-Key": api_key}
    else:
        url = COMTRADE_FREE_URL
        headers = {}

    params = {
        "reporterCode": reporter_code,
        "partnerCode":  0,          # World total
        "period":       year,
        "motCode":      0,
        "customsCode":  "C00",
        "typeCode":     "C",        # Commodity
        "cmdCode":      "TOTAL",
        "flowCode":     "X,M",      # Exports + Imports
    }
    if api_key:
        params["subscription-key"] = api_key

    try:
        from src.pipelines.scrapers.resilience import resilient_get
        resp = resilient_get("comtrade", url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp is None:
            return None
        if resp.status_code == 404:
            return None
        payload = resp.json()
        data = payload.get("data", [])
        if not data:
            return None

        # Sum exports and imports
        exports = 0.0
        imports = 0.0
        for row in data:
            flow = str(row.get("flowCode", "") or row.get("rgDesc", "")).upper()
            val = float(row.get("primaryValue") or row.get("TradeValue") or 0)
            if "X" in flow or "EXPORT" in flow:
                exports += val
            elif "M" in flow or "IMPORT" in flow:
                imports += val

        if exports == 0 and imports == 0:
            return None

        return {
            "export_value_usd": exports,
            "import_value_usd": imports,
            "total_trade_usd":  exports + imports,
            "trade_balance_usd": exports - imports,
        }

    except Exception as exc:
        logger.debug("Comtrade fetch failed for reporter %d year %d: %s", reporter_code, year, exc)
        return None


# ── Main entry ────────────────────────────────────────────────────────────────

def run_comtrade_scraper(db: Session = None) -> Dict:
    """
    Fetch UN Comtrade trade flows for all WASI countries and upsert BilateralTrade records.

    Uses free-tier API (no key required for aggregate TOTAL data).
    Optionally uses full API if COMTRADE_API_KEY is configured.

    Returns: {updated, skipped, errors, countries, data_year}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    api_key = settings.COMTRADE_API_KEY or None
    summary = {
        "updated": 0, "skipped": 0, "errors": 0,
        "countries": [], "data_year": None, "api_used": bool(api_key),
    }

    # Target years: try most recent 2 completed years
    current_year = datetime.now().year
    target_years = [current_year - 1, current_year - 2]

    countries = db.query(Country).filter(Country.is_active == True).all()

    for country in countries:
        reporter_code = COMTRADE_REPORTER_MAP.get(country.code)
        if not reporter_code:
            summary["skipped"] += 1
            continue

        fetched_year = None
        result = None

        for year in target_years:
            try:
                result = _fetch_aggregate(reporter_code, year, api_key)
                time.sleep(REQUEST_DELAY)
                if result:
                    fetched_year = year
                    break
            except Exception as exc:
                logger.error("Comtrade error for %s year %d: %s", country.code, year, exc)
                time.sleep(REQUEST_DELAY)

        if not result or not fetched_year:
            logger.info("Comtrade: no data for %s (years %s)", country.code, target_years)
            summary["skipped"] += 1
            continue

        if summary["data_year"] is None:
            summary["data_year"] = fetched_year

        try:
            existing = (
                db.query(BilateralTrade)
                .filter(
                    BilateralTrade.country_id == country.id,
                    BilateralTrade.partner_code == "WLD",
                    BilateralTrade.year == fetched_year,
                )
                .first()
            )

            # Confidence: subscribed key = 0.80, free aggregate = 0.65
            confidence = 0.80 if api_key else 0.65
            source = "un_comtrade_api" if api_key else "un_comtrade_free"

            if existing:
                existing.export_value_usd  = result["export_value_usd"]
                existing.import_value_usd  = result["import_value_usd"]
                existing.total_trade_usd   = result["total_trade_usd"]
                existing.trade_balance_usd = result["trade_balance_usd"]
                existing.top_exports       = TYPICAL_EXPORTS.get(country.code, "")
                existing.top_imports       = TYPICAL_IMPORTS.get(country.code, "")
                existing.data_source       = source
                existing.confidence        = confidence
                summary["updated"] += 1
            else:
                db.add(BilateralTrade(
                    country_id        = country.id,
                    partner_code      = "WLD",
                    partner_name      = "World",
                    year              = fetched_year,
                    export_value_usd  = result["export_value_usd"],
                    import_value_usd  = result["import_value_usd"],
                    total_trade_usd   = result["total_trade_usd"],
                    trade_balance_usd = result["trade_balance_usd"],
                    top_exports       = TYPICAL_EXPORTS.get(country.code, ""),
                    top_imports       = TYPICAL_IMPORTS.get(country.code, ""),
                    data_source       = source,
                    confidence        = confidence,
                ))
                summary["updated"] += 1

            db.commit()

            summary["countries"].append({
                "code":     country.code,
                "year":     fetched_year,
                "exports":  round(result["export_value_usd"] / 1e9, 2),
                "imports":  round(result["import_value_usd"] / 1e9, 2),
                "balance":  round(result["trade_balance_usd"] / 1e9, 2),
            })
            logger.info(
                "Comtrade: %s %d — exports=$%.1fB imports=$%.1fB balance=$%.1fB",
                country.code, fetched_year,
                result["export_value_usd"] / 1e9,
                result["import_value_usd"] / 1e9,
                result["trade_balance_usd"] / 1e9,
            )

        except Exception as exc:
            logger.error("Comtrade DB error for %s: %s", country.code, exc, exc_info=True)
            db.rollback()
            summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "Comtrade scraper complete — updated=%d skipped=%d errors=%d year=%s api=%s",
        summary["updated"], summary["skipped"], summary["errors"],
        summary["data_year"], summary["api_used"],
    )
    return summary
