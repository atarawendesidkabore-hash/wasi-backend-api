"""
Burkina Faso (BF) data scraper.

Burkina Faso is landlocked — no direct port access.
Data sources focus on transit trade and land-border volumes:
  - ONAC (Office National du Commerce): trade statistics
  - BCEAO: financial/trade flow data
  - World Bank Logistics Performance Index sub-indicators

Since BF is not in the WASI composite weights, this scraper provides
supplementary data for regional analysis and procurement tracking.
"""
from datetime import date
from typing import Optional

from .base_scraper import BaseScraper, ScraperResult

# BF is landlocked; port fields are 0; focus on trade/GDP metrics
_BENCHMARKS = {
    "ship_arrivals":         0,           # N/A — landlocked
    "cargo_tonnage":         0,           # N/A
    "container_teu":         0,           # N/A
    "port_efficiency_score": 0.0,         # N/A
    "dwell_time_days":       30.0,        # transit dwell (estimated)
    "gdp_growth_pct":        2.0,         # conservative (political instability)
    "trade_value_usd":       180_000_000, # monthly cross-border trade (USD)
}


class BFScraper(BaseScraper):
    """
    Burkina Faso — supplementary scraper (not in WASI composite).

    Used for procurement data enrichment and regional context.
    """

    COUNTRY_CODE = "BF"

    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        """
        BF data comes from ONAC monthly trade reports and BCEAO.

        Note: confidence is LOW (0.3) because:
          - No direct port data
          - Political instability since 2022 affects data continuity
          - Limited statistical infrastructure

        TODO (production):
          resp = requests.get(BCEAO_API, params={"country": "BF", "month": period_date})
          ...
        """
        self.logger.info("BF scraper: using benchmark data for %s (landlocked country)", period_date)

        return ScraperResult(
            country_code="BF",
            period_date=period_date,
            ship_arrivals=_BENCHMARKS["ship_arrivals"],
            cargo_tonnage=_BENCHMARKS["cargo_tonnage"],
            container_teu=_BENCHMARKS["container_teu"],
            port_efficiency_score=_BENCHMARKS["port_efficiency_score"],
            dwell_time_days=_BENCHMARKS["dwell_time_days"],
            gdp_growth_pct=_BENCHMARKS["gdp_growth_pct"],
            trade_value_usd=_BENCHMARKS["trade_value_usd"],
            confidence=0.30,    # low — landlocked + data gaps
            data_source="bf_benchmark_v1",
            notes="Landlocked; no port data. Trade via Abidjan/Lomé corridors.",
        )
