from typing import Dict, Any


class IndexCalculationEngine:
    """
    Calculates a per-country shipping/trade index score (0.0 – 100.0)
    from raw port data using four weighted sub-components.

    Sub-component weights:
      Shipping       40%  (ship arrivals + cargo tonnage)
      Trade          30%  (cargo tonnage + container TEU)
      Infrastructure 20%  (port efficiency + dwell time, inverted)
      Economic       10%  (GDP growth + trade value)
    """

    COMPONENT_WEIGHTS = {
        "shipping":       0.40,
        "trade":          0.30,
        "infrastructure": 0.20,
        "economic":       0.10,
    }

    # Normalization reference values (West African port benchmarks)
    NORMALIZATION = {
        "ship_arrivals":          {"min": 0,    "max": 500},
        "cargo_tonnage":          {"min": 0,    "max": 5_000_000},
        "container_teu":          {"min": 0,    "max": 1_000_000},
        "port_efficiency_score":  {"min": 0,    "max": 100},
        "dwell_time_days":        {"min": 1,    "max": 30},   # inverted: lower = better
        "gdp_growth_pct":         {"min": -5.0, "max": 15.0},
        "trade_value_usd":        {"min": 0,    "max": 50_000_000_000},
    }

    def _normalize(self, value: float, key: str, invert: bool = False) -> float:
        ref = self.NORMALIZATION[key]
        span = ref["max"] - ref["min"]
        if span == 0:
            return 50.0
        clamped = max(ref["min"], min(ref["max"], value))
        score = ((clamped - ref["min"]) / span) * 100.0
        return 100.0 - score if invert else score

    def calculate_shipping_score(self, data: Dict[str, Any]) -> float:
        arrivals = self._normalize(data.get("ship_arrivals", 0), "ship_arrivals")
        cargo = self._normalize(data.get("cargo_tonnage", 0), "cargo_tonnage")
        return arrivals * 0.5 + cargo * 0.5

    def calculate_trade_score(self, data: Dict[str, Any]) -> float:
        cargo = self._normalize(data.get("cargo_tonnage", 0), "cargo_tonnage")
        teu = self._normalize(data.get("container_teu", 0), "container_teu")
        return cargo * 0.5 + teu * 0.5

    def calculate_infrastructure_score(self, data: Dict[str, Any]) -> float:
        efficiency = self._normalize(
            data.get("port_efficiency_score", 50), "port_efficiency_score"
        )
        dwell = self._normalize(
            data.get("dwell_time_days", 15), "dwell_time_days", invert=True
        )
        return efficiency * 0.6 + dwell * 0.4

    def calculate_economic_score(self, data: Dict[str, Any]) -> float:
        gdp = self._normalize(data.get("gdp_growth_pct", 0), "gdp_growth_pct")
        trade = self._normalize(data.get("trade_value_usd", 0), "trade_value_usd")
        return gdp * 0.4 + trade * 0.6

    def calculate_country_index(self, data: Dict[str, Any]) -> Dict[str, float]:
        """
        Returns all sub-scores and the final weighted index value.
        All values are in the range 0.0 – 100.0.
        """
        shipping = self.calculate_shipping_score(data)
        trade = self.calculate_trade_score(data)
        infrastructure = self.calculate_infrastructure_score(data)
        economic = self.calculate_economic_score(data)

        index_value = (
            shipping       * self.COMPONENT_WEIGHTS["shipping"] +
            trade          * self.COMPONENT_WEIGHTS["trade"] +
            infrastructure * self.COMPONENT_WEIGHTS["infrastructure"] +
            economic       * self.COMPONENT_WEIGHTS["economic"]
        )

        return {
            "shipping_score":       round(shipping, 4),
            "trade_score":          round(trade, 4),
            "infrastructure_score": round(infrastructure, 4),
            "economic_score":       round(economic, 4),
            "index_value":          round(index_value, 4),
        }
