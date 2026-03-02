"""
eCFA CBDC USSD Wallet Engine.

Extends the WASI USSD menu with option 6: eCFA Wallet.
Provides phone-based banking over USSD for feature phones.

Menu Structure (*384*WASI# → option 6):
  1. Solde (Check Balance) — requires PIN
  2. Envoyer (Send Money)
     → Enter recipient phone → Enter amount → Enter PIN → Confirm
  3. Payer marchand (Pay Merchant)
     → Enter merchant code → Enter amount → Enter PIN → Confirm
  4. Retrait / Dépôt (Cash In/Out)
     → 1=Dépôt 2=Retrait → Enter agent code → Enter amount → Enter PIN
  5. Historique (Transaction History — last 5)
  6. Mon compte (My Account)
     → 1=Changer PIN → 2=Statut KYC → 3=Créer portefeuille

Protocol: Africa's Talking CON/END style.
Privacy: phone numbers are SHA-256 hashed; raw MSISDNs are never stored.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Tuple

from sqlalchemy.orm import Session

from src.database.cbdc_models import CbdcWallet, CbdcTransaction, CbdcMerchant
from src.engines.ussd_engine import (
    _hash_phone, COUNTRY_CURRENCY, DEFAULT_FX_RATES,
)
from src.utils.cbdc_crypto import hash_pin, verify_pin, generate_wallet_id
from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

logger = logging.getLogger(__name__)

# Phone prefix → country code (reuse from ussd_engine)
PHONE_PREFIXES = {
    "225": "CI", "221": "SN", "223": "ML", "226": "BF",
    "229": "BJ", "228": "TG", "227": "NE", "245": "GW",
    "234": "NG", "233": "GH", "224": "GN", "232": "SL",
    "231": "LR", "220": "GM", "222": "MR", "238": "CV",
}


def _detect_country_from_phone(phone: str) -> str:
    """Detect country code from phone number prefix."""
    clean = phone.lstrip("+").replace(" ", "")
    for prefix, cc in PHONE_PREFIXES.items():
        if clean.startswith(prefix):
            return cc
    return "CI"  # default to Cote d'Ivoire (BCEAO HQ)


class CbdcUSSDEngine:
    """eCFA wallet operations over USSD."""

    def __init__(self, db: Session):
        self.db = db
        self.ledger = CbdcLedgerEngine(db)

    def handle_ecfa_menu(
        self, parts: list[str], phone_number: str, country_code: str
    ) -> Tuple[str, str]:
        """Handle the eCFA wallet sub-menu (option 6 from main WASI menu).

        Args:
            parts: Remaining text chain after "6" (e.g., ["1"] for balance).
            phone_number: Raw MSISDN for hashing.
            country_code: ISO-2 country code.

        Returns:
            (response_text, session_type)
        """
        phone_hash = _hash_phone(phone_number)

        if len(parts) == 0:
            return (
                "CON eCFA Portefeuille Digital\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "1. Solde\n"
                "2. Envoyer eCFA\n"
                "3. Payer marchand\n"
                "4. Retrait / Dépôt\n"
                "5. Historique\n"
                "6. Mon compte"
            ), "ECFA_MENU"

        choice = parts[0]

        if choice == "1":
            return self._handle_balance(parts[1:], phone_hash, country_code)
        elif choice == "2":
            return self._handle_send(parts[1:], phone_hash, phone_number, country_code)
        elif choice == "3":
            return self._handle_merchant_pay(parts[1:], phone_hash, country_code)
        elif choice == "4":
            return self._handle_cash_in_out(parts[1:], phone_hash, country_code)
        elif choice == "5":
            return self._handle_history(parts[1:], phone_hash)
        elif choice == "6":
            return self._handle_account(parts[1:], phone_hash, phone_number, country_code)
        else:
            return "END Option invalide.", "ERROR"

    # ------------------------------------------------------------------
    # 1. Solde (Balance)
    # ------------------------------------------------------------------

    def _handle_balance(self, parts: list[str], phone_hash: str,
                        country_code: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA. Composez 6*6*3 pour en créer un.", "ECFA_NO_WALLET"

        if len(parts) == 0:
            return "CON Entrez votre PIN:", "ECFA_BALANCE_PIN"

        pin = parts[0]
        if not self._verify_pin_safe(wallet, pin):
            return "END PIN incorrect.", "ECFA_BAD_PIN"

        currency = COUNTRY_CURRENCY.get(country_code, "XOF")
        return (
            f"END Solde eCFA\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Disponible: {wallet.available_balance_ecfa:,.0f} {currency}\n"
            f"En attente: {wallet.hold_amount_ecfa:,.0f} {currency}\n"
            f"Total: {wallet.balance_ecfa:,.0f} {currency}\n"
            f"Tier KYC: {wallet.kyc_tier}\n"
            f"Limite jour: {wallet.daily_limit_ecfa:,.0f} {currency}"
        ), "ECFA_BALANCE"

    # ------------------------------------------------------------------
    # 2. Envoyer (Send Money)
    # ------------------------------------------------------------------

    def _handle_send(self, parts: list[str], phone_hash: str,
                     sender_phone: str, country_code: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        currency = COUNTRY_CURRENCY.get(country_code, "XOF")

        if len(parts) == 0:
            return "CON Entrez le numéro du destinataire:", "ECFA_SEND_PHONE"

        if len(parts) == 1:
            return f"CON Montant en {currency}:", "ECFA_SEND_AMOUNT"

        if len(parts) == 2:
            return "CON Entrez votre PIN:", "ECFA_SEND_PIN"

        if len(parts) == 3:
            receiver_phone = parts[0]
            try:
                amount = float(parts[1])
            except ValueError:
                return "END Montant invalide.", "ERROR"
            pin = parts[2]

            if not self._verify_pin_safe(wallet, pin):
                return "END PIN incorrect.", "ECFA_BAD_PIN"

            # Find receiver wallet
            receiver_hash = _hash_phone(receiver_phone)
            receiver_wallet = self._find_wallet(receiver_hash)
            if not receiver_wallet:
                return "END Destinataire non trouvé.", "ECFA_SEND_NO_DEST"

            # Execute transfer
            try:
                result = self.ledger.transfer(
                    sender_wallet_id=wallet.wallet_id,
                    receiver_wallet_id=receiver_wallet.wallet_id,
                    amount_ecfa=amount,
                    tx_type="TRANSFER_P2P",
                    channel="USSD",
                    pin=pin,
                )
                return (
                    f"END Envoi réussi!\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Montant: {amount:,.0f} {currency}\n"
                    f"ID: {result['transaction_id'][:8]}...\n"
                    f"Nouveau solde: {result['sender_new_balance']:,.0f} {currency}"
                ), "ECFA_SEND_OK"
            except Exception as e:
                logger.error(f"eCFA USSD send failed: {e}")
                return f"END Échec: {str(e)[:80]}", "ECFA_SEND_FAIL"

        return "END Erreur de navigation.", "ERROR"

    # ------------------------------------------------------------------
    # 3. Payer marchand (Merchant Payment)
    # ------------------------------------------------------------------

    def _handle_merchant_pay(self, parts: list[str], phone_hash: str,
                             country_code: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        currency = COUNTRY_CURRENCY.get(country_code, "XOF")

        if len(parts) == 0:
            return "CON Entrez le code marchand:", "ECFA_MERCH_CODE"

        if len(parts) == 1:
            # Verify merchant exists
            merchant = self.db.query(CbdcMerchant).filter(
                CbdcMerchant.merchant_id == parts[0]
            ).first()
            if not merchant:
                # Try by ussd_code
                merchant = self.db.query(CbdcMerchant).filter(
                    CbdcMerchant.ussd_code == parts[0]
                ).first()
            name = merchant.business_name if merchant else "Marchand"
            return f"CON Payer {name}\nMontant en {currency}:", "ECFA_MERCH_AMOUNT"

        if len(parts) == 2:
            return "CON Entrez votre PIN:", "ECFA_MERCH_PIN"

        if len(parts) == 3:
            merchant_code = parts[0]
            try:
                amount = float(parts[1])
            except ValueError:
                return "END Montant invalide.", "ERROR"
            pin = parts[2]

            if not self._verify_pin_safe(wallet, pin):
                return "END PIN incorrect.", "ECFA_BAD_PIN"

            # Find merchant
            merchant = self.db.query(CbdcMerchant).filter(
                (CbdcMerchant.merchant_id == merchant_code) |
                (CbdcMerchant.ussd_code == merchant_code)
            ).first()
            if not merchant:
                return "END Marchand non trouvé.", "ECFA_MERCH_NOT_FOUND"

            try:
                result = self.ledger.transfer(
                    sender_wallet_id=wallet.wallet_id,
                    receiver_wallet_id=merchant.wallet_id,
                    amount_ecfa=amount,
                    tx_type="MERCHANT_PAYMENT",
                    channel="USSD",
                    pin=pin,
                    spending_category=merchant.business_type,
                )
                return (
                    f"END Paiement réussi!\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Marchand: {merchant.business_name}\n"
                    f"Montant: {amount:,.0f} {currency}\n"
                    f"ID: {result['transaction_id'][:8]}..."
                ), "ECFA_MERCH_OK"
            except Exception as e:
                logger.error(f"eCFA USSD merchant pay failed: {e}")
                return f"END Échec: {str(e)[:80]}", "ECFA_MERCH_FAIL"

        return "END Erreur de navigation.", "ERROR"

    # ------------------------------------------------------------------
    # 4. Retrait / Dépôt (Cash In / Cash Out)
    # ------------------------------------------------------------------

    def _handle_cash_in_out(self, parts: list[str], phone_hash: str,
                            country_code: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        currency = COUNTRY_CURRENCY.get(country_code, "XOF")

        if len(parts) == 0:
            return (
                "CON Opération:\n"
                "1. Dépôt (Cash In)\n"
                "2. Retrait (Cash Out)"
            ), "ECFA_CASHIO"

        if len(parts) == 1:
            return "CON Code agent:", "ECFA_CASHIO_AGENT"

        if len(parts) == 2:
            return f"CON Montant en {currency}:", "ECFA_CASHIO_AMOUNT"

        if len(parts) == 3:
            return "CON Entrez votre PIN:", "ECFA_CASHIO_PIN"

        if len(parts) == 4:
            operation = parts[0]  # 1=deposit, 2=withdrawal
            agent_code = parts[1]
            try:
                amount = float(parts[2])
            except ValueError:
                return "END Montant invalide.", "ERROR"
            pin = parts[3]

            if not self._verify_pin_safe(wallet, pin):
                return "END PIN incorrect.", "ECFA_BAD_PIN"

            # Find agent wallet
            agent_wallet = self.db.query(CbdcWallet).filter(
                CbdcWallet.wallet_type == "AGENT",
                CbdcWallet.institution_code == agent_code,
            ).first()
            if not agent_wallet:
                return "END Agent non trouvé.", "ECFA_CASHIO_NO_AGENT"

            try:
                if operation == "1":  # Cash In: agent → user
                    result = self.ledger.transfer(
                        sender_wallet_id=agent_wallet.wallet_id,
                        receiver_wallet_id=wallet.wallet_id,
                        amount_ecfa=amount,
                        tx_type="CASH_IN",
                        channel="USSD",
                        pin=pin,
                    )
                    op_name = "Dépôt"
                else:  # Cash Out: user → agent
                    result = self.ledger.transfer(
                        sender_wallet_id=wallet.wallet_id,
                        receiver_wallet_id=agent_wallet.wallet_id,
                        amount_ecfa=amount,
                        tx_type="CASH_OUT",
                        channel="USSD",
                        pin=pin,
                    )
                    op_name = "Retrait"

                return (
                    f"END {op_name} réussi!\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Montant: {amount:,.0f} {currency}\n"
                    f"ID: {result['transaction_id'][:8]}..."
                ), "ECFA_CASHIO_OK"
            except Exception as e:
                logger.error(f"eCFA USSD cash-in/out failed: {e}")
                return f"END Échec: {str(e)[:80]}", "ECFA_CASHIO_FAIL"

        return "END Erreur de navigation.", "ERROR"

    # ------------------------------------------------------------------
    # 5. Historique (Transaction History)
    # ------------------------------------------------------------------

    def _handle_history(self, parts: list[str], phone_hash: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        txs = self.db.query(CbdcTransaction).filter(
            (CbdcTransaction.sender_wallet_id == wallet.wallet_id) |
            (CbdcTransaction.receiver_wallet_id == wallet.wallet_id)
        ).order_by(CbdcTransaction.initiated_at.desc()).limit(5).all()

        if not txs:
            return "END Aucune transaction.", "ECFA_HISTORY_EMPTY"

        lines = ["END 5 dernières transactions:"]
        lines.append("━━━━━━━━━━━━━━━━━━")
        for tx in txs:
            direction = "→" if tx.sender_wallet_id == wallet.wallet_id else "←"
            dt = tx.initiated_at.strftime("%d/%m %H:%M") if tx.initiated_at else ""
            lines.append(
                f"{direction} {tx.amount_ecfa:,.0f} XOF | {tx.tx_type[:8]} | {dt}"
            )

        return "\n".join(lines), "ECFA_HISTORY"

    # ------------------------------------------------------------------
    # 6. Mon compte (Account)
    # ------------------------------------------------------------------

    def _handle_account(self, parts: list[str], phone_hash: str,
                        phone_number: str, country_code: str) -> Tuple[str, str]:
        if len(parts) == 0:
            return (
                "CON Mon compte eCFA:\n"
                "1. Changer PIN\n"
                "2. Statut KYC\n"
                "3. Créer portefeuille"
            ), "ECFA_ACCOUNT"

        if parts[0] == "1":
            return self._handle_change_pin(parts[1:], phone_hash)
        elif parts[0] == "2":
            return self._handle_kyc_status(phone_hash)
        elif parts[0] == "3":
            return self._handle_create_wallet(parts[1:], phone_hash, phone_number, country_code)
        else:
            return "END Option invalide.", "ERROR"

    def _handle_change_pin(self, parts: list[str], phone_hash: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        if len(parts) == 0:
            return "CON Ancien PIN:", "ECFA_PIN_OLD"
        if len(parts) == 1:
            return "CON Nouveau PIN (4-6 chiffres):", "ECFA_PIN_NEW"
        if len(parts) == 2:
            old_pin = parts[0]
            new_pin = parts[1]

            if not self._verify_pin_safe(wallet, old_pin):
                return "END Ancien PIN incorrect.", "ECFA_BAD_PIN"

            if len(new_pin) < 4 or len(new_pin) > 6 or not new_pin.isdigit():
                return "END PIN invalide. 4-6 chiffres requis.", "ECFA_PIN_INVALID"

            wallet.pin_hash = hash_pin(new_pin)
            from src.utils.cbdc_audit import log_pin_changed
            log_pin_changed(self.db, wallet.wallet_id, actor_channel="USSD")
            self.db.commit()

            return "END PIN changé avec succès!", "ECFA_PIN_CHANGED"

        return "END Erreur.", "ERROR"

    def _handle_kyc_status(self, phone_hash: str) -> Tuple[str, str]:
        wallet = self._find_wallet(phone_hash)
        if not wallet:
            return "END Pas de portefeuille eCFA.", "ECFA_NO_WALLET"

        tier_labels = {
            0: "Anonyme (50K/jour)",
            1: "Téléphone vérifié (500K/jour)",
            2: "ID vérifié (5M/jour)",
            3: "KYC complet (illimité)",
        }
        label = tier_labels.get(wallet.kyc_tier, "Inconnu")

        return (
            f"END Statut KYC\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Tier: {wallet.kyc_tier} — {label}\n"
            f"Statut: {wallet.status}\n"
            f"Pour monter de tier, visitez un agent eCFA."
        ), "ECFA_KYC_STATUS"

    def _handle_create_wallet(self, parts: list[str], phone_hash: str,
                              phone_number: str,
                              country_code: str) -> Tuple[str, str]:
        # Check if wallet already exists
        existing = self._find_wallet(phone_hash)
        if existing:
            return (
                f"END Portefeuille existant.\n"
                f"ID: {existing.wallet_id[:8]}...\n"
                f"Solde: {existing.balance_ecfa:,.0f} XOF"
            ), "ECFA_WALLET_EXISTS"

        if len(parts) == 0:
            return "CON Créer un portefeuille eCFA.\nChoisissez un PIN (4-6 chiffres):", "ECFA_CREATE_PIN"

        if len(parts) == 1:
            pin = parts[0]
            if len(pin) < 4 or len(pin) > 6 or not pin.isdigit():
                return "END PIN invalide. 4-6 chiffres requis.", "ECFA_PIN_INVALID"

            # Create wallet
            from src.database.models import Country
            country = self.db.query(Country).filter(
                Country.code == country_code
            ).first()
            if not country:
                return "END Pays non supporté.", "ECFA_COUNTRY_ERROR"

            wallet_id = generate_wallet_id()
            wallet = CbdcWallet(
                wallet_id=wallet_id,
                country_id=country.id,
                phone_hash=phone_hash,
                wallet_type="RETAIL",
                kyc_tier=0,
                daily_limit_ecfa=50_000.0,
                balance_limit_ecfa=200_000.0,
                pin_hash=hash_pin(pin),
                status="active",
            )
            self.db.add(wallet)

            from src.utils.cbdc_audit import log_wallet_created
            log_wallet_created(
                self.db, wallet_id, "RETAIL", country_code,
                actor_channel="USSD",
            )
            self.db.commit()

            return (
                f"END Portefeuille créé!\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"ID: {wallet_id[:8]}...\n"
                f"Tier: 0 (anonyme)\n"
                f"Limite: 50,000 XOF/jour\n"
                f"Gardez votre PIN en sécurité!"
            ), "ECFA_WALLET_CREATED"

        return "END Erreur.", "ERROR"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_wallet(self, phone_hash: str) -> CbdcWallet | None:
        """Find a retail wallet by phone hash."""
        return self.db.query(CbdcWallet).filter(
            CbdcWallet.phone_hash == phone_hash,
            CbdcWallet.wallet_type == "RETAIL",
        ).first()

    def _verify_pin_safe(self, wallet: CbdcWallet, pin: str) -> bool:
        """Verify PIN without raising exceptions (for USSD flow)."""
        if not wallet.pin_hash:
            return False
        try:
            return verify_pin(pin, wallet.pin_hash)
        except Exception:
            return False
