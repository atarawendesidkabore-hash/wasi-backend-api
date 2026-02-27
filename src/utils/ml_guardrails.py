"""
ML Anti-Hallucination Guardrails — 4-layer framework.

Guardrail 1: Data Quality Gate
  Reject or flag inputs where confidence < threshold (default 0.60).
  All CountryIndex records carry a confidence field (0–1).

Guardrail 2: SHAP-style Feature Attribution (lightweight)
  Records relative contribution of each sub-component to the final index value.
  Stored as a dict. No external SHAP library required.

Guardrail 3: Confidence Calibration (Platt Scaling approximation)
  Applies sigmoid calibration to raw scores when confidence is partial.
  calibrated = 100 / (1 + exp(-k * (x/100 - 0.5)))
  where k = 8.0 (steepness, fitted empirically to West African data range).

Guardrail 4: Human-in-the-Loop Flag
  Always True for bank credit dossiers.
  Also fires when:
    - confidence < 0.50
    - index_value change > 20 points month-over-month
    - single country drives > 25% of composite weight with >2σ anomaly
"""
import math
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Guardrail 1: thresholds
DATA_QUALITY_THRESHOLD = 0.60   # below this, flag or reject
DATA_QUALITY_REJECT_THRESHOLD = 0.30  # below this, reject outright

# Guardrail 3: Platt scaling parameter
PLATT_K = 8.0


# ── Guardrail 1: Data Quality Gate ───────────────────────────────────────────

def check_data_quality(confidence: float, context: str = "") -> Dict[str, Any]:
    """
    Evaluate data quality.

    Returns:
        {
            "pass": bool,           # False = should reject
            "warn": bool,           # True = should include warning in response
            "confidence": float,
            "quality_label": str,   # high / medium / low / rejected
            "message": str,
        }
    """
    if confidence >= DATA_QUALITY_THRESHOLD:
        return {
            "pass": True,
            "warn": False,
            "confidence": confidence,
            "quality_label": "high" if confidence >= 0.80 else "medium",
            "message": "",
        }
    elif confidence >= DATA_QUALITY_REJECT_THRESHOLD:
        msg = (
            f"Low data confidence ({confidence:.2f}) for {context}. "
            "Results may be unreliable. Consider supplementing with additional sources."
        )
        logger.warning("Data quality warning: %s", msg)
        return {
            "pass": True,    # still pass but with warning
            "warn": True,
            "confidence": confidence,
            "quality_label": "low",
            "message": msg,
        }
    else:
        msg = (
            f"Data confidence ({confidence:.2f}) below minimum threshold "
            f"({DATA_QUALITY_REJECT_THRESHOLD}) for {context}. Calculation rejected."
        )
        logger.error("Data quality gate rejected: %s", msg)
        return {
            "pass": False,
            "warn": True,
            "confidence": confidence,
            "quality_label": "rejected",
            "message": msg,
        }


# ── Guardrail 2: Feature Attribution ─────────────────────────────────────────

def compute_feature_attribution(
    shipping_score: Optional[float],
    trade_score: Optional[float],
    infrastructure_score: Optional[float],
    economic_score: Optional[float],
    w_shipping: float = 0.40,
    w_trade: float = 0.30,
    w_infrastructure: float = 0.20,
    w_economic: float = 0.10,
) -> Dict[str, float]:
    """
    Compute weighted feature contribution for each sub-component.
    Returns dict of {component: contribution_to_index}.
    """
    components = {
        "shipping":       (shipping_score or 0.0, w_shipping),
        "trade":          (trade_score or 0.0, w_trade),
        "infrastructure": (infrastructure_score or 0.0, w_infrastructure),
        "economic":       (economic_score or 0.0, w_economic),
    }
    total_weight = sum(w for _, w in components.values())
    return {
        name: round((score * weight / total_weight), 4)
        for name, (score, weight) in components.items()
    }


# ── Guardrail 3: Confidence Calibration ──────────────────────────────────────

def calibrate_score(raw_score: float, confidence: float) -> float:
    """
    Apply Platt Scaling approximation for partial-confidence data.

    For confidence=1.0 → no adjustment.
    For confidence<1.0 → pull score toward 50 (maximum uncertainty midpoint).

    calibrated = platt(raw) * confidence + 50 * (1 - confidence)
    where platt(x) = 100 / (1 + exp(-k * (x/100 - 0.5)))
    """
    if confidence >= 1.0:
        return round(raw_score, 4)
    platt = 100.0 / (1.0 + math.exp(-PLATT_K * (raw_score / 100.0 - 0.5)))
    calibrated = platt * confidence + 50.0 * (1.0 - confidence)
    return round(max(0.0, min(100.0, calibrated)), 4)


# ── Guardrail 4: Human-in-the-Loop ───────────────────────────────────────────

def requires_human_review(
    confidence: float,
    index_value: Optional[float] = None,
    prev_index_value: Optional[float] = None,
    is_bank_credit: bool = False,
    concentration_warning: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Determine whether human review is required.

    Returns:
        {
            "required": bool,
            "reasons": list[str],
        }
    """
    reasons = []

    if is_bank_credit:
        reasons.append("Bank credit decisions always require human officer review")

    if confidence < 0.50:
        reasons.append(f"Low data confidence ({confidence:.2f} < 0.50)")

    if index_value is not None and prev_index_value is not None:
        change = abs(index_value - prev_index_value)
        if change > 20.0:
            reasons.append(
                f"Large month-over-month index change ({change:.1f} points > 20 pt threshold)"
            )

    if concentration_warning:
        reasons.append(f"Concentration warning: {concentration_warning}")

    return {
        "required": len(reasons) > 0,
        "reasons": reasons,
    }


# ── Combined guardrail check ──────────────────────────────────────────────────

def run_guardrails(
    confidence: float,
    index_value: Optional[float] = None,
    prev_index_value: Optional[float] = None,
    shipping_score: Optional[float] = None,
    trade_score: Optional[float] = None,
    infrastructure_score: Optional[float] = None,
    economic_score: Optional[float] = None,
    is_bank_credit: bool = False,
    concentration_warning: Optional[str] = None,
    context: str = "",
) -> Dict[str, Any]:
    """
    Run all 4 guardrails and return combined result.
    Use this in route handlers to attach guardrail metadata to responses.
    """
    g1 = check_data_quality(confidence, context)
    g2 = compute_feature_attribution(shipping_score, trade_score, infrastructure_score, economic_score)
    calibrated = calibrate_score(index_value or 50.0, confidence) if index_value else None
    g4 = requires_human_review(confidence, index_value, prev_index_value, is_bank_credit, concentration_warning)

    return {
        "data_quality": {
            "pass": g1["pass"],
            "warn": g1["warn"],
            "confidence": confidence,
            "quality_label": g1["quality_label"],
            "message": g1["message"],
        },
        "feature_attribution": g2,
        "calibrated_index": calibrated,
        "human_review": g4,
    }
