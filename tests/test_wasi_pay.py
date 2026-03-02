"""
WASI-Pay Cross-Border Payment Test Suite.

Tests the payment interoperability layer:
  1. FX Engine — rate lookup, conversion, locking, position tracking
  2. Payment Router — route determination, quoting, execution
  3. Corridors — available routes across 15 ECOWAS countries
  4. Payment Trace — hop-by-hop visibility
"""
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Country
from src.database.cbdc_models import CbdcWallet, CbdcFxRate
import src.database.cbdc_payment_models  # noqa: register payment tables
import src.database.cbdc_models  # noqa: register CBDC tables
import src.database.ussd_models  # noqa: register USSD tables

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
def seed_waemu_countries(db):
    """Seed CI (Cote d'Ivoire) and SN (Senegal) — both WAEMU."""
    ci = Country(code="CI", name="Cote d'Ivoire", tier="primary", weight=0.22, is_active=True)
    sn = Country(code="SN", name="Senegal", tier="primary", weight=0.10, is_active=True)
    db.add_all([ci, sn])
    db.commit()
    return ci, sn


@pytest.fixture
def seed_ng_country(db):
    """Seed NG (Nigeria) — WAMZ zone."""
    ng = Country(code="NG", name="Nigeria", tier="primary", weight=0.28, is_active=True)
    db.add(ng)
    db.commit()
    return ng


@pytest.fixture
def seed_fx_rates(db):
    """Seed FX rates for all 8 non-XOF currencies."""
    rates = {
        "NGN": 2.54, "GHS": 0.041, "GNF": 14.10,
        "SLE": 0.036, "LRD": 0.315, "GMD": 0.115,
        "MRU": 0.066, "CVE": 0.167,
    }
    for currency, rate in rates.items():
        db.add(CbdcFxRate(
            base_currency="XOF",
            target_currency=currency,
            rate=rate,
            inverse_rate=round(1.0 / rate, 4),
            effective_date=date.today(),
            source="TEST_SEED",
        ))
    db.commit()
    return rates


def _create_treasury(db, country):
    """Helper: create a BCEAO treasury wallet for a country."""
    from src.utils.cbdc_crypto import generate_wallet_id
    treasury = CbdcWallet(
        wallet_id=generate_wallet_id(),
        country_id=country.id,
        wallet_type="CENTRAL_BANK",
        institution_code="BCEAO",
        institution_name=f"BCEAO Treasury — {country.code}",
        kyc_tier=3,
        daily_limit_ecfa=999_999_999_999.0,
        balance_limit_ecfa=999_999_999_999.0,
        status="active",
    )
    db.add(treasury)
    db.commit()
    db.refresh(treasury)
    return treasury


def _create_wallet(db, country, wallet_type="RETAIL", balance=1_000_000.0, treasury=None):
    """Helper: create a test wallet with balance via engine mint."""
    from src.utils.cbdc_crypto import generate_wallet_id, hash_pin
    from src.engines.cbdc_ledger_engine import CbdcLedgerEngine

    wallet = CbdcWallet(
        wallet_id=generate_wallet_id(),
        country_id=country.id,
        phone_hash=f"test_hash_{generate_wallet_id()[:8]}",
        wallet_type=wallet_type,
        kyc_tier=2,
        daily_limit_ecfa=5_000_000.0,
        balance_limit_ecfa=10_000_000.0,
        pin_hash=hash_pin("1234"),
        status="active",
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)

    if balance > 0 and treasury:
        engine = CbdcLedgerEngine(db)
        engine.mint(
            central_bank_wallet_id=treasury.wallet_id,
            target_wallet_id=wallet.wallet_id,
            amount_ecfa=balance,
            reference=f"TEST_MINT_{wallet.wallet_id[:8]}",
        )
        db.refresh(wallet)

    return wallet


# =====================================================================
# 1. FX Engine — Rate Lookup & Conversion
# =====================================================================

class TestFxEngine:
    def test_get_rate_xof_identity(self, db):
        """XOF→XOF should return identity rate."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.get_rate("XOF")
        assert result["rate"] == 1.0
        assert result["spread_percent"] == 0.0
        assert result["source"] == "IDENTITY"

    def test_get_rate_ngn(self, db, seed_fx_rates):
        """Should return seeded NGN rate."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.get_rate("NGN")
        assert result["rate"] == 2.54
        assert result["target"] == "NGN"
        assert result["base"] == "XOF"

    def test_get_rate_not_found(self, db):
        """Should raise 404 for unknown currency."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        from fastapi import HTTPException
        fx = CbdcFxEngine(db)
        with pytest.raises(HTTPException) as exc_info:
            fx.get_rate("USD")
        assert exc_info.value.status_code == 404

    def test_get_all_rates(self, db, seed_fx_rates):
        """Should return rates for all 8 non-XOF currencies."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        rates = fx.get_all_rates()
        assert len(rates) == 8
        currencies = {r["target"] for r in rates}
        assert "NGN" in currencies
        assert "CVE" in currencies

    def test_convert_same_currency(self, db):
        """Same currency conversion = identity."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.convert(10000, "XOF", "XOF")
        assert result["amount_target"] == 10000
        assert result["rate_used"] == 1.0

    def test_convert_xof_to_ngn(self, db, seed_fx_rates):
        """Convert 10000 XOF to NGN."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.convert(10000, "XOF", "NGN")
        assert result["from_currency"] == "XOF"
        assert result["to_currency"] == "NGN"
        assert result["amount_source"] == 10000
        assert result["amount_target"] > 0
        assert result["spread_percent"] == pytest.approx(0.35)  # NGN volatile tier

    def test_convert_ngn_to_xof(self, db, seed_fx_rates):
        """Convert 1000 NGN to XOF."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.convert(1000, "NGN", "XOF")
        assert result["from_currency"] == "NGN"
        assert result["to_currency"] == "XOF"
        assert result["amount_target"] > 0

    def test_convert_cross_currency_chain(self, db, seed_fx_rates):
        """NGN→GHS should chain through XOF."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.convert(1000, "NGN", "GHS")
        assert result["from_currency"] == "NGN"
        assert result["to_currency"] == "GHS"
        assert result["amount_target"] > 0
        # Spread should be sum of both legs
        assert result["spread_percent"] > 0.25

    def test_spread_tiers(self, db, seed_fx_rates):
        """Verify spread tier differences."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        cve = fx.convert(10000, "XOF", "CVE")
        ghs = fx.convert(10000, "XOF", "GHS")
        ngn = fx.convert(10000, "XOF", "NGN")
        assert cve["spread_percent"] == pytest.approx(0.15)  # stable
        assert ghs["spread_percent"] == pytest.approx(0.25)  # medium
        assert ngn["spread_percent"] == pytest.approx(0.35)  # volatile

    def test_lock_rate(self, db, seed_fx_rates):
        """Rate lock should create a CbdcRateLock row."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        from src.database.cbdc_payment_models import CbdcRateLock
        fx = CbdcFxEngine(db)
        result = fx.lock_rate("NGN", 50000.0)
        db.commit()
        assert "lock_id" in result
        assert result["rate"] == 2.54
        lock = db.query(CbdcRateLock).filter(
            CbdcRateLock.lock_id == result["lock_id"]
        ).first()
        assert lock is not None
        assert not lock.consumed

    def test_consume_rate_lock(self, db, seed_fx_rates):
        """Consuming a lock should mark it consumed."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        lock = fx.lock_rate("NGN", 50000.0)
        db.commit()
        result = fx.consume_rate_lock(lock["lock_id"], "test-payment-123")
        db.commit()
        assert result["lock_id"] == lock["lock_id"]
        assert result["rate"] == 2.54

    def test_consume_already_consumed(self, db, seed_fx_rates):
        """Double-consuming should raise 400."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        from fastapi import HTTPException
        fx = CbdcFxEngine(db)
        lock = fx.lock_rate("NGN", 50000.0)
        db.commit()
        fx.consume_rate_lock(lock["lock_id"], "payment-1")
        db.commit()
        with pytest.raises(HTTPException) as exc_info:
            fx.consume_rate_lock(lock["lock_id"], "payment-2")
        assert exc_info.value.status_code == 400

    def test_update_rate(self, db, seed_fx_rates):
        """Admin rate update should change today's rate."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        result = fx.update_rate("NGN", 2.60, source="ADMIN_TEST")
        db.commit()
        assert result["rate"] == 2.60
        assert result["source"] == "ADMIN_TEST"

    def test_country_currency_lookup(self, db):
        """Country code → currency lookup."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        assert fx.get_currency_for_country("CI") == "XOF"
        assert fx.get_currency_for_country("NG") == "NGN"
        assert fx.get_currency_for_country("GH") == "GHS"

    def test_same_currency_zone(self, db):
        """WAEMU countries share currency zone."""
        from src.engines.cbdc_fx_engine import CbdcFxEngine
        fx = CbdcFxEngine(db)
        assert fx.is_same_currency_zone("CI", "SN") is True
        assert fx.is_same_currency_zone("CI", "NG") is False


# =====================================================================
# 2. Payment Router — Route Determination
# =====================================================================

class TestPaymentRouter:
    def test_waemu_internal_route(self, db, seed_waemu_countries, seed_fx_rates):
        """CI→SN should route as ECFA_INTERNAL (no FX)."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        route = router.determine_route("CI", "SN")
        assert route["rail_type"] == "ECFA_INTERNAL"
        assert route["requires_fx"] is False
        assert route["platform_fee_pct"] == 0.1

    def test_ecfa_to_external_route(self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates):
        """CI→NG should route as ECFA_TO_EXTERNAL (FX required)."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        route = router.determine_route("CI", "NG")
        assert route["rail_type"] == "ECFA_TO_EXTERNAL"
        assert route["requires_fx"] is True
        assert route["platform_fee_pct"] == 0.5
        assert route["rail_fee_ecfa"] == 500.0  # NG rail fee

    def test_external_to_ecfa_route(self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates):
        """NG→CI should route as EXTERNAL_TO_ECFA (FX required)."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        route = router.determine_route("NG", "CI")
        assert route["rail_type"] == "EXTERNAL_TO_ECFA"
        assert route["requires_fx"] is True

    def test_settlement_time(self, db, seed_waemu_countries, seed_fx_rates):
        """WAEMU internal should be near-instant (5s)."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        route = router.determine_route("CI", "SN")
        assert route["estimated_settlement_sec"] == 5


# =====================================================================
# 3. Payment Router — Quoting
# =====================================================================

class TestPaymentQuoting:
    def test_waemu_quote_no_fx(self, db, seed_waemu_countries, seed_fx_rates):
        """WAEMU→WAEMU quote should have no FX spread."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sn_treasury = _create_treasury(db, sn)
        sender = _create_wallet(db, ci, treasury=ci_treasury)
        receiver = _create_wallet(db, sn, treasury=sn_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        quote = router.get_quote(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=receiver.wallet_id,
            receiver_country="SN",
            amount=100000,
            source_currency="XOF",
            target_currency="XOF",
            lock_rate=False,
        )
        assert quote["rail_type"] == "ECFA_INTERNAL"
        assert quote["fx_rate"] is None
        assert quote["amount_target"] == 100000
        assert quote["platform_fee_ecfa"] == 100.0  # 0.10% of 100000

    def test_cross_border_quote_with_fx(self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates):
        """CI→NG quote should include FX conversion and fees."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sender = _create_wallet(db, ci, treasury=ci_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        quote = router.get_quote(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=None,
            receiver_country="NG",
            amount=100000,
            source_currency="XOF",
            target_currency="NGN",
            lock_rate=True,
        )
        assert quote["rail_type"] == "ECFA_TO_EXTERNAL"
        assert quote["fx_rate"] is not None
        assert quote["amount_target"] > 0
        assert quote["platform_fee_ecfa"] == 500.0  # 0.50% of 100000
        assert quote["rail_fee_ecfa"] == 500.0  # NG rail fee
        assert quote["quote_id"] is not None  # rate was locked


# =====================================================================
# 4. Payment Router — Execution
# =====================================================================

class TestPaymentExecution:
    def test_waemu_internal_payment(self, db, seed_waemu_countries, seed_fx_rates):
        """CI→SN internal payment should settle instantly."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sn_treasury = _create_treasury(db, sn)
        sender = _create_wallet(db, ci, balance=500_000, treasury=ci_treasury)
        receiver = _create_wallet(db, sn, balance=0, treasury=sn_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=receiver.wallet_id,
            receiver_country="SN",
            amount=100000,
            source_currency="XOF",
            target_currency="XOF",
            pin="1234",
        )
        assert result["status"] == "SETTLED"
        assert result["rail_type"] == "ECFA_INTERNAL"
        assert result["payment_id"] is not None
        assert result["source_tx_id"] is not None

    def test_cross_border_payment_ecfa_to_external(
        self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates
    ):
        """CI→NG cross-border payment with FX conversion."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sender = _create_wallet(db, ci, balance=500_000, treasury=ci_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=None,
            receiver_country="NG",
            amount=100000,
            source_currency="XOF",
            target_currency="NGN",
            pin="1234",
            purpose="Family remittance",
        )
        assert result["status"] == "SETTLED"
        assert result["rail_type"] == "ECFA_TO_EXTERNAL"
        assert result["fx_rate_applied"] is not None
        assert result["amount_target"] is not None
        assert result["platform_fee_ecfa"] > 0
        assert result["rail_fee_ecfa"] == 500.0

    def test_payment_with_locked_quote(self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates):
        """Execute payment using a previously locked rate."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sender = _create_wallet(db, ci, balance=500_000, treasury=ci_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)

        # Step 1: Get quote with rate lock
        quote = router.get_quote(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=None,
            receiver_country="NG",
            amount=100000,
            source_currency="XOF",
            target_currency="NGN",
            lock_rate=True,
        )
        assert quote["quote_id"] is not None

        # Step 2: Execute with quote_id
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=None,
            receiver_country="NG",
            amount=100000,
            source_currency="XOF",
            target_currency="NGN",
            pin="1234",
            quote_id=quote["quote_id"],
        )
        assert result["status"] == "SETTLED"

    def test_insufficient_balance_fails(self, db, seed_waemu_countries, seed_fx_rates):
        """Payment should fail if sender doesn't have enough balance."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sn_treasury = _create_treasury(db, sn)
        sender = _create_wallet(db, ci, balance=100, treasury=ci_treasury)
        receiver = _create_wallet(db, sn, balance=0, treasury=sn_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=receiver.wallet_id,
            receiver_country="SN",
            amount=100000,
            source_currency="XOF",
            target_currency="XOF",
            pin="1234",
        )
        assert result["status"] == "FAILED"
        assert result["failure_reason"] is not None


# =====================================================================
# 5. Payment Status & Trace
# =====================================================================

class TestPaymentTracking:
    def test_get_payment_status(self, db, seed_waemu_countries, seed_fx_rates):
        """Status lookup should return full payment info."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sn_treasury = _create_treasury(db, sn)
        sender = _create_wallet(db, ci, balance=500_000, treasury=ci_treasury)
        receiver = _create_wallet(db, sn, balance=0, treasury=sn_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=receiver.wallet_id,
            receiver_country="SN",
            amount=50000,
            source_currency="XOF",
            target_currency="XOF",
            pin="1234",
        )
        status = router.get_payment_status(result["payment_id"])
        assert status["payment_id"] == result["payment_id"]
        assert status["status"] == "SETTLED"
        assert status["sender_country"] == "CI"
        assert status["receiver_country"] == "SN"

    def test_payment_trace_hops(self, db, seed_waemu_countries, seed_ng_country, seed_fx_rates):
        """Trace should include multiple hops for cross-border."""
        ci, sn = seed_waemu_countries
        ci_treasury = _create_treasury(db, ci)
        sender = _create_wallet(db, ci, balance=500_000, treasury=ci_treasury)

        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        result = router.execute_payment(
            sender_wallet_id=sender.wallet_id,
            receiver_wallet_id=None,
            receiver_country="NG",
            amount=100000,
            source_currency="XOF",
            target_currency="NGN",
            pin="1234",
        )
        trace = router.get_payment_trace(result["payment_id"])
        assert trace["payment_id"] == result["payment_id"]
        assert len(trace["hops"]) >= 4  # compliance, FX, debit, conversion, credit, settlement

    def test_payment_not_found(self, db):
        """Should raise 404 for unknown payment."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        from fastapi import HTTPException
        router = CbdcPaymentRouter(db)
        with pytest.raises(HTTPException) as exc_info:
            router.get_payment_status("nonexistent-id")
        assert exc_info.value.status_code == 404


# =====================================================================
# 6. Corridors
# =====================================================================

class TestCorridors:
    def test_list_corridors(self, db, seed_waemu_countries, seed_fx_rates):
        """Should list corridors for all country pairs."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        corridors = router.list_corridors()
        # 16 countries × 15 = 240 corridors
        assert len(corridors) == 240

    def test_waemu_corridor_available(self, db, seed_waemu_countries, seed_fx_rates):
        """WAEMU corridors should be marked available."""
        from src.engines.cbdc_payment_router import CbdcPaymentRouter
        router = CbdcPaymentRouter(db)
        corridors = router.list_corridors()
        ci_sn = [c for c in corridors if c["source_country"] == "CI" and c["dest_country"] == "SN"]
        assert len(ci_sn) == 1
        assert ci_sn[0]["available"] is True
        assert ci_sn[0]["rail_type"] == "ECFA_INTERNAL"
