"""
eCFA CBDC Immutable Audit Trail.

Every state change in the CBDC system is logged to CbdcAuditLog.
Entries are NEVER updated or deleted — append-only by design.

Covers: wallet lifecycle, KYC changes, freeze/unfreeze, policy changes,
admin actions, PIN events, mint/burn, settlement confirmations, AML alerts.
"""
import hashlib
import json
import uuid
from datetime import timezone, datetime

from sqlalchemy.orm import Session

from src.database.cbdc_models import CbdcAuditLog


def _compute_audit_hash(event_type: str, actor_wallet_id: str | None,
                        target_wallet_id: str | None, details: str | None,
                        created_at: str) -> str:
    """SHA-256 hash of audit entry for integrity verification."""
    payload = (
        f"{event_type}"
        f"|{actor_wallet_id or 'SYSTEM'}"
        f"|{target_wallet_id or 'NONE'}"
        f"|{details or ''}"
        f"|{created_at}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_audit_event(
    db: Session,
    event_type: str,
    *,
    actor_wallet_id: str | None = None,
    actor_ip: str | None = None,
    actor_channel: str = "API",
    target_wallet_id: str | None = None,
    target_entity_type: str | None = None,
    target_entity_id: str | None = None,
    details: dict | None = None,
) -> CbdcAuditLog:
    """Append an immutable audit log entry.

    Args:
        db: Database session.
        event_type: One of the defined event types (WALLET_CREATED, MINT_EXECUTED, etc.).
        actor_wallet_id: Wallet ID of the user/admin performing the action.
        actor_ip: IP address of the request (if available).
        actor_channel: API | USSD | BANK_GATEWAY | BATCH | ADMIN.
        target_wallet_id: Wallet affected by the action.
        target_entity_type: Type of entity affected (wallet, transaction, policy, kyc).
        target_entity_id: ID of the affected entity.
        details: Additional context as a dict (stored as JSON).

    Returns:
        The created CbdcAuditLog instance.
    """
    now = datetime.now(timezone.utc)
    details_json = json.dumps(details, default=str) if details else None

    entry_hash = _compute_audit_hash(
        event_type,
        actor_wallet_id,
        target_wallet_id,
        details_json,
        now.isoformat(),
    )

    audit_entry = CbdcAuditLog(
        audit_id=str(uuid.uuid4()),
        event_type=event_type,
        actor_wallet_id=actor_wallet_id,
        actor_ip=actor_ip,
        actor_channel=actor_channel,
        target_wallet_id=target_wallet_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        details=details_json,
        entry_hash=entry_hash,
        created_at=now,
    )
    db.add(audit_entry)
    return audit_entry


# Convenience wrappers for common events

def log_wallet_created(db: Session, wallet_id: str, wallet_type: str,
                       country_code: str, actor_channel: str = "API",
                       actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "WALLET_CREATED",
        target_wallet_id=wallet_id,
        target_entity_type="wallet",
        target_entity_id=wallet_id,
        actor_channel=actor_channel,
        actor_ip=actor_ip,
        details={"wallet_type": wallet_type, "country_code": country_code},
    )


def log_wallet_frozen(db: Session, target_wallet_id: str,
                      actor_wallet_id: str, reason: str,
                      actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "WALLET_FROZEN",
        actor_wallet_id=actor_wallet_id,
        target_wallet_id=target_wallet_id,
        target_entity_type="wallet",
        target_entity_id=target_wallet_id,
        actor_channel="ADMIN",
        actor_ip=actor_ip,
        details={"reason": reason},
    )


def log_wallet_unfrozen(db: Session, target_wallet_id: str,
                        actor_wallet_id: str,
                        actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "WALLET_UNFROZEN",
        actor_wallet_id=actor_wallet_id,
        target_wallet_id=target_wallet_id,
        target_entity_type="wallet",
        target_entity_id=target_wallet_id,
        actor_channel="ADMIN",
        actor_ip=actor_ip,
    )


def log_mint(db: Session, cb_wallet_id: str, target_wallet_id: str,
             amount_ecfa: float, transaction_id: str,
             actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "MINT_EXECUTED",
        actor_wallet_id=cb_wallet_id,
        target_wallet_id=target_wallet_id,
        target_entity_type="transaction",
        target_entity_id=transaction_id,
        actor_channel="ADMIN",
        actor_ip=actor_ip,
        details={"amount_ecfa": amount_ecfa},
    )


def log_burn(db: Session, cb_wallet_id: str, source_wallet_id: str,
             amount_ecfa: float, transaction_id: str,
             actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "BURN_EXECUTED",
        actor_wallet_id=cb_wallet_id,
        target_wallet_id=source_wallet_id,
        target_entity_type="transaction",
        target_entity_id=transaction_id,
        actor_channel="ADMIN",
        actor_ip=actor_ip,
        details={"amount_ecfa": amount_ecfa},
    )


def log_kyc_submitted(db: Session, wallet_id: str, tier_requested: int,
                      id_type: str | None = None,
                      actor_channel: str = "API") -> CbdcAuditLog:
    return log_audit_event(
        db, "KYC_SUBMITTED",
        target_wallet_id=wallet_id,
        target_entity_type="kyc",
        actor_channel=actor_channel,
        details={"tier_requested": tier_requested, "id_type": id_type},
    )


def log_kyc_approved(db: Session, wallet_id: str, tier_granted: int,
                     verified_by: str,
                     actor_ip: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "KYC_APPROVED",
        actor_wallet_id=verified_by,
        target_wallet_id=wallet_id,
        target_entity_type="kyc",
        actor_channel="ADMIN",
        actor_ip=actor_ip,
        details={"tier_granted": tier_granted},
    )


def log_pin_changed(db: Session, wallet_id: str,
                    actor_channel: str = "USSD") -> CbdcAuditLog:
    return log_audit_event(
        db, "PIN_CHANGED",
        target_wallet_id=wallet_id,
        target_entity_type="wallet",
        target_entity_id=wallet_id,
        actor_channel=actor_channel,
    )


def log_pin_locked(db: Session, wallet_id: str) -> CbdcAuditLog:
    return log_audit_event(
        db, "PIN_LOCKED",
        target_wallet_id=wallet_id,
        target_entity_type="wallet",
        target_entity_id=wallet_id,
        actor_channel="SYSTEM",
        details={"reason": "max_pin_attempts_exceeded"},
    )


def log_aml_alert_created(db: Session, wallet_id: str, alert_id: str,
                          alert_type: str, severity: str) -> CbdcAuditLog:
    return log_audit_event(
        db, "AML_ALERT_CREATED",
        target_wallet_id=wallet_id,
        target_entity_type="aml_alert",
        target_entity_id=alert_id,
        actor_channel="SYSTEM",
        details={"alert_type": alert_type, "severity": severity},
    )


def log_settlement_submitted(db: Session, settlement_id: str,
                             settlement_type: str, net_amount: float,
                             actor_wallet_id: str | None = None) -> CbdcAuditLog:
    return log_audit_event(
        db, "SETTLEMENT_SUBMITTED",
        actor_wallet_id=actor_wallet_id,
        target_entity_type="settlement",
        target_entity_id=settlement_id,
        actor_channel="BATCH",
        details={"settlement_type": settlement_type, "net_amount_ecfa": net_amount},
    )
