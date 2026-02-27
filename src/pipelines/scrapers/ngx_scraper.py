"""
NGX (Nigerian Exchange Group) stock market scraper.

Free data source: https://afx.kwayisi.org/ngx/
  - Returns JSON with All-Share Index value and listed equities
  - No API key required, delayed ~24h

Live endpoint (GET, returns JSON):
  https://afx.kwayisi.org/api/ngx/
  Response shape:
  {
    "index": 71234.56,
    "change": 0.45,       # day-over-day % change
    "market_cap": 43000000000000,  # NGN
    ...
  }

NGN → USD conversion: 1 USD ≈ 1500 NGN (2024 parallel market rate)
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

EXCHANGE_CODE = "NGX"
INDEX_NAME    = "NGX All-Share Index"
COUNTRY_CODES = "NG"
NGN_TO_USD    = 1 / 1500.0
_API_URL      = "https://afx.kwayisi.org/api/ngx/"


def fetch_ngx() -> Optional[dict]:
    """
    Fetch latest NGX All-Share Index from Kwayisi free API.
    Returns a dict ready for StockMarketData, or None on failure.
    """
    try:
        import httpx
        resp = httpx.get(_API_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        index_val = float(data.get("index", 0))
        change    = float(data.get("change", 0))
        mcap_ngn  = float(data.get("market_cap", 0))

        return {
            "exchange_code":  EXCHANGE_CODE,
            "index_name":     INDEX_NAME,
            "country_codes":  COUNTRY_CODES,
            "trade_date":     date.today().replace(day=1),
            "index_value":    round(index_val, 2),
            "change_pct":     round(change, 2),
            "ytd_change_pct": None,
            "market_cap_usd": round(mcap_ngn * NGN_TO_USD, 2),
            "volume_usd":     None,
            "data_source":    "kwayisi_ngx",
            "confidence":     0.80,
        }
    except Exception as exc:
        logger.warning("NGX scraper failed: %s", exc)
        return None
