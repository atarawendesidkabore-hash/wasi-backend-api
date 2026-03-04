"""
Scenario Engine — what-if analysis for WASI forecasts.

Pre-built scenarios based on ECOWAS economic patterns:
  1. OIL_SHOCK:        Brent drops 30% over 3 months
  2. PORT_DISRUPTION:  Major port shutdown (NG/CI) for 2 months
  3. COCOA_BOOM:       Cocoa prices surge 25% over 6 months
  4. POLITICAL_CRISIS: Country-specific -20pt shock with 6-month decay
  5. CUSTOM:           User-defined shocks to any variable

Shocks propagate through the multivariate model when available.
"""
import json
import logging
import math
import uuid
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class ScenarioEngine:
    """What-if scenario analysis for WASI forecasts."""

    PRESET_SCENARIOS = {
        "oil_shock": {
            "name": "Brent Oil Price Shock",
            "description": "Brent crude drops 30% over 3 months",
            "shocks": {
                "commodity_BRENT": {
                    "type": "pct_change",
                    "value": -30.0,
                    "months": 3,
                },
            },
            "affected_countries": {"NG": 0.7, "GH": 0.2, "CI": 0.1},
        },
        "port_disruption": {
            "name": "Major Port Disruption (Nigeria)",
            "description": "Lagos/Apapa port disruption for 2 months",
            "shocks": {
                "country_NG_shipping": {
                    "type": "abs_change",
                    "value": -40.0,
                    "months": 2,
                },
            },
            "affected_countries": {"NG": 1.0, "BJ": 0.3, "NE": 0.2},
        },
        "cocoa_boom": {
            "name": "Cocoa Price Boom",
            "description": "Cocoa prices surge 25% over 6 months",
            "shocks": {
                "commodity_COCOA": {
                    "type": "pct_change",
                    "value": 25.0,
                    "months": 6,
                },
            },
            "affected_countries": {"CI": 0.6, "GH": 0.3},
        },
        "political_crisis": {
            "name": "Political Instability",
            "description": "Political crisis in target country, -20pt WASI shock with decay",
            "shocks": {
                "country_TARGET_index": {
                    "type": "abs_change",
                    "value": -20.0,
                    "months": 6,
                    "decay": 0.85,
                },
            },
        },
        "gold_rally": {
            "name": "Gold Price Rally",
            "description": "Gold prices surge 20% over 4 months",
            "shocks": {
                "commodity_GOLD": {
                    "type": "pct_change",
                    "value": 20.0,
                    "months": 4,
                },
            },
            "affected_countries": {"ML": 0.4, "BF": 0.3, "GN": 0.2},
        },
    }

    def run_scenario(
        self,
        baseline_periods: List[dict],
        scenario_type: str,
        target_code: Optional[str] = None,
        custom_shocks: Optional[dict] = None,
        horizon_months: int = 12,
    ) -> dict:
        """
        Compute scenario-adjusted forecast.

        Args:
            baseline_periods: list of baseline forecast period dicts
                [{"period_offset": 1, "forecast_value": 52.3, ...}, ...]
            scenario_type: preset name or "custom"
            target_code: country code (required for political_crisis)
            custom_shocks: user-defined shocks for "custom" type
            horizon_months: forecast horizon

        Returns:
            {
                "scenario_id": str,
                "scenario_name": str,
                "scenario_type": str,
                "description": str,
                "baseline_periods": [...],
                "scenario_periods": [...],
                "impact_delta": [...],
                "impact_summary": {
                    "max_negative_impact": float,
                    "max_positive_impact": float,
                    "avg_impact": float,
                    "recovery_month": int or None,
                },
            }
        """
        scenario_id = str(uuid.uuid4())

        if scenario_type == "custom":
            if not custom_shocks:
                return self._error_result(scenario_id, "Custom shocks required")
            scenario_def = {
                "name": "Custom Scenario",
                "description": "User-defined shock scenario",
                "shocks": custom_shocks,
                "affected_countries": {},
            }
        else:
            scenario_def = self.PRESET_SCENARIOS.get(scenario_type)
            if not scenario_def:
                return self._error_result(
                    scenario_id, f"Unknown scenario type: {scenario_type}"
                )
            # Deep copy to avoid mutation
            scenario_def = {**scenario_def, "shocks": {**scenario_def["shocks"]}}

        # For political_crisis, replace TARGET with actual country
        if scenario_type == "political_crisis" and target_code:
            shocks = {}
            for key, shock in scenario_def["shocks"].items():
                new_key = key.replace("TARGET", target_code)
                shocks[new_key] = shock
            scenario_def["shocks"] = shocks
            if "affected_countries" not in scenario_def:
                scenario_def["affected_countries"] = {}
            scenario_def["affected_countries"][target_code] = 1.0

        # Compute shock trajectory
        shock_trajectory = self._compute_shock_trajectory(
            scenario_def["shocks"], horizon_months,
        )

        # Apply to baseline
        scenario_periods = []
        impact_delta = []
        for period in baseline_periods[:horizon_months]:
            offset = period.get("period_offset", 1)
            base_val = period.get("forecast_value", 0.0)

            if offset - 1 < len(shock_trajectory):
                shock = shock_trajectory[offset - 1]
            else:
                shock = 0.0

            # Apply affected_countries weighting if this is a country-specific forecast
            affected = scenario_def.get("affected_countries", {})
            if target_code and affected:
                country_weight = affected.get(target_code, 0.1)
                shock *= country_weight

            scenario_val = base_val + shock
            delta = shock

            scenario_period = {**period, "forecast_value": round(scenario_val, 4)}
            scenario_periods.append(scenario_period)
            impact_delta.append(round(delta, 4))

        # Impact summary
        if impact_delta:
            neg_impacts = [d for d in impact_delta if d < 0]
            pos_impacts = [d for d in impact_delta if d > 0]
            recovery_month = None
            for i, d in enumerate(impact_delta):
                if abs(d) < 1.0:  # within 1 point of baseline
                    recovery_month = i + 1
                    break

            summary = {
                "max_negative_impact": round(min(impact_delta), 4),
                "max_positive_impact": round(max(impact_delta), 4),
                "avg_impact": round(sum(impact_delta) / len(impact_delta), 4),
                "recovery_month": recovery_month,
            }
        else:
            summary = {
                "max_negative_impact": 0.0,
                "max_positive_impact": 0.0,
                "avg_impact": 0.0,
                "recovery_month": None,
            }

        return {
            "scenario_id": scenario_id,
            "scenario_name": scenario_def.get("name", scenario_type),
            "scenario_type": scenario_type,
            "description": scenario_def.get("description", ""),
            "baseline_periods": baseline_periods[:horizon_months],
            "scenario_periods": scenario_periods,
            "impact_delta": impact_delta,
            "impact_summary": summary,
        }

    def _compute_shock_trajectory(
        self,
        shocks: dict,
        horizon: int,
    ) -> np.ndarray:
        """
        Compute the combined shock trajectory over the horizon.

        Each shock can be:
          - pct_change: percentage change applied linearly over 'months'
          - abs_change: absolute index point change, optionally with decay
        """
        trajectory = np.zeros(horizon)

        for key, shock in shocks.items():
            shock_type = shock.get("type", "abs_change")
            value = shock.get("value", 0.0)
            months = shock.get("months", horizon)
            decay = shock.get("decay", 1.0)

            if shock_type == "pct_change":
                # Linear ramp of percentage change, then hold
                for h in range(horizon):
                    if h < months:
                        # Linearly ramp to full value
                        fraction = (h + 1) / months
                        trajectory[h] += value * fraction
                    else:
                        # Hold at full value, then decay
                        periods_past = h - months
                        trajectory[h] += value * (decay ** periods_past)

            elif shock_type == "abs_change":
                for h in range(horizon):
                    if h < months:
                        # Full shock during active period
                        if decay < 1.0:
                            trajectory[h] += value * (decay ** h)
                        else:
                            trajectory[h] += value
                    else:
                        # Decay after active period
                        periods_past = h - months + 1
                        trajectory[h] += value * (decay ** periods_past)

        return trajectory

    def _error_result(self, scenario_id: str, error: str) -> dict:
        """Return error result dict."""
        return {
            "scenario_id": scenario_id,
            "scenario_name": "Error",
            "scenario_type": "error",
            "description": error,
            "baseline_periods": [],
            "scenario_periods": [],
            "impact_delta": [],
            "impact_summary": {},
            "error": error,
        }

    def list_presets(self) -> List[dict]:
        """Return list of available preset scenarios for API response."""
        presets = []
        for key, scenario in self.PRESET_SCENARIOS.items():
            presets.append({
                "scenario_type": key,
                "name": scenario["name"],
                "description": scenario["description"],
                "requires_target_code": key == "political_crisis",
            })
        return presets
