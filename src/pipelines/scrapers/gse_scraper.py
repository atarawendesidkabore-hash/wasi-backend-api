"""
GSE (Ghana Stock Exchange) stock market scraper.

Free data source: https://dev.kwayisi.org/apis/gse/
  - Returns JSON with GSE Composite Index value
  - No API key required

Live endpoint (GET, returns JSON):
  https://dev.kwayisi.org/apis/gse/
  Response shape:
  {
    "composite": 2847.32,
    "change": 1.23,
    "market_cap": 73000000000,   # GHS
    ...
  }

GHS → USD conversion: 1 USD ≈ 15.5 GHS (2024 rate; cedi depreciation factored)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

EXCHANGE_CODE = "GSE"
INDEX_NAME    = "GSE Composite"
COUNTRY_CODES = "GH"
GHS_TO_USD    = 1 / 15.5
_API_URL      = "https://dev.kwayisi.org/apis/gse/"


def fetch_gse() -> Optional[dict]:
    """
    Fetch latest GSE Composite Index from Kwayisi free API.
    Returns a dict ready for StockMarketData, or None on failure.
    """
    try:
        import httpx
        resp = httpx.get(_API_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        index_val = float(data.get("composite", 0))
        change    = float(data.get("change", 0))
        mcap_ghs  = float(data.get("market_cap", 0))

        return {
            "exchange_code":  EXCHANGE_CODE,
            "index_name":     INDEX_NAME,
            "country_codes":  COUNTRY_CODES,
            "trade_date":     date.today().replace(day=1),
            "index_value":    round(index_val, 2),
            "change_pct":     round(change, 2),
            "ytd_change_pct": None,
            "market_cap_usd": round(mcap_ghs * GHS_TO_USD, 2),
            "volume_usd":     None,
            "data_source":    "kwayisi_gse",
            "confidence":     0.80,
        }
    except Exception as exc:
        logger.warning("GSE scraper failed: %s", exc)
        return None
