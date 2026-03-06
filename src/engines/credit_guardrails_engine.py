"""
WASI Credit Guardrails Engine (expert model, no ML).

Implements:
- Weighted 7-component score
- Sovereign debt veto for BF/ML/NE/GN
- Mandatory human review + advisory disclaimer
"""
from __future__ import annotations

from dataclasses import dataclass

from src.utils.wacc_params import VALID_WASI_COUNTRIES

DISCLAIMER = "Advisory only. D\u00e9cision finale = validation humaine"

VALID_LOAN_TYPES = {
    "projet",
    "trade_finance",
    "dette_souveraine",
    "private_equity",
    "court_terme",
    "credit_bail",
    "microfinance",
}
SOVEREIGN_VETO_COUNTRIES = {"BF", "ML", "NE", "GN"}

COMPONENT_WEIGHTS: dict[str, float] = {
    "pays": 0.20,
    "politique": 0.15,
    "sectoriel": 0.15,
    "flux": 0.15,
    "corridor": 0.10,
    "emprunteur": 0.15,
    "change": 0.10,
}


@dataclass
class CreditDecisionInput:
    country: str
    loan_type: str
    components: dict[str, float]


def _validate_component(name: str, value: float) -> None:
    if not isinstance(value, (int, float)):
        raise ValueError(f"components.{name} must be numeric")
    if value < 0 or value > 100:
        raise ValueError(f"components.{name} must be between 0 and 100")


def _proposal_from_score(score: float) -> str:
    if score >= 75:
        return "APPROVE"
    if score >= 55:
        return "REVIEW"
    return "REJECT"


class WASIExpertScoringEngine:
    """Stateless expert scoring engine."""

    def evaluate(self, payload: CreditDecisionInput) -> dict:
        country = payload.country.upper().strip()
        loan_type = payload.loan_type.strip()

        if country not in VALID_WASI_COUNTRIES:
            raise ValueError(f"Country '{country}' is not in WASI ECOWAS set.")
        if loan_type not in VALID_LOAN_TYPES:
            allowed = ", ".join(sorted(VALID_LOAN_TYPES))
            raise ValueError(f"loan_type must be one of: {allowed}")

        for key in COMPONENT_WEIGHTS:
            if key not in payload.components:
                raise ValueError(f"components.{key} is required")
            _validate_component(key, float(payload.components[key]))

        if loan_type == "dette_souveraine" and country in SOVEREIGN_VETO_COUNTRIES:
            return {
                "decision_proposal": "VETOED",
                "score": 0.0,
                "veto_applied": True,
                "veto_reason": "dette_souveraine blocked for BF/ML/NE/GN",
                "human_review_required": True,
                "disclaimer": DISCLAIMER,
            }

        score = 0.0
        for key, weight in COMPONENT_WEIGHTS.items():
            score += float(payload.components[key]) * weight
        score = round(score, 2)

        return {
            "decision_proposal": _proposal_from_score(score),
            "score": score,
            "veto_applied": False,
            "veto_reason": None,
            "human_review_required": True,
            "disclaimer": DISCLAIMER,
        }
