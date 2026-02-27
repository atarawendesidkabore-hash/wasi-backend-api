"""
Ghana (GH) data scraper.

Primary data sources:
  - Ghana Ports and Harbours Authority (GPHA): https://www.ghanaports.gov.gh/
  - Ghana Statistical Service: https://statsghana.gov.gh/
  - Bank of Ghana trade statistics
"""
from datetime import date
from typing import Optional

from .base_scraper import BaseScraper, ScraperResult

_BENCHMARKS = {
    "ship_arrivals":         120,
    "cargo_tonnage":         1_200_000,
    "container_teu":         85_000,
    "port_efficiency_score": 65.0,
    "dwell_time_days":       8.0,
    "gdp_growth_pct":        5.5,
    "trade_value_usd":       1_400_000_000,
}


class GHScraper(BaseScraper):
    """Ghana — primary-tier scraper (weight 15%)."""

    COUNTRY_CODE = "GH"

    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        self.logger.info("GH scraper: using benchmark data for %s", period_date)

        return ScraperResult(
            country_code="GH",
            period_date=period_date,
            ship_arrivals=_BENCHMARKS["ship_arrivals"],
            cargo_tonnage=_BENCHMARKS["cargo_tonnage"],
            container_teu=_BENCHMARKS["container_teu"],
            port_efficiency_score=_BENCHMARKS["port_efficiency_score"],
            dwell_time_days=_BENCHMARKS["dwell_time_days"],
            gdp_growth_pct=_BENCHMARKS["gdp_growth_pct"],
            trade_value_usd=_BENCHMARKS["trade_value_usd"],
            confidence=0.65,
            data_source="gh_benchmark_v1",
            notes="GPHA Tema Port benchmark",
        )
