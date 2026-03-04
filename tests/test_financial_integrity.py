"""
Financial Integrity Integration Tests
======================================

End-to-end tests for money-handling paths. These verify:
1. CBDC double-entry: mint -> transfer -> burn, all ledger entries balance to zero
2. Credit flow: register -> topup -> query (deduction) -> insufficient balance (402)
3. Ledger hash chain integrity
4. Balance verification via engine.get_balance()
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country
from src.database.cbdc_models import CbdcWallet, CbdcLedgerEntry
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _register_and_login(username, email, password="TestPass1!", is_admin=False):
    reg_resp = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert reg_resp.status_code == 201, f"Register failed: {reg_resp.status_code} {reg_resp.text}"
    if is_admin:
        db = TestingSessionLocal()
        u = db.query(User).filter(User.username == username).first()
        u.is_admin = True
        db.commit()
        db.close()
    resp = client.post("/api/auth/login", data={
        "username": username, "password": password,
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(username):
    db = TestingSessionLocal()
    u = db.query(User).filter(User.username == username).first()
    uid = u.id
    db.close()
    return uid


def _get_country_id(code="CI"):
    db = TestingSessionLocal()
    c = db.query(Country).filter(Country.code == code).first()
    cid = c.id
    db.close()
    return cid


def _create_wallet(user_id, country_id, wallet_type="RETAIL",
                   balance=500_000.0, pin="1234"):
    from src.utils.cbdc_crypto import generate_wallet_id, hash_pin
    db = TestingSessionLocal()
    wid = generate_wallet_id()
    kyc = 3 if wallet_type == "CENTRAL_BANK" else 2
    dlimit = 999_999_999_999.0 if wallet_type == "CENTRAL_BANK" else 5_000_000.0
    blimit = 999_999_999_999.0 if wallet_type == "CENTRAL_BANK" else 10_000_000.0
    db.add(CbdcWallet(
        wallet_id=wid,
        user_id=user_id,
        country_id=country_id,
        wallet_type=wallet_type,
        institution_code="BCEAO" if wallet_type == "CENTRAL_BANK" else None,
        institution_name="BCEAO Treasury" if wallet_type == "CENTRAL_BANK" else None,
        balance_ecfa=balance,
        available_balance_ecfa=balance,
        kyc_tier=kyc,
        daily_limit_ecfa=dlimit,
        balance_limit_ecfa=blimit,
        status="active",
        pin_hash=hash_pin(pin),
    ))
    db.commit()
    db.close()
    return wid


def _set_balance(username, amount, tier="pro"):
    """Set user x402 balance and tier directly in DB."""
    db = TestingSessionLocal()
    u = db.query(User).filter(User.username == username).first()
    u.x402_balance = amount
    u.tier = tier  # "pro" has query_cost=1.0; "free" has 0.0
    db.commit()
    db.close()


# ── Test 1: CBDC Double-Entry Integrity ──────────────────────────────────────

def test_cbdc_mint_transfer_burn_balance_to_zero():
    """
    Full lifecycle: mint 1M -> transfer 300K -> burn remaining 700K.
    After burn, all ledger entries should sum to zero for each wallet.
    """
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    headers = _register_and_login("fi_mgr", "fi_mgr@test.com", is_admin=True)
    uid = _get_user_id("fi_mgr")
    cid = _get_country_id("CI")

    cb_wallet = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    user_wallet = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    db = TestingSessionLocal()
    try:
        engine = CbdcLedgerEngine(db)

        # Step 1: Mint 1,000,000 eCFA to user wallet
        mint_result = engine.mint(cb_wallet, user_wallet, 1_000_000.0, "INTEGRITY_TEST_MINT")
        assert mint_result["status"] == "completed"
        assert mint_result["target_new_balance"] == 1_000_000.0

        # Step 2: Transfer 300,000 eCFA from user to CB (simulates payment)
        transfer_result = engine.transfer(
            user_wallet, cb_wallet, 300_000.0,
            tx_type="TRANSFER_P2P", channel="ADMIN", _system_auth=True,
        )
        assert transfer_result["status"] == "completed"
        assert transfer_result["sender_new_balance"] == 700_000.0

        # Step 3: Burn remaining 700,000 from user wallet
        burn_result = engine.burn(cb_wallet, user_wallet, 700_000.0, "INTEGRITY_TEST_BURN")
        assert burn_result["status"] == "completed"
        assert burn_result["source_new_balance"] == 0.0

        # Verify: user wallet balance is zero
        user_balance = engine.get_balance(user_wallet)
        assert user_balance["balance_ecfa"] == 0.0
        assert user_balance["balance_matches_ledger"] is True

        # Verify: global ledger sums to zero (all debits == all credits)
        all_entries = db.query(CbdcLedgerEntry).all()
        total_debits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "DEBIT")
        total_credits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "CREDIT")
        assert abs(total_debits - total_credits) < 0.01, (
            f"Ledger imbalance: debits={total_debits}, credits={total_credits}"
        )
    finally:
        db.close()


# ── Test 2: Credit Deduction Flow ────────────────────────────────────────────

def test_credit_deduction_and_insufficient_balance():
    """
    Direct test: deduct_credits charges pro-tier user, raises 402 when exhausted.
    Verifies atomic balance update, transaction logging, and 402 error format.
    """
    from src.utils.credits import deduct_credits
    from src.database.models import X402Transaction
    from fastapi import HTTPException

    db = TestingSessionLocal()
    try:
        # Create a pro-tier user with 5.0 balance
        from src.utils.security import hash_password
        user = User(
            username="fi_credit",
            email="fi_credit@test.com",
            hashed_password=hash_password("TestPass1!"),
            x402_balance=5.0,
            tier="pro",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Deduct 1 credit (pro tier, cost_multiplier=1.0)
        cost = deduct_credits(user, db, "/api/indices/latest", method="GET", cost_multiplier=1.0)
        assert cost == 1.0
        assert user.x402_balance == 4.0

        # Deduct 3 credits (cost_multiplier=3.0)
        cost = deduct_credits(user, db, "/api/composite/report", method="GET", cost_multiplier=3.0)
        assert cost == 3.0
        assert user.x402_balance == 1.0

        # Verify transaction records created
        tx_count = db.query(X402Transaction).filter(
            X402Transaction.user_id == user.id,
        ).count()
        assert tx_count == 2

        # Try to deduct 3 more — should fail (only 1.0 left)
        with pytest.raises(HTTPException) as exc_info:
            deduct_credits(user, db, "/api/composite/report", method="GET", cost_multiplier=3.0)
        assert exc_info.value.status_code == 402
        detail = exc_info.value.detail
        assert detail["balance"] == 1.0
        assert detail["cost"] == 3.0
        assert detail["topup_url"] == "/api/payment/topup"

        # Balance unchanged after failed deduction
        db.refresh(user)
        assert user.x402_balance == 1.0
    finally:
        db.close()


# ── Test 3: Ledger Entry Count Invariant ─────────────────────────────────────

def test_transfer_creates_exactly_two_ledger_entries():
    """Each transfer creates exactly 2 ledger entries (DEBIT + CREDIT)."""
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    headers = _register_and_login("fi_count", "fi_count@test.com", is_admin=True)
    uid = _get_user_id("fi_count")
    cid = _get_country_id("CI")

    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    w1 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)
    w2 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    db = TestingSessionLocal()
    try:
        engine = CbdcLedgerEngine(db)

        # Mint to w1
        engine.mint(cb, w1, 100_000.0, "COUNT_TEST_MINT")
        entries_after_mint = db.query(CbdcLedgerEntry).count()
        assert entries_after_mint == 2  # 1 debit CB + 1 credit w1

        # Transfer w1 -> w2
        engine.transfer(
            w1, w2, 50_000.0,
            tx_type="TRANSFER_P2P", channel="ADMIN", _system_auth=True,
        )
        entries_after_transfer = db.query(CbdcLedgerEntry).count()
        assert entries_after_transfer == 4  # +2 for the transfer

        # Verify w1 has 1 CREDIT (from mint) and 1 DEBIT (from transfer)
        w1_entries = db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == w1,
        ).all()
        w1_credits = [e for e in w1_entries if e.entry_type == "CREDIT"]
        w1_debits = [e for e in w1_entries if e.entry_type == "DEBIT"]
        assert len(w1_credits) == 1
        assert len(w1_debits) == 1
        assert w1_credits[0].amount_ecfa == 100_000.0
        assert w1_debits[0].amount_ecfa == 50_000.0
    finally:
        db.close()


# ── Test 4: Hash Chain Integrity ─────────────────────────────────────────────

def test_ledger_hash_chain():
    """Each ledger entry references the previous entry's hash."""
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    headers = _register_and_login("fi_hash", "fi_hash@test.com", is_admin=True)
    uid = _get_user_id("fi_hash")
    cid = _get_country_id("CI")

    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    w1 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    db = TestingSessionLocal()
    try:
        engine = CbdcLedgerEngine(db)

        # Create 3 transactions to build a chain for w1
        engine.mint(cb, w1, 100_000.0, "HASH_TEST_1")
        engine.mint(cb, w1, 200_000.0, "HASH_TEST_2")
        engine.mint(cb, w1, 300_000.0, "HASH_TEST_3")

        # Get all entries for w1, ordered by creation
        entries = (
            db.query(CbdcLedgerEntry)
            .filter(CbdcLedgerEntry.wallet_id == w1)
            .order_by(CbdcLedgerEntry.created_at.asc())
            .all()
        )
        assert len(entries) == 3  # 3 CREDIT entries from 3 mints

        # First entry should have no previous hash (or empty)
        # Subsequent entries should reference the previous entry's hash
        for i in range(1, len(entries)):
            prev_hash = entries[i - 1].entry_hash
            curr_prev = entries[i].prev_entry_hash
            assert curr_prev == prev_hash, (
                f"Hash chain broken at entry {i}: "
                f"prev.hash={prev_hash}, curr.prev_hash={curr_prev}"
            )

        # All entries should have non-empty hashes
        for e in entries:
            assert e.entry_hash is not None
            assert len(e.entry_hash) == 64  # SHA-256 hex digest
    finally:
        db.close()


# ── Test 5: Insufficient Balance Rejection ───────────────────────────────────

def test_cbdc_transfer_insufficient_balance_rejected():
    """Transfer exceeding available balance is rejected, no ledger entries created."""
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    headers = _register_and_login("fi_insuff", "fi_insuff@test.com", is_admin=True)
    uid = _get_user_id("fi_insuff")
    cid = _get_country_id("CI")

    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    w1 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)
    w2 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    db = TestingSessionLocal()
    try:
        engine = CbdcLedgerEngine(db)
        engine.mint(cb, w1, 100_000.0, "INSUFF_TEST")
        entries_before = db.query(CbdcLedgerEntry).count()

        # Try to transfer more than available
        with pytest.raises(Exception) as exc_info:
            engine.transfer(
                w1, w2, 200_000.0,
                tx_type="TRANSFER_P2P", channel="ADMIN", _system_auth=True,
            )

        # Verify no new ledger entries were created
        entries_after = db.query(CbdcLedgerEntry).count()
        assert entries_after == entries_before, "Ledger entries created for failed transfer"

        # Balance unchanged
        bal = engine.get_balance(w1)
        assert bal["balance_ecfa"] == 100_000.0
    finally:
        db.close()


# ── Test 6: Wallet Balance Matches Ledger After Multiple Operations ──────────

def test_balance_matches_ledger_after_many_ops():
    """After 10 transactions, cached balance still matches ledger sum."""
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    headers = _register_and_login("fi_multi", "fi_multi@test.com", is_admin=True)
    uid = _get_user_id("fi_multi")
    cid = _get_country_id("CI")

    cb = _create_wallet(uid, cid, wallet_type="CENTRAL_BANK", balance=0.0)
    w1 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)
    w2 = _create_wallet(uid, cid, wallet_type="RETAIL", balance=0.0)

    db = TestingSessionLocal()
    try:
        engine = CbdcLedgerEngine(db)

        # Mint 1M to w1
        engine.mint(cb, w1, 1_000_000.0, "MULTI_MINT")

        # 5 transfers: w1 -> w2 (various amounts)
        for i, amount in enumerate([10_000, 25_000, 50_000, 75_000, 100_000]):
            engine.transfer(
                w1, w2, float(amount),
                tx_type="TRANSFER_P2P", channel="ADMIN", _system_auth=True,
            )

        # 3 transfers: w2 -> w1 (return some)
        for amount in [5_000, 15_000, 30_000]:
            engine.transfer(
                w2, w1, float(amount),
                tx_type="TRANSFER_P2P", channel="ADMIN", _system_auth=True,
            )

        # Burn 100K from w1
        engine.burn(cb, w1, 100_000.0, "MULTI_BURN")

        # Verify both wallets match ledger
        for wid in [w1, w2]:
            bal = engine.get_balance(wid)
            assert bal["balance_matches_ledger"] is True, (
                f"Wallet {wid}: cached={bal['balance_ecfa']}, "
                f"ledger={bal['ledger_verified_balance']}"
            )

        # Verify global ledger balance
        all_entries = db.query(CbdcLedgerEntry).all()
        total_debits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "DEBIT")
        total_credits = sum(e.amount_ecfa for e in all_entries if e.entry_type == "CREDIT")
        assert abs(total_debits - total_credits) < 0.01
    finally:
        db.close()
