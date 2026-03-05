"""
World Bank Open Data Scraper — src/pipelines/scrapers/worldbank_scraper.py

Fetches real macroeconomic and trade indicators from the World Bank API
for all 16 WASI countries, then computes and upserts CountryIndex records.

API:        https://api.worldbank.org/v2  (free, no key required)
Rate limit: ~100 requests/minute
Data lag:   1–2 years behind current (annual official statistics)

World Bank indicators fetched:
  NY.GDP.MKTP.KD.ZG  — GDP growth rate (annual %)
  FP.CPI.TOTL.ZG      — Consumer price inflation (annual %)
  NE.EXP.GNFS.CD      — Exports of goods and services (current USD)
  NE.IMP.GNFS.CD      — Imports of goods and services (current USD)
  IS.SHP.GOOD.TU      — Container port traffic (TEU)
  IS.AIR.PSGR         — Air transport, passengers carried
  LP.LPI.OVRL.XQ      — Logistics Performance Index, overall (1–5 scale)
  LP.LPI.CUST.XQ      — LPI Customs efficiency (1–5 scale)

Derived fields for IndexCalculationEngine:
  container_teu       ← IS.SHP.GOOD.TU (direct, or estimated)
  trade_value_usd     ← exports + imports
  gdp_growth_pct      ← NY.GDP.MKTP.KD.ZG
  port_efficiency_score ← LP.LPI.OVRL.XQ / 5 * 100
  dwell_time_days     ← estimated from LP.LPI.CUST.XQ (high LPI → low dwell)
  cargo_tonnage       ← estimated from trade_value_usd / 250 ($/tonne proxy)
  ship_arrivals       ← estimated from container_teu / 1500 (TEU/vessel proxy)
"""

import logging
import time
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex
from src.engines.index_calculation import IndexCalculationEngine

logger = logging.getLogger(__name__)

# ── World Bank API config ─────────────────────────────────────────────────────
WB_BASE_URL = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT = 20   # seconds
REQUEST_DELAY   = 0.4  # polite inter-request delay (seconds)

WB_INDICATORS: Dict[str, str] = {
    "gdp_growth":    "NY.GDP.MKTP.KD.ZG",
    "inflation":     "FP.CPI.TOTL.ZG",
    "exports_usd":   "NE.EXP.GNFS.CD",
    "imports_usd":   "NE.IMP.GNFS.CD",
    "container_teu": "IS.SHP.GOOD.TU",
    "air_pax":       "IS.AIR.PSGR",
    "lpi_overall":   "LP.LPI.OVRL.XQ",
    "lpi_customs":   "LP.LPI.CUST.XQ",
}

# WASI → World Bank country code map (mostly ISO-2, all match for these countries)
WB_COUNTRY_MAP: Dict[str, str] = {
    "CI": "CI", "NG": "NG", "GH": "GH", "SN": "SN",
    "BF": "BF", "ML": "ML", "GN": "GN", "BJ": "BJ",
    "TG": "TG", "NE": "NE", "MR": "MR", "GW": "GW",
    "SL": "SL", "LR": "LR", "GM": "GM", "CV": "CV",
}

# Regional benchmarks for normalization (used when WB data is missing)
# Container port TEU annual totals (approximate 2022–2023)
TEU_BENCHMARKS: Dict[str, int] = {
    "NG": 1_500_000, "CI": 1_400_000, "TG": 1_400_000,
    "GH": 900_000,   "SN": 400_000,   "BJ": 300_000,
    "CM": 400_000,   "GN": 120_000,   "MR": 80_000,
    "SL": 60_000,    "LR": 50_000,    "GM": 30_000,
    "GW": 15_000,    "CV": 60_000,    "ML": 0,
    "BF": 0,         "NE": 0,
}

# Annual trade value benchmarks (USD, approximate 2022–2023)
TRADE_BENCHMARKS: Dict[str, float] = {
    "NG": 140_000_000_000, "CI": 35_000_000_000, "GH": 32_000_000_000,
    "SN": 12_000_000_000,  "ML": 8_000_000_000,  "BF": 6_000_000_000,
    "GN": 9_000_000_000,   "BJ": 5_000_000_000,  "TG": 6_000_000_000,
    "NE": 4_000_000_000,   "MR": 5_000_000_000,  "SL": 2_000_000_000,
    "LR": 2_500_000_000,   "GM": 1_000_000_000,  "GW": 700_000_000,
    "CV": 1_200_000_000,
}


# ── World Bank API fetch helpers ──────────────────────────────────────────────

def _fetch_indicator(wb_code: str, indicator: str, years: int = 5) -> Tuple[Optional[float], Optional[int]]:
    """
    Fetch the most recent non-null value for one indicator from the WB API.
    Returns (value, year) or (None, None) if unavailable.
    """
    url = f"{WB_BASE_URL}/country/{wb_code}/indicator/{indicator}"
    params = {"format": "json", "mrv": years, "per_page": years}
    try:
        from src.pipelines.scrapers.resilience import resilient_get
        resp = resilient_get("worldbank", url, params=params, timeout=REQUEST_TIMEOUT)
        if resp is None:
            return None, None
        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            return None, None
        for entry in payload[1]:
            if entry.get("value") is not None:
                try:
                    year = int(entry["date"])
                except (ValueError, KeyError):
                    year = None
                return float(entry["value"]), year
        return None, None
    except Exception as exc:
        logger.debug("WB fetch skipped %s/%s: %s", wb_code, indicator, exc)
        return None, None


def _fetch_country_data(wasi_code: str) -> Tuple[Dict[str, Optional[float]], Optional[int]]:
    """
    Fetch all WB indicators for one WASI country.
    Returns (data_dict, latest_year).
    latest_year is the most common year across indicators (best estimate).
    """
    wb_code = WB_COUNTRY_MAP.get(wasi_code)
    if not wb_code:
        return {}, None

    raw: Dict[str, Optional[float]] = {}
    years = []

    for field, indicator_code in WB_INDICATORS.items():
        value, year = _fetch_indicator(wb_code, indicator_code)
        raw[field] = value
        if year:
            years.append(year)
        time.sleep(REQUEST_DELAY)

    # Determine representative year (most common, fallback to max)
    data_year = max(set(years), key=years.count) if years else datetime.now().year - 2
    return raw, data_year


# ── Index computation from WB data ───────────────────────────────────────────

def _build_engine_input(raw: Dict[str, Optional[float]], country_code: str) -> Dict[str, float]:
    """
    Map World Bank indicator values to IndexCalculationEngine input fields.
    Missing WB indicators are estimated from regional benchmarks.
    """
    exports = raw.get("exports_usd") or 0.0
    imports = raw.get("imports_usd") or 0.0
    trade_value = exports + imports
    if trade_value == 0:
        trade_value = TRADE_BENCHMARKS.get(country_code, 3_000_000_000) * 0.7

    # container_teu — direct from WB or fallback to regional benchmark
    teu_raw = raw.get("container_teu")
    if teu_raw and teu_raw > 0:
        container_teu = float(teu_raw)
    else:
        container_teu = float(TEU_BENCHMARKS.get(country_code, 50_000))

    # cargo_tonnage — estimated from trade value (~$250/tonne proxy for mixed cargo)
    cargo_tonnage = trade_value / 250.0

    # ship_arrivals — estimated from TEU (~1500 TEU per vessel call)
    ship_arrivals = max(1, container_teu / 1500.0)

    # port_efficiency_score — from LPI overall (scale 1–5 → 0–100)
    lpi = raw.get("lpi_overall")
    if lpi and 1.0 <= lpi <= 5.0:
        port_efficiency_score = (lpi - 1.0) / 4.0 * 100.0
    else:
        port_efficiency_score = 45.0  # ECOWAS average (~LPI 2.8)

    # dwell_time_days — from LPI customs efficiency (1–5 → 20–3 days, inverted)
    lpi_cust = raw.get("lpi_customs")
    if lpi_cust and 1.0 <= lpi_cust <= 5.0:
        dwell_time_days = 20.0 - (lpi_cust - 1.0) / 4.0 * 17.0
    else:
        dwell_time_days = 12.0  # ECOWAS average

    # gdp_growth_pct — direct
    gdp_growth = raw.get("gdp_growth") or 0.0

    return {
        "ship_arrivals":         round(ship_arrivals, 1),
        "cargo_tonnage":         round(cargo_tonnage, 0),
        "container_teu":         round(container_teu, 0),
        "port_efficiency_score": round(port_efficiency_score, 2),
        "dwell_time_days":       round(dwell_time_days, 2),
        "gdp_growth_pct":        round(gdp_growth, 2),
        "trade_value_usd":       round(trade_value, 0),
    }


def _assess_data_quality(raw: Dict[str, Optional[float]]) -> Tuple[float, str]:
    """
    Compute confidence (0–1) and data_quality label based on non-null WB fields.
    LPI fields are published every 2 years so may be missing — penalize less.
    """
    critical = ["gdp_growth", "exports_usd", "imports_usd"]
    supplementary = ["container_teu", "air_pax", "inflation"]
    lpi_fields = ["lpi_overall", "lpi_customs"]

    critical_ok = sum(1 for f in critical if raw.get(f) is not None)
    supp_ok = sum(1 for f in supplementary if raw.get(f) is not None)
    lpi_ok = sum(1 for f in lpi_fields if raw.get(f) is not None)

    # Scoring: critical = 0.25 each (max 0.75), supplementary = 0.05 each (max 0.15), LPI = 0.05 each (max 0.10)
    confidence = (
        critical_ok * 0.25 +
        supp_ok     * 0.05 +
        lpi_ok      * 0.05
    )
    confidence = min(0.90, confidence)   # cap — WB data always has some lag

    if confidence >= 0.70:
        quality = "high"
    elif confidence >= 0.45:
        quality = "medium"
    else:
        quality = "low"

    return round(confidence, 2), quality


# ── Main scraper entry point ──────────────────────────────────────────────────

def run_worldbank_scraper(db: Session = None) -> Dict:
    """
    Fetch World Bank data for all 16 WASI countries, compute WASI indices,
    and upsert CountryIndex records.

    Only updates existing records if the new data has equal or higher confidence.
    Marks data_source as "World Bank Open Data API" for traceability.

    Returns: {updated, skipped, errors, countries, data_year}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    engine = IndexCalculationEngine()
    summary = {"updated": 0, "skipped": 0, "errors": 0, "countries": [], "data_year": None}

    countries = db.query(Country).filter(Country.is_active == True).all()

    for country in countries:
        logger.info("WorldBank scraper: %s (%s)", country.name, country.code)
        try:
            raw, data_year = _fetch_country_data(country.code)
            if not raw:
                logger.warning("WB: no data returned for %s", country.code)
                summary["skipped"] += 1
                continue

            if summary["data_year"] is None:
                summary["data_year"] = data_year

            engine_input = _build_engine_input(raw, country.code)
            scores = engine.calculate_country_index(engine_input)
            confidence, quality = _assess_data_quality(raw)

            # period_date = January 1st of the data year
            period_date = date(data_year, 1, 1)

            existing = (
                db.query(CountryIndex)
                .filter(
                    CountryIndex.country_id == country.id,
                    CountryIndex.period_date == period_date,
                )
                .first()
            )

            if existing:
                # Only overwrite if new data is at least as good
                if confidence >= (existing.confidence or 0.0):
                    existing.ship_arrivals         = int(engine_input["ship_arrivals"])
                    existing.cargo_tonnage         = engine_input["cargo_tonnage"]
                    existing.container_teu         = engine_input["container_teu"]
                    existing.port_efficiency_score = engine_input["port_efficiency_score"]
                    existing.dwell_time_days       = engine_input["dwell_time_days"]
                    existing.gdp_growth_pct        = engine_input["gdp_growth_pct"]
                    existing.trade_value_usd       = engine_input["trade_value_usd"]
                    existing.shipping_score        = scores["shipping_score"]
                    existing.trade_score           = scores["trade_score"]
                    existing.infrastructure_score  = scores["infrastructure_score"]
                    existing.economic_score        = scores["economic_score"]
                    existing.index_value           = scores["index_value"]
                    existing.confidence            = confidence
                    existing.data_quality          = quality
                    existing.data_source           = "World Bank Open Data API"
                    summary["updated"] += 1
                else:
                    summary["skipped"] += 1
            else:
                db.add(CountryIndex(
                    country_id            = country.id,
                    period_date           = period_date,
                    ship_arrivals         = int(engine_input["ship_arrivals"]),
                    cargo_tonnage         = engine_input["cargo_tonnage"],
                    container_teu         = engine_input["container_teu"],
                    port_efficiency_score = engine_input["port_efficiency_score"],
                    dwell_time_days       = engine_input["dwell_time_days"],
                    gdp_growth_pct        = engine_input["gdp_growth_pct"],
                    trade_value_usd       = engine_input["trade_value_usd"],
                    shipping_score        = scores["shipping_score"],
                    trade_score           = scores["trade_score"],
                    infrastructure_score  = scores["infrastructure_score"],
                    economic_score        = scores["economic_score"],
                    index_value           = scores["index_value"],
                    confidence            = confidence,
                    data_quality          = quality,
                    data_source           = "World Bank Open Data API",
                ))
                summary["updated"] += 1

            db.commit()

            summary["countries"].append({
                "code":        country.code,
                "index_value": round(scores["index_value"], 2),
                "confidence":  confidence,
                "quality":     quality,
                "data_year":   data_year,
            })
            logger.info(
                "WB: %s → index=%.1f quality=%s confidence=%.2f (year %s)",
                country.code, scores["index_value"], quality, confidence, data_year
            )

        except Exception as exc:
            logger.error("WB scraper error for %s: %s", country.code, exc, exc_info=True)
            db.rollback()
            summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "WorldBank scraper complete — updated=%d skipped=%d errors=%d year=%s",
        summary["updated"], summary["skipped"], summary["errors"], summary["data_year"]
    )
    return summary
