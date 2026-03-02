"""
WASI-Pay Payment Router — Cross-Border Payment Orchestrator.

The brain of WASI-Pay. Determines the optimal payment path across
15 ECOWAS countries and executes the full payment lifecycle:

  WAEMU→WAEMU:     eCFA internal ledger (no FX, instant, 0.10% fee)
  WAEMU→non-WAEMU: eCFA debit → FX → external bridge stub (0.50% fee)
  non-WAEMU→WAEMU: external bridge → FX → eCFA credit (0.50% fee)
  non-WAEMU→non-WAEMU: chained via XOF (0.50% fee)

External bridge adapters (NIBSS, GhIPSS, etc.) are stubs for Phase 1.
Real integration comes when country agreements are signed.
"""
import uuid
import logging
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.database.cbdc_models import CbdcWallet, CbdcTransaction
from src.database.cbdc_payment_models import CbdcCrossBorderPayment
from src.engines.cbdc_fx_engine import (
    CbdcFxEngine, WAEMU_COUNTRIES, COUNTRY_CURRENCY,
)
from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
from src.engines.cbdc_compliance_engine import CbdcComplianceEngine
from src.utils.cbdc_audit import log_audit_event

logger = logging.getLogger(__name__)

# ── Fee Schedule ──────────────────────────────────────────────────────

PLATFORM_FEE_PCT = {
    "ECFA_INTERNAL": 0.001,       # 0.10%
    "ECFA_TO_EXTERNAL": 0.005,    # 0.50%
    "EXTERNAL_TO_ECFA": 0.005,    # 0.50%
    "EXTERNAL_BRIDGE": 0.005,     # 0.50%
}

EXTERNAL_RAIL_FEE_ECFA = {
    "NG": 500.0, "GH": 300.0, "GN": 200.0, "SL": 200.0,
    "LR": 200.0, "GM": 150.0, "MR": 250.0, "CV": 200.0,
}

SETTLEMENT_TIME_SEC = {
    "ECFA_INTERNAL": 5,
    "ECFA_TO_EXTERNAL": 3600,
    "EXTERNAL_TO_ECFA": 3600,
    "EXTERNAL_BRIDGE": 7200,
}

ALL_ECOWAS = sorted(COUNTRY_CURRENCY.keys())


class CbdcPaymentRouter:
    """Cross-border payment orchestrator for ECOWAS."""

    def __init__(self, db: Session):
        self.db = db
        self.fx_engine = CbdcFxEngine(db)
        self.ledger_engine = CbdcLedgerEngine(db)
        self.compliance_engine = CbdcComplianceEngine(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def determine_route(self, sender_country: str,
                        receiver_country: str) -> dict:
        """Determine the optimal payment rail."""
        sender_country = sender_country.upper()
        receiver_country = receiver_country.upper()

        s_waemu = sender_country in WAEMU_COUNTRIES
        r_waemu = receiver_country in WAEMU_COUNTRIES
        s_currency = COUNTRY_CURRENCY.get(sender_country, "XOF")
        r_currency = COUNTRY_CURRENCY.get(receiver_country, "XOF")

        if s_waemu and r_waemu:
            rail_type = "ECFA_INTERNAL"
            requires_fx = False
        elif s_waemu and not r_waemu:
            rail_type = "ECFA_TO_EXTERNAL"
            requires_fx = True
        elif not s_waemu and r_waemu:
            rail_type = "EXTERNAL_TO_ECFA"
            requires_fx = True
        else:
            rail_type = "EXTERNAL_BRIDGE"
            requires_fx = s_currency != r_currency

        rail_fee = 0.0
        if not s_waemu:
            rail_fee += EXTERNAL_RAIL_FEE_ECFA.get(sender_country, 200.0)
        if not r_waemu:
            rail_fee += EXTERNAL_RAIL_FEE_ECFA.get(receiver_country, 200.0)

        return {
            "rail_type": rail_type,
            "requires_fx": requires_fx,
            "source_currency": s_currency,
            "target_currency": r_currency,
            "platform_fee_pct": PLATFORM_FEE_PCT[rail_type] * 100,
            "rail_fee_ecfa": rail_fee,
            "estimated_settlement_sec": SETTLEMENT_TIME_SEC[rail_type],
            "description": f"{sender_country}→{receiver_country} via {rail_type}",
        }

    def get_quote(self, sender_wallet_id: str,
                  receiver_wallet_id: str | None,
                  receiver_country: str, amount: float,
                  source_currency: str, target_currency: str,
                  lock_rate: bool = True) -> dict:
        """Calculate fee/rate quote without executing."""
        sender_wallet = self._get_wallet(sender_wallet_id)
        sender_country = self._get_country_code(sender_wallet)
        receiver_country = receiver_country.upper()

        route = self.determine_route(sender_country, receiver_country)

        # Calculate amounts
        fx_rate = None
        fx_spread = None
        amount_target = amount
        spread_cost_ecfa = 0.0
        quote_id = None
        rate_expires_at = None

        if route["requires_fx"]:
            conversion = self.fx_engine.convert(
                amount, source_currency, target_currency
            )
            amount_target = conversion["amount_target"]
            fx_rate = conversion["rate_used"]
            fx_spread = conversion["spread_percent"]
            spread_cost_ecfa = conversion["spread_cost_ecfa"]

            # Lock rate if requested
            if lock_rate:
                # Determine which currency to lock
                lock_currency = (
                    target_currency if source_currency == "XOF" else source_currency
                )
                lock_amount = (
                    amount if source_currency == "XOF"
                    else conversion["amount_target"]
                )
                lock_result = self.fx_engine.lock_rate(lock_currency, lock_amount)
                quote_id = lock_result["lock_id"]
                rate_expires_at = lock_result["expires_at"]

        # Calculate fees
        amount_ecfa = (
            amount if source_currency == "XOF"
            else self.fx_engine.convert(amount, source_currency, "XOF")["amount_target"]
        )
        platform_fee = round(amount_ecfa * PLATFORM_FEE_PCT[route["rail_type"]], 2)
        rail_fee = route["rail_fee_ecfa"]
        total_cost = round(platform_fee + rail_fee + spread_cost_ecfa, 2)

        return {
            "quote_id": quote_id,
            "rail_type": route["rail_type"],
            "amount_source": amount,
            "source_currency": source_currency,
            "amount_target": round(amount_target, 2),
            "target_currency": target_currency,
            "fx_rate": fx_rate,
            "fx_spread_percent": fx_spread,
            "platform_fee_ecfa": platform_fee,
            "rail_fee_ecfa": rail_fee,
            "total_cost_ecfa": total_cost,
            "rate_expires_at": rate_expires_at,
            "estimated_settlement_sec": route["estimated_settlement_sec"],
        }

    def execute_payment(self, sender_wallet_id: str,
                        receiver_wallet_id: str | None,
                        receiver_country: str, amount: float,
                        source_currency: str, target_currency: str,
                        purpose: str | None = None,
                        pin: str | None = None,
                        quote_id: str | None = None) -> dict:
        """Execute a cross-border payment through the full state machine."""
        sender_wallet = self._get_wallet(sender_wallet_id)
        sender_country = self._get_country_code(sender_wallet)
        receiver_country = receiver_country.upper()
        source_currency = source_currency.upper()
        target_currency = target_currency.upper()

        route = self.determine_route(sender_country, receiver_country)
        payment_id = str(uuid.uuid4())

        # 1. INITIATED — Create payment record
        payment = CbdcCrossBorderPayment(
            payment_id=payment_id,
            sender_wallet_id=sender_wallet_id,
            sender_country=sender_country,
            receiver_wallet_id=receiver_wallet_id,
            receiver_country=receiver_country,
            amount_source=amount,
            source_currency=source_currency,
            target_currency=target_currency,
            rail_type=route["rail_type"],
            status="INITIATED",
            purpose=purpose,
        )
        self.db.add(payment)
        self.db.flush()

        self._log_event(payment, "CROSS_BORDER_INITIATED", {
            "rail_type": route["rail_type"],
            "amount": amount,
            "source_currency": source_currency,
            "target_currency": target_currency,
        })

        try:
            # 2. COMPLIANCE_CHECK
            self._update_status(payment, "COMPLIANCE_CHECK")
            if receiver_wallet_id:
                compliance = self.compliance_engine.pre_screen(
                    sender_wallet_id, receiver_wallet_id, amount
                )
            else:
                compliance = self.compliance_engine.pre_screen(
                    sender_wallet_id, sender_wallet_id, amount
                )

            if not compliance["allowed"]:
                payment.compliance_status = "blocked"
                payment.compliance_alert_id = compliance.get("alert_id")
                self._fail_payment(payment, f"Compliance blocked: {compliance['reason']}")
                self.db.commit()
                return self._payment_to_dict(payment, route)

            payment.compliance_status = "cleared"
            self._log_event(payment, "CROSS_BORDER_COMPLIANCE_CHECKED",
                            {"status": "cleared"})

            # 3. FX_LOCKED — Lock or consume rate
            fx_rate = None
            fx_spread = None
            amount_target = amount
            spread_cost_ecfa = 0.0

            if route["requires_fx"]:
                self._update_status(payment, "FX_LOCKED")

                if quote_id:
                    try:
                        lock_info = self.fx_engine.consume_rate_lock(
                            quote_id, payment_id
                        )
                        fx_rate = lock_info["rate"]
                        fx_spread = lock_info["spread_percent"]
                        payment.rate_lock_id = quote_id
                    except HTTPException:
                        # Lock expired or invalid — get fresh rate
                        pass

                if fx_rate is None:
                    conversion = self.fx_engine.convert(
                        amount, source_currency, target_currency
                    )
                    amount_target = conversion["amount_target"]
                    fx_rate = conversion["rate_used"]
                    fx_spread = conversion["spread_percent"]
                    spread_cost_ecfa = conversion["spread_cost_ecfa"]
                else:
                    # Use locked rate for conversion
                    if source_currency == "XOF":
                        spread_pct = fx_spread / 100.0
                        effective_rate = fx_rate * (1.0 + spread_pct)
                        amount_target = round(amount / effective_rate, 2)
                        spread_cost_ecfa = round(amount * spread_pct, 2)
                    else:
                        spread_pct = fx_spread / 100.0
                        effective_rate = fx_rate * (1.0 - spread_pct)
                        amount_target = round(amount * effective_rate, 2)
                        spread_cost_ecfa = round(amount * fx_rate * spread_pct, 2)

                payment.fx_rate_applied = fx_rate
                payment.fx_spread_applied = fx_spread
                payment.amount_target = amount_target

                self._log_event(payment, "CROSS_BORDER_FX_LOCKED", {
                    "rate": fx_rate, "spread": fx_spread,
                    "amount_target": amount_target,
                })
            else:
                payment.amount_target = amount

            # Calculate fees
            amount_ecfa = (
                amount if source_currency == "XOF"
                else amount_target if target_currency == "XOF"
                else amount  # fallback
            )
            platform_fee = round(
                amount_ecfa * PLATFORM_FEE_PCT[route["rail_type"]], 2
            )
            rail_fee = route["rail_fee_ecfa"]
            total_cost = round(platform_fee + rail_fee + spread_cost_ecfa, 2)

            payment.platform_fee_ecfa = platform_fee
            payment.rail_fee_ecfa = rail_fee
            payment.total_cost_ecfa = total_cost

            # 4. SOURCE_DEBITED
            self._update_status(payment, "SOURCE_DEBITED")

            if route["rail_type"] == "ECFA_INTERNAL":
                # Direct eCFA transfer
                if not receiver_wallet_id:
                    self._fail_payment(payment, "Receiver wallet required for WAEMU internal transfer")
                    self.db.commit()
                    return self._payment_to_dict(payment, route)

                tx_result = self.ledger_engine.transfer(
                    sender_wallet_id=sender_wallet_id,
                    receiver_wallet_id=receiver_wallet_id,
                    amount_ecfa=amount,
                    tx_type="TRANSFER_P2P",
                    channel="API",
                    pin=pin,
                    fee_ecfa=platform_fee,
                )
                payment.source_tx_id = tx_result["transaction_id"]
                payment.dest_tx_id = tx_result["transaction_id"]

                self._log_event(payment, "CROSS_BORDER_SOURCE_DEBITED", {
                    "tx_id": tx_result["transaction_id"],
                    "amount": amount,
                })

                # For internal, skip FX_CONVERTED and DEST_CREDITED
                self._update_status(payment, "SETTLED")
                payment.settled_at = datetime.utcnow()

            elif route["rail_type"] in ("ECFA_TO_EXTERNAL", "EXTERNAL_BRIDGE"):
                # Debit sender → BCEAO treasury (escrow)
                treasury = self._get_treasury_wallet(sender_country)
                tx_result = self.ledger_engine.transfer(
                    sender_wallet_id=sender_wallet_id,
                    receiver_wallet_id=treasury.wallet_id,
                    amount_ecfa=amount + platform_fee,
                    tx_type="CROSS_BORDER",
                    channel="API",
                    pin=pin,
                    fee_ecfa=0.0,
                )
                payment.source_tx_id = tx_result["transaction_id"]

                self._log_event(payment, "CROSS_BORDER_SOURCE_DEBITED", {
                    "tx_id": tx_result["transaction_id"],
                    "amount": amount + platform_fee,
                    "escrow": treasury.wallet_id,
                })

                # 5. FX_CONVERTED
                self._update_status(payment, "FX_CONVERTED")
                if route["requires_fx"]:
                    direction = "BUY" if source_currency == "XOF" else "SELL"
                    fx_currency = (
                        target_currency if source_currency == "XOF"
                        else source_currency
                    )
                    self.fx_engine.update_position(fx_currency, amount_ecfa, direction)

                # 6. DEST_CREDITED — External bridge stub
                self._update_status(payment, "DEST_CREDITED")
                bridge_result = self._external_bridge_send(
                    payment, amount_target, target_currency
                )
                payment.external_bridge_ref = bridge_result["bridge_ref"]

                self._log_event(payment, "CROSS_BORDER_DEST_CREDITED", {
                    "amount": amount_target,
                    "currency": target_currency,
                    "bridge_ref": bridge_result["bridge_ref"],
                    "simulated": bridge_result["simulated"],
                })

                # 7. SETTLED
                self._update_status(payment, "SETTLED")
                payment.settled_at = datetime.utcnow()

            elif route["rail_type"] == "EXTERNAL_TO_ECFA":
                # External bridge receive stub → mint/credit receiver eCFA
                bridge_result = self._external_bridge_receive(
                    payment, amount, source_currency
                )
                payment.external_bridge_ref = bridge_result["bridge_ref"]

                # Credit receiver from BCEAO treasury
                if receiver_wallet_id:
                    receiver_wallet = self._get_wallet(receiver_wallet_id)
                    r_country = self._get_country_code(receiver_wallet)
                    treasury = self._get_treasury_wallet(r_country)

                    tx_result = self.ledger_engine.transfer(
                        sender_wallet_id=treasury.wallet_id,
                        receiver_wallet_id=receiver_wallet_id,
                        amount_ecfa=amount_target,
                        tx_type="CROSS_BORDER",
                        channel="API",
                        fee_ecfa=0.0,
                    )
                    payment.source_tx_id = bridge_result["bridge_ref"]
                    payment.dest_tx_id = tx_result["transaction_id"]

                self._update_status(payment, "SETTLED")
                payment.settled_at = datetime.utcnow()

            self._log_event(payment, "CROSS_BORDER_SETTLED", {
                "total_cost_ecfa": total_cost,
            })

            self.db.commit()
            return self._payment_to_dict(payment, route)

        except HTTPException as e:
            self._fail_payment(payment, e.detail)
            self.db.commit()
            return self._payment_to_dict(payment, route)
        except Exception as e:
            logger.error("Payment %s failed: %s", payment_id, str(e))
            self._fail_payment(payment, str(e))
            self.db.commit()
            return self._payment_to_dict(payment, route)

    def get_payment_status(self, payment_id: str) -> dict:
        """Get current status of a cross-border payment."""
        payment = self.db.query(CbdcCrossBorderPayment).filter(
            CbdcCrossBorderPayment.payment_id == payment_id,
        ).first()

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment {payment_id} not found",
            )

        return {
            "payment_id": payment.payment_id,
            "status": payment.status,
            "rail_type": payment.rail_type,
            "sender_country": payment.sender_country,
            "receiver_country": payment.receiver_country,
            "amount_source": payment.amount_source,
            "source_currency": payment.source_currency,
            "amount_target": payment.amount_target,
            "target_currency": payment.target_currency,
            "compliance_status": payment.compliance_status,
            "created_at": payment.created_at,
            "updated_at": payment.updated_at,
            "settled_at": payment.settled_at,
            "failure_reason": payment.failure_reason,
        }

    def get_payment_trace(self, payment_id: str) -> dict:
        """Get detailed trace of payment path."""
        payment = self.db.query(CbdcCrossBorderPayment).filter(
            CbdcCrossBorderPayment.payment_id == payment_id,
        ).first()

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment {payment_id} not found",
            )

        hops = []

        # Hop 1: Compliance
        hops.append({
            "step": 1, "hop_type": "COMPLIANCE_CHECK",
            "status": payment.compliance_status or "pending",
            "timestamp": payment.created_at,
        })

        # Hop 2: FX lock (if applicable)
        if payment.fx_rate_applied:
            hops.append({
                "step": 2, "hop_type": "FX_LOCK",
                "amount": payment.amount_source,
                "currency": payment.source_currency,
                "status": "locked",
                "timestamp": payment.created_at,
                "details": {
                    "rate": payment.fx_rate_applied,
                    "spread": payment.fx_spread_applied,
                },
            })

        # Hop 3: Source debit
        if payment.source_tx_id:
            hops.append({
                "step": 3, "hop_type": "SOURCE_DEBIT",
                "amount": payment.amount_source,
                "currency": payment.source_currency,
                "status": "completed",
                "timestamp": payment.updated_at,
            })

        # Hop 4: FX conversion
        if payment.fx_rate_applied and payment.amount_target:
            hops.append({
                "step": 4, "hop_type": "FX_CONVERSION",
                "amount": payment.amount_target,
                "currency": payment.target_currency,
                "status": "completed",
                "timestamp": payment.updated_at,
                "details": {
                    "from_amount": payment.amount_source,
                    "to_amount": payment.amount_target,
                    "rate": payment.fx_rate_applied,
                },
            })

        # Hop 5: Destination credit
        if payment.status in ("DEST_CREDITED", "SETTLED"):
            hops.append({
                "step": 5, "hop_type": "DEST_CREDIT",
                "amount": payment.amount_target or payment.amount_source,
                "currency": payment.target_currency,
                "status": "completed",
                "timestamp": payment.settled_at or payment.updated_at,
            })

        # Hop 6: Settlement
        if payment.status == "SETTLED":
            hops.append({
                "step": 6, "hop_type": "SETTLEMENT",
                "status": "settled",
                "timestamp": payment.settled_at,
                "details": {
                    "bridge_ref": payment.external_bridge_ref,
                    "star_uemoa_ref": payment.star_uemoa_ref,
                },
            })

        return {
            "payment_id": payment.payment_id,
            "status": payment.status,
            "rail_type": payment.rail_type,
            "hops": hops,
        }

    def list_corridors(self) -> list[dict]:
        """List available payment corridors with fees."""
        corridors = []
        for src in ALL_ECOWAS:
            for dst in ALL_ECOWAS:
                if src == dst:
                    continue
                route = self.determine_route(src, dst)
                # Phase 1: only corridors with at least one WAEMU end
                available = (
                    src in WAEMU_COUNTRIES or dst in WAEMU_COUNTRIES
                )
                corridors.append({
                    "source_country": src,
                    "dest_country": dst,
                    "source_currency": route["source_currency"],
                    "dest_currency": route["target_currency"],
                    "rail_type": route["rail_type"],
                    "requires_fx": route["requires_fx"],
                    "platform_fee_pct": route["platform_fee_pct"],
                    "rail_fee_ecfa": route["rail_fee_ecfa"],
                    "estimated_settlement_sec": route["estimated_settlement_sec"],
                    "available": available,
                })
        return corridors

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_wallet(self, wallet_id: str) -> CbdcWallet:
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == wallet_id,
        ).first()
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wallet {wallet_id} not found",
            )
        return wallet

    def _get_country_code(self, wallet: CbdcWallet) -> str:
        if wallet.country:
            return wallet.country.code
        return "XX"

    def _get_treasury_wallet(self, country_code: str) -> CbdcWallet:
        """Get the BCEAO treasury wallet for a WAEMU country."""
        from src.database.models import Country
        country = self.db.query(Country).filter(
            Country.code == country_code,
        ).first()
        if not country:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Country {country_code} not found",
            )
        treasury = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_type == "CENTRAL_BANK",
            CbdcWallet.country_id == country.id,
        ).first()
        if not treasury:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No treasury wallet for {country_code}",
            )
        return treasury

    def _external_bridge_send(self, payment: CbdcCrossBorderPayment,
                              amount_local: float,
                              currency: str) -> dict:
        """STUB: Simulate sending via external rail (NIBSS, GhIPSS, etc.)."""
        bridge_ref = f"BRIDGE-{payment.receiver_country}-{uuid.uuid4().hex[:12].upper()}"
        logger.info(
            "STUB: External bridge send %s %.2f %s → %s (ref=%s)",
            payment.payment_id, amount_local, currency,
            payment.receiver_country, bridge_ref,
        )
        return {
            "bridge_ref": bridge_ref,
            "status": "completed",
            "simulated": True,
        }

    def _external_bridge_receive(self, payment: CbdcCrossBorderPayment,
                                 amount: float,
                                 currency: str) -> dict:
        """STUB: Simulate receiving from external rail."""
        bridge_ref = f"BRIDGE-{payment.sender_country}-{uuid.uuid4().hex[:12].upper()}"
        logger.info(
            "STUB: External bridge receive %s %.2f %s from %s (ref=%s)",
            payment.payment_id, amount, currency,
            payment.sender_country, bridge_ref,
        )
        return {
            "bridge_ref": bridge_ref,
            "status": "completed",
            "simulated": True,
        }

    def _update_status(self, payment: CbdcCrossBorderPayment,
                       new_status: str) -> None:
        payment.status = new_status
        payment.updated_at = datetime.utcnow()

    def _fail_payment(self, payment: CbdcCrossBorderPayment,
                      reason: str) -> None:
        payment.status = "FAILED"
        payment.failure_reason = reason
        payment.updated_at = datetime.utcnow()
        self._log_event(payment, "CROSS_BORDER_FAILED", {"reason": reason})

    def _log_event(self, payment: CbdcCrossBorderPayment,
                   event_type: str, details: dict | None = None) -> None:
        log_audit_event(
            self.db, event_type,
            actor_wallet_id=payment.sender_wallet_id,
            target_entity_type="cross_border_payment",
            target_entity_id=payment.payment_id,
            actor_channel="API",
            details=details,
        )

    def _payment_to_dict(self, payment: CbdcCrossBorderPayment,
                         route: dict) -> dict:
        return {
            "payment_id": payment.payment_id,
            "status": payment.status,
            "rail_type": payment.rail_type,
            "amount_source": payment.amount_source,
            "source_currency": payment.source_currency,
            "amount_target": payment.amount_target,
            "target_currency": payment.target_currency,
            "fx_rate_applied": payment.fx_rate_applied,
            "platform_fee_ecfa": payment.platform_fee_ecfa,
            "rail_fee_ecfa": payment.rail_fee_ecfa,
            "total_cost_ecfa": payment.total_cost_ecfa,
            "source_tx_id": payment.source_tx_id,
            "dest_tx_id": payment.dest_tx_id,
            "estimated_settlement_sec": route["estimated_settlement_sec"],
            "failure_reason": payment.failure_reason,
            "created_at": payment.created_at,
        }
