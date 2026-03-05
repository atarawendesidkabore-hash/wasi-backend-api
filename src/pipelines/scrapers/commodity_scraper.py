"""
World Bank Pink Sheet Commodity Scraper — src/pipelines/scrapers/commodity_scraper.py

Fetches global commodity spot prices from the World Bank Commodity Price Data (Pink Sheet)
via the WB Data API v2 (free, no key required).

API:    https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&mrv=12
        World = reporter "1W" or "WLD" depending on indicator version.

Commodities fetched (key for WASI country revenues):
  Cocoa    — PCOCOA     — USD/kg     — CI/GH/NG/CM
  Brent    — POILBRE    — USD/bbl    — NG/CI/GH
  Gold     — PGOLD      — USD/troy oz — GH/ML/BF/GN
  Cotton   — PCOTTON    — USD/kg     — ML/BF/BJ/TG
  Coffee   — PCOFFEA    — USD/kg     — CI/GN/TG
  Iron ore — PIORECR    — USD/dmt    — LR/GN/MR (emerging)

Prices are stored in CommodityPrice table (monthly, 1st of month).
Used by AI agent to contextualize commodity-exporting country indices.

WB Pink Sheet API note:
  These are world-level (not per-country) series.
  The API response format may have "WLD" or a null country code.
  We specifically look for world-level aggregate rows.
"""
from __future__ import annotations

import logging
import time
from datetime import timezone, datetime, date
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import CommodityPrice

logger = logging.getLogger(__name__)

# ── API config ────────────────────────────────────────────────────────────────
WB_BASE_URL     = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT = 20
REQUEST_DELAY   = 0.4

# Commodity definitions: code → (wb_indicator, display_name, unit, affected_countries)
COMMODITIES: Dict[str, Tuple[str, str, str, str]] = {
    "COCOA":    ("PCOCOA",   "Cocoa",         "USD/kg",      "CI, GH, NG, BJ, TG, CM"),
    "BRENT":    ("POILBRE",  "Brent Crude Oil","USD/bbl",     "NG, CI, GH, MR"),
    "GOLD":     ("PGOLD",    "Gold",           "USD/troy oz", "GH, ML, BF, GN, SL, LR, NE"),
    "COTTON":   ("PCOTTON",  "Cotton A-Index", "USD/kg",      "ML, BF, BJ, TG, NE"),
    "COFFEE":   ("PCOFFEA",  "Coffee (Arabica)","USD/kg",     "CI, GN, TG, GH"),
    "IRON_ORE": ("PIORECR",  "Iron Ore",       "USD/dmt",     "LR, GN, MR, SL"),
}

# Known prices fallback (Jan 2025 approximate) in case WB API is unavailable
_FALLBACK_PRICES: Dict[str, Tuple[float, str]] = {
    "COCOA":    (9.20,    "2025-01"),
    "BRENT":    (76.80,   "2025-01"),
    "GOLD":     (2650.00, "2025-01"),
    "COTTON":   (0.86,    "2025-01"),
    "COFFEE":   (3.20,    "2025-01"),
    "IRON_ORE": (105.00,  "2025-01"),
}


# ── WB API fetch ──────────────────────────────────────────────────────────────

def _fetch_commodity_price(wb_indicator: str, months: int = 12) -> List[Dict]:
    """
    Fetch recent monthly price data for one commodity from WB API.
    Returns list of {date_str, price} dicts sorted newest first.
    """
    # Try "WLD" (World) country code first
    for country_code in ("WLD", "1W", "all"):
        url = f"{WB_BASE_URL}/country/{country_code}/indicator/{wb_indicator}"
        params = {
            "format":   "json",
            "mrv":      months,
            "per_page": months,
            "frequency": "M",   # monthly
        }
        try:
            from src.pipelines.scrapers.resilience import resilient_get
            resp = resilient_get("commodity", url, params=params, timeout=REQUEST_TIMEOUT)
            if resp is None:
                continue
            if resp.status_code in (400, 404):
                continue
            payload = resp.json()

            if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
                continue

            entries = []
            for row in payload[1]:
                val = row.get("value")
                dt  = row.get("date", "")
                if val is None:
                    continue
                try:
                    price = float(val)
                    # WB returns YYYY-MM or YYYY format
                    if len(dt) == 7:
                        d = date(int(dt[:4]), int(dt[5:7]), 1)
                    elif len(dt) == 4:
                        d = date(int(dt), 1, 1)
                    else:
                        continue
                    entries.append({"date": d, "price": price})
                except (ValueError, TypeError):
                    continue

            if entries:
                return sorted(entries, key=lambda x: x["date"], reverse=True)

        except Exception as exc:
            logger.debug("WB commodity fetch failed %s/%s: %s", country_code, wb_indicator, exc)
            continue

    return []


def _calculate_changes(current: float, prev_month: Optional[float], prev_year: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """Compute MoM and YoY % changes. Returns (mom_pct, yoy_pct)."""
    mom = round((current - prev_month) / prev_month * 100, 2) if prev_month else None
    yoy = round((current - prev_year)  / prev_year  * 100, 2) if prev_year  else None
    return mom, yoy


# ── Main entry ────────────────────────────────────────────────────────────────

def run_commodity_scraper(db: Session = None) -> Dict:
    """
    Fetch WB Pink Sheet commodity prices and upsert CommodityPrice records.

    Returns: {updated, skipped, errors, commodities, latest_prices}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary = {
        "updated": 0, "skipped": 0, "errors": 0,
        "commodities": [], "latest_prices": {},
    }

    for code, (wb_indicator, name, unit, affected) in COMMODITIES.items():
        try:
            entries = _fetch_commodity_price(wb_indicator, months=14)  # 14 months for YoY calc
            time.sleep(REQUEST_DELAY)

            if not entries:
                logger.warning("Commodity scraper: no data from WB for %s, trying fallback", code)
                # Use fallback price
                fb_price, fb_period = _FALLBACK_PRICES.get(code, (0.0, "2025-01"))
                yr, mo = int(fb_period[:4]), int(fb_period[5:7])
                entries = [{"date": date(yr, mo, 1), "price": fb_price}]

            # Latest entry
            latest = entries[0]
            prev_month_entry = entries[1] if len(entries) > 1 else None
            prev_year_entry  = next(
                (e for e in entries if e["date"].year == latest["date"].year - 1
                 and e["date"].month == latest["date"].month),
                None
            )

            mom, yoy = _calculate_changes(
                latest["price"],
                prev_month_entry["price"] if prev_month_entry else None,
                prev_year_entry["price"]  if prev_year_entry  else None,
            )

            # Upsert latest price
            existing = (
                db.query(CommodityPrice)
                .filter(
                    CommodityPrice.commodity_code == code,
                    CommodityPrice.period_date    == latest["date"],
                )
                .first()
            )

            if existing:
                existing.price_usd        = latest["price"]
                existing.pct_change_mom   = mom
                existing.pct_change_yoy   = yoy
                existing.fetched_at       = datetime.now(timezone.utc)
                summary["updated"] += 1
            else:
                db.add(CommodityPrice(
                    commodity_code  = code,
                    commodity_name  = name,
                    unit            = unit,
                    period_date     = latest["date"],
                    price_usd       = latest["price"],
                    pct_change_mom  = mom,
                    pct_change_yoy  = yoy,
                    data_source     = "wb_pinksheet",
                ))
                summary["updated"] += 1

            # Also insert historical entries (previous 12 months) for trend queries
            for hist in entries[1:13]:
                hist_existing = (
                    db.query(CommodityPrice)
                    .filter(
                        CommodityPrice.commodity_code == code,
                        CommodityPrice.period_date    == hist["date"],
                    )
                    .first()
                )
                if not hist_existing:
                    db.add(CommodityPrice(
                        commodity_code = code,
                        commodity_name = name,
                        unit           = unit,
                        period_date    = hist["date"],
                        price_usd      = hist["price"],
                        data_source    = "wb_pinksheet",
                    ))

            db.commit()

            summary["commodities"].append({
                "code":        code,
                "name":        name,
                "price_usd":   latest["price"],
                "unit":        unit,
                "period":      str(latest["date"]),
                "mom_pct":     mom,
                "yoy_pct":     yoy,
                "affected":    affected,
            })
            summary["latest_prices"][code] = latest["price"]

            logger.info(
                "Commodity: %s — $%.2f %s (%s) MoM=%s%% YoY=%s%%",
                code, latest["price"], unit, latest["date"],
                f"{mom:+.1f}" if mom is not None else "N/A",
                f"{yoy:+.1f}" if yoy is not None else "N/A",
            )

        except Exception as exc:
            logger.error("Commodity scraper error for %s: %s", code, exc, exc_info=True)
            db.rollback()
            summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "Commodity scraper complete — updated=%d skipped=%d errors=%d",
        summary["updated"], summary["skipped"], summary["errors"],
    )
    return summary
