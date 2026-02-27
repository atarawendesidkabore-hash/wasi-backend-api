"""
BCEAO (Banque Centrale des États de l'Afrique de l'Ouest) scraper.

Target portal: https://edenpub.bceao.int
BCEAO publishes monthly statistical bulletins covering 8 UEMOA countries.
WASI-relevant subset: CI (Côte d'Ivoire), SN (Sénégal), BJ (Bénin), TG (Togo).

Current implementation: falls back to the bundled sample CSV when the live
portal is unreachable (no scraping credentials, rate-limit, or network issue).

To enable live scraping:
  1. Obtain a session token from edenpub.bceao.int (browser login or API key)
  2. Set BCEAO_SESSION_TOKEN in .env
  3. Implement _fetch_live() below using the confirmed endpoint/format

Data series scraped:
  - PIB (taux de croissance annuel, %)
  - Taux d'inflation (%, IPC)
  - Exportations (milliards FCFA)
  - Importations (milliards FCFA)
  - IPI (Indice de Production Industrielle, base 100)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from src.pipelines.parsers.bceao_parser import BCEAORecord, parse_csv

logger = logging.getLogger(__name__)

# Fallback CSV bundled with the repository
_FALLBACK_CSV = (
    Path(__file__).resolve().parents[4] / "data" / "sample_bceao_uemoa_2019_2024.csv"
)

# Environment variable for live scraping session token (optional)
_SESSION_TOKEN_ENV = "BCEAO_SESSION_TOKEN"

# Live API endpoint template (fill in once confirmed)
_LIVE_BASE_URL = "https://edenpub.bceao.int"


def _fetch_live(session_token: str) -> Optional[list[BCEAORecord]]:
    """
    Attempt to scrape live data from edenpub.bceao.int.

    Returns a list of BCEAORecord on success, None on any failure.
    This is a stub — implement with actual endpoint/format when available.
    """
    try:
        import httpx  # type: ignore

        # TODO: replace with confirmed BCEAO API endpoint and payload
        # Example (hypothetical):
        # url = f"{_LIVE_BASE_URL}/api/series/monthly"
        # params = {"countries": "CI,SN,BJ,TG", "series": "PIB,INFLATION,TRADE,IPI"}
        # response = httpx.get(url, headers={"Authorization": f"Bearer {session_token}"}, timeout=30)
        # response.raise_for_status()
        # return _parse_live_response(response.json())

        logger.info(
            "BCEAO live scraping not yet implemented — falling back to sample CSV. "
            "Set BCEAO_SESSION_TOKEN and implement _fetch_live() to enable."
        )
        return None
    except Exception as exc:
        logger.warning("BCEAO live fetch failed: %s", exc)
        return None


def fetch_bceao_records() -> list[BCEAORecord]:
    """
    Retrieve BCEAO monthly records for WASI countries (CI, SN, BJ, TG).

    Strategy:
      1. If BCEAO_SESSION_TOKEN is set, attempt live scraping.
      2. Fall back to sample CSV bundled in data/.

    Returns a (possibly empty) list of BCEAORecord objects.
    """
    token = os.environ.get(_SESSION_TOKEN_ENV, "").strip()
    if token:
        records = _fetch_live(token)
        if records is not None:
            logger.info("BCEAO live scrape returned %d records", len(records))
            return records

    # Fallback
    if _FALLBACK_CSV.exists():
        logger.info("Using BCEAO fallback CSV: %s", _FALLBACK_CSV)
        return parse_csv(_FALLBACK_CSV)

    logger.warning(
        "BCEAO fallback CSV not found at %s — returning empty list", _FALLBACK_CSV
    )
    return []
