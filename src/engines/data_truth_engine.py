"""
Data Truth Engine -- Guardrails G5, G6, G7.

G5: Cross-source validation (2+ sources must converge within tolerance).
G6: Staleness detection (data age thresholds).
G7: Statistical anomaly detection (z-score rejection).
"""
import logging
import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import CountryIndex, Country, MacroIndicator
from src.database.sovereign_models import DataTruthAudit, SovereignVeto

logger = logging.getLogger(__name__)

CROSS_SOURCE_TOLERANCE_PCT = 15.0
CROSS_SOURCE_WARN_PCT = 10.0
STALE_THRESHOLD_DAYS = 30
EXPIRED_THRESHOLD_DAYS = 90
ZSCORE_WARN = 2.0
ZSCORE_REJECT = 3.0


def check_cross_source(
    value_a: float,
    value_b: float,
    source_a: str = "source_a",
    source_b: str = "source_b",
) -> dict:
    """G5: Compare two source values. Returns verdict + divergence %."""
    avg = (abs(value_a) + abs(value_b)) / 2.0
    if avg == 0:
        divergence_pct = 0.0
    else:
        divergence_pct = abs(value_a - value_b) / avg * 100.0

    if divergence_pct <= CROSS_SOURCE_WARN_PCT:
        verdict = "AGREE"
        confidence_penalty = 0.0
    elif divergence_pct <= CROSS_SOURCE_TOLERANCE_PCT:
        verdict = "AGREE"
        confidence_penalty = 0.05
    else:
        verdict = "DIVERGE"
        confidence_penalty = min(0.40, divergence_pct / 100.0)

    within = "within tolerance" if verdict == "AGREE" else "EXCEEDS tolerance -- data conflict"
    return {
        "verdict": verdict,
        "divergence_pct": round(divergence_pct, 2),
        "confidence_penalty": round(confidence_penalty, 4),
        "source_a": source_a,
        "source_b": source_b,
        "value_a": value_a,
        "value_b": value_b,
        "message": f"Sources {source_a} vs {source_b}: divergence {divergence_pct:.1f}% ({within})",
    }


def check_staleness(
    data_timestamp: Optional[datetime],
    label: str = "data",
) -> dict:
    """G6: Check if data is stale or expired based on age."""
    if data_timestamp is None:
        return {
            "verdict": "EXPIRED",
            "age_days": None,
            "confidence_penalty": 0.50,
            "message": f"No timestamp available for {label} -- treated as expired.",
        }

    if data_timestamp.tzinfo is None:
        data_timestamp = data_timestamp.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_days = (now - data_timestamp).days

    if age_days <= STALE_THRESHOLD_DAYS:
        return {
            "verdict": "FRESH",
            "age_days": age_days,
            "confidence_penalty": 0.0,
            "message": f"{label}: {age_days}d old -- fresh.",
        }
    elif age_days <= EXPIRED_THRESHOLD_DAYS:
        penalty = min(0.30, (age_days - STALE_THRESHOLD_DAYS) / 200.0)
        return {
            "verdict": "STALE",
            "age_days": age_days,
            "confidence_penalty": round(penalty, 4),
            "message": f"{label}: {age_days}d old -- stale. Results may be outdated.",
        }
    else:
        return {
            "verdict": "EXPIRED",
            "age_days": age_days,
            "confidence_penalty": 0.50,
            "message": f"{label}: {age_days}d old -- expired. Data too old for reliable scoring.",
        }


def check_anomaly(
    value: float,
    historical_values: list[float],
    label: str = "metric",
) -> dict:
    """G7: Z-score anomaly detection. Requires >= 5 historical points."""
    if len(historical_values) < 5:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "z_score": None,
            "confidence_penalty": 0.10,
            "message": f"Insufficient history ({len(historical_values)} pts) for anomaly detection on {label}.",
        }

    mean = sum(historical_values) / len(historical_values)
    variance = sum((x - mean) ** 2 for x in historical_values) / len(historical_values)
    std = math.sqrt(variance) if variance > 0 else 0.0
    z = abs(value - mean) / std if std > 0 else 0.0

    if z <= ZSCORE_WARN:
        return {
            "verdict": "NORMAL",
            "z_score": round(z, 3),
            "confidence_penalty": 0.0,
            "message": f"{label}: z={z:.2f} -- within normal range.",
        }
    elif z <= ZSCORE_REJECT:
        penalty = min(0.20, (z - ZSCORE_WARN) * 0.20)
        return {
            "verdict": "ANOMALY_WARN",
            "z_score": round(z, 3),
            "confidence_penalty": round(penalty, 4),
            "message": f"{label}: z={z:.2f} -- unusual value, flagged for review.",
        }
    else:
        return {
            "verdict": "ANOMALY_REJECT",
            "z_score": round(z, 3),
            "confidence_penalty": 0.50,
            "message": f"{label}: z={z:.2f} -- statistical anomaly (>3 sigma). Rejected.",
        }


def run_data_truth_check(country_code: str, db: Session) -> dict:
    """Run full G5+G6+G7 truth check for a country using DB data."""
    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        return {
            "pass": False,
            "country_code": country_code.upper(),
            "checks": [],
            "overall_confidence_penalty": 1.0,
            "message": f"Country {country_code} not found.",
        }

    checks = []
    total_penalty = 0.0

    latest = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    ts = None
    if latest and latest.period_date:
        ts = datetime.combine(latest.period_date, datetime.min.time(), tzinfo=timezone.utc)
    staleness = check_staleness(ts, label=f"{country_code} index data")
    checks.append({"guardrail": "G6_STALENESS", **staleness})
    total_penalty += staleness["confidence_penalty"]

    history_rows = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .limit(24)
        .all()
    )
    if latest and latest.index_value is not None and len(history_rows) > 1:
        hist_values = [r.index_value for r in history_rows[1:] if r.index_value is not None]
        anomaly = check_anomaly(latest.index_value, hist_values, label=f"{country_code} index_value")
        checks.append({"guardrail": "G7_ANOMALY", **anomaly})
        total_penalty += anomaly["confidence_penalty"]

    total_penalty = min(1.0, total_penalty)
    passed = total_penalty < 0.50

    return {
        "pass": passed,
        "country_code": country_code.upper(),
        "checks": checks,
        "overall_confidence_penalty": round(total_penalty, 4),
        "adjusted_confidence": round(max(0.0, 1.0 - total_penalty), 4),
        "message": "Data truth check passed." if passed else "Data truth check FAILED -- confidence too degraded.",
    }


def record_truth_audit(
    db: Session,
    country_code: str,
    metric_name: str,
    source_a: str,
    source_b: str,
    value_a: float,
    value_b: float,
) -> DataTruthAudit:
    """Run G5 cross-source check and persist audit record."""
    result = check_cross_source(value_a, value_b, source_a, source_b)
    audit = DataTruthAudit(
        country_code=country_code.upper(),
        metric_name=metric_name,
        source_a=source_a,
        source_b=source_b,
        value_a=value_a,
        value_b=value_b,
        divergence_pct=result["divergence_pct"],
        verdict=result["verdict"],
        confidence_after=round(1.0 - result["confidence_penalty"], 4),
        details=result["message"],
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit



def validate_country_data(db: Session, country_code: str) -> dict:
    """
    Run full data truth validation for a country.
    Cross-references CountryIndex + MacroIndicator, checks active vetoes.
    Returns aggregated truth assessment.
    """
    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        return {
            'error': f'Country {country_code} not found',
            'checks': [],
            'human_review_required': True,
            'advisory': 'Advisory only. Decision finale = validation humaine.',
        }

    # Active vetoes
    active_vetoes = db.query(SovereignVeto).filter(
        SovereignVeto.country_code == country_code.upper(),
        SovereignVeto.is_active == True,
    ).all()

    # Run G5+G6+G7 on index data
    truth_result = run_data_truth_check(country_code, db)

    # Macro cross-reference
    macro_checks = []
    macro_records = (
        db.query(MacroIndicator)
        .filter(MacroIndicator.country_id == country.id)
        .order_by(MacroIndicator.year.desc())
        .limit(10)
        .all()
    )
    if macro_records:
        latest_macro = macro_records[0]
        historical_gdp = [
            m.gdp_growth_pct for m in macro_records
            if m.gdp_growth_pct is not None
        ]
        if latest_macro.gdp_growth_pct is not None and len(historical_gdp) > 1:
            anomaly = check_anomaly(
                latest_macro.gdp_growth_pct,
                historical_gdp[1:],
                label=f'{country_code} gdp_growth',
            )
            macro_checks.append({'guardrail': 'G7_MACRO_ANOMALY', **anomaly})
        if latest_macro.fetched_at:
            staleness = check_staleness(latest_macro.fetched_at, label=f'{country_code} macro data')
            macro_checks.append({'guardrail': 'G6_MACRO_STALENESS', **staleness})

    all_checks = truth_result.get('checks', []) + macro_checks

    # Aggregate truth score
    penalties = [c.get('confidence_penalty', 0.0) for c in all_checks]
    total_penalty = min(1.0, sum(penalties))
    overall_confidence = round(max(0.0, 1.0 - total_penalty), 4)

    # Overall verdict
    verdicts = [c.get('verdict', '') for c in all_checks]
    if any(v == 'ANOMALY_REJECT' for v in verdicts):
        overall_verdict = 'ANOMALY_DETECTED'
    elif any(v == 'DIVERGE' for v in verdicts):
        overall_verdict = 'DIVERGENCE_DETECTED'
    elif any(v in ('STALE', 'EXPIRED') for v in verdicts):
        overall_verdict = 'STALE_DATA'
    elif not all_checks:
        overall_verdict = 'NO_DATA'
    else:
        overall_verdict = 'VERIFIED'

    return {
        'country_code': country_code.upper(),
        'country_name': country.name,
        'overall_truth_score': overall_confidence,
        'overall_verdict': overall_verdict,
        'active_vetoes': len(active_vetoes),
        'veto_details': [
            {
                'id': v.id,
                'veto_type': v.veto_type,
                'severity': v.severity,
                'issued_by': v.issued_by,
                'reason': v.reason,
                'effective_date': str(v.effective_date),
            }
            for v in active_vetoes
        ],
        'checks': all_checks,
        'human_review_required': overall_verdict != 'VERIFIED' or len(active_vetoes) > 0,
        'advisory': 'Advisory only. Decision finale = validation humaine.',
    }
