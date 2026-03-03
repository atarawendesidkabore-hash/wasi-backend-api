"""
FX Rate Scraper — Fetches daily ECOWAS currency rates from free APIs.

Primary:   Fawazahmed0 Currency API (no key, no rate limit, daily)
Fallback:  ExchangeRate-API (no key, daily)
Static:    XOF peg (655.957/EUR), CVE peg (110.265/EUR)

Currencies tracked: NGN, GHS, GMD, GNF, SLE, LRD, MRU, CVE, XOF.
Also cross-updates CbdcFxRate for CBDC engine compatibility.
"""
import logging
import time
from datetime import date, timedelta, timezone, datetime
from typing import Optional

import requests
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.fx_models import FxDailyRate
from src.database.cbdc_models import CbdcFxRate

logger = logging.getLogger(__name__)

# ── URLs ─────────────────────────────────────────────────────────────────

PRIMARY_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
FALLBACK_URL = "https://latest.currency-api.pages.dev/v1/currencies/usd.json"
SECONDARY_URL = "https://open.er-api.com/v6/latest/USD"
REQUEST_TIMEOUT = 15

# ── Peg constants ────────────────────────────────────────────────────────

XOF_PER_EUR = 655.957
CVE_PER_EUR = 110.265

# ── Currencies to track ─────────────────────────────────────────────────

# Maps WASI code → lowercase API code for fawazahmed0
ECOWAS_CURRENCIES = {
    "NGN": "ngn", "GHS": "ghs", "GMD": "gmd", "GNF": "gnf",
    "SLE": "sle", "LRD": "lrd", "MRU": "mru", "CVE": "cve",
}

# Fallback seed rates (1 USD = X units of currency, March 2026 approx)
FALLBACK_RATES_USD = {
    "NGN": 1550.0, "GHS": 15.2, "GMD": 70.0, "GNF": 8600.0,
    "SLE": 22.5, "LRD": 192.0, "MRU": 39.5, "CVE": 101.0,
    "EUR": 0.92,
}


# ── Private fetch functions ──────────────────────────────────────────────

def _fetch_fawazahmed0() -> Optional[dict]:
    """Fetch USD-base rates from Fawazahmed0 Currency API."""
    for url in (PRIMARY_URL, FALLBACK_URL):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            rates = data.get("usd", {})
            if rates and "eur" in rates:
                logger.info("fx_scraper: fetched %d rates from %s", len(rates), url)
                return rates
        except Exception as exc:
            logger.warning("fx_scraper: %s failed: %s", url, exc)
    return None


def _fetch_exchangerate_api() -> Optional[dict]:
    """Fetch USD-base rates from ExchangeRate-API."""
    try:
        resp = requests.get(SECONDARY_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") == "success":
            raw = data.get("rates", {})
            # Convert to lowercase keys for consistency
            rates = {k.lower(): v for k, v in raw.items()}
            logger.info("fx_scraper: fetched %d rates from ExchangeRate-API", len(rates))
            return rates
    except Exception as exc:
        logger.warning("fx_scraper: ExchangeRate-API failed: %s", exc)
    return None


def _get_pct_change(db: Session, currency_code: str, current_rate: float,
                    today: date, days_back: int) -> Optional[float]:
    """Compute percentage change vs rate N days ago."""
    target_date = today - timedelta(days=days_back)
    row = (
        db.query(FxDailyRate)
        .filter(
            FxDailyRate.currency_code == currency_code,
            FxDailyRate.rate_date <= target_date,
        )
        .order_by(FxDailyRate.rate_date.desc())
        .first()
    )
    if row and row.rate_to_usd and row.rate_to_usd > 0:
        old_rate = float(row.rate_to_usd)
        return round((current_rate - old_rate) / old_rate * 100.0, 4)
    return None


def _upsert_fx_daily(db: Session, currency_code: str, rate_date: date,
                     rate_usd: float, rate_eur: float, rate_xof: float,
                     source: str, confidence: float) -> bool:
    """Insert or update FxDailyRate row. Returns True if new."""
    existing = (
        db.query(FxDailyRate)
        .filter(FxDailyRate.currency_code == currency_code,
                FxDailyRate.rate_date == rate_date)
        .first()
    )

    pct_1d = _get_pct_change(db, currency_code, rate_usd, rate_date, 1)
    pct_7d = _get_pct_change(db, currency_code, rate_usd, rate_date, 7)
    pct_30d = _get_pct_change(db, currency_code, rate_usd, rate_date, 30)

    if existing:
        existing.rate_to_usd = rate_usd
        existing.rate_to_eur = rate_eur
        existing.rate_to_xof = rate_xof
        existing.pct_change_1d = pct_1d
        existing.pct_change_7d = pct_7d
        existing.pct_change_30d = pct_30d
        existing.data_source = source
        existing.confidence = confidence
        return False
    else:
        db.add(FxDailyRate(
            currency_code=currency_code,
            rate_date=rate_date,
            rate_to_usd=rate_usd,
            rate_to_eur=rate_eur,
            rate_to_xof=rate_xof,
            pct_change_1d=pct_1d,
            pct_change_7d=pct_7d,
            pct_change_30d=pct_30d,
            data_source=source,
            confidence=confidence,
        ))
        return True


def _cross_update_cbdc_rate(db: Session, currency_code: str,
                            xof_per_unit: float, source: str):
    """Update CbdcFxRate table so the CBDC engine gets fresh rates."""
    today = date.today()
    inverse = round(1.0 / xof_per_unit, 6) if xof_per_unit > 0 else 0

    existing = (
        db.query(CbdcFxRate)
        .filter(CbdcFxRate.target_currency == currency_code,
                CbdcFxRate.effective_date == today)
        .first()
    )
    if existing:
        existing.rate = xof_per_unit
        existing.inverse_rate = inverse
        existing.source = source
    else:
        db.add(CbdcFxRate(
            base_currency="XOF",
            target_currency=currency_code,
            rate=xof_per_unit,
            inverse_rate=inverse,
            effective_date=today,
            source=source,
        ))


def _seed_fallback_rates(db: Session):
    """Seed fallback rates when no API data available."""
    today = date.today()
    eur_usd = FALLBACK_RATES_USD["EUR"]
    xof_usd = XOF_PER_EUR * eur_usd  # XOF per USD

    for cc, rate_usd in FALLBACK_RATES_USD.items():
        if cc == "EUR":
            continue
        rate_eur = rate_usd / eur_usd if eur_usd > 0 else 0
        rate_xof = rate_usd / xof_usd if xof_usd > 0 else 0
        _upsert_fx_daily(db, cc, today, rate_usd, rate_eur, rate_xof,
                         "fallback_seed", 0.5)
        if cc != "XOF":
            xof_per_unit = xof_usd / rate_usd if rate_usd > 0 else 0
            _cross_update_cbdc_rate(db, cc, xof_per_unit, "FALLBACK_SEED")

    # XOF itself
    _upsert_fx_daily(db, "XOF", today, xof_usd, XOF_PER_EUR, 1.0,
                     "fallback_seed", 1.0)

    db.commit()
    logger.info("fx_scraper: seeded %d fallback rates", len(FALLBACK_RATES_USD) - 1)


# ── Public entry point ───────────────────────────────────────────────────

def run_fx_scraper(db: Session = None) -> dict:
    """
    Fetch daily FX rates, upsert FxDailyRate rows, cross-update CbdcFxRate.

    Returns: {updated, skipped, errors, data_source, currencies}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary = {
        "updated": 0, "skipped": 0, "errors": 0,
        "data_source": "unknown", "currencies": [],
    }

    try:
        # Try primary API
        usd_rates = _fetch_fawazahmed0()
        source = "fawazahmed0"
        confidence = 1.0

        # Fallback to secondary
        if usd_rates is None:
            usd_rates = _fetch_exchangerate_api()
            source = "exchangerate_api"
            confidence = 0.9

        # Fallback to seeds
        if usd_rates is None:
            logger.warning("fx_scraper: all APIs failed — using fallback seed rates")
            _seed_fallback_rates(db)
            summary["data_source"] = "fallback_seed"
            summary["updated"] = len(FALLBACK_RATES_USD) - 1
            summary["currencies"] = list(ECOWAS_CURRENCIES.keys())
            return summary

        summary["data_source"] = source
        today = date.today()

        # EUR rate for peg derivation
        eur_usd = usd_rates.get("eur", FALLBACK_RATES_USD["EUR"])
        xof_usd = XOF_PER_EUR * eur_usd  # 1 USD = X XOF

        # Process each ECOWAS currency
        for wasi_code, api_code in ECOWAS_CURRENCIES.items():
            try:
                rate_usd = usd_rates.get(api_code)

                # Try alternate code for Sierra Leone (SLL → SLE)
                if rate_usd is None and wasi_code == "SLE":
                    rate_usd = usd_rates.get("sll")
                    if rate_usd is not None:
                        rate_usd = rate_usd / 1000.0  # SLL→SLE redenomination

                if rate_usd is None:
                    rate_usd = FALLBACK_RATES_USD.get(wasi_code)
                    confidence = 0.5

                if rate_usd is None or rate_usd <= 0:
                    logger.warning("fx_scraper: no rate for %s", wasi_code)
                    summary["errors"] += 1
                    continue

                rate_eur = round(rate_usd / eur_usd, 6) if eur_usd > 0 else 0
                rate_xof = round(rate_usd / xof_usd, 6) if xof_usd > 0 else 0

                is_new = _upsert_fx_daily(
                    db, wasi_code, today, round(rate_usd, 6),
                    rate_eur, rate_xof, source, confidence,
                )

                # Cross-update CbdcFxRate: XOF per 1 unit of currency
                xof_per_unit = round(xof_usd / rate_usd, 6) if rate_usd > 0 else 0
                _cross_update_cbdc_rate(db, wasi_code, xof_per_unit, source.upper())

                if is_new:
                    summary["updated"] += 1
                else:
                    summary["skipped"] += 1
                summary["currencies"].append(wasi_code)

            except Exception as exc:
                logger.error("fx_scraper: error processing %s: %s", wasi_code, exc)
                summary["errors"] += 1

        # XOF row (derived from EUR peg)
        try:
            _upsert_fx_daily(db, "XOF", today, round(xof_usd, 6),
                             XOF_PER_EUR, 1.0, source, 1.0)
            summary["currencies"].append("XOF")
            summary["updated"] += 1
        except Exception as exc:
            logger.error("fx_scraper: error processing XOF: %s", exc)
            summary["errors"] += 1

        db.commit()
        logger.info(
            "fx_scraper: updated=%d skipped=%d errors=%d source=%s",
            summary["updated"], summary["skipped"], summary["errors"], source,
        )

    except Exception as exc:
        logger.error("fx_scraper failed: %s", exc, exc_info=True)
        summary["errors"] += 1
        db.rollback()
    finally:
        if own_session:
            db.close()

    return summary
