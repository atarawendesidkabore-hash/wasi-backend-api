"""
BCEAO (Banque Centrale des États de l'Afrique de l'Ouest) data parser.

Maps BCEAO/UEMOA monthly bulletin columns to WASI CountryIndex fields.
Covers 4 WASI countries: CI, SN, BJ, TG.

FCFA → USD conversion:  1 USD ≈ 600 FCFA (XOF fixed peg to EUR at 655.957 FCFA/EUR)
Confidence assigned: 0.95  (official central bank data)
Data quality: "high"
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# FCFA to USD: XOF is pegged at 655.957 FCFA/EUR; using ~600 FCFA/USD approximation
FCFA_TO_USD = 1 / 600.0

# Billions FCFA → USD
_B_FCFA_TO_USD = 1_000_000_000 * FCFA_TO_USD

# BCEAO-covered WASI country codes
BCEAO_WASI_CODES = {"CI", "SN", "BJ", "TG"}

# Column name aliases (BCEAO may publish with slight variations)
_COL_ALIASES: dict[str, str] = {
    # date
    "date": "date",
    "période": "date",
    "periode": "date",
    # country
    "pays_code": "pays_code",
    "code": "pays_code",
    "country_code": "pays_code",
    # GDP growth
    "taux_croissance_pib_annuel": "gdp_growth",
    "pib_croissance": "gdp_growth",
    "croissance_pib": "gdp_growth",
    "gdp_growth": "gdp_growth",
    # inflation
    "taux_inflation": "inflation",
    "inflation": "inflation",
    "ipc": "inflation",
    # exports (billions FCFA)
    "exportations_milliards_fcfa": "exports_bfcfa",
    "exportations": "exports_bfcfa",
    "exports": "exports_bfcfa",
    # imports (billions FCFA)
    "importations_milliards_fcfa": "imports_bfcfa",
    "importations": "imports_bfcfa",
    "imports": "imports_bfcfa",
    # trade balance
    "solde_commercial_milliards_fcfa": "balance_bfcfa",
    "solde_commercial": "balance_bfcfa",
    "trade_balance": "balance_bfcfa",
    # industrial production index
    "ipi": "ipi",
    "indice_production_industrielle": "ipi",
}


class BCEAORecord:
    """One parsed monthly BCEAO record, ready to merge into CountryIndex."""

    __slots__ = (
        "country_code",
        "period_date",
        "gdp_growth_pct",
        "inflation_pct",
        "export_value_usd",
        "import_value_usd",
        "trade_value_usd",
        "trade_balance_usd",
        "ipi",
        "confidence",
        "data_quality",
        "data_source",
    )

    def __init__(
        self,
        country_code: str,
        period_date: date,
        gdp_growth_pct: Optional[float],
        inflation_pct: Optional[float],
        export_value_usd: Optional[float],
        import_value_usd: Optional[float],
        ipi: Optional[float],
    ):
        self.country_code = country_code.upper().strip()
        self.period_date = period_date
        self.gdp_growth_pct = gdp_growth_pct
        self.inflation_pct = inflation_pct
        self.export_value_usd = export_value_usd
        self.import_value_usd = import_value_usd
        self.trade_value_usd = (
            (export_value_usd or 0.0) + (import_value_usd or 0.0)
            if (export_value_usd is not None or import_value_usd is not None)
            else None
        )
        self.trade_balance_usd = (
            (export_value_usd or 0.0) - (import_value_usd or 0.0)
            if (export_value_usd is not None or import_value_usd is not None)
            else None
        )
        self.ipi = ipi
        self.confidence = 0.95
        self.data_quality = "high"
        self.data_source = "bceao"


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns using _COL_ALIASES, lowercasing first."""
    df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
    return df.rename(columns={k: v for k, v in _COL_ALIASES.items() if k in df.columns})


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _parse_date(val) -> Optional[date]:
    """Parse YYYY-MM-DD or YYYY-MM-01 strings to date, normalised to 1st of month."""
    try:
        d = pd.to_datetime(val)
        return d.replace(day=1).date()
    except Exception:
        return None


def parse_csv(filepath: str | Path) -> list[BCEAORecord]:
    """
    Parse a BCEAO-format CSV file and return a list of BCEAORecord objects.

    Expected columns (French or English, flexible via _COL_ALIASES):
        date, pays_code, taux_croissance_pib_annuel, taux_inflation,
        exportations_milliards_fcfa, importations_milliards_fcfa, ipi

    FCFA values are converted to USD at FCFA_TO_USD.
    Rows with unknown pays_code or unparseable dates are skipped.
    """
    fp = Path(filepath)
    if not fp.exists():
        logger.warning("BCEAO CSV not found: %s", fp)
        return []

    try:
        df = pd.read_csv(fp, encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to read BCEAO CSV %s: %s", fp, exc)
        return []

    df = _normalise_columns(df)
    records: list[BCEAORecord] = []

    for _, row in df.iterrows():
        code = str(row.get("pays_code", "")).upper().strip()
        if code not in BCEAO_WASI_CODES:
            logger.debug("Skipping non-WASI country code: %s", code)
            continue

        period = _parse_date(row.get("date"))
        if period is None:
            logger.warning("Skipping row with unparseable date: %s", row.get("date"))
            continue

        gdp = _safe_float(row.get("gdp_growth"))
        inflation = _safe_float(row.get("inflation"))
        ipi = _safe_float(row.get("ipi"))

        # Convert billions FCFA → USD
        exp_raw = _safe_float(row.get("exports_bfcfa"))
        imp_raw = _safe_float(row.get("imports_bfcfa"))
        exp_usd = exp_raw * _B_FCFA_TO_USD if exp_raw is not None else None
        imp_usd = imp_raw * _B_FCFA_TO_USD if imp_raw is not None else None

        records.append(
            BCEAORecord(
                country_code=code,
                period_date=period,
                gdp_growth_pct=gdp,
                inflation_pct=inflation,
                export_value_usd=exp_usd,
                import_value_usd=imp_usd,
                ipi=ipi,
            )
        )

    logger.info("BCEAO CSV parsed: %d records from %s", len(records), fp.name)
    return records
