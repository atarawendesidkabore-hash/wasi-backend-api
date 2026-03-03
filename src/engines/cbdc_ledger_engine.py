"""
eCFA CBDC Core Ledger Engine.

The single source of truth for all eCFA monetary movement.
Every operation creates exactly 2 CbdcLedgerEntry rows (DEBIT + CREDIT).

Design invariants:
  1. Sum of all DEBITs == Sum of all CREDITs (system-wide)
  2. wallet.balance_ecfa == sum(CREDITs) - sum(DEBITs) for that wallet
  3. Ledger entries are NEVER updated or deleted
  4. Hash chain per wallet detects retroactive tampering
  5. All balance mutations go through _execute_double_entry()
  6. Wallet rows are locked (SELECT FOR UPDATE / WITH_FOR_UPDATE) during mutations

Thread-safety: relies on database-level row locking.
"""
import math
import uuid
from datetime import datetime, date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.database.cbdc_models import (
    CbdcWallet, CbdcLedgerEntry, CbdcTransaction, CbdcPolicy,
    KYC_TIER_LIMITS,
)
from src.utils.cbdc_crypto import (
    compute_entry_hash, verify_pin, verify_signature,
    generate_transaction_id, build_canonical_tx_data, generate_nonce,
)
from src.utils.cbdc_audit import (
    log_mint, log_burn, log_wallet_frozen, log_wallet_unfrozen,
)

# BCEAO SAR threshold (XOF) — ~25,000 USD
SAR_THRESHOLD_XOF = 15_000_000.0

# PIN lockout
MAX_PIN_ATTEMPTS = 3
PIN_LOCKOUT_MINUTES = 30


class CbdcLedgerEngine:
    """Core double-entry ledger engine for eCFA CBDC."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mint(self, central_bank_wallet_id: str, target_wallet_id: str,
             amount_ecfa: float, reference: str,
             memo: str | None = None,
             actor_ip: str | None = None) -> dict:
        """Central bank creates new eCFA.

        Only CENTRAL_BANK wallets can mint. Minting credits the target wallet
        and debits the central bank's reserve (accounting entry only — the CB
        reserve can go negative as it represents issuance authority).
        """
        cb_wallet = self._get_wallet(central_bank_wallet_id)
        target_wallet = self._get_wallet(target_wallet_id)

        if cb_wallet.wallet_type != "CENTRAL_BANK":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only CENTRAL_BANK wallets can mint eCFA",
            )
        if target_wallet.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target wallet is {target_wallet.status}",
            )
        if amount_ecfa <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mint amount must be positive",
            )

        # Balance limit check for non-CB wallets
        if target_wallet.wallet_type != "CENTRAL_BANK":
            self._check_balance_limit(target_wallet, amount_ecfa)

        tx_id = generate_transaction_id()
        now = datetime.utcnow()

        # Create transaction record
        tx = CbdcTransaction(
            transaction_id=tx_id,
            sender_wallet_id=central_bank_wallet_id,
            receiver_wallet_id=target_wallet_id,
            amount_ecfa=amount_ecfa,
            fee_ecfa=0.0,
            total_ecfa=amount_ecfa,
            tx_type="MINT",
            channel="ADMIN",
            status="completed",
            sender_country=self._get_country_code(cb_wallet),
            receiver_country=self._get_country_code(target_wallet),
            cobol_ref=self._generate_cobol_ref(tx_id),
            initiated_at=now,
            completed_at=now,
        )
        self.db.add(tx)

        # Execute double entry
        self._execute_double_entry(
            tx_id, central_bank_wallet_id, target_wallet_id,
            amount_ecfa, "MINT", "ADMIN",
            reference=reference, memo=memo,
        )

        # Audit
        log_mint(self.db, central_bank_wallet_id, target_wallet_id,
                 amount_ecfa, tx_id, actor_ip)

        self.db.commit()

        return {
            "transaction_id": tx_id,
            "status": "completed",
            "amount_ecfa": amount_ecfa,
            "target_wallet_id": target_wallet_id,
            "target_new_balance": target_wallet.balance_ecfa,
        }

    def burn(self, central_bank_wallet_id: str, source_wallet_id: str,
             amount_ecfa: float, reference: str,
             actor_ip: str | None = None) -> dict:
        """Central bank destroys eCFA."""
        cb_wallet = self._get_wallet(central_bank_wallet_id)
        source_wallet = self._get_wallet(source_wallet_id)

        if cb_wallet.wallet_type != "CENTRAL_BANK":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only CENTRAL_BANK wallets can burn eCFA",
            )
        if amount_ecfa <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Burn amount must be positive",
            )
        if source_wallet.available_balance_ecfa < amount_ecfa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient balance in source wallet",
            )

        tx_id = generate_transaction_id()
        now = datetime.utcnow()

        tx = CbdcTransaction(
            transaction_id=tx_id,
            sender_wallet_id=source_wallet_id,
            receiver_wallet_id=central_bank_wallet_id,
            amount_ecfa=amount_ecfa,
            fee_ecfa=0.0,
            total_ecfa=amount_ecfa,
            tx_type="BURN",
            channel="ADMIN",
            status="completed",
            sender_country=self._get_country_code(source_wallet),
            receiver_country=self._get_country_code(cb_wallet),
            cobol_ref=self._generate_cobol_ref(tx_id),
            initiated_at=now,
            completed_at=now,
        )
        self.db.add(tx)

        self._execute_double_entry(
            tx_id, source_wallet_id, central_bank_wallet_id,
            amount_ecfa, "BURN", "ADMIN",
            reference=reference,
        )

        log_burn(self.db, central_bank_wallet_id, source_wallet_id,
                 amount_ecfa, tx_id, actor_ip)

        self.db.commit()

        return {
            "transaction_id": tx_id,
            "status": "completed",
            "amount_ecfa": amount_ecfa,
            "source_wallet_id": source_wallet_id,
            "source_new_balance": source_wallet.balance_ecfa,
        }

    def transfer(self, sender_wallet_id: str, receiver_wallet_id: str,
                 amount_ecfa: float, tx_type: str = "TRANSFER_P2P",
                 channel: str = "API",
                 pin: str | None = None,
                 signature: str | None = None,
                 nonce: str | None = None,
                 policy_id: int | None = None,
                 spending_category: str | None = None,
                 memo: str | None = None,
                 fee_ecfa: float = 0.0,
                 _system_auth: bool = False) -> dict:
        """Execute a transfer between wallets.

        Validation chain:
          1. Sender wallet active, not frozen
          2. PIN verification (USSD) or signature verification (API)
          3. Sufficient available balance
          4. Daily limit check (KYC tier)
          5. Balance limit check on receiver
          6. Policy enforcement (spending restrictions)
          7. Execute double entry
        """
        # 0. Input validation — reject NaN, Inf, negative, zero, and self-transfers
        if not math.isfinite(amount_ecfa) or amount_ecfa <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transfer amount must be a positive finite number",
            )
        if not math.isfinite(fee_ecfa) or fee_ecfa < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fee must be a non-negative finite number",
            )
        if sender_wallet_id == receiver_wallet_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot transfer to the same wallet",
            )

        # Lock wallets in sorted ID order to prevent deadlocks
        ids = sorted([sender_wallet_id, receiver_wallet_id])
        w1 = self._get_wallet(ids[0])
        w2 = self._get_wallet(ids[1])
        sender = w1 if w1.wallet_id == sender_wallet_id else w2
        receiver = w1 if w1.wallet_id == receiver_wallet_id else w2

        # 1. Status checks
        if sender.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sender wallet is {sender.status}",
            )
        if receiver.status not in ("active", "pending_kyc"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Receiver wallet is {receiver.status}",
            )

        # 2. Authentication — mandatory for all channels
        if _system_auth:
            pass  # Internal system call (e.g. batch disbursements) — pre-authorized
        elif channel == "USSD":
            if not pin:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="PIN is required for USSD transfers",
                )
            self._verify_wallet_pin(sender, pin)
        elif channel == "API":
            if not signature or not sender.public_key_hex:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Signature and public key are required for API transfers",
                )
            if not nonce:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Nonce is required for signed API transfers",
                )
            tx_data = build_canonical_tx_data(
                sender_wallet_id, receiver_wallet_id, amount_ecfa, tx_type, nonce
            )
            if not verify_signature(sender.public_key_hex, tx_data, signature):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid transaction signature",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported channel: {channel}",
            )

        # 3. Balance check — refresh from DB to defeat race conditions
        self.db.refresh(sender)
        total = amount_ecfa + fee_ecfa
        if sender.available_balance_ecfa < total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient balance",
            )

        # 4. Daily limit
        self._check_daily_limit(sender, total)

        # 5. Receiver balance limit
        if receiver.wallet_type not in ("CENTRAL_BANK", "COMMERCIAL_BANK"):
            self._check_balance_limit(receiver, amount_ecfa)

        # 6. Policy enforcement
        if policy_id:
            self._enforce_policy(policy_id, spending_category, receiver)

        # 7. Execute
        tx_id = generate_transaction_id()
        now = datetime.utcnow()

        is_cross_border = self._get_country_code(sender) != self._get_country_code(receiver)

        tx = CbdcTransaction(
            transaction_id=tx_id,
            sender_wallet_id=sender_wallet_id,
            receiver_wallet_id=receiver_wallet_id,
            amount_ecfa=amount_ecfa,
            fee_ecfa=fee_ecfa,
            total_ecfa=total,
            tx_type=tx_type,
            channel=channel,
            status="completed",
            is_cross_border=is_cross_border,
            sender_country=self._get_country_code(sender),
            receiver_country=self._get_country_code(receiver),
            policy_id=policy_id,
            spending_category=spending_category,
            aml_status="cleared" if total < SAR_THRESHOLD_XOF else "flagged",
            kyc_tier_at_time=sender.kyc_tier,
            sender_signature=signature,
            cobol_ref=self._generate_cobol_ref(tx_id),
            initiated_at=now,
            completed_at=now,
        )
        self.db.add(tx)

        # Main transfer
        self._execute_double_entry(
            tx_id, sender_wallet_id, receiver_wallet_id,
            amount_ecfa, tx_type, channel, memo=memo,
        )

        # Fee (if any) — debit sender, credit CB/treasury
        if fee_ecfa > 0:
            # Find the central bank wallet for sender's country
            cb_wallet = self.db.query(CbdcWallet).filter(
                CbdcWallet.wallet_type == "CENTRAL_BANK",
                CbdcWallet.country_id == sender.country_id,
            ).first()
            if cb_wallet:
                self._execute_double_entry(
                    tx_id, sender_wallet_id, cb_wallet.wallet_id,
                    fee_ecfa, "FEE", channel,
                )

        # Update daily spent
        self._update_daily_spent(sender, total)

        self.db.commit()

        return {
            "transaction_id": tx_id,
            "status": "completed",
            "amount_ecfa": amount_ecfa,
            "fee_ecfa": fee_ecfa,
            "sender_wallet_id": sender_wallet_id,
            "receiver_wallet_id": receiver_wallet_id,
            "sender_new_balance": sender.balance_ecfa,
            "is_cross_border": is_cross_border,
        }

    def freeze_wallet(self, admin_wallet_id: str, target_wallet_id: str,
                      reason: str,
                      actor_ip: str | None = None) -> dict:
        """Freeze a wallet (compliance action)."""
        admin = self._get_wallet(admin_wallet_id)
        target = self._get_wallet(target_wallet_id)

        if admin.wallet_type not in ("CENTRAL_BANK", "COMMERCIAL_BANK"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only CENTRAL_BANK or COMMERCIAL_BANK wallets can freeze",
            )
        if target.status == "frozen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wallet is already frozen",
            )

        now = datetime.utcnow()
        target.status = "frozen"
        target.freeze_reason = reason
        target.frozen_at = now
        target.frozen_by = admin_wallet_id

        log_wallet_frozen(self.db, target_wallet_id, admin_wallet_id,
                          reason, actor_ip)
        self.db.commit()

        return {
            "wallet_id": target_wallet_id,
            "status": "frozen",
            "reason": reason,
            "frozen_at": now.isoformat(),
        }

    def unfreeze_wallet(self, admin_wallet_id: str, target_wallet_id: str,
                        actor_ip: str | None = None) -> dict:
        """Unfreeze a previously frozen wallet."""
        admin = self._get_wallet(admin_wallet_id)
        target = self._get_wallet(target_wallet_id)

        if admin.wallet_type not in ("CENTRAL_BANK", "COMMERCIAL_BANK"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only CENTRAL_BANK or COMMERCIAL_BANK wallets can unfreeze",
            )
        if target.status != "frozen":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Wallet is not frozen (status: {target.status})",
            )

        target.status = "active"
        target.freeze_reason = None
        target.frozen_at = None
        target.frozen_by = None

        log_wallet_unfrozen(self.db, target_wallet_id, admin_wallet_id, actor_ip)
        self.db.commit()

        return {"wallet_id": target_wallet_id, "status": "active"}

    def get_balance(self, wallet_id: str) -> dict:
        """Get wallet balance — both cached and ledger-verified."""
        wallet = self._get_wallet(wallet_id)

        # Recompute from ledger for verification
        credits = self.db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == wallet_id,
            CbdcLedgerEntry.entry_type == "CREDIT",
        ).all()
        debits = self.db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == wallet_id,
            CbdcLedgerEntry.entry_type == "DEBIT",
        ).all()

        ledger_balance = sum(e.amount_ecfa for e in credits) - sum(e.amount_ecfa for e in debits)

        return {
            "wallet_id": wallet_id,
            "balance_ecfa": wallet.balance_ecfa,
            "available_balance_ecfa": wallet.available_balance_ecfa,
            "hold_amount_ecfa": wallet.hold_amount_ecfa,
            "ledger_verified_balance": round(ledger_balance, 2),
            "balance_matches_ledger": abs(wallet.balance_ecfa - ledger_balance) < 0.01,
            "kyc_tier": wallet.kyc_tier,
            "daily_limit_ecfa": wallet.daily_limit_ecfa,
            "daily_spent_ecfa": wallet.daily_spent_ecfa,
            "status": wallet.status,
        }

    # ------------------------------------------------------------------
    # Internal Methods
    # ------------------------------------------------------------------

    def _get_wallet(self, wallet_id: str) -> CbdcWallet:
        """Fetch wallet with row-level lock for write operations."""
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == wallet_id
        ).with_for_update().first()
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wallet {wallet_id} not found",
            )
        return wallet

    def _execute_double_entry(self, transaction_id: str,
                               debit_wallet_id: str, credit_wallet_id: str,
                               amount: float, tx_type: str, channel: str,
                               reference: str | None = None,
                               memo: str | None = None) -> tuple:
        """Atomic double-entry execution.

        Lock order: sort wallet IDs to prevent deadlocks.
        """
        now = datetime.utcnow()

        # Fetch wallets in sorted order
        ids = sorted([debit_wallet_id, credit_wallet_id])
        w1 = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == ids[0]
        ).with_for_update().first()
        w2 = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == ids[1]
        ).with_for_update().first()

        debit_wallet = w1 if w1.wallet_id == debit_wallet_id else w2
        credit_wallet = w1 if w1.wallet_id == credit_wallet_id else w2

        # Atomic balance guard under row lock — prevents double-spend
        # Skip for CENTRAL_BANK wallets: minting creates money from nothing
        if debit_wallet.wallet_type != "CENTRAL_BANK" and debit_wallet.available_balance_ecfa < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient balance",
            )

        # Get previous hash for each wallet
        debit_prev = self._get_last_entry_hash(debit_wallet_id)
        credit_prev = self._get_last_entry_hash(credit_wallet_id)

        # DEBIT entry — subtract from sender
        debit_wallet.balance_ecfa -= amount
        debit_wallet.available_balance_ecfa -= amount
        debit_wallet.last_activity_at = now

        debit_hash = compute_entry_hash(
            debit_wallet_id, "DEBIT", amount, debit_wallet.balance_ecfa,
            tx_type, debit_prev, now.isoformat(),
        )
        debit_entry = CbdcLedgerEntry(
            entry_id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            wallet_id=debit_wallet_id,
            entry_type="DEBIT",
            amount_ecfa=amount,
            balance_after_ecfa=debit_wallet.balance_ecfa,
            tx_type=tx_type,
            counterparty_wallet_id=credit_wallet_id,
            reference=reference,
            memo=memo,
            country_code=self._get_country_code(debit_wallet),
            channel=channel,
            entry_hash=debit_hash,
            prev_entry_hash=debit_prev,
            created_at=now,
        )
        self.db.add(debit_entry)

        # CREDIT entry — add to receiver
        credit_wallet.balance_ecfa += amount
        credit_wallet.available_balance_ecfa += amount
        credit_wallet.last_activity_at = now

        credit_hash = compute_entry_hash(
            credit_wallet_id, "CREDIT", amount, credit_wallet.balance_ecfa,
            tx_type, credit_prev, now.isoformat(),
        )
        credit_entry = CbdcLedgerEntry(
            entry_id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            wallet_id=credit_wallet_id,
            entry_type="CREDIT",
            amount_ecfa=amount,
            balance_after_ecfa=credit_wallet.balance_ecfa,
            tx_type=tx_type,
            counterparty_wallet_id=debit_wallet_id,
            reference=reference,
            memo=memo,
            country_code=self._get_country_code(credit_wallet),
            channel=channel,
            entry_hash=credit_hash,
            prev_entry_hash=credit_prev,
            created_at=now,
        )
        self.db.add(credit_entry)

        return debit_entry, credit_entry

    def _get_last_entry_hash(self, wallet_id: str) -> str | None:
        """Get the hash of the most recent ledger entry for this wallet."""
        last = self.db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == wallet_id
        ).order_by(CbdcLedgerEntry.created_at.desc()).first()
        return last.entry_hash if last else None

    def _get_country_code(self, wallet: CbdcWallet) -> str:
        """Get ISO-2 country code from wallet's country relationship."""
        if wallet.country:
            return wallet.country.code
        return "XX"

    def _check_daily_limit(self, wallet: CbdcWallet, amount: float) -> None:
        """Check if transaction would exceed the wallet's daily limit."""
        today = date.today()
        if wallet.daily_reset_date != today:
            wallet.daily_spent_ecfa = 0.0
            wallet.daily_reset_date = today

        if wallet.daily_spent_ecfa + amount > wallet.daily_limit_ecfa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Daily limit exceeded. Limit: {wallet.daily_limit_ecfa:.0f} XOF, "
                       f"Already spent: {wallet.daily_spent_ecfa:.0f}, "
                       f"Attempted: {amount:.0f}",
            )

    def _check_balance_limit(self, wallet: CbdcWallet, incoming: float) -> None:
        """Check if receiving would exceed the wallet's balance limit."""
        if wallet.balance_ecfa + incoming > wallet.balance_limit_ecfa:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Balance limit exceeded for KYC Tier {wallet.kyc_tier}. "
                       f"Limit: {wallet.balance_limit_ecfa:.0f} XOF",
            )

    def _update_daily_spent(self, wallet: CbdcWallet, amount: float) -> None:
        """Update daily spent tracking."""
        today = date.today()
        if wallet.daily_reset_date != today:
            wallet.daily_spent_ecfa = amount
            wallet.daily_reset_date = today
        else:
            wallet.daily_spent_ecfa += amount

    def _verify_wallet_pin(self, wallet: CbdcWallet, pin: str) -> None:
        """Verify PIN with lockout protection."""
        from src.utils.cbdc_audit import log_pin_locked

        now = datetime.utcnow()

        # Check lockout
        if wallet.pin_locked_until and wallet.pin_locked_until > now:
            remaining = (wallet.pin_locked_until - now).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"PIN locked. Try again in {remaining + 1} minutes.",
            )

        if not wallet.pin_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No PIN set for this wallet. Set a PIN first.",
            )

        if not verify_pin(pin, wallet.pin_hash):
            wallet.pin_attempts += 1
            if wallet.pin_attempts >= MAX_PIN_ATTEMPTS:
                wallet.pin_locked_until = now + timedelta(minutes=PIN_LOCKOUT_MINUTES)
                wallet.pin_attempts = 0
                log_pin_locked(self.db, wallet.wallet_id)
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"PIN locked for {PIN_LOCKOUT_MINUTES} minutes after "
                           f"{MAX_PIN_ATTEMPTS} failed attempts.",
                )
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid PIN. {MAX_PIN_ATTEMPTS - wallet.pin_attempts} attempts remaining.",
            )

        # Success — reset attempts
        wallet.pin_attempts = 0
        wallet.pin_locked_until = None

    def _enforce_policy(self, policy_id: int, spending_category: str | None,
                        receiver: CbdcWallet) -> None:
        """Enforce programmable money policy on a transaction."""
        import json

        policy = self.db.query(CbdcPolicy).filter(
            CbdcPolicy.id == policy_id,
            CbdcPolicy.is_active == True,
        ).first()
        if not policy:
            return  # No active policy — allow

        now = datetime.utcnow()
        if policy.effective_until and policy.effective_until < now:
            return  # Expired policy

        conditions = json.loads(policy.conditions) if policy.conditions else {}

        if policy.policy_type == "SPENDING_RESTRICTION":
            allowed = conditions.get("allowed_categories", [])
            if allowed and spending_category not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Policy restriction: funds may only be spent on "
                           f"{', '.join(allowed)}. Got: {spending_category}",
                )

    def _generate_cobol_ref(self, tx_id: str) -> str:
        """Generate a SWIFT-compatible 35-character reference from UUID."""
        return tx_id.replace("-", "").upper()[:35]
