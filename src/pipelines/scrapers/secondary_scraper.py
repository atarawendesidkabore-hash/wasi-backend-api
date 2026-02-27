"""
Secondary-tier country scrapers for WASI (combined module).

Covers: CM (Cameroon), AO (Angola), TZ (Tanzania), KE (Kenya),
        MA (Morocco), MZ (Mozambique), ET (Ethiopia),
        BJ (Benin), TG (Togo), GN (Guinea), MG (Madagascar), MU (Mauritius).

For efficiency, all secondary-tier countries share a single module.
Each country has its own benchmark dict and scraper class.
"""
from datetime import date
from typing import Dict, Optional

from .base_scraper import BaseScraper, ScraperResult


# ── Country benchmark data ────────────────────────────────────────────────────

_BENCHMARKS: Dict[str, dict] = {
    "CM": {  # Cameroon — Port of Douala
        "ship_arrivals": 70, "cargo_tonnage": 800_000, "container_teu": 35_000,
        "port_efficiency_score": 48.0, "dwell_time_days": 14.0,
        "gdp_growth_pct": 3.8, "trade_value_usd": 600_000_000,
        "confidence": 0.60,
    },
    "AO": {  # Angola — Port of Luanda
        "ship_arrivals": 80, "cargo_tonnage": 950_000, "container_teu": 42_000,
        "port_efficiency_score": 45.0, "dwell_time_days": 16.0,
        "gdp_growth_pct": 1.5, "trade_value_usd": 1_100_000_000,
        "confidence": 0.55,
    },
    "TZ": {  # Tanzania — Port of Dar es Salaam
        "ship_arrivals": 55, "cargo_tonnage": 700_000, "container_teu": 55_000,
        "port_efficiency_score": 52.0, "dwell_time_days": 12.0,
        "gdp_growth_pct": 5.0, "trade_value_usd": 450_000_000,
        "confidence": 0.60,
    },
    "KE": {  # Kenya — Port of Mombasa
        "ship_arrivals": 65, "cargo_tonnage": 850_000, "container_teu": 95_000,
        "port_efficiency_score": 60.0, "dwell_time_days": 10.0,
        "gdp_growth_pct": 5.5, "trade_value_usd": 750_000_000,
        "confidence": 0.65,
    },
    "MA": {  # Morocco — Port of Casablanca / Tanger Med
        "ship_arrivals": 150, "cargo_tonnage": 1_800_000, "container_teu": 130_000,
        "port_efficiency_score": 74.0, "dwell_time_days": 5.0,
        "gdp_growth_pct": 3.5, "trade_value_usd": 2_000_000_000,
        "confidence": 0.75,
    },
    "MZ": {  # Mozambique — Port of Maputo
        "ship_arrivals": 30, "cargo_tonnage": 400_000, "container_teu": 20_000,
        "port_efficiency_score": 42.0, "dwell_time_days": 18.0,
        "gdp_growth_pct": 4.0, "trade_value_usd": 280_000_000,
        "confidence": 0.50,
    },
    "ET": {  # Ethiopia — landlocked; Djibouti corridor
        "ship_arrivals": 0, "cargo_tonnage": 0, "container_teu": 0,
        "port_efficiency_score": 0.0, "dwell_time_days": 28.0,
        "gdp_growth_pct": 6.0, "trade_value_usd": 350_000_000,
        "confidence": 0.45,
    },
    "BJ": {  # Benin — Port of Cotonou
        "ship_arrivals": 45, "cargo_tonnage": 450_000, "container_teu": 30_000,
        "port_efficiency_score": 50.0, "dwell_time_days": 11.0,
        "gdp_growth_pct": 6.5, "trade_value_usd": 300_000_000,
        "confidence": 0.55,
    },
    "TG": {  # Togo — Port of Lomé
        "ship_arrivals": 50, "cargo_tonnage": 500_000, "container_teu": 48_000,
        "port_efficiency_score": 62.0, "dwell_time_days": 8.0,
        "gdp_growth_pct": 5.5, "trade_value_usd": 340_000_000,
        "confidence": 0.60,
    },
    "GN": {  # Guinea — Port of Conakry
        "ship_arrivals": 35, "cargo_tonnage": 350_000, "container_teu": 18_000,
        "port_efficiency_score": 40.0, "dwell_time_days": 20.0,
        "gdp_growth_pct": 4.5, "trade_value_usd": 200_000_000,
        "confidence": 0.45,
    },
    "MG": {  # Madagascar — Port of Toamasina
        "ship_arrivals": 28, "cargo_tonnage": 280_000, "container_teu": 15_000,
        "port_efficiency_score": 38.0, "dwell_time_days": 22.0,
        "gdp_growth_pct": 3.0, "trade_value_usd": 150_000_000,
        "confidence": 0.45,
    },
    "MU": {  # Mauritius — Port Louis
        "ship_arrivals": 40, "cargo_tonnage": 350_000, "container_teu": 28_000,
        "port_efficiency_score": 80.0, "dwell_time_days": 4.0,
        "gdp_growth_pct": 5.0, "trade_value_usd": 400_000_000,
        "confidence": 0.75,
    },
}


class SecondaryScraper(BaseScraper):
    """Generic scraper for any secondary/tertiary-tier country."""

    def __init__(self, country_code: str, timeout_seconds: int = 30):
        self.COUNTRY_CODE = country_code
        super().__init__(timeout_seconds)

    def fetch(self, period_date: date) -> Optional[ScraperResult]:
        bm = _BENCHMARKS.get(self.COUNTRY_CODE)
        if not bm:
            self.logger.warning("No benchmark data for country code: %s", self.COUNTRY_CODE)
            return None

        self.logger.info("%s scraper: using benchmark data for %s", self.COUNTRY_CODE, period_date)

        return ScraperResult(
            country_code=self.COUNTRY_CODE,
            period_date=period_date,
            ship_arrivals=bm["ship_arrivals"],
            cargo_tonnage=bm["cargo_tonnage"],
            container_teu=bm["container_teu"],
            port_efficiency_score=bm["port_efficiency_score"],
            dwell_time_days=bm["dwell_time_days"],
            gdp_growth_pct=bm["gdp_growth_pct"],
            trade_value_usd=bm["trade_value_usd"],
            confidence=bm["confidence"],
            data_source=f"{self.COUNTRY_CODE.lower()}_benchmark_v1",
        )


# Convenience factory function
def get_secondary_scraper(country_code: str) -> SecondaryScraper:
    """Return a secondary scraper for the given country code."""
    return SecondaryScraper(country_code)


# Pre-built instances for all secondary/tertiary countries
ALL_SECONDARY_SCRAPERS = {
    code: SecondaryScraper(code)
    for code in _BENCHMARKS
}
