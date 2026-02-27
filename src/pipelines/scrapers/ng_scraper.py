"""
Nigeria (NG) data scraper.

Primary data sources:
  - Nigerian Ports Authority (NPA): https://www.nigerianports.gov.ng/
  - National Bureau of Statistics (NBS): https://nigerianstat.gov.ng/
  - CBN Trade Data: https://www.cbn.gov.ng/

In production, replace the `fetch()` stub with live HTTP calls.
The benchmark values below are based on Apapa & Tin Can Island ports, 2019–2024.
"""
from datetime import date
from typing import Optional

from .base_scraper import BaseScraper, ScraperResult

# Monthly benchmarks derived from NPA annual reports (2019–2023 averages)
_BENCHMARKS = {
    "ship_arrivals":         190,        # vessels/month (Apapa + Tin Can)
    "cargo_tonnage":         3_500_000,  # metric tonnes/month
    "container_teu":         110_000,    # TEU/month
    "port_efficiency_score": 52.0,       # composite port performance (0–100)
    "dwell_time_days":       12.0,       # avg container dwell time (days)
    "gdp_growth_pct":        3.2,        # annualised GDP growth
    "trade_value_usd":       4_200_000_000,  # monthly trade value (USD)
}


class NGScraper(BaseScraper):
    """Nigeria — West African primary-tier scraper (weight 28%)."""

    COUNTRY_CODE = "NG"

    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        """
        Return port & trade data for Nigeria for the given month.

        TODO (production):
          resp = requests.get(NPA_API_URL, params={"month": period_date}, timeout=self.timeout)
          resp.raise_for_status()
          raw = resp.json()
          ... parse raw into ScraperResult fields ...
        """
        self.logger.info("NG scraper: using benchmark data for %s", period_date)

        return ScraperResult(
            country_code="NG",
            period_date=period_date,
            ship_arrivals=_BENCHMARKS["ship_arrivals"],
            cargo_tonnage=_BENCHMARKS["cargo_tonnage"],
            container_teu=_BENCHMARKS["container_teu"],
            port_efficiency_score=_BENCHMARKS["port_efficiency_score"],
            dwell_time_days=_BENCHMARKS["dwell_time_days"],
            gdp_growth_pct=_BENCHMARKS["gdp_growth_pct"],
            trade_value_usd=_BENCHMARKS["trade_value_usd"],
            confidence=0.65,    # benchmark/estimated — not live primary data
            data_source="ng_benchmark_v1",
            notes="NPA Apapa+Tin Can benchmark; replace with live NPA API",
        )
