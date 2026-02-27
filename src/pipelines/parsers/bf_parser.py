"""
Burkina Faso (BF) data parser and index processor.

Handles two input formats:
  1. CSV: monthly trade/procurement reports from ONAC or BCEAO
  2. Dict: structured data from BFScraper or manual entry

Since BF is landlocked, the parser adapts the standard port-centric
schema by zeroing out port fields and deriving a trade-only index.

Expected CSV columns (all optional, zero-filled if absent):
    date, country_code, gdp_growth_pct, trade_value_usd,
    dwell_time_days, tender_count, awarded_count, total_value_usd

The computed index emphasises trade & economic scores (port/shipping = 0).
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from src.engines.index_calculation import IndexCalculationEngine

logger = logging.getLogger(__name__)

# BF has no ports; override weights for landlocked countries
# Trade: 50%, Economic: 40%, Infrastructure (transit): 10%, Shipping: 0%
_BF_WEIGHT_OVERRIDES = {
    "shipping_weight":      0.00,
    "trade_weight":         0.50,
    "infrastructure_weight": 0.10,
    "economic_weight":      0.40,
}

COUNTRY_CODE = "BF"


class BFParser:
    """
    Parses and processes Burkina Faso trade/procurement data into a
    CountryIndex-compatible record.
    """

    def __init__(self):
        self._engine = IndexCalculationEngine()

    # ── CSV parsing ──────────────────────────────────────────────────────────

    def parse_csv(self, filepath: str) -> List[Dict]:
        """
        Read a BF CSV file and return a list of processed records.

        Each record is ready for direct insertion into CountryIndex
        (after looking up country_id by code "BF").

        Returns empty list on failure.
        """
        if not os.path.isfile(filepath):
            logger.error("BF CSV not found: %s", filepath)
            return []

        try:
            df = pd.read_csv(filepath, parse_dates=["date"])
        except Exception as exc:
            logger.error("Failed to read BF CSV %s: %s", filepath, exc)
            return []

        records = []
        for _, row in df.iterrows():
            code = str(row.get("country_code", "BF")).strip().upper()
            if code != COUNTRY_CODE:
                logger.warning("BFParser skipping non-BF row: country_code=%s", code)
                continue

            period_date = row["date"].date().replace(day=1)
            processed = self._process_row(row.to_dict(), period_date)
            if processed:
                records.append(processed)

        logger.info("BFParser parsed %d records from %s", len(records), filepath)
        return records

    # ── Dict / scraper result processing ─────────────────────────────────────

    def process_dict(self, data: Dict, period_date: date) -> Optional[Dict]:
        """
        Process a raw data dict (e.g. from BFScraper) into a CountryIndex record.
        """
        return self._process_row(data, period_date)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _process_row(self, row: Dict, period_date: date) -> Optional[Dict]:
        """Apply BF-specific weight overrides and return a processed record dict."""
        raw = {
            "ship_arrivals":         0,    # N/A — landlocked
            "cargo_tonnage":         0,    # N/A
            "container_teu":         0,    # N/A
            "port_efficiency_score": 0.0,  # N/A
            "dwell_time_days":       float(row.get("dwell_time_days") or 30),
            "gdp_growth_pct":        float(row.get("gdp_growth_pct") or 0),
            "trade_value_usd":       float(row.get("trade_value_usd") or 0),
        }

        # Compute sub-scores using the standard engine, then override weights
        scores = self._engine.calculate_country_index(raw)

        # Re-compute index_value with BF-specific weights (no shipping)
        index_value = (
            scores["shipping_score"]      * _BF_WEIGHT_OVERRIDES["shipping_weight"]
            + scores["trade_score"]       * _BF_WEIGHT_OVERRIDES["trade_weight"]
            + scores["infrastructure_score"] * _BF_WEIGHT_OVERRIDES["infrastructure_weight"]
            + scores["economic_score"]    * _BF_WEIGHT_OVERRIDES["economic_weight"]
        )

        return {
            "country_code":          COUNTRY_CODE,
            "period_date":           period_date,
            "ship_arrivals":         0,
            "cargo_tonnage":         0.0,
            "container_teu":         0.0,
            "port_efficiency_score": 0.0,
            "dwell_time_days":       raw["dwell_time_days"],
            "gdp_growth_pct":        raw["gdp_growth_pct"],
            "trade_value_usd":       raw["trade_value_usd"],
            "shipping_score":        0.0,
            "trade_score":           round(scores["trade_score"], 4),
            "infrastructure_score":  round(scores["infrastructure_score"], 4),
            "economic_score":        round(scores["economic_score"], 4),
            "index_value":           round(max(0.0, min(100.0, index_value)), 4),
            "confidence":            float(row.get("confidence", 0.30)),
            "data_quality":          "low",   # always low for BF (landlocked, data gaps)
            "data_source":           str(row.get("data_source", "bf_parser")),
        }
