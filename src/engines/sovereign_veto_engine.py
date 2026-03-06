"""
Sovereign Credit Veto Engine -- BCEAO authority enforcement.

When a sovereign veto is active for a country:
- FULL_BLOCK: All credit scoring endpoints return 403
- PARTIAL: Credit allowed but capped at max_loan_cap_usd
"""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from src.database.sovereign_models import SovereignVeto

logger = logging.getLogger(__name__)

VETO_TYPES = {
    "SANCTIONS",        # International sanctions (UN, EU, ECOWAS)
    "DEBT_CEILING",     # Country exceeded UEMOA 70% debt-to-GDP ceiling
    "MONETARY_POLICY",  # BCEAO monetary policy restriction
    "POLITICAL_CRISIS", # Coup, civil unrest, unconstitutional change
    "AML_CFT",          # Anti-money laundering / counter-terrorism financing
}


def get_active_vetoes(country_code: str, db: Session) -> list[SovereignVeto]:
    """Retrieve all active, non-expired vetoes for a country."""
    today = date.today()
    return (
        db.query(SovereignVeto)
        .filter(
            SovereignVeto.country_code == country_code.upper(),
            SovereignVeto.is_active.is_(True),
            SovereignVeto.effective_date <= today,
        )
        .filter(
            (SovereignVeto.expiry_date.is_(None))
            | (SovereignVeto.expiry_date >= today)
        )
        .all()
    )


def check_sovereign_veto(
    country_code: str,
    db: Session,
    loan_amount_usd: Optional[float] = None,
) -> dict:
    """
    Check if a sovereign veto blocks or restricts credit for this country.

    Returns:
        {
            "blocked": bool,
            "partial": bool,
            "max_loan_cap_usd": float | None,
            "vetoes": list[dict],
            "message": str,
        }
    """
    vetoes = get_active_vetoes(country_code, db)
    if not vetoes:
        return {
            "blocked": False,
            "partial": False,
            "max_loan_cap_usd": None,
            "vetoes": [],
            "message": f"No sovereign veto active for {country_code.upper()}.",
        }

    full_blocks = [v for v in vetoes if v.severity == "FULL_BLOCK"]
    partials = [v for v in vetoes if v.severity == "PARTIAL"]

    veto_list = []
    for v in vetoes:
        veto_list.append({
            "id": v.id,
            "veto_type": v.veto_type,
            "severity": v.severity,
            "reason": v.reason,
            "issued_by": v.issued_by,
            "reference_number": v.reference_number,
            "effective_date": str(v.effective_date),
            "expiry_date": str(v.expiry_date) if v.expiry_date else None,
        })

    if full_blocks:
        reasons = "; ".join(v.reason for v in full_blocks)
        return {
            "blocked": True,
            "partial": False,
            "max_loan_cap_usd": 0.0,
            "vetoes": veto_list,
            "message": (
                f"SOVEREIGN VETO: Credit operations BLOCKED for {country_code.upper()}. "
                f"Authority: {full_blocks[0].issued_by}. Reason: {reasons}"
            ),
        }

    # Only partial vetoes
    caps = [v.max_loan_cap_usd for v in partials if v.max_loan_cap_usd is not None]
    effective_cap = min(caps) if caps else None

    exceeds = False
    if loan_amount_usd and effective_cap and loan_amount_usd > effective_cap:
        exceeds = True

    reasons = "; ".join(v.reason for v in partials)
    msg = f"SOVEREIGN ADVISORY: Partial restrictions on {country_code.upper()}. {reasons}"
    if effective_cap:
        msg += f" Max loan cap:  USD."
    if exceeds:
        msg += f" Requested amount  EXCEEDS cap."

    return {
        "blocked": exceeds,
        "partial": True,
        "max_loan_cap_usd": effective_cap,
        "vetoes": veto_list,
        "message": msg,
    }


def issue_veto(
    db: Session,
    country_code: str,
    veto_type: str,
    reason: str,
    issued_by: str,
    effective_date: date,
    expiry_date: Optional[date] = None,
    severity: str = "FULL_BLOCK",
    max_loan_cap_usd: Optional[float] = None,
    reference_number: Optional[str] = None,
    legal_basis: Optional[str] = None,
    issued_by_user_id: Optional[int] = None,
) -> SovereignVeto:
    """Issue a new sovereign veto. Admin-only operation."""
    if veto_type not in VETO_TYPES:
        raise ValueError(f"Invalid veto_type: {veto_type}. Must be one of {VETO_TYPES}")
    if severity not in ("FULL_BLOCK", "PARTIAL"):
        raise ValueError(f"Invalid severity: {severity}. Must be FULL_BLOCK or PARTIAL")

    veto = SovereignVeto(
        country_code=country_code.upper(),
        veto_type=veto_type,
        reason=reason,
        issued_by=issued_by,
        issued_by_user_id=issued_by_user_id,
        reference_number=reference_number,
        legal_basis=legal_basis,
        effective_date=effective_date,
        expiry_date=expiry_date,
        is_active=True,
        severity=severity,
        max_loan_cap_usd=max_loan_cap_usd,
    )
    db.add(veto)
    db.commit()
    db.refresh(veto)
    logger.warning(
        "SOVEREIGN VETO ISSUED: %s on %s by %s -- %s",
        veto_type, country_code.upper(), issued_by, reason,
    )
    return veto


def revoke_veto(
    db: Session,
    veto_id: int,
    revoked_by: str,
    revocation_reason: Optional[str] = None,
    revoked_by_user_id: Optional[int] = None,
) -> SovereignVeto:
    """Revoke an active veto. Admin-only operation."""
    from datetime import datetime, timezone
    veto = db.query(SovereignVeto).filter(SovereignVeto.id == veto_id).first()
    if not veto:
        raise ValueError(f"Veto {veto_id} not found")
    if not veto.is_active:
        raise ValueError(f"Veto {veto_id} is already revoked")
    veto.is_active = False
    veto.revoked_at = datetime.now(timezone.utc)
    veto.revoked_by = revoked_by
    veto.revoked_by_user_id = revoked_by_user_id
    veto.revocation_reason = revocation_reason
    db.commit()
    db.refresh(veto)
    logger.warning(
        "SOVEREIGN VETO REVOKED: id=%d, type=%s, country=%s by %s",
        veto_id, veto.veto_type, veto.country_code, revoked_by,
    )
    return veto
