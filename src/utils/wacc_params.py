"""
Shared WACC parameters for the WASI platform.

Used by: src/routes/bank.py (credit scoring), src/engines/valuation_engine.py (DCF).
Source: Country betas from Damodaran EM database, tax rates from ECOWAS fiscal codes.
"""

# ── Static political risk table (0-10, lower = more stable) ──────────────────
POLITICAL_RISK: dict = {
    "NG": 6.5, "CI": 5.0, "GH": 3.5, "SN": 4.0,
    "BF": 8.0, "ML": 8.5, "GN": 7.0, "BJ": 4.5,
    "TG": 5.5, "NE": 8.0, "MR": 6.0, "GW": 7.5,
    "SL": 5.5, "LR": 5.5, "GM": 4.5, "CV": 2.5,
}

# WASI v3.0 ECOWAS country set
VALID_WASI_COUNTRIES: set = set(POLITICAL_RISK.keys())

# ── Country-specific WACC parameters ─────────────────────────────────────────
# beta: systematic risk vs global EM market (1.0 = average)
# eq_ratio: equity share of capital structure (rest is debt)
# tax: corporate income tax rate
# currency: ISO code
COUNTRY_WACC_PARAMS: dict = {
    "NG": {"beta": 1.30, "eq_ratio": 0.55, "tax": 0.30, "currency": "NGN"},
    "CI": {"beta": 1.15, "eq_ratio": 0.58, "tax": 0.25, "currency": "XOF"},
    "GH": {"beta": 1.25, "eq_ratio": 0.57, "tax": 0.25, "currency": "GHS"},
    "SN": {"beta": 1.10, "eq_ratio": 0.60, "tax": 0.30, "currency": "XOF"},
    "CM": {"beta": 1.20, "eq_ratio": 0.55, "tax": 0.33, "currency": "XAF"},
    "AO": {"beta": 1.35, "eq_ratio": 0.52, "tax": 0.25, "currency": "AOA"},
    "BF": {"beta": 1.40, "eq_ratio": 0.50, "tax": 0.28, "currency": "XOF"},
    "ML": {"beta": 1.40, "eq_ratio": 0.50, "tax": 0.30, "currency": "XOF"},
    "GN": {"beta": 1.35, "eq_ratio": 0.52, "tax": 0.35, "currency": "GNF"},
    "BJ": {"beta": 1.15, "eq_ratio": 0.58, "tax": 0.30, "currency": "XOF"},
    "TG": {"beta": 1.20, "eq_ratio": 0.57, "tax": 0.27, "currency": "XOF"},
    "NE": {"beta": 1.40, "eq_ratio": 0.50, "tax": 0.30, "currency": "XOF"},
    "MR": {"beta": 1.30, "eq_ratio": 0.53, "tax": 0.25, "currency": "MRU"},
    "GW": {"beta": 1.40, "eq_ratio": 0.50, "tax": 0.25, "currency": "XOF"},
    "SL": {"beta": 1.30, "eq_ratio": 0.53, "tax": 0.30, "currency": "SLE"},
    "LR": {"beta": 1.30, "eq_ratio": 0.53, "tax": 0.25, "currency": "LRD"},
    "GM": {"beta": 1.20, "eq_ratio": 0.57, "tax": 0.31, "currency": "GMD"},
    "CV": {"beta": 1.05, "eq_ratio": 0.62, "tax": 0.25, "currency": "CVE"},
}
_DEFAULT_WACC_PARAMS = {"beta": 1.25, "eq_ratio": 0.55, "tax": 0.28, "currency": "USD"}

# Market constants (updated Feb 2026)
_RF = 0.0405   # US 10-year Treasury risk-free rate (Feb 2026, FRED DGS10)
_ERP = 0.0425  # Global implied equity risk premium (Damodaran Jan 2026: 4.23%)
