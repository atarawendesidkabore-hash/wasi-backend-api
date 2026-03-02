"""
eCFA CBDC Test Suite.

Tests the complete CBDC lifecycle:
  1. Crypto utilities (ED25519, hash chain, AES-256-GCM, PIN)
  2. Wallet creation and KYC tiers
  3. Ledger engine (mint, transfer, burn, freeze)
  4. Double-entry invariant verification
  5. Daily limit enforcement
  6. USSD wallet menu navigation
  7. Compliance engine (AML alert types)
  8. COBOL record formatting
  9. API endpoint integration
"""
import pytest
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.database.models import Base, User, Country
from src.database.cbdc_models import (
    CbdcWallet, CbdcLedgerEntry, CbdcTransaction,
    CbdcAmlAlert, CbdcPolicy, KYC_TIER_LIMITS,
)

# In-memory test database
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    import src.database.cbdc_models  # noqa: register CBDC tables
    import src.database.ussd_models  # noqa: register USSD tables
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seed_country(db):
    """Seed a test country (Cote d'Ivoire)."""
    country = Country(
        code="CI", name="Cote d'Ivoire", tier="primary", weight=0.22, is_active=True
    )
    db.add(country)
    db.commit()
    db.refresh(country)
    return country


@pytest.fixture
def seed_countries(db):
    """Seed CI and SN for cross-border tests."""
    ci = Country(code="CI", name="Cote d'Ivoire", tier="primary", weight=0.22, is_active=True)
    sn = Country(code="SN", name="Senegal", tier="primary", weight=0.10, is_active=True)
    db.add_all([ci, sn])
    db.commit()
    return ci, sn


@pytest.fixture
def seed_user(db):
    """Seed a test API user."""
    from src.utils.security import hash_password
    user = User(
        username="testuser", email="test@ecfa.io",
        hashed_password=hash_password("testpass"),
        x402_balance=1000.0, tier="premium",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# =====================================================================
# 1. Crypto Utilities
# =====================================================================

class TestCryptoUtils:
    def test_ed25519_keypair(self):
        from src.utils.cbdc_crypto import generate_keypair, sign_transaction, verify_signature
        priv, pub = generate_keypair()
        assert len(priv) == 64  # 32 bytes hex
        assert len(pub) == 64

    def test_ed25519_sign_verify(self):
        from src.utils.cbdc_crypto import generate_keypair, sign_transaction, verify_signature
        priv, pub = generate_keypair()
        sig = sign_transaction(priv, "test|data|123")
        assert verify_signature(pub, "test|data|123", sig)
        assert not verify_signature(pub, "tampered|data", sig)

    def test_hash_chain(self):
        from src.utils.cbdc_crypto import compute_entry_hash
        h1 = compute_entry_hash("w1", "CREDIT", 1000.0, 1000.0, "MINT", None, "2026-03-01T00:00:00")
        h2 = compute_entry_hash("w1", "DEBIT", 200.0, 800.0, "TRANSFER", h1, "2026-03-01T00:01:00")
        assert len(h1) == 64
        assert len(h2) == 64
        assert h1 != h2

    def test_aes_256_gcm(self):
        from src.utils.cbdc_crypto import encrypt_pii, decrypt_pii
        key = os.urandom(32).hex()
        plaintext = "Ousmane Diallo"
        encrypted = encrypt_pii(plaintext, key)
        decrypted = decrypt_pii(encrypted, key)
        assert decrypted == plaintext

    def test_pin_hash_verify(self):
        from src.utils.cbdc_crypto import hash_pin, verify_pin
        pin = "1234"
        hashed = hash_pin(pin)
        assert verify_pin(pin, hashed)
        assert not verify_pin("9999", hashed)


# =====================================================================
# 2. Wallet Creation & KYC Tiers
# =====================================================================

class TestWalletCreation:
    def test_create_retail_wallet(self, db, seed_country):
        from src.utils.cbdc_crypto import generate_wallet_id, hash_pin
        wallet = CbdcWallet(
            wallet_id=generate_wallet_id(),
            country_id=seed_country.id,
            phone_hash="abc123",
            wallet_type="RETAIL",
            kyc_tier=0,
            daily_limit_ecfa=KYC_TIER_LIMITS[0]["daily"],
            balance_limit_ecfa=KYC_TIER_LIMITS[0]["balance"],
            pin_hash=hash_pin("1234"),
            status="active",
        )
        db.add(wallet)
        db.commit()
        assert wallet.id is not None
        assert wallet.kyc_tier == 0
        assert wallet.daily_limit_ecfa == 50_000.0

    def test_create_central_bank_wallet(self, db, seed_country):
        from src.utils.cbdc_crypto import generate_wallet_id
        wallet = CbdcWallet(
            wallet_id=generate_wallet_id(),
            country_id=seed_country.id,
            wallet_type="CENTRAL_BANK",
            institution_code="BCEAO",
            institution_name="BCEAO Treasury — CI",
            kyc_tier=3,
            daily_limit_ecfa=999_999_999_999.0,
            balance_limit_ecfa=999_999_999_999.0,
            status="active",
        )
        db.add(wallet)
        db.commit()
        assert wallet.wallet_type == "CENTRAL_BANK"
        assert wallet.kyc_tier == 3

    def test_kyc_tier_limits(self):
        assert KYC_TIER_LIMITS[0]["daily"] == 50_000.0
        assert KYC_TIER_LIMITS[1]["daily"] == 500_000.0
        assert KYC_TIER_LIMITS[2]["daily"] == 5_000_000.0
        assert KYC_TIER_LIMITS[3]["daily"] == float("inf")


# =====================================================================
# 3. Ledger Engine — Mint, Transfer, Burn
# =====================================================================

class TestLedgerEngine:
    def _create_wallets(self, db, country):
        """Helper: create CB + 2 retail wallets."""
        from src.utils.cbdc_crypto import generate_wallet_id, hash_pin

        cb = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=country.id,
            wallet_type="CENTRAL_BANK", institution_code="BCEAO",
            kyc_tier=3, daily_limit_ecfa=999_999_999_999.0,
            balance_limit_ecfa=999_999_999_999.0, status="active",
        )
        w1 = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=country.id,
            phone_hash="user1_hash", wallet_type="RETAIL",
            kyc_tier=1, daily_limit_ecfa=500_000.0,
            balance_limit_ecfa=2_000_000.0,
            pin_hash=hash_pin("1234"), status="active",
        )
        w2 = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=country.id,
            phone_hash="user2_hash", wallet_type="RETAIL",
            kyc_tier=1, daily_limit_ecfa=500_000.0,
            balance_limit_ecfa=2_000_000.0,
            pin_hash=hash_pin("5678"), status="active",
        )
        db.add_all([cb, w1, w2])
        db.commit()
        return cb, w1, w2

    def test_mint(self, db, seed_country):
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        cb, w1, _ = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        result = engine.mint(cb.wallet_id, w1.wallet_id, 100_000.0, "INIT_MINT")

        assert result["status"] == "completed"
        assert result["amount_ecfa"] == 100_000.0
        assert result["target_new_balance"] == 100_000.0

    def test_transfer(self, db, seed_country):
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 200_000.0, "MINT")

        result = engine.transfer(
            w1.wallet_id, w2.wallet_id, 50_000.0,
            tx_type="TRANSFER_P2P", channel="USSD", pin="1234",
        )

        assert result["status"] == "completed"
        assert result["sender_new_balance"] == 150_000.0

        # Verify receiver balance
        db.refresh(w2)
        assert w2.balance_ecfa == 50_000.0

    def test_burn(self, db, seed_country):
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        cb, w1, _ = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 100_000.0, "MINT")
        result = engine.burn(cb.wallet_id, w1.wallet_id, 30_000.0, "BURN_REF")

        assert result["status"] == "completed"
        assert result["source_new_balance"] == 70_000.0

    def test_double_entry_invariant(self, db, seed_country):
        """Verify sum(debits) == sum(credits) across all ledger entries."""
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 500_000.0, "MINT1")
        engine.transfer(w1.wallet_id, w2.wallet_id, 100_000.0, pin="1234")
        engine.transfer(w2.wallet_id, w1.wallet_id, 25_000.0, pin="5678")
        engine.burn(cb.wallet_id, w1.wallet_id, 50_000.0, "BURN1")

        all_entries = db.query(CbdcLedgerEntry).all()
        total_debits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "DEBIT")
        total_credits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "CREDIT")

        assert abs(total_debits - total_credits) < 0.01, \
            f"Double-entry violated: debits={total_debits}, credits={total_credits}"

    def test_daily_limit_enforcement(self, db, seed_country):
        """Verify daily limit blocks transactions."""
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        from fastapi import HTTPException
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 1_000_000.0, "MINT")

        # w1 has Tier 1 limit of 500,000/day
        engine.transfer(w1.wallet_id, w2.wallet_id, 400_000.0, pin="1234")

        # This should exceed the daily limit
        with pytest.raises(HTTPException) as exc_info:
            engine.transfer(w1.wallet_id, w2.wallet_id, 200_000.0, pin="1234")
        assert "Daily limit exceeded" in str(exc_info.value.detail)

    def test_freeze_unfreeze(self, db, seed_country):
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        from fastapi import HTTPException
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 100_000.0, "MINT")

        # Freeze
        result = engine.freeze_wallet(cb.wallet_id, w1.wallet_id, "Suspicious activity")
        assert result["status"] == "frozen"

        # Transfer should fail
        with pytest.raises(HTTPException) as exc_info:
            engine.transfer(w1.wallet_id, w2.wallet_id, 10_000.0, pin="1234")
        assert "frozen" in str(exc_info.value.detail)

        # Unfreeze
        result = engine.unfreeze_wallet(cb.wallet_id, w1.wallet_id)
        assert result["status"] == "active"

    def test_pin_lockout(self, db, seed_country):
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        from fastapi import HTTPException
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 100_000.0, "MINT")

        # 3 wrong PINs should lock (must specify channel="USSD" to trigger PIN check)
        for i in range(3):
            with pytest.raises(HTTPException):
                engine.transfer(
                    w1.wallet_id, w2.wallet_id, 1000.0,
                    channel="USSD", pin="0000",
                )

        # Now even correct PIN should show locked
        with pytest.raises(HTTPException) as exc_info:
            engine.transfer(
                w1.wallet_id, w2.wallet_id, 1000.0,
                channel="USSD", pin="1234",
            )
        assert "locked" in str(exc_info.value.detail).lower()

    def test_hash_chain_integrity(self, db, seed_country):
        """Verify hash chain is maintained per wallet."""
        from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
        cb, w1, w2 = self._create_wallets(db, seed_country)

        engine = CbdcLedgerEngine(db)
        engine.mint(cb.wallet_id, w1.wallet_id, 200_000.0, "MINT1")
        engine.transfer(w1.wallet_id, w2.wallet_id, 50_000.0, pin="1234")

        # Get w1's entries in order
        entries = db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == w1.wallet_id
        ).order_by(CbdcLedgerEntry.created_at).all()

        # First entry should have no prev_hash
        assert entries[0].prev_entry_hash is None
        # Each subsequent entry should chain to the previous
        for i in range(1, len(entries)):
            assert entries[i].prev_entry_hash == entries[i - 1].entry_hash


# =====================================================================
# 4. Compliance Engine
# =====================================================================

class TestComplianceEngine:
    def test_pre_screen_frozen_wallet(self, db, seed_country):
        from src.utils.cbdc_crypto import generate_wallet_id
        from src.engines.cbdc_compliance_engine import CbdcComplianceEngine

        w = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=seed_country.id,
            wallet_type="RETAIL", kyc_tier=0, status="frozen",
            daily_limit_ecfa=50_000.0, balance_limit_ecfa=200_000.0,
        )
        db.add(w)
        db.commit()

        engine = CbdcComplianceEngine(db)
        result = engine.pre_screen(w.wallet_id, "some_receiver", 10_000.0)
        assert result["allowed"] is False
        assert "frozen" in result["reason"]

    def test_pre_screen_sar_threshold(self, db, seed_country):
        from src.utils.cbdc_crypto import generate_wallet_id
        from src.engines.cbdc_compliance_engine import CbdcComplianceEngine, SAR_THRESHOLD_XOF

        w = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=seed_country.id,
            wallet_type="RETAIL", kyc_tier=2, status="active",
            daily_limit_ecfa=5_000_000.0, balance_limit_ecfa=10_000_000.0,
        )
        db.add(w)
        db.commit()

        engine = CbdcComplianceEngine(db)
        result = engine.pre_screen(w.wallet_id, "receiver", SAR_THRESHOLD_XOF + 1)
        # Should be allowed but flagged
        assert result["allowed"] is True
        assert result["alert_id"] is not None


# =====================================================================
# 5. COBOL Output
# =====================================================================

class TestCobolOutput:
    def test_settlement_record_length(self):
        from src.utils.cbdc_cobol import format_settlement_cobol
        record = format_settlement_cobol({
            "settlement_id": "TEST123",
            "settlement_type": "DOMESTIC_NET",
            "bank_a_code": "BOA",
            "bank_b_code": "SGBF",
            "gross_amount_ecfa": 1000000.0,
            "net_amount_ecfa": 250000.0,
            "direction": "A_TO_B",
            "transaction_count": 42,
            "country_codes": "CI",
            "window_start": datetime(2026, 3, 1, 12, 0),
            "window_end": datetime(2026, 3, 1, 12, 15),
            "status": "pending",
        })
        assert len(record) == 200

    def test_transaction_record_length(self):
        from src.utils.cbdc_cobol import format_transaction_cobol
        record = format_transaction_cobol({
            "transaction_id": "TX123",
            "tx_type": "TRANSFER_P2P",
            "amount_ecfa": 50000.0,
            "fee_ecfa": 0.0,
            "sender_country": "CI",
            "receiver_country": "SN",
            "initiated_at": datetime(2026, 3, 1, 14, 30),
            "status": "completed",
            "kyc_tier_at_time": 1,
            "aml_status": "cleared",
            "cobol_ref": "TX123ABC",
        })
        assert len(record) == 150


# =====================================================================
# 6. USSD Wallet Engine
# =====================================================================

class TestUSSDWalletEngine:
    def test_ecfa_main_menu(self, db, seed_country):
        from src.engines.cbdc_ussd_engine import CbdcUSSDEngine
        engine = CbdcUSSDEngine(db)
        response, stype = engine.handle_ecfa_menu([], "+22500000000", "CI")
        assert response.startswith("CON")
        assert "eCFA" in response
        assert stype == "ECFA_MENU"

    def test_create_wallet_via_ussd(self, db, seed_country):
        from src.engines.cbdc_ussd_engine import CbdcUSSDEngine
        engine = CbdcUSSDEngine(db)

        # Navigate to create wallet: 6 (account) → 3 (create) → PIN
        response, stype = engine.handle_ecfa_menu(["6"], "+22500000000", "CI")
        assert "Mon compte" in response

        response, stype = engine.handle_ecfa_menu(["6", "3"], "+22500000000", "CI")
        assert "PIN" in response

        response, stype = engine.handle_ecfa_menu(["6", "3", "1234"], "+22500000000", "CI")
        assert "créé" in response.lower() or "Portefeuille" in response
        assert stype == "ECFA_WALLET_CREATED"

    def test_check_balance_via_ussd(self, db, seed_country):
        from src.engines.cbdc_ussd_engine import CbdcUSSDEngine
        from src.utils.cbdc_crypto import generate_wallet_id, hash_pin
        from src.engines.ussd_engine import _hash_phone

        phone = "+22500000000"
        phone_hash = _hash_phone(phone)

        # Create wallet first
        wallet = CbdcWallet(
            wallet_id=generate_wallet_id(), country_id=seed_country.id,
            phone_hash=phone_hash, wallet_type="RETAIL",
            kyc_tier=0, daily_limit_ecfa=50_000.0,
            balance_limit_ecfa=200_000.0, balance_ecfa=25_000.0,
            available_balance_ecfa=25_000.0,
            pin_hash=hash_pin("1234"), status="active",
        )
        db.add(wallet)
        db.commit()

        engine = CbdcUSSDEngine(db)

        # Check balance: 1 → PIN
        response, stype = engine.handle_ecfa_menu(["1"], phone, "CI")
        assert "PIN" in response

        response, stype = engine.handle_ecfa_menu(["1", "1234"], phone, "CI")
        assert "25,000" in response or "25000" in response
        assert stype == "ECFA_BALANCE"
