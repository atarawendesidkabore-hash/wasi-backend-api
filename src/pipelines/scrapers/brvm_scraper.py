"""
BRVM (Bourse Régionale des Valeurs Mobilières) stock market scraper.

Covers 8 UEMOA countries — WASI-relevant: CI, SN, BJ, TG (34% combined weight).
Official portal: https://www.brvm.org/en

Two indices tracked:
  BRVM Composite — all listed securities
  BRVM 10        — top 10 most liquid securities

Free data: brvm.org publishes daily index values publicly.
Open-source reference: https://github.com/Kyac99/brvm-data-platform

XOF (FCFA) → USD: 1 USD ≈ 600 XOF (fixed peg)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

EXCHANGE_CODE   = "BRVM"
XOF_TO_USD      = 1 / 600.0

_INDICES = [
    {
        "index_name":    "BRVM Composite",
        "country_codes": "CI,SN,BJ,TG",
        "data_source":   "brvm_org",
        "confidence":    0.85,
    },
    {
        "index_name":    "BRVM 10",
        "country_codes": "CI,SN,BJ,TG",
        "data_source":   "brvm_org",
        "confidence":    0.85,
    },
]

# BRVM portal endpoints (HTML scrape fallback)
_BASE_URL = "https://www.brvm.org/en"


def _scrape_brvm_portal() -> Optional[dict[str, float]]:
    """
    Attempt to scrape index values from brvm.org.
    Returns {index_name: value} or None on failure.

    NOTE: BRVM does not expose a public JSON API.
    This is a best-effort HTML parse of the indices table.
    If the layout changes, update the CSS selector below.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup  # type: ignore

        resp = httpx.get(_BASE_URL, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results = {}

        # Try to find index table rows containing "BRVM" in the text
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).upper()
                value_text = cells[1].get_text(strip=True).replace(",", "").replace(" ", "")
                if "BRVM COMPOSITE" in label or "BRVMCOMPOSITE" in label:
                    try:
                        results["BRVM Composite"] = float(value_text)
                    except ValueError:
                        pass
                elif "BRVM10" in label or "BRVM 10" in label:
                    try:
                        results["BRVM 10"] = float(value_text)
                    except ValueError:
                        pass

        return results if results else None

    except ImportError:
        logger.warning("BeautifulSoup not installed; BRVM scraper needs: pip install beautifulsoup4")
        return None
    except Exception as exc:
        logger.warning("BRVM portal scrape failed: %s", exc)
        return None


def fetch_brvm() -> list[dict]:
    """
    Fetch latest BRVM Composite and BRVM 10 index values.
    Returns a list of dicts (one per index) ready for StockMarketData,
    or an empty list on failure.
    """
    trade_date = date.today().replace(day=1)
    scraped = _scrape_brvm_portal()

    records = []
    for meta in _INDICES:
        iname = meta["index_name"]
        value = scraped.get(iname) if scraped else None

        if value is None:
            logger.info("BRVM: no live value for %s — skipping", iname)
            continue

        records.append({
            "exchange_code":  EXCHANGE_CODE,
            "index_name":     iname,
            "country_codes":  meta["country_codes"],
            "trade_date":     trade_date,
            "index_value":    round(value, 2),
            "change_pct":     None,
            "ytd_change_pct": None,
            "market_cap_usd": None,
            "volume_usd":     None,
            "data_source":    meta["data_source"],
            "confidence":     meta["confidence"],
        })

    return records
