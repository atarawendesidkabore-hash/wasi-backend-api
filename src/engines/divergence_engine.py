"""
Divergence Engine — cross-references West African stock market performance
against WASI fundamental scores to detect over/undervaluation.

Core concept
------------
  divergence = stock_change_pct - fundamentals_change_pct

  Positive divergence (+):
    Market is outrunning fundamentals → potential OVERVALUATION
    e.g. NGX up 20% while Nigeria WASI score flat → rally not backed by trade/port data

  Negative divergence (-):
    Market is lagging fundamentals → potential UNDERVALUATION / buying opportunity
    e.g. BRVM flat while CI/SN economic scores rising → equities not priced in

  low_liquidity:
    Volume below $5M/day average — signal is unreliable; thin market can be
    moved by a single large order. Do not trade on divergence alone.

Exchange → WASI country mapping
---------------------------------
  NGX  → NG         (28% weight)
  GSE  → GH         (15% weight)
  BRVM → CI,SN,BJ,TG (34% combined weight)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Exchange → list of WASI country codes it represents
EXCHANGE_COUNTRY_MAP: dict[str, list[str]] = {
    "NGX":  ["NG"],
    "GSE":  ["GH"],
    "BRVM": ["CI", "SN", "BJ", "TG"],
}

# Combined WASI weights per exchange
EXCHANGE_WASI_WEIGHT: dict[str, float] = {
    "NGX":  0.28,
    "GSE":  0.15,
    "BRVM": 0.34,  # CI 22% + SN 10% + BJ 1% + TG 1%
}

# W1 — Minimum average daily volume (USD) to trust a divergence signal
# Below this threshold the signal is flagged "low_liquidity" regardless of divergence
LIQUIDITY_THRESHOLD_USD: float = 5_000_000.0

_SIGNAL_THRESHOLDS = {
    "strong_overvalued":   10.0,
    "overvalued":           4.0,
    "aligned":              4.0,   # within ±4% = aligned
    "undervalued":         -4.0,
    "strong_undervalued": -10.0,
}


@dataclass
class DivergenceResult:
    exchange_code:        str
    index_name:           str
    country_codes:        list[str]
    wasi_weight:          float

    # Stock side
    stock_change_pct:     Optional[float]   # period % change in index
    stock_index_value:    float
    stock_market_cap_usd: Optional[float]
    volume_usd:           Optional[float]   # W1: average daily volume for period

    # Fundamentals side
    avg_wasi_score:           Optional[float]
    fundamentals_change_pct:  Optional[float]

    # Divergence
    divergence_pct:  Optional[float]
    signal:          str    # strong_overvalued | overvalued | aligned | undervalued |
                            # strong_undervalued | insufficient_data | low_liquidity
    liquidity_flag:  bool   # True if volume below LIQUIDITY_THRESHOLD_USD
    narrative:       str


def _classify_signal(
    divergence: Optional[float],
    liquidity_flag: bool,
) -> str:
    if liquidity_flag:
        return "low_liquidity"
    if divergence is None:
        return "insufficient_data"
    if divergence >= _SIGNAL_THRESHOLDS["strong_overvalued"]:
        return "strong_overvalued"
    if divergence >= _SIGNAL_THRESHOLDS["overvalued"]:
        return "overvalued"
    if divergence <= _SIGNAL_THRESHOLDS["strong_undervalued"]:
        return "strong_undervalued"
    if divergence <= _SIGNAL_THRESHOLDS["undervalued"]:
        return "undervalued"
    return "aligned"


def _build_narrative(
    exchange: str,
    index_name: str,
    country_codes: list[str],
    stock_change: Optional[float],
    fund_change: Optional[float],
    divergence: Optional[float],
    signal: str,
    volume_usd: Optional[float],
) -> str:
    countries = ", ".join(country_codes)

    if signal == "low_liquidity":
        vol_str = f"${volume_usd / 1_000_000:.1f}M" if volume_usd else "unknown"
        return (
            f"{index_name} ({exchange}): Average daily volume {vol_str} is below the "
            f"${LIQUIDITY_THRESHOLD_USD / 1_000_000:.0f}M liquidity threshold. "
            f"Divergence signal suppressed — thin market conditions for {countries}. "
            f"Verify with an official data vendor before acting on price movements."
        )

    if signal == "insufficient_data":
        return (
            f"{index_name} ({exchange}): Insufficient data to compute divergence "
            f"for {countries}."
        )

    dir_stock = "up" if (stock_change or 0) >= 0 else "down"
    dir_fund  = "up" if (fund_change  or 0) >= 0 else "down"

    stock_str = f"{abs(stock_change):.1f}%" if stock_change is not None else "N/A"
    fund_str  = f"{abs(fund_change):.1f}%"  if fund_change  is not None else "N/A"
    div_str   = f"{abs(divergence):.1f}%"   if divergence   is not None else "N/A"

    if signal == "strong_overvalued":
        return (
            f"{index_name} ({exchange}) is {dir_stock} {stock_str} but WASI fundamentals "
            f"for {countries} are only {dir_fund} {fund_str}. "
            f"Divergence of +{div_str} signals the market is significantly OUTRUNNING "
            f"trade and port fundamentals — elevated overvaluation risk."
        )
    if signal == "overvalued":
        return (
            f"{index_name} ({exchange}) is {dir_stock} {stock_str} while WASI fundamentals "
            f"for {countries} are {dir_fund} {fund_str}. "
            f"Moderate positive divergence (+{div_str}) — market ahead of fundamentals."
        )
    if signal == "strong_undervalued":
        return (
            f"{index_name} ({exchange}) is {dir_stock} {stock_str} but WASI fundamentals "
            f"for {countries} are {dir_fund} {fund_str}. "
            f"Divergence of {div_str} signals the market is significantly LAGGING "
            f"trade and port fundamentals — potential undervaluation / buy signal."
        )
    if signal == "undervalued":
        return (
            f"{index_name} ({exchange}) is {dir_stock} {stock_str} while WASI fundamentals "
            f"for {countries} are {dir_fund} {fund_str}. "
            f"Moderate negative divergence ({div_str}) — equities lagging fundamentals."
        )
    return (
        f"{index_name} ({exchange}) is {dir_stock} {stock_str}, in line with WASI "
        f"fundamentals for {countries} ({dir_fund} {fund_str}). "
        f"Divergence of {div_str} — market and fundamentals are broadly ALIGNED."
    )


def compute_divergence(
    exchange_code: str,
    index_name: str,
    stock_index_value: float,
    stock_change_pct: Optional[float],
    stock_market_cap_usd: Optional[float],
    country_index_values: dict[str, float],
    prev_country_index_values: dict[str, float],
    volume_usd: Optional[float] = None,          # W1: pass avg daily volume
) -> DivergenceResult:
    """
    Compute divergence between one stock index and WASI fundamentals.

    Parameters
    ----------
    country_index_values      : latest WASI CountryIndex.index_value per code
    prev_country_index_values : prior period values (for fundamentals_change_pct)
    volume_usd                : average daily trading volume in USD (W1 liquidity check)
    """
    country_codes = EXCHANGE_COUNTRY_MAP.get(exchange_code, [])

    # W1: liquidity check — suppress noisy signals from thin markets
    liquidity_flag = (
        volume_usd is not None and volume_usd < LIQUIDITY_THRESHOLD_USD
    )

    # Average WASI score for covered countries
    covered_latest = [country_index_values[c] for c in country_codes if c in country_index_values]
    covered_prev   = [prev_country_index_values[c] for c in country_codes if c in prev_country_index_values]

    avg_latest: Optional[float] = (
        sum(covered_latest) / len(covered_latest) if covered_latest else None
    )
    avg_prev: Optional[float] = (
        sum(covered_prev) / len(covered_prev) if covered_prev else None
    )

    fund_change: Optional[float] = None
    if avg_latest is not None and avg_prev is not None and avg_prev != 0:
        fund_change = round((avg_latest - avg_prev) / avg_prev * 100, 2)

    divergence: Optional[float] = None
    if stock_change_pct is not None and fund_change is not None:
        divergence = round(stock_change_pct - fund_change, 2)

    signal    = _classify_signal(divergence, liquidity_flag)
    narrative = _build_narrative(
        exchange_code, index_name, country_codes,
        stock_change_pct, fund_change, divergence, signal, volume_usd,
    )

    return DivergenceResult(
        exchange_code=exchange_code,
        index_name=index_name,
        country_codes=country_codes,
        wasi_weight=EXCHANGE_WASI_WEIGHT.get(exchange_code, 0.0),
        stock_change_pct=stock_change_pct,
        stock_index_value=stock_index_value,
        stock_market_cap_usd=stock_market_cap_usd,
        volume_usd=volume_usd,
        avg_wasi_score=round(avg_latest, 4) if avg_latest is not None else None,
        fundamentals_change_pct=fund_change,
        divergence_pct=divergence,
        signal=signal,
        liquidity_flag=liquidity_flag,
        narrative=narrative,
    )
