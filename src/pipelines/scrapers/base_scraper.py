"""
Base scraper class for all WASI country data scrapers.

Each country scraper subclasses BaseScraper and implements `fetch()`.
The returned dict must match the CountryIndex raw-input schema.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScraperResult:
    """Structured output from a scraper run."""
    country_code: str
    period_date: date
    ship_arrivals: float = 0.0
    cargo_tonnage: float = 0.0
    container_teu: float = 0.0
    port_efficiency_score: float = 50.0
    dwell_time_days: float = 15.0
    gdp_growth_pct: float = 0.0
    trade_value_usd: float = 0.0
    # Data quality metadata
    confidence: float = 1.0         # 0.0 = no data, 1.0 = verified primary source
    data_quality: str = "high"      # "high" | "medium" | "low"
    data_source: str = "scraper"
    notes: str = ""

    def to_raw_dict(self) -> dict:
        """Return the raw-input dict expected by IndexCalculationEngine."""
        return {
            "ship_arrivals":         self.ship_arrivals,
            "cargo_tonnage":         self.cargo_tonnage,
            "container_teu":         self.container_teu,
            "port_efficiency_score": self.port_efficiency_score,
            "dwell_time_days":       self.dwell_time_days,
            "gdp_growth_pct":        self.gdp_growth_pct,
            "trade_value_usd":       self.trade_value_usd,
        }

    @staticmethod
    def quality_from_confidence(confidence: float) -> str:
        if confidence >= 0.8:
            return "high"
        if confidence >= 0.5:
            return "medium"
        return "low"


class BaseScraper(ABC):
    """
    Abstract base class for country data scrapers.

    Subclasses override `fetch()` to retrieve data from their specific source.
    The base class provides shared HTTP helpers and normalisation utilities.
    """

    COUNTRY_CODE: str = ""

    def __init__(self, timeout_seconds: int = 30):
        self.timeout = timeout_seconds
        self.logger = logging.getLogger(f"{__name__}.{self.COUNTRY_CODE}")

    @abstractmethod
    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        """
        Fetch data for the given month.

        Args:
            period_date: First day of the target month (e.g. date(2024, 1, 1)).

        Returns:
            ScraperResult on success, None if no data available.
        """

    def run(self, period_date: date) -> Optional[ScraperResult]:
        """Safe wrapper around fetch() — catches exceptions and logs them."""
        try:
            result = self.fetch(period_date)
            if result:
                result.data_quality = ScraperResult.quality_from_confidence(result.confidence)
            return result
        except Exception as exc:
            self.logger.error(
                "Scraper %s failed for %s: %s",
                self.COUNTRY_CODE, period_date, exc, exc_info=True,
            )
            return None

    # ── Shared utilities ──────────────────────────────────────────────────────

    @staticmethod
    def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, value))
