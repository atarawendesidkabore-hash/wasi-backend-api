"""
IMF World Economic Outlook (WEO) Scraper — src/pipelines/scrapers/imf_scraper.py

Fetches macroeconomic indicators from the IMF DataMapper API (free, no key required)
for all 16 WASI countries and upserts MacroIndicator records.

API:        https://www.imf.org/external/datamapper/api/v1  (free, no auth)
Rate limit: polite — 0.3s delay between indicator requests
Data:       Annual, includes current-year projections from WEO (April/October releases)

Indicators fetched:
  NGDP_RPCH     — Real GDP growth rate (%)
  PCPIPCH       — Consumer price inflation (%)
  GGXWDG_NGDP   — General government gross debt (% of GDP)
  BCA_NGDPD     — Current account balance (% of GDP)
  LUR           — Unemployment rate (%)
  NGDPD         — Nominal GDP (current USD billions)

WASI ISO-2 → IMF ISO-3 code mapping (mostly identical, a few exceptions):
  CI → CIV (Côte d'Ivoire)
  NG → NGA
  GH → GHA  SN → SEN  BF → BFA  ML → MLI  GN → GIN  BJ → BEN
  TG → TGO  NE → NER  MR → MRT  GW → GNB  SL → SLE  LR → LBR
  GM → GMB  CV → CPV
"""
from __future__ import annotations

import logging
import time
from datetime import timezone, datetime
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, MacroIndicator

logger = logging.getLogger(__name__)

# ── API config ────────────────────────────────────────────────────────────────
IMF_BASE_URL   = "https://www.imf.org/external/datamapper/api/v1"
REQUEST_TIMEOUT = 25
REQUEST_DELAY   = 0.3   # polite delay between indicator fetches

# IMF indicators to fetch
IMF_INDICATORS: Dict[str, str] = {
    "gdp_growth_pct":           "NGDP_RPCH",
    "inflation_pct":            "PCPIPCH",
    "debt_gdp_pct":             "GGXWDG_NGDP",
    "current_account_gdp_pct":  "BCA_NGDPD",
    "unemployment_pct":         "LUR",
    "gdp_usd_billions":         "NGDPD",
}

# WASI ISO-2 → IMF ISO-3
IMF_COUNTRY_MAP: Dict[str, str] = {
    "CI": "CIV", "NG": "NGA", "GH": "GHA", "SN": "SEN",
    "BF": "BFA", "ML": "MLI", "GN": "GIN", "BJ": "BEN",
    "TG": "TGO", "NE": "NER", "MR": "MRT", "GW": "GNB",
    "SL": "SLE", "LR": "LBR", "GM": "GMB", "CV": "CPV",
}

# Reverse map: IMF-3 → WASI-2
_REVERSE_MAP: Dict[str, str] = {v: k for k, v in IMF_COUNTRY_MAP.items()}

# Fetch recent years + upcoming projection
_YEARS = [str(y) for y in range(datetime.now().year - 3, datetime.now().year + 2)]


# ── API fetch ─────────────────────────────────────────────────────────────────

def _fetch_indicator_all_countries(imf_code: str) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Fetch one IMF indicator for all countries.
    Returns {imf_country_code: {year_str: value}} or empty dict on failure.
    """
    url = f"{IMF_BASE_URL}/{imf_code}"
    params = {"periods": ",".join(_YEARS)}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        # Expected: {"values": {"NGDP_RPCH": {"NGA": {"2022": 3.31, ...}, ...}}}
        return payload.get("values", {}).get(imf_code, {})
    except Exception as exc:
        logger.warning("IMF fetch failed for %s: %s", imf_code, exc)
        return {}


def _best_value(country_data: Dict[str, Optional[float]]) -> Tuple[Optional[float], Optional[int], bool]:
    """
    Pick the most recent non-null actual value (prefer the latest non-projection year).
    Returns (value, year, is_projection).
    Projections are current and future years in WEO.
    """
    current_year = datetime.now().year
    # Try recent actual years first (1–3 years ago), then accept projections
    for lag in range(1, 4):
        yr = str(current_year - lag)
        if yr in country_data and country_data[yr] is not None:
            return float(country_data[yr]), int(yr), False
    # Fall back to projection year (current year IMF estimate)
    yr = str(current_year)
    if yr in country_data and country_data[yr] is not None:
        return float(country_data[yr]), int(yr), True
    # Next year forecast
    yr = str(current_year + 1)
    if yr in country_data and country_data[yr] is not None:
        return float(country_data[yr]), int(yr), True
    return None, None, False


# ── Main entry ────────────────────────────────────────────────────────────────

def run_imf_scraper(db: Session = None) -> Dict:
    """
    Fetch IMF WEO data for all 16 WASI countries and upsert MacroIndicator records.

    Returns: {updated, skipped, errors, countries, data_year}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary = {
        "updated": 0, "skipped": 0, "errors": 0,
        "countries": [], "data_year": None,
    }

    # Step 1: bulk-fetch all indicators at once (one request per indicator)
    raw_data: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for field, imf_code in IMF_INDICATORS.items():
        raw_data[field] = _fetch_indicator_all_countries(imf_code)
        logger.debug("IMF: fetched %s — %d countries returned", imf_code, len(raw_data[field]))
        time.sleep(REQUEST_DELAY)

    # Step 2: per-country upsert
    countries = db.query(Country).filter(Country.is_active == True).all()

    for country in countries:
        imf_code = IMF_COUNTRY_MAP.get(country.code)
        if not imf_code:
            logger.debug("IMF: no code mapping for %s", country.code)
            summary["skipped"] += 1
            continue

        try:
            # Gather values for this country
            values: Dict[str, Tuple[Optional[float], Optional[int], bool]] = {}
            for field in IMF_INDICATORS:
                country_series = raw_data[field].get(imf_code, {})
                val, yr, is_proj = _best_value(country_series)
                values[field] = (val, yr, is_proj)

            # Determine representative year (most common among non-null fields)
            years_present = [v[1] for v in values.values() if v[1] is not None]
            if not years_present:
                logger.warning("IMF: no data at all for %s", country.code)
                summary["skipped"] += 1
                continue

            data_year = max(set(years_present), key=years_present.count)
            is_projection = any(v[2] for v in values.values() if v[1] == data_year)

            if summary["data_year"] is None:
                summary["data_year"] = data_year

            # Confidence: fraction of non-null fields
            non_null = sum(1 for v in values.values() if v[0] is not None)
            confidence = round(min(0.90, non_null / len(IMF_INDICATORS) * 0.90), 2)

            # Upsert
            existing = (
                db.query(MacroIndicator)
                .filter(
                    MacroIndicator.country_id == country.id,
                    MacroIndicator.year == data_year,
                    MacroIndicator.data_source == "imf_weo",
                )
                .first()
            )

            if existing:
                if confidence >= (existing.confidence or 0.0):
                    existing.gdp_growth_pct           = values["gdp_growth_pct"][0]
                    existing.inflation_pct            = values["inflation_pct"][0]
                    existing.debt_gdp_pct             = values["debt_gdp_pct"][0]
                    existing.current_account_gdp_pct  = values["current_account_gdp_pct"][0]
                    existing.unemployment_pct         = values["unemployment_pct"][0]
                    existing.gdp_usd_billions         = values["gdp_usd_billions"][0]
                    existing.is_projection            = is_projection
                    existing.confidence               = confidence
                    existing.fetched_at               = datetime.now(timezone.utc)
                    summary["updated"] += 1
                else:
                    summary["skipped"] += 1
            else:
                db.add(MacroIndicator(
                    country_id               = country.id,
                    year                     = data_year,
                    gdp_growth_pct           = values["gdp_growth_pct"][0],
                    inflation_pct            = values["inflation_pct"][0],
                    debt_gdp_pct             = values["debt_gdp_pct"][0],
                    current_account_gdp_pct  = values["current_account_gdp_pct"][0],
                    unemployment_pct         = values["unemployment_pct"][0],
                    gdp_usd_billions         = values["gdp_usd_billions"][0],
                    data_source              = "imf_weo",
                    is_projection            = is_projection,
                    confidence               = confidence,
                ))
                summary["updated"] += 1

            db.commit()

            summary["countries"].append({
                "code":           country.code,
                "year":           data_year,
                "gdp_growth":     values["gdp_growth_pct"][0],
                "debt_gdp":       values["debt_gdp_pct"][0],
                "inflation":      values["inflation_pct"][0],
                "is_projection":  is_projection,
                "confidence":     confidence,
            })
            logger.info(
                "IMF: %s %d — gdp_growth=%.1f%% debt=%.1f%% inflation=%.1f%% (proj=%s)",
                country.code, data_year,
                values["gdp_growth_pct"][0] or 0,
                values["debt_gdp_pct"][0] or 0,
                values["inflation_pct"][0] or 0,
                is_projection,
            )

        except Exception as exc:
            logger.error("IMF scraper error for %s: %s", country.code, exc, exc_info=True)
            db.rollback()
            summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "IMF scraper complete — updated=%d skipped=%d errors=%d year=%s",
        summary["updated"], summary["skipped"], summary["errors"], summary["data_year"],
    )
    return summary
