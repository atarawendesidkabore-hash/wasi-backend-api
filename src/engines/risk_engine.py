"""
Country Risk Scoring Engine — multi-dimensional risk assessment for 16 ECOWAS countries.

Combines 5 risk dimensions:
  1. Trade Risk (30%)     — WASI trade scores, bilateral concentration, commodity dependency
  2. Macro Risk (25%)     — GDP, inflation, debt/GDP, current account
  3. Political Risk (20%) — active news events, ACLED conflict, governance signals
  4. Logistics Risk (15%) — port efficiency, transport composite, clearance delays
  5. Market Risk (10%)    — forecast uncertainty, WASI volatility, FX divergence

Output: 0–100 risk score (0 = lowest risk, 100 = highest risk)
"""

import logging
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc

from src.database.models import CountryIndex, Country

logger = logging.getLogger(__name__)

# ── Risk dimension weights ───────────────────────────────────────────
RISK_WEIGHTS = {
    "trade": 0.30,
    "macro": 0.25,
    "political": 0.20,
    "logistics": 0.15,
    "market": 0.10,
}

# ── Macro thresholds (based on ECOWAS convergence criteria) ─────────
# Higher values = higher risk.  Scores normalized 0–100.
MACRO_THRESHOLDS = {
    "inflation": {"low": 3.0, "high": 10.0},        # WAEMU target < 3%
    "debt_gdp": {"low": 40.0, "high": 70.0},         # ECOWAS limit 70%
    "current_account": {"low": -3.0, "high": -8.0},   # deficit threshold
    "gdp_growth": {"low": 5.0, "high": 0.0},          # inverted: low growth = high risk
    "unemployment": {"low": 5.0, "high": 20.0},
}

# ── ECOWAS countries ────────────────────────────────────────────────
ECOWAS_CODES = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG",
    "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]


class RiskEngine:
    """Multi-dimensional country risk scoring engine."""

    def __init__(self, db: Session):
        self.db = db

    # ── Public API ───────────────────────────────────────────────────

    def score_country(self, country_code: str) -> dict:
        """Compute full risk profile for a single country."""
        cc = country_code.upper()
        country = self.db.query(Country).filter(Country.code == cc).first()
        if not country:
            return {"error": f"Country {cc} not found", "country_code": cc}

        trade = self._trade_risk(cc, country.id)
        macro = self._macro_risk(cc)
        political = self._political_risk(cc, country.id)
        logistics = self._logistics_risk(cc, country.id)
        market = self._market_risk(cc, country.id)

        composite = (
            trade["score"] * RISK_WEIGHTS["trade"]
            + macro["score"] * RISK_WEIGHTS["macro"]
            + political["score"] * RISK_WEIGHTS["political"]
            + logistics["score"] * RISK_WEIGHTS["logistics"]
            + market["score"] * RISK_WEIGHTS["market"]
        )
        composite = round(min(100.0, max(0.0, composite)), 2)

        rating = self._risk_rating(composite)

        return {
            "country_code": cc,
            "country_name": country.name,
            "risk_score": composite,
            "risk_rating": rating,
            "dimensions": {
                "trade": trade,
                "macro": macro,
                "political": political,
                "logistics": logistics,
                "market": market,
            },
            "weights": RISK_WEIGHTS,
            "computed_at": date.today().isoformat(),
        }

    def score_all_countries(self) -> dict:
        """Risk scores for all 16 ECOWAS countries."""
        results = []
        for cc in ECOWAS_CODES:
            result = self.score_country(cc)
            if "error" not in result:
                results.append(result)

        if not results:
            return {"countries": [], "regional_risk": 0.0}

        avg_risk = round(sum(r["risk_score"] for r in results) / len(results), 2)
        max_risk = max(results, key=lambda r: r["risk_score"])
        min_risk = min(results, key=lambda r: r["risk_score"])

        return {
            "countries": results,
            "regional_risk": avg_risk,
            "regional_rating": self._risk_rating(avg_risk),
            "highest_risk": {"country": max_risk["country_code"], "score": max_risk["risk_score"]},
            "lowest_risk": {"country": min_risk["country_code"], "score": min_risk["risk_score"]},
            "computed_at": date.today().isoformat(),
        }

    def detect_anomalies(self, country_code: str, lookback_days: int = 30) -> dict:
        """Detect anomalies in recent data for a country."""
        cc = country_code.upper()
        country = self.db.query(Country).filter(Country.code == cc).first()
        if not country:
            return {"error": f"Country {cc} not found"}

        anomalies = []
        cutoff = date.today() - timedelta(days=lookback_days)

        # Check WASI index volatility
        indices = (
            self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id, CountryIndex.period_date >= cutoff)
            .order_by(CountryIndex.period_date)
            .all()
        )
        if len(indices) >= 5:
            values = [i.index_value for i in indices if i.index_value is not None]
            if len(values) >= 5:
                mean = sum(values) / len(values)
                std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) if len(values) > 1 else 0
                if std > 0:
                    latest = values[-1]
                    z_score = abs(latest - mean) / std
                    if z_score > 2.0:
                        anomalies.append({
                            "type": "WASI_INDEX_OUTLIER",
                            "severity": "HIGH" if z_score > 3.0 else "MEDIUM",
                            "detail": f"WASI index {latest:.1f} is {z_score:.1f}σ from {lookback_days}-day mean {mean:.1f}",
                            "z_score": round(z_score, 2),
                        })

                # Check for sudden drops
                if len(values) >= 2:
                    pct_change = (values[-1] - values[-2]) / values[-2] * 100 if values[-2] != 0 else 0
                    if abs(pct_change) > 15:
                        anomalies.append({
                            "type": "SUDDEN_INDEX_CHANGE",
                            "severity": "HIGH",
                            "detail": f"WASI index changed {pct_change:+.1f}% in one period",
                            "pct_change": round(pct_change, 2),
                        })

        # Check news event accumulation
        try:
            from src.database.models import NewsEvent
            active_events = (
                self.db.query(NewsEvent)
                .filter(
                    NewsEvent.country_code == cc,
                    NewsEvent.is_active == True,
                )
                .all()
            )
            negative_magnitude = sum(e.magnitude for e in active_events if e.magnitude < 0)
            if negative_magnitude < -15:
                anomalies.append({
                    "type": "EVENT_ACCUMULATION",
                    "severity": "HIGH",
                    "detail": f"{len(active_events)} active events with net magnitude {negative_magnitude}",
                    "net_magnitude": negative_magnitude,
                })
        except Exception as e:
            logger.warning("Anomaly detection: news event query failed for %s: %s", cc, e)

        # Check data staleness
        if indices:
            latest_date = max(i.period_date for i in indices)
            days_stale = (date.today() - latest_date).days
            if days_stale > 7:
                anomalies.append({
                    "type": "DATA_STALE",
                    "severity": "MEDIUM" if days_stale < 14 else "HIGH",
                    "detail": f"Latest WASI data is {days_stale} days old",
                    "days_stale": days_stale,
                })

        return {
            "country_code": cc,
            "lookback_days": lookback_days,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "computed_at": date.today().isoformat(),
        }

    def correlate_countries(self, country_a: str, country_b: str, lookback_days: int = 90) -> dict:
        """Compute correlation between two countries' WASI indices."""
        cc_a, cc_b = country_a.upper(), country_b.upper()

        c_a = self.db.query(Country).filter(Country.code == cc_a).first()
        c_b = self.db.query(Country).filter(Country.code == cc_b).first()
        if not c_a or not c_b:
            return {"error": "One or both countries not found"}

        cutoff = date.today() - timedelta(days=lookback_days)

        idx_a = {
            i.period_date: i.index_value
            for i in self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == c_a.id, CountryIndex.period_date >= cutoff)
            .all()
            if i.index_value is not None
        }
        idx_b = {
            i.period_date: i.index_value
            for i in self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == c_b.id, CountryIndex.period_date >= cutoff)
            .all()
            if i.index_value is not None
        }

        common_dates = sorted(set(idx_a.keys()) & set(idx_b.keys()))
        if len(common_dates) < 5:
            return {
                "country_a": cc_a,
                "country_b": cc_b,
                "correlation": None,
                "data_points": len(common_dates),
                "error": "Insufficient overlapping data points (need ≥5)",
            }

        vals_a = [idx_a[d] for d in common_dates]
        vals_b = [idx_b[d] for d in common_dates]

        corr = self._pearson(vals_a, vals_b)

        return {
            "country_a": cc_a,
            "country_b": cc_b,
            "correlation": round(corr, 4),
            "data_points": len(common_dates),
            "period_start": common_dates[0].isoformat(),
            "period_end": common_dates[-1].isoformat(),
            "interpretation": self._interpret_correlation(corr),
            "computed_at": date.today().isoformat(),
        }

    # ── Private: risk dimension calculators ──────────────────────────

    def _trade_risk(self, cc: str, country_id: int) -> dict:
        """Trade risk: low trade scores, commodity concentration, trade deficit."""
        score = 50.0  # neutral default
        factors = []

        # Latest WASI trade score (inverted: low trade = high risk)
        latest = (
            self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == country_id)
            .order_by(desc(CountryIndex.period_date))
            .first()
        )
        if latest and latest.trade_score is not None:
            trade_score = latest.trade_score
            # Invert: 100 trade_score = 0 risk, 0 trade_score = 100 risk
            score = 100.0 - trade_score
            factors.append(f"WASI trade score: {trade_score:.1f}")

        # Bilateral trade concentration
        try:
            from src.database.models import BilateralTrade
            trades = (
                self.db.query(BilateralTrade)
                .filter(BilateralTrade.country_code == cc)
                .order_by(desc(BilateralTrade.year))
                .limit(10)
                .all()
            )
            if trades:
                total = sum(t.total_trade_usd for t in trades if t.total_trade_usd)
                if total > 0:
                    max_partner = max(t.total_trade_usd for t in trades if t.total_trade_usd)
                    concentration = max_partner / total * 100
                    if concentration > 50:
                        score = min(100, score + 15)
                        factors.append(f"High trade concentration: {concentration:.0f}% with top partner")
        except Exception as e:
            logger.warning("Trade risk: bilateral trade query failed for %s: %s", cc, e)

        return {"score": round(min(100, max(0, score)), 2), "factors": factors}

    def _macro_risk(self, cc: str) -> dict:
        """Macro risk: inflation, debt, growth, current account."""
        score = 50.0
        factors = []

        try:
            from src.database.models import MacroIndicator
            latest = (
                self.db.query(MacroIndicator)
                .filter(MacroIndicator.country_code == cc, MacroIndicator.is_projection == False)
                .order_by(desc(MacroIndicator.year))
                .first()
            )
            if latest:
                sub_scores = []

                # Inflation risk
                if latest.inflation_pct is not None:
                    inf = latest.inflation_pct
                    inf_risk = self._normalize_risk(inf, 3.0, 10.0)
                    sub_scores.append(inf_risk)
                    factors.append(f"Inflation: {inf:.1f}%")

                # Debt/GDP risk
                if latest.debt_gdp_pct is not None:
                    debt = latest.debt_gdp_pct
                    debt_risk = self._normalize_risk(debt, 40.0, 70.0)
                    sub_scores.append(debt_risk)
                    factors.append(f"Debt/GDP: {debt:.1f}%")

                # GDP growth (inverted: low growth = high risk)
                if latest.gdp_growth_pct is not None:
                    gdp = latest.gdp_growth_pct
                    gdp_risk = self._normalize_risk(-gdp, -5.0, 0.0)
                    sub_scores.append(gdp_risk)
                    factors.append(f"GDP growth: {gdp:.1f}%")

                # Current account
                if latest.current_account_gdp_pct is not None:
                    ca = latest.current_account_gdp_pct
                    ca_risk = self._normalize_risk(-ca, 3.0, 8.0)
                    sub_scores.append(ca_risk)
                    factors.append(f"Current account: {ca:.1f}% of GDP")

                if sub_scores:
                    score = sum(sub_scores) / len(sub_scores)
        except Exception as e:
            logger.warning("Macro risk: indicator query failed for %s: %s", cc, e)

        return {"score": round(min(100, max(0, score)), 2), "factors": factors}

    def _political_risk(self, cc: str, country_id: int) -> dict:
        """Political risk: active negative events, conflict signals."""
        score = 30.0  # baseline: moderate
        factors = []

        try:
            from src.database.models import NewsEvent
            active = (
                self.db.query(NewsEvent)
                .filter(NewsEvent.country_code == cc, NewsEvent.is_active == True)
                .all()
            )
            if active:
                neg_count = sum(1 for e in active if e.magnitude < 0)
                neg_magnitude = sum(e.magnitude for e in active if e.magnitude < 0)

                # Each negative event adds risk
                score += neg_count * 8
                score += abs(neg_magnitude) * 1.5

                if neg_count > 0:
                    factors.append(f"{neg_count} negative events (magnitude: {neg_magnitude})")

                # Political risk events are worse
                political = [e for e in active if e.event_type == "POLITICAL_RISK"]
                if political:
                    score += len(political) * 10
                    factors.append(f"{len(political)} active political risk events")
        except Exception as e:
            logger.warning("Political risk: news event query failed for %s: %s", cc, e)

        return {"score": round(min(100, max(0, score)), 2), "factors": factors}

    def _logistics_risk(self, cc: str, country_id: int) -> dict:
        """Logistics risk: port efficiency, infrastructure score, dwell times."""
        score = 50.0
        factors = []

        latest = (
            self.db.query(CountryIndex)
            .filter(CountryIndex.country_id == country_id)
            .order_by(desc(CountryIndex.period_date))
            .first()
        )
        if latest:
            # Infrastructure score (inverted)
            if latest.infrastructure_score is not None:
                infra = latest.infrastructure_score
                score = 100.0 - infra
                factors.append(f"Infrastructure score: {infra:.1f}")

            # Port efficiency
            if latest.port_efficiency_score is not None:
                pe = latest.port_efficiency_score
                pe_risk = 100.0 - pe
                score = (score + pe_risk) / 2
                factors.append(f"Port efficiency: {pe:.1f}")

            # Dwell time
            if latest.dwell_time_days is not None:
                dwell = latest.dwell_time_days
                dwell_risk = self._normalize_risk(dwell, 3.0, 14.0)
                score = (score + dwell_risk) / 2
                factors.append(f"Dwell time: {dwell:.1f} days")

        return {"score": round(min(100, max(0, score)), 2), "factors": factors}

    def _market_risk(self, cc: str, country_id: int) -> dict:
        """Market risk: forecast uncertainty, WASI volatility."""
        score = 40.0  # moderate default
        factors = []

        # Check forecast uncertainty
        try:
            from src.database.forecast_models import ForecastResult
            forecasts = (
                self.db.query(ForecastResult)
                .filter(
                    ForecastResult.target_type == "COUNTRY_INDEX",
                    ForecastResult.target_code == cc,
                )
                .order_by(desc(ForecastResult.calculated_at))
                .limit(3)
                .all()
            )
            if forecasts:
                avg_residual = sum(f.residual_std for f in forecasts if f.residual_std) / max(1, len(forecasts))
                if avg_residual > 10:
                    score += 20
                    factors.append(f"High forecast uncertainty (σ={avg_residual:.1f})")
                elif avg_residual > 5:
                    score += 10
                    factors.append(f"Moderate forecast uncertainty (σ={avg_residual:.1f})")

                avg_conf = sum(f.confidence for f in forecasts if f.confidence) / max(1, len(forecasts))
                if avg_conf < 0.5:
                    score += 15
                    factors.append(f"Low forecast confidence ({avg_conf:.2f})")
        except Exception as e:
            logger.warning("Market risk: forecast query failed for %s: %s", cc, e)

        # WASI index recent volatility
        cutoff = date.today() - timedelta(days=30)
        indices = (
            self.db.query(CountryIndex.index_value)
            .filter(
                CountryIndex.country_id == country_id,
                CountryIndex.period_date >= cutoff,
            )
            .all()
        )
        values = [i[0] for i in indices if i[0] is not None]
        if len(values) >= 3:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            cv = (math.sqrt(variance) / mean * 100) if mean > 0 else 0
            if cv > 15:
                score += 15
                factors.append(f"High WASI volatility (CV={cv:.1f}%)")
            elif cv > 8:
                score += 8
                factors.append(f"Moderate WASI volatility (CV={cv:.1f}%)")

        return {"score": round(min(100, max(0, score)), 2), "factors": factors}

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_risk(value: float, low: float, high: float) -> float:
        """Normalize a value to 0–100 risk scale between low (0 risk) and high (100 risk)."""
        if high == low:
            return 50.0
        ratio = (value - low) / (high - low)
        return min(100.0, max(0.0, ratio * 100.0))

    @staticmethod
    def _risk_rating(score: float) -> str:
        """Convert numeric risk score to letter rating."""
        if score < 20:
            return "LOW"
        elif score < 40:
            return "MODERATE"
        elif score < 60:
            return "ELEVATED"
        elif score < 80:
            return "HIGH"
        else:
            return "CRITICAL"

    @staticmethod
    def _pearson(x: list, y: list) -> float:
        """Pearson correlation coefficient."""
        n = len(x)
        if n < 2:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (std_x * std_y)

    @staticmethod
    def _interpret_correlation(corr: float) -> str:
        """Human-readable correlation interpretation."""
        abs_c = abs(corr)
        direction = "positive" if corr > 0 else "negative"
        if abs_c < 0.2:
            return "Negligible correlation"
        elif abs_c < 0.4:
            return f"Weak {direction} correlation"
        elif abs_c < 0.6:
            return f"Moderate {direction} correlation"
        elif abs_c < 0.8:
            return f"Strong {direction} correlation"
        else:
            return f"Very strong {direction} correlation"
