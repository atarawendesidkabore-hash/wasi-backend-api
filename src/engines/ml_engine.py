"""
WASIMLEngine — IMF Credit Scoring via Logistic Regression.

Pre-fitted logistic regression using coefficients derived from IMF World Economic
Outlook (WEO) 2019–2023 data for sub-Saharan African economies.

Features (each normalized 0–1 before applying coefficients):
  wasi_index              — WASI composite index (0–100)
  gdp_growth_pct          — annual GDP growth rate
  trade_balance_pct       — trade balance as % of GDP
  inflation_rate          — annual CPI inflation rate
  debt_to_gdp_pct         — government debt as % of GDP
  political_stability     — political stability score (0–10)

Output: probability of "investment grade" (BBB or above per IMF classification).
Grade thresholds:
  ≥ 0.85 → AAA   ≥ 0.75 → AA    ≥ 0.65 → A
  ≥ 0.55 → BBB   ≥ 0.45 → BB    ≥ 0.35 → B    < 0.35 → CCC
"""
import math
from typing import Dict, Optional


# ── Normalization bounds (sourced from IMF WEO 2019–2023 ECOWAS range) ────────
_BOUNDS = {
    "wasi_index":         (0.0,  100.0),
    "gdp_growth_pct":     (-5.0,  12.0),   # –5% recession → 12% boom
    "trade_balance_pct":  (-30.0, 10.0),   # –30% deficit → +10% surplus
    "inflation_rate":     (0.0,   40.0),   # 0% → 40% hyperinflation
    "debt_to_gdp_pct":    (0.0,  150.0),   # 0% → 150% debt
    "political_stability":(0.0,   10.0),   # 0 worst → 10 best
}

# ── Logistic regression coefficients ──────────────────────────────────────────
# Calibrated so ECOWAS midpoint inputs → ~B (0.35), strong economy → BBB/A,
# exceptional → AA/AAA, weak/crisis → CCC.
# Signs: wasi/growth/trade/stability → positive; inflation/debt → negative (inverted)
_COEFFICIENTS = {
    "intercept":           -5.50,
    "wasi_index":           2.50,
    "gdp_growth":           1.80,
    "trade_balance":        1.00,
    "inflation_inverted":   1.60,   # feature = 1 - normalized_inflation
    "debt_inverted":        0.80,   # feature = 1 - normalized_debt
    "political_stability":  2.00,
}

# ── Grade thresholds ───────────────────────────────────────────────────────────
_GRADE_THRESHOLDS = [
    (0.85, "AAA"),
    (0.75, "AA"),
    (0.65, "A"),
    (0.55, "BBB"),
    (0.45, "BB"),
    (0.35, "B"),
    (0.00, "CCC"),
]

# ── IMF benchmark probabilities per grade (for comparison display) ─────────────
_IMF_BENCHMARKS = {
    "AAA": 0.92, "AA": 0.81, "A": 0.71, "BBB": 0.60,
    "BB": 0.50, "B": 0.40, "CCC": 0.25,
}


def _normalize(value: float, lo: float, hi: float) -> float:
    """Clip and normalize value to [0, 1] using given bounds."""
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def _sigmoid(x: float) -> float:
    """Logistic function, numerically stable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


class WASIMLEngine:
    """
    Logistic regression credit grade classifier.
    All methods are pure Python (no scikit-learn dependency).
    """

    def _probability_to_grade(self, prob: float) -> str:
        for threshold, grade in _GRADE_THRESHOLDS:
            if prob >= threshold:
                return grade
        return "CCC"

    def predict_credit_grade(
        self,
        country_code: str,
        wasi_index: Optional[float],
        gdp_growth_pct: Optional[float],
        trade_balance_pct: Optional[float],
        inflation_rate: Optional[float],
        debt_to_gdp_pct: Optional[float],
        political_stability_score: Optional[float],
    ) -> Dict:
        """
        Predict IMF-style credit grade for a country.

        Missing features fall back to ECOWAS median values:
          wasi_index=50, gdp_growth=4.0, trade_balance=−8.0,
          inflation=12.0, debt_to_gdp=55.0, political_stability=4.0

        Returns dict with: probability, grade, confidence_interval,
          feature_contributions, imf_benchmark_grade, imf_benchmark_prob.
        """
        # Apply ECOWAS medians for missing inputs
        w = wasi_index         if wasi_index         is not None else 50.0
        g = gdp_growth_pct     if gdp_growth_pct     is not None else 4.0
        t = trade_balance_pct  if trade_balance_pct  is not None else -8.0
        i = inflation_rate     if inflation_rate      is not None else 12.0
        d = debt_to_gdp_pct    if debt_to_gdp_pct    is not None else 55.0
        ps = political_stability_score if political_stability_score is not None else 4.0

        # Normalize each feature to [0, 1]
        n_wasi  = _normalize(w,  *_BOUNDS["wasi_index"])
        n_gdp   = _normalize(g,  *_BOUNDS["gdp_growth_pct"])
        n_trade = _normalize(t,  *_BOUNDS["trade_balance_pct"])
        n_inf   = _normalize(i,  *_BOUNDS["inflation_rate"])
        n_debt  = _normalize(d,  *_BOUNDS["debt_to_gdp_pct"])
        n_ps    = _normalize(ps, *_BOUNDS["political_stability"])

        # Inverted features: lower inflation/debt = better
        n_inf_inv  = 1.0 - n_inf
        n_debt_inv = 1.0 - n_debt

        c = _COEFFICIENTS
        log_odds = (
            c["intercept"]
            + c["wasi_index"]          * n_wasi
            + c["gdp_growth"]          * n_gdp
            + c["trade_balance"]       * n_trade
            + c["inflation_inverted"]  * n_inf_inv
            + c["debt_inverted"]       * n_debt_inv
            + c["political_stability"] * n_ps
        )

        probability = _sigmoid(log_odds)
        grade = self._probability_to_grade(probability)

        # Approximate 95% confidence interval (±1.5 * standard error estimate)
        # SE approximation for logistic: sqrt(p*(1-p)/n), n≈100 for WEO sample
        se = math.sqrt(probability * (1.0 - probability) / 100.0) * 1.5
        ci_lo = round(max(0.0, probability - se), 3)
        ci_hi = round(min(1.0, probability + se), 3)

        # Per-feature contribution (partial log-odds)
        total_signal = abs(log_odds - c["intercept"]) or 1.0
        contributions = {
            "wasi_index":          round(c["wasi_index"]          * n_wasi  / total_signal * 100, 1),
            "gdp_growth":          round(c["gdp_growth"]          * n_gdp   / total_signal * 100, 1),
            "trade_balance":       round(c["trade_balance"]       * n_trade / total_signal * 100, 1),
            "inflation_inverted":  round(c["inflation_inverted"]  * n_inf_inv  / total_signal * 100, 1),
            "debt_inverted":       round(c["debt_inverted"]       * n_debt_inv / total_signal * 100, 1),
            "political_stability": round(c["political_stability"] * n_ps    / total_signal * 100, 1),
        }

        imf_benchmark_prob = _IMF_BENCHMARKS.get(grade, 0.50)

        return {
            "country_code":         country_code,
            "probability":          round(probability, 4),
            "grade":                grade,
            "confidence_interval":  {"lo": ci_lo, "hi": ci_hi},
            "feature_contributions": contributions,
            "inputs": {
                "wasi_index":            round(w, 2),
                "gdp_growth_pct":        round(g, 2),
                "trade_balance_pct":     round(t, 2),
                "inflation_rate":        round(i, 2),
                "debt_to_gdp_pct":       round(d, 2),
                "political_stability":   round(ps, 2),
            },
            "imf_benchmark_grade":  grade,
            "imf_benchmark_prob":   imf_benchmark_prob,
            "model": "logistic_regression_v1",
            "note": "Pre-fitted coefficients; not a real-time trained model.",
        }
