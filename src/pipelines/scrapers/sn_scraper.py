"""
Senegal (SN) data scraper.

Primary data sources:
  - Port Autonome de Dakar (PAD): https://www.portdakar.sn/
  - Agence Nationale de la Statistique et de la Démographie (ANSD)
  - BCEAO trade data
"""
from datetime import date
from typing import Optional

from .base_scraper import BaseScraper, ScraperResult

_BENCHMARKS = {
    "ship_arrivals":         95,
    "cargo_tonnage":         750_000,
    "container_teu":         55_000,
    "port_efficiency_score": 68.0,
    "dwell_time_days":       7.5,
    "gdp_growth_pct":        5.0,
    "trade_value_usd":       800_000_000,
}


class SNScraper(BaseScraper):
    """Senegal — primary-tier scraper (weight 10%)."""

    COUNTRY_CODE = "SN"

    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        self.logger.info("SN scraper: using benchmark data for %s", period_date)

        return ScraperResult(
            country_code="SN",
            period_date=period_date,
            ship_arrivals=_BENCHMARKS["ship_arrivals"],
            cargo_tonnage=_BENCHMARKS["cargo_tonnage"],
            container_teu=_BENCHMARKS["container_teu"],
            port_efficiency_score=_BENCHMARKS["port_efficiency_score"],
            dwell_time_days=_BENCHMARKS["dwell_time_days"],
            gdp_growth_pct=_BENCHMARKS["gdp_growth_pct"],
            trade_value_usd=_BENCHMARKS["trade_value_usd"],
            confidence=0.60,
            data_source="sn_benchmark_v1",
            notes="PAD Dakar benchmark",
        )
