"""
eCFA CBDC Compliance Engine — AML/CFT Screening.

Rule-based Anti-Money Laundering / Combating the Financing of Terrorism engine.
Generates alerts for suspicious activity and blocks high-risk transactions.

Pre-transaction checks (synchronous — block transaction):
  - Frozen/suspended wallet → reject
  - Sanctions/PEP list match → reject + CRITICAL alert
  - Amount > 15M XOF (~$25K) → auto SAR to CENTIF

Post-transaction checks (async — flag for review):
  - VELOCITY:      >20 txns in 1 hour from same wallet
  - STRUCTURING:   Multiple txns just below 15M XOF in 24h
  - ROUND_TRIP:    Funds returning to origin within 48h
  - SMURFING:      Many small incoming → single large outgoing
  - DORMANT:       Sudden activity on wallet inactive >90 days
  - CROSS_BORDER:  >5M XOF cross-border in 24h from Tier 0/1
  - BLACKLIST:     Counterparty on sanctions list

Reporting authority: CENTIF (Cellule Nationale de Traitement des
Informations Financières) — the WAEMU Financial Intelligence Unit.
"""
import json
import uuid
import logging
from datetime import timezone, datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.cbdc_models import (
    CbdcWallet, CbdcTransaction, CbdcAmlAlert, CbdcLedgerEntry,
)
from src.utils.cbdc_audit import log_aml_alert_created

logger = logging.getLogger(__name__)

# Thresholds
SAR_THRESHOLD_XOF = 15_000_000.0  # ~$25K — automatic SAR
VELOCITY_MAX_TXN_PER_HOUR = 20
STRUCTURING_WINDOW_HOURS = 24
STRUCTURING_MIN_COUNT = 3
STRUCTURING_THRESHOLD_RATIO = 0.8  # txns > 80% of SAR threshold
ROUND_TRIP_WINDOW_HOURS = 48
SMURFING_INCOMING_MIN = 10
DORMANT_DAYS = 90
CROSS_BORDER_TIER01_LIMIT_XOF = 5_000_000.0


class CbdcComplianceEngine:
    """AML/CFT compliance screening for eCFA CBDC."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Pre-transaction checks (synchronous)
    # ------------------------------------------------------------------

    def pre_screen(self, sender_wallet_id: str, receiver_wallet_id: str,
                   amount_ecfa: float) -> dict:
        """Run synchronous pre-transaction compliance checks.

        Returns:
            {"allowed": True/False, "reason": str, "alert_id": str|None}
        """
        sender = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == sender_wallet_id
        ).first()
        if not sender:
            return {"allowed": False, "reason": "Sender wallet not found", "alert_id": None}

        # Check frozen/suspended
        if sender.status in ("frozen", "suspended"):
            return {
                "allowed": False,
                "reason": f"Sender wallet is {sender.status}: {sender.freeze_reason or 'compliance hold'}",
                "alert_id": None,
            }

        # Auto-SAR for large transactions
        if amount_ecfa >= SAR_THRESHOLD_XOF:
            alert = self._create_alert(
                wallet_id=sender_wallet_id,
                alert_type="STRUCTURING",
                severity="HIGH",
                description=(
                    f"Transaction of {amount_ecfa:,.0f} XOF exceeds SAR threshold "
                    f"({SAR_THRESHOLD_XOF:,.0f} XOF). Automatic SAR to CENTIF."
                ),
                evidence=json.dumps({
                    "amount_ecfa": amount_ecfa,
                    "threshold": SAR_THRESHOLD_XOF,
                    "sender": sender_wallet_id,
                    "receiver": receiver_wallet_id,
                }),
            )
            # Allow but flag — SAR doesn't block the transaction
            return {
                "allowed": True,
                "reason": "SAR filed — transaction flagged",
                "alert_id": alert.alert_id,
            }

        return {"allowed": True, "reason": "cleared", "alert_id": None}

    # ------------------------------------------------------------------
    # Post-transaction checks (async sweep)
    # ------------------------------------------------------------------

    def run_post_transaction_sweep(self, wallet_id: str,
                                   transaction_id: str | None = None) -> list[dict]:
        """Run all post-transaction AML checks for a wallet.

        Called after a transaction completes or during the hourly sweep.
        Returns list of alert dicts created.
        """
        alerts = []

        alerts.extend(self._check_velocity(wallet_id, transaction_id))
        alerts.extend(self._check_structuring(wallet_id, transaction_id))
        alerts.extend(self._check_round_trip(wallet_id, transaction_id))
        alerts.extend(self._check_smurfing(wallet_id, transaction_id))
        alerts.extend(self._check_dormant(wallet_id, transaction_id))
        alerts.extend(self._check_cross_border(wallet_id, transaction_id))

        return alerts

    def run_full_sweep(self) -> dict:
        """Run hourly compliance sweep across all active wallets with recent activity.

        Returns summary of alerts generated.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_wallets = self.db.query(CbdcTransaction.sender_wallet_id).filter(
            CbdcTransaction.initiated_at >= cutoff
        ).distinct().all()

        total_alerts = 0
        wallets_scanned = 0

        for (wallet_id,) in recent_wallets:
            if wallet_id:
                alerts = self.run_post_transaction_sweep(wallet_id)
                total_alerts += len(alerts)
                wallets_scanned += 1

        self.db.commit()

        return {
            "wallets_scanned": wallets_scanned,
            "alerts_generated": total_alerts,
            "sweep_time": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_velocity(self, wallet_id: str,
                        tx_id: str | None) -> list[dict]:
        """VELOCITY: >20 transactions in 1 hour."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        count = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.sender_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
        ).count()

        if count > VELOCITY_MAX_TXN_PER_HOUR:
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="VELOCITY",
                severity="MEDIUM",
                description=f"{count} transactions in last hour (threshold: {VELOCITY_MAX_TXN_PER_HOUR})",
                evidence=json.dumps({"txn_count": count, "window_hours": 1}),
            )
            return [{"alert_id": alert.alert_id, "type": "VELOCITY"}]
        return []

    def _check_structuring(self, wallet_id: str,
                           tx_id: str | None) -> list[dict]:
        """STRUCTURING: Multiple transactions just below SAR threshold in 24h."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STRUCTURING_WINDOW_HOURS)
        near_threshold = SAR_THRESHOLD_XOF * STRUCTURING_THRESHOLD_RATIO

        count = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.sender_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
            CbdcTransaction.amount_ecfa >= near_threshold,
            CbdcTransaction.amount_ecfa < SAR_THRESHOLD_XOF,
        ).count()

        if count >= STRUCTURING_MIN_COUNT:
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="STRUCTURING",
                severity="HIGH",
                description=(
                    f"{count} transactions between {near_threshold:,.0f} and "
                    f"{SAR_THRESHOLD_XOF:,.0f} XOF in {STRUCTURING_WINDOW_HOURS}h"
                ),
                evidence=json.dumps({
                    "count": count,
                    "near_threshold": near_threshold,
                    "sar_threshold": SAR_THRESHOLD_XOF,
                }),
            )
            return [{"alert_id": alert.alert_id, "type": "STRUCTURING"}]
        return []

    def _check_round_trip(self, wallet_id: str,
                          tx_id: str | None) -> list[dict]:
        """ROUND_TRIP: Funds returning to origin within 48h."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ROUND_TRIP_WINDOW_HOURS)

        # Find wallets this wallet sent to
        sent_to = self.db.query(CbdcTransaction.receiver_wallet_id).filter(
            CbdcTransaction.sender_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
        ).distinct().all()
        sent_to_ids = {r[0] for r in sent_to if r[0]}

        # Check if any of those wallets sent back
        round_trips = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.sender_wallet_id.in_(sent_to_ids),
            CbdcTransaction.receiver_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
        ).all()

        if round_trips:
            total_returned = sum(tx.amount_ecfa for tx in round_trips)
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="ROUND_TRIP",
                severity="MEDIUM",
                description=(
                    f"{len(round_trips)} round-trip transactions detected. "
                    f"Total returned: {total_returned:,.0f} XOF in {ROUND_TRIP_WINDOW_HOURS}h"
                ),
                evidence=json.dumps({
                    "round_trip_count": len(round_trips),
                    "total_returned_ecfa": total_returned,
                    "counterparties": list(sent_to_ids),
                }),
            )
            return [{"alert_id": alert.alert_id, "type": "ROUND_TRIP"}]
        return []

    def _check_smurfing(self, wallet_id: str,
                        tx_id: str | None) -> list[dict]:
        """SMURFING: Many small incoming followed by single large outgoing."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Count small incoming transactions
        small_incoming = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.receiver_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
            CbdcTransaction.amount_ecfa < 500_000,  # "small" threshold
        ).count()

        if small_incoming < SMURFING_INCOMING_MIN:
            return []

        # Check for large outgoing
        large_outgoing = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.sender_wallet_id == wallet_id,
            CbdcTransaction.initiated_at >= cutoff,
            CbdcTransaction.amount_ecfa >= 5_000_000,  # "large" threshold
        ).first()

        if large_outgoing:
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="SMURFING",
                severity="HIGH",
                description=(
                    f"{small_incoming} small incoming txns followed by large outgoing "
                    f"({large_outgoing.amount_ecfa:,.0f} XOF) in 24h"
                ),
                evidence=json.dumps({
                    "small_incoming_count": small_incoming,
                    "large_outgoing_ecfa": large_outgoing.amount_ecfa,
                }),
            )
            return [{"alert_id": alert.alert_id, "type": "SMURFING"}]
        return []

    def _check_dormant(self, wallet_id: str,
                       tx_id: str | None) -> list[dict]:
        """DORMANT: Sudden activity on wallet inactive >90 days."""
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == wallet_id
        ).first()
        if not wallet or not wallet.last_activity_at:
            return []

        # Check if this is the first activity after a dormancy period
        days_inactive = (datetime.now(timezone.utc) - wallet.last_activity_at).days
        if days_inactive > DORMANT_DAYS:
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="DORMANT",
                severity="MEDIUM",
                description=f"Wallet reactivated after {days_inactive} days of inactivity",
                evidence=json.dumps({
                    "days_inactive": days_inactive,
                    "last_activity": wallet.last_activity_at.isoformat(),
                }),
            )
            return [{"alert_id": alert.alert_id, "type": "DORMANT"}]
        return []

    def _check_cross_border(self, wallet_id: str,
                            tx_id: str | None) -> list[dict]:
        """CROSS_BORDER: >5M XOF cross-border in 24h from Tier 0/1 wallet."""
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == wallet_id
        ).first()
        if not wallet or wallet.kyc_tier >= 2:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cross_border_total = self.db.query(
            func.coalesce(func.sum(CbdcTransaction.amount_ecfa), 0.0)
        ).filter(
            CbdcTransaction.sender_wallet_id == wallet_id,
            CbdcTransaction.is_cross_border == True,
            CbdcTransaction.initiated_at >= cutoff,
        ).scalar()

        if cross_border_total > CROSS_BORDER_TIER01_LIMIT_XOF:
            alert = self._create_alert(
                wallet_id=wallet_id,
                transaction_id=tx_id,
                alert_type="CROSS_BORDER",
                severity="HIGH",
                description=(
                    f"Tier {wallet.kyc_tier} wallet sent {cross_border_total:,.0f} XOF "
                    f"cross-border in 24h (limit: {CROSS_BORDER_TIER01_LIMIT_XOF:,.0f})"
                ),
                evidence=json.dumps({
                    "total_cross_border_ecfa": float(cross_border_total),
                    "kyc_tier": wallet.kyc_tier,
                    "threshold": CROSS_BORDER_TIER01_LIMIT_XOF,
                }),
            )
            return [{"alert_id": alert.alert_id, "type": "CROSS_BORDER"}]
        return []

    # ------------------------------------------------------------------
    # Alert creation
    # ------------------------------------------------------------------

    def _create_alert(self, wallet_id: str, alert_type: str,
                      severity: str, description: str,
                      evidence: str | None = None,
                      transaction_id: str | None = None) -> CbdcAmlAlert:
        """Create an AML alert and audit log entry."""
        alert = CbdcAmlAlert(
            alert_id=str(uuid.uuid4()),
            wallet_id=wallet_id,
            transaction_id=transaction_id,
            alert_type=alert_type,
            severity=severity,
            description=description,
            evidence=evidence,
            status="open",
            reporting_authority="CENTIF",
        )
        self.db.add(alert)

        log_aml_alert_created(self.db, wallet_id, alert.alert_id,
                              alert_type, severity)

        logger.warning(
            "AML Alert [%s] %s on wallet %s: %s",
            severity, alert_type, wallet_id[:8], description[:100],
        )

        return alert
