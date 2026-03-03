from typing import Dict, List, Optional
from datetime import timezone, date, datetime
import numpy as np
from sqlalchemy.orm import Session


class CompositeEngine:
    """
    Calculates the WASI Composite Index from per-country index scores.

    Formula: WASI_Composite = Σ(Country_Index_i × Weight_i)

    16 ECOWAS-focused West African countries, weights summing to exactly 1.0:
      Primary   (75%): NG 28%, CI 22%, GH 15%, SN 10%
      Secondary (20%): BF 4%, ML 4%, GN 4%, BJ 3%, TG 3%
      Tertiary   (5%): NE 1%, MR 1%, GW 1%, SL 1%, LR 1%, GM 1%, CV 1%
    """

    COUNTRY_WEIGHTS: Dict[str, float] = {
        # Primary Tier (75%)
        "NG": 0.28,  # Nigeria
        "CI": 0.22,  # Côte d'Ivoire
        "GH": 0.15,  # Ghana
        "SN": 0.10,  # Senegal
        # Secondary Tier (20%)
        "BF": 0.04,  # Burkina Faso
        "ML": 0.04,  # Mali
        "GN": 0.04,  # Guinea
        "BJ": 0.03,  # Benin
        "TG": 0.03,  # Togo
        # Tertiary Tier (5%)
        "NE": 0.01,  # Niger
        "MR": 0.01,  # Mauritania
        "GW": 0.01,  # Guinea-Bissau
        "SL": 0.01,  # Sierra Leone
        "LR": 0.01,  # Liberia
        "GM": 0.01,  # Gambia
        "CV": 0.01,  # Cabo Verde
    }

    def __init__(self):
        total = sum(self.COUNTRY_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights must sum to 1.0, got {total}"

    def calculate_composite(
        self,
        country_indices: Dict[str, float],
        period_date: date,
        history: Optional[List[float]] = None,
    ) -> Dict:
        """
        Calculate the WASI composite index.

        Args:
            country_indices: {country_code: index_value} for available countries.
                             Missing countries are excluded; weights are re-normalized.
            period_date: The period this composite belongs to.
            history: Previous composite values (oldest first) for volatility metrics.

        Returns:
            Dict with composite_value, trend, volatility metrics, and contributions.
        """
        available = {
            code: val
            for code, val in country_indices.items()
            if code in self.COUNTRY_WEIGHTS
        }

        if not available:
            raise ValueError("No valid WASI country codes in provided indices")

        total_available_weight = sum(self.COUNTRY_WEIGHTS[c] for c in available)

        composite_value = sum(
            val * (self.COUNTRY_WEIGHTS[code] / total_available_weight)
            for code, val in available.items()
        )

        contributions = {
            code: round(val * (self.COUNTRY_WEIGHTS[code] / total_available_weight), 4)
            for code, val in available.items()
        }

        result = {
            "period_date":               period_date,
            "composite_value":           round(composite_value, 4),
            "countries_included":        len(available),
            "country_contributions":     contributions,
            "std_dev":                   None,
            "annualized_volatility":     None,
            "sharpe_ratio":              None,
            "max_drawdown":              None,
            "coefficient_of_variation":  None,
            "mom_change":                None,
            "yoy_change":                None,
            "trend_direction":           "flat",
        }

        if history and len(history) >= 2:
            result.update(self._calculate_volatility(composite_value, history))

        return result

    def _calculate_volatility(self, current: float, history: List[float]) -> Dict:
        series = np.array(history + [current], dtype=float)
        returns = np.diff(series) / np.where(series[:-1] != 0, series[:-1], 1e-9)

        std_dev = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
        annualized_vol = std_dev * np.sqrt(12)

        mean_return = float(np.mean(returns))
        sharpe = mean_return / std_dev if std_dev > 0 else 0.0

        # Max drawdown: largest peak-to-trough percentage decline
        peak = series[0]
        max_dd = 0.0
        for val in series[1:]:
            if val > peak:
                peak = val
            if peak > 0:
                drawdown = (peak - val) / peak
                if drawdown > max_dd:
                    max_dd = drawdown

        cv = abs(std_dev / mean_return) if mean_return != 0 else 0.0

        mom_change = (
            (current - history[-1]) / history[-1] * 100
            if history[-1] != 0 else None
        )
        yoy_change = None
        if len(history) >= 12 and history[-12] != 0:
            yoy_change = (current - history[-12]) / history[-12] * 100

        trend = "flat"
        if mom_change is not None:
            trend = "up" if mom_change > 0.5 else ("down" if mom_change < -0.5 else "flat")

        return {
            "std_dev":                   round(std_dev, 6),
            "annualized_volatility":     round(annualized_vol, 6),
            "sharpe_ratio":              round(sharpe, 4),
            "max_drawdown":              round(max_dd, 4),
            "coefficient_of_variation":  round(cv, 4),
            "mom_change":                round(mom_change, 4) if mom_change is not None else None,
            "yoy_change":                round(yoy_change, 4) if yoy_change is not None else None,
            "trend_direction":           trend,
        }

    def generate_report(
        self,
        latest_composite,
        history: List,
        contributions: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """Assemble the full composite report."""
        return {
            "latest": latest_composite,
            "history_12m": history[-12:] if len(history) > 12 else history,
            "country_contributions": contributions or {},
            "generated_at": datetime.now(timezone.utc),
        }
