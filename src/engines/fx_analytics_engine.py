"""
FX Analytics Engine — Market analytics for ECOWAS currency regimes.

Provides volatility measurement, regime divergence analysis,
and bilateral trade cost impact calculation.
Separate from CbdcFxEngine (which handles CBDC payment conversions).
"""
import math
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.database.fx_models import FxDailyRate, FxVolatility
from src.engines.cbdc_fx_engine import COUNTRY_CURRENCY, SPREAD_TIERS

logger = logging.getLogger(__name__)

# ── Zone classification ──────────────────────────────────────────────────

CFA_ZONE = {"CI", "SN", "BF", "ML", "BJ", "TG", "NE", "GW"}
FLOATING_ZONE = {"NG", "GH", "GM", "SL", "LR", "GN"}
SPECIAL_ZONE = {"CV", "MR"}  # CVE pegged to EUR, MRU managed float

REGIME_MAP = {
    "XOF": "PEGGED", "CVE": "PEGGED",
    "MRU": "MANAGED",
    "NGN": "FLOATING", "GHS": "FLOATING", "GMD": "FLOATING",
    "GNF": "FLOATING", "SLE": "FLOATING", "LRD": "FLOATING",
}

CURRENCY_COUNTRIES = {
    "XOF": ["CI", "SN", "BF", "ML", "BJ", "TG", "NE", "GW"],
    "NGN": ["NG"], "GHS": ["GH"], "GMD": ["GM"], "GNF": ["GN"],
    "SLE": ["SL"], "LRD": ["LR"], "MRU": ["MR"], "CVE": ["CV"],
}

ALL_CURRENCIES = list(REGIME_MAP.keys())

# WASI weights (from CompositeEngine)
WASI_WEIGHTS = {
    "NG": 0.28, "CI": 0.22, "GH": 0.15, "SN": 0.10,
    "BF": 0.04, "ML": 0.04, "GN": 0.04, "BJ": 0.03, "TG": 0.03,
    "NE": 0.01, "MR": 0.01, "GW": 0.01, "SL": 0.01,
    "LR": 0.01, "GM": 0.01, "CV": 0.01,
}


class FxAnalyticsEngine:
    """FX market analytics engine for ECOWAS currencies."""

    def __init__(self, db: Session):
        self.db = db

    # ── Current Rates ────────────────────────────────────────────────

    def get_current_rates(self) -> list[dict]:
        """Get latest rate for each ECOWAS currency."""
        rates = []
        for cc in ALL_CURRENCIES:
            row = (
                self.db.query(FxDailyRate)
                .filter(FxDailyRate.currency_code == cc)
                .order_by(desc(FxDailyRate.rate_date))
                .first()
            )
            if row:
                rates.append({
                    "currency_code": cc,
                    "rate_to_usd": float(row.rate_to_usd),
                    "rate_to_eur": float(row.rate_to_eur) if row.rate_to_eur else None,
                    "rate_to_xof": float(row.rate_to_xof) if row.rate_to_xof else None,
                    "pct_change_1d": row.pct_change_1d,
                    "pct_change_7d": row.pct_change_7d,
                    "pct_change_30d": row.pct_change_30d,
                    "regime": REGIME_MAP.get(cc, "FLOATING"),
                    "rate_date": row.rate_date,
                    "data_source": row.data_source or "unknown",
                    "confidence": row.confidence or 1.0,
                })
        return rates

    # ── Currency Profile ─────────────────────────────────────────────

    def get_currency_profile(self, currency_code: str) -> Optional[dict]:
        """Deep dive on a single currency: rate, volatility, trend."""
        cc = currency_code.upper()
        if cc not in REGIME_MAP:
            return None

        latest = (
            self.db.query(FxDailyRate)
            .filter(FxDailyRate.currency_code == cc)
            .order_by(desc(FxDailyRate.rate_date))
            .first()
        )
        if not latest:
            return None

        vol = (
            self.db.query(FxVolatility)
            .filter(FxVolatility.currency_code == cc)
            .order_by(desc(FxVolatility.period_end))
            .first()
        )

        return {
            "currency_code": cc,
            "regime": REGIME_MAP.get(cc, "FLOATING"),
            "trend": vol.trend if vol else "STABLE",
            "latest_rate_usd": float(latest.rate_to_usd),
            "latest_rate_eur": float(latest.rate_to_eur) if latest.rate_to_eur else None,
            "latest_rate_xof": float(latest.rate_to_xof) if latest.rate_to_xof else None,
            "rate_date": latest.rate_date,
            "volatility_7d": vol.volatility_7d if vol else None,
            "volatility_30d": vol.volatility_30d if vol else None,
            "volatility_90d": vol.volatility_90d if vol else None,
            "annualized_vol": vol.annualized_vol if vol else None,
            "max_drawdown_pct": vol.max_drawdown_pct if vol else None,
            "pct_change_1d": latest.pct_change_1d,
            "pct_change_7d": latest.pct_change_7d,
            "pct_change_30d": latest.pct_change_30d,
            "countries": CURRENCY_COUNTRIES.get(cc, []),
        }

    # ── Rate History ─────────────────────────────────────────────────

    def get_rate_history(self, currency_code: str, days: int = 30) -> list[dict]:
        """Get historical daily rates for a currency."""
        cc = currency_code.upper()
        cutoff = date.today() - timedelta(days=days)
        rows = (
            self.db.query(FxDailyRate)
            .filter(FxDailyRate.currency_code == cc,
                    FxDailyRate.rate_date >= cutoff)
            .order_by(FxDailyRate.rate_date.desc())
            .all()
        )
        return [
            {
                "rate_date": r.rate_date,
                "rate_to_usd": float(r.rate_to_usd),
                "rate_to_eur": float(r.rate_to_eur) if r.rate_to_eur else None,
                "rate_to_xof": float(r.rate_to_xof) if r.rate_to_xof else None,
                "pct_change_1d": r.pct_change_1d,
            }
            for r in rows
        ]

    # ── Volatility ───────────────────────────────────────────────────

    def _compute_vol_window(self, currency_code: str, window_days: int) -> Optional[float]:
        """Compute annualized volatility from daily log returns over a window."""
        cutoff = date.today() - timedelta(days=window_days + 5)
        rows = (
            self.db.query(FxDailyRate.rate_to_usd, FxDailyRate.rate_date)
            .filter(FxDailyRate.currency_code == currency_code,
                    FxDailyRate.rate_date >= cutoff)
            .order_by(FxDailyRate.rate_date.asc())
            .all()
        )
        if len(rows) < 3:
            return None

        rates = [float(r.rate_to_usd) for r in rows if r.rate_to_usd and r.rate_to_usd > 0]
        if len(rates) < 3:
            return None

        log_returns = []
        for i in range(1, len(rates)):
            if rates[i - 1] > 0:
                log_returns.append(math.log(rates[i] / rates[i - 1]))

        if len(log_returns) < 2:
            return None

        mean = sum(log_returns) / len(log_returns)
        variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
        daily_vol = math.sqrt(variance)
        annualized = daily_vol * math.sqrt(252)
        return round(annualized, 6)

    def compute_volatility(self, currency_code: str) -> dict:
        """Compute and store volatility metrics for a currency."""
        cc = currency_code.upper()
        today = date.today()

        vol_7d = self._compute_vol_window(cc, 7)
        vol_30d = self._compute_vol_window(cc, 30)
        vol_90d = self._compute_vol_window(cc, 90)
        ann = vol_30d  # Use 30d as primary annualized measure

        # Max drawdown
        drawdown = self._compute_max_drawdown(cc, 30)

        # Trend from 30d price movement
        trend = self._compute_trend(cc, 30)

        regime = REGIME_MAP.get(cc, "FLOATING")

        # Upsert FxVolatility
        existing = (
            self.db.query(FxVolatility)
            .filter(FxVolatility.currency_code == cc,
                    FxVolatility.period_end == today)
            .first()
        )
        if existing:
            existing.volatility_7d = vol_7d
            existing.volatility_30d = vol_30d
            existing.volatility_90d = vol_90d
            existing.annualized_vol = ann
            existing.max_drawdown_pct = drawdown
            existing.trend = trend
            existing.regime = regime
        else:
            self.db.add(FxVolatility(
                currency_code=cc,
                period_start=today - timedelta(days=30),
                period_end=today,
                volatility_7d=vol_7d,
                volatility_30d=vol_30d,
                volatility_90d=vol_90d,
                annualized_vol=ann,
                max_drawdown_pct=drawdown,
                trend=trend,
                regime=regime,
            ))

        return {
            "currency_code": cc,
            "regime": regime,
            "volatility_7d": vol_7d,
            "volatility_30d": vol_30d,
            "volatility_90d": vol_90d,
            "annualized_vol": ann,
            "max_drawdown_pct": drawdown,
            "trend": trend,
        }

    def _compute_max_drawdown(self, currency_code: str, days: int) -> Optional[float]:
        """Max peak-to-trough drop in USD rate over the window."""
        cutoff = date.today() - timedelta(days=days + 5)
        rows = (
            self.db.query(FxDailyRate.rate_to_usd)
            .filter(FxDailyRate.currency_code == currency_code,
                    FxDailyRate.rate_date >= cutoff)
            .order_by(FxDailyRate.rate_date.asc())
            .all()
        )
        rates = [float(r.rate_to_usd) for r in rows if r.rate_to_usd and r.rate_to_usd > 0]
        if len(rates) < 2:
            return None

        peak = rates[0]
        max_dd = 0.0
        for r in rates[1:]:
            if r > peak:
                peak = r
            dd = (peak - r) / peak * 100.0 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    def _compute_trend(self, currency_code: str, days: int) -> str:
        """Determine price trend over window."""
        cutoff = date.today() - timedelta(days=days + 5)
        rows = (
            self.db.query(FxDailyRate.rate_to_usd, FxDailyRate.rate_date)
            .filter(FxDailyRate.currency_code == currency_code,
                    FxDailyRate.rate_date >= cutoff)
            .order_by(FxDailyRate.rate_date.asc())
            .all()
        )
        rates = [float(r.rate_to_usd) for r in rows if r.rate_to_usd and r.rate_to_usd > 0]
        if len(rates) < 2:
            return "STABLE"

        change_pct = (rates[-1] - rates[0]) / rates[0] * 100.0 if rates[0] > 0 else 0
        # For currencies quoted as units-per-USD: increase = depreciation
        if change_pct > 2.0:
            return "DEPRECIATING"
        elif change_pct < -2.0:
            return "APPRECIATING"
        return "STABLE"

    def recompute_all_volatility(self) -> dict:
        """Recompute volatility for all 9 currencies."""
        results = []
        for cc in ALL_CURRENCIES:
            try:
                result = self.compute_volatility(cc)
                results.append(result)
            except Exception as exc:
                logger.warning("Volatility compute failed for %s: %s", cc, exc)
        return {"currencies_computed": len(results), "results": results}

    # ── Trade Cost ───────────────────────────────────────────────────

    def compute_trade_cost(self, from_country: str, to_country: str,
                           amount_usd: float = 100_000.0) -> dict:
        """Compute FX cost for bilateral trade between two ECOWAS countries."""
        from_cc = from_country.upper()
        to_cc = to_country.upper()
        from_cur = COUNTRY_CURRENCY.get(from_cc, "XOF")
        to_cur = COUNTRY_CURRENCY.get(to_cc, "XOF")

        same_zone = from_cur == to_cur

        if same_zone:
            return {
                "from_country": from_cc,
                "to_country": to_cc,
                "from_currency": from_cur,
                "to_currency": to_cur,
                "amount_usd": amount_usd,
                "spread_cost_usd": 0.0,
                "volatility_premium_usd": 0.0,
                "total_fx_cost_usd": 0.0,
                "fx_cost_pct": 0.0,
                "same_currency_zone": True,
                "settlement_risk": "LOW",
            }

        # Spread costs
        spread_from = SPREAD_TIERS.get(from_cur, 0.0) if from_cur != "XOF" else 0.0
        spread_to = SPREAD_TIERS.get(to_cur, 0.0) if to_cur != "XOF" else 0.0
        total_spread = spread_from + spread_to
        spread_cost = amount_usd * total_spread

        # Volatility premium: vol × √(settlement_days / 252)
        SETTLEMENT_DAYS = 3
        vol_factor = math.sqrt(SETTLEMENT_DAYS / 252.0)
        vol_from = self._get_annualized_vol(from_cur) if from_cur != "XOF" else 0.0
        vol_to = self._get_annualized_vol(to_cur) if to_cur != "XOF" else 0.0
        combined_vol = max(vol_from, vol_to)
        vol_premium = amount_usd * combined_vol * vol_factor if combined_vol else 0.0

        total_cost = spread_cost + vol_premium
        cost_pct = round(total_cost / amount_usd * 100.0, 4) if amount_usd > 0 else 0

        # Settlement risk
        if combined_vol and combined_vol > 0.20:
            risk = "HIGH"
        elif combined_vol and combined_vol > 0.10:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return {
            "from_country": from_cc,
            "to_country": to_cc,
            "from_currency": from_cur,
            "to_currency": to_cur,
            "amount_usd": amount_usd,
            "spread_cost_usd": round(spread_cost, 2),
            "volatility_premium_usd": round(vol_premium, 2),
            "total_fx_cost_usd": round(total_cost, 2),
            "fx_cost_pct": cost_pct,
            "same_currency_zone": False,
            "settlement_risk": risk,
        }

    def _get_annualized_vol(self, currency_code: str) -> float:
        """Get latest annualized volatility for a currency."""
        vol = (
            self.db.query(FxVolatility)
            .filter(FxVolatility.currency_code == currency_code)
            .order_by(desc(FxVolatility.period_end))
            .first()
        )
        return vol.annualized_vol if vol and vol.annualized_vol else 0.0

    # ── Regime Divergence ────────────────────────────────────────────

    def get_regime_divergence(self) -> dict:
        """Compare CFA zone stability vs floating currency volatility."""
        cfa_vols = []
        floating_vols = []
        special_vols = []

        for cc in ALL_CURRENCIES:
            vol = self._get_annualized_vol(cc)
            regime = REGIME_MAP.get(cc, "FLOATING")
            if regime == "PEGGED":
                cfa_vols.append(vol)
            elif regime == "MANAGED":
                special_vols.append(vol)
            else:
                floating_vols.append(vol)

        avg_cfa = sum(cfa_vols) / len(cfa_vols) if cfa_vols else 0
        avg_floating = sum(floating_vols) / len(floating_vols) if floating_vols else 0
        avg_special = sum(special_vols) / len(special_vols) if special_vols else 0

        divergence = round(avg_floating / avg_cfa, 2) if avg_cfa > 0.001 else None

        if divergence is None:
            interp = "Insufficient data to compute regime divergence."
        elif divergence > 10:
            interp = (f"Floating currencies are {divergence}x more volatile than CFA zone. "
                      "Cross-zone trade carries significant FX risk.")
        elif divergence > 3:
            interp = (f"Floating currencies are {divergence}x more volatile than CFA zone. "
                      "Moderate FX risk for cross-zone trade.")
        else:
            interp = "Low divergence between currency regimes."

        return {
            "cfa_zone": {
                "zone_name": "CFA Franc (BCEAO)",
                "currencies": ["XOF", "CVE"],
                "countries": sorted(CFA_ZONE | {"CV"}),
                "avg_annualized_vol": round(avg_cfa, 6) if avg_cfa else None,
                "avg_30d_vol": None,
            },
            "floating_zone": {
                "zone_name": "Floating Currencies",
                "currencies": ["NGN", "GHS", "GMD", "GNF", "SLE", "LRD"],
                "countries": sorted(FLOATING_ZONE),
                "avg_annualized_vol": round(avg_floating, 6) if avg_floating else None,
                "avg_30d_vol": None,
            },
            "special_zone": {
                "zone_name": "Managed Float",
                "currencies": ["MRU"],
                "countries": sorted(SPECIAL_ZONE),
                "avg_annualized_vol": round(avg_special, 6) if avg_special else None,
                "avg_30d_vol": None,
            },
            "divergence_ratio": divergence,
            "interpretation": interp,
        }

    # ── ECOWAS Dashboard ────────────────────────────────────────────

    def get_ecowas_fx_dashboard(self) -> dict:
        """16-country FX analytics dashboard with WASI-weighted risk."""
        countries = []
        weighted_risk_sum = 0.0

        # Pre-fetch all latest rates by currency
        rate_cache = {}
        for cc in ALL_CURRENCIES:
            row = (
                self.db.query(FxDailyRate)
                .filter(FxDailyRate.currency_code == cc)
                .order_by(desc(FxDailyRate.rate_date))
                .first()
            )
            if row:
                rate_cache[cc] = row

        for country_code in sorted(WASI_WEIGHTS.keys()):
            currency = COUNTRY_CURRENCY.get(country_code, "XOF")
            regime = REGIME_MAP.get(currency, "FLOATING")
            weight = WASI_WEIGHTS.get(country_code, 0.0)

            rate_row = rate_cache.get(currency)
            rate_usd = float(rate_row.rate_to_usd) if rate_row else None
            pct_1d = rate_row.pct_change_1d if rate_row else None

            ann_vol = self._get_annualized_vol(currency)

            # FX risk score: 0 for pegged, scaled from volatility for floating
            if regime == "PEGGED":
                fx_risk = 0.0
            elif regime == "MANAGED":
                fx_risk = min(100.0, ann_vol * 200) if ann_vol else 15.0
            else:
                fx_risk = min(100.0, ann_vol * 300) if ann_vol else 30.0

            weighted_risk_sum += fx_risk * weight

            countries.append({
                "country_code": country_code,
                "currency": currency,
                "regime": regime,
                "wasi_weight": weight,
                "rate_to_usd": rate_usd,
                "pct_change_1d": pct_1d,
                "annualized_vol": ann_vol if ann_vol else None,
                "fx_risk_score": round(fx_risk, 1),
            })

        pegged_count = sum(1 for c in countries if c["regime"] == "PEGGED")
        floating_count = sum(1 for c in countries if c["regime"] == "FLOATING")
        managed_count = sum(1 for c in countries if c["regime"] == "MANAGED")

        return {
            "total_countries": len(countries),
            "weighted_fx_risk": round(weighted_risk_sum, 2),
            "countries": countries,
            "regime_summary": {
                "pegged": pegged_count,
                "floating": floating_count,
                "managed": managed_count,
            },
        }
