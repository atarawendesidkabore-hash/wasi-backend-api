"""
Tests for eCFA CBDC Monetary Policy Engine.

Covers:
  - Policy rate management (taux directeur, corridor auto-adjustment)
  - Reserve requirement computation and compliance checking
  - Standing facility operations (lending/deposit, maturation)
  - Interest accrual and demurrage
  - M0/M1/M2 money supply computation
  - Monetary policy decision recording
"""
import pytest
import uuid
import json
from datetime import datetime, date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import Base, Country
from src.database.cbdc_models import (
    CbdcWallet, CbdcLedgerEntry, CbdcTransaction, CbdcPolicy,
    CbdcPolicyRate, CbdcReserveRequirement, CbdcStandingFacility,
    CbdcMonetaryPolicyDecision, CbdcEligibleCollateral,
    CbdcMonetaryAggregate,
)
from src.engines.cbdc_monetary_policy_engine import CbdcMonetaryPolicyEngine


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite database with StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

    # Seed a test country
    ci = Country(
        code="CI", name="Cote d'Ivoire",
        weight=0.22, tier="primary",
    )
    session.add(ci)
    session.commit()

    # Central bank wallet for CI
    cb_wallet = CbdcWallet(
        wallet_id="cb-ci-001",
        country_id=ci.id,
        wallet_type="CENTRAL_BANK",
        institution_code="BCEAO",
        institution_name="BCEAO Treasury — CI",
        balance_ecfa=0.0,
        available_balance_ecfa=0.0,
        kyc_tier=3,
        daily_limit_ecfa=999_999_999_999.0,
        balance_limit_ecfa=999_999_999_999.0,
        status="active",
    )
    session.add(cb_wallet)

    # Commercial bank wallet
    bank_wallet = CbdcWallet(
        wallet_id="bank-sgbci-001",
        country_id=ci.id,
        wallet_type="COMMERCIAL_BANK",
        institution_code="SGBCI",
        institution_name="Societe Generale CI",
        balance_ecfa=500_000_000.0,
        available_balance_ecfa=500_000_000.0,
        kyc_tier=3,
        daily_limit_ecfa=999_999_999_999.0,
        balance_limit_ecfa=999_999_999_999.0,
        status="active",
    )
    session.add(bank_wallet)

    # Retail wallets linked to SGBCI
    for i in range(3):
        session.add(CbdcWallet(
            wallet_id=f"retail-ci-{i:03d}",
            country_id=ci.id,
            wallet_type="RETAIL",
            institution_code="SGBCI",
            balance_ecfa=200_000.0,
            available_balance_ecfa=200_000.0,
            kyc_tier=1,
            daily_limit_ecfa=500_000.0,
            balance_limit_ecfa=2_000_000.0,
            status="active",
        ))

    session.commit()
    yield session
    session.close()


@pytest.fixture
def engine(db):
    """Monetary policy engine instance."""
    return CbdcMonetaryPolicyEngine(db)


# ── 1. Policy Rate Tests ─────────────────────────────────────────────

class TestPolicyRates:

    def test_get_default_rates(self, engine):
        """When no rates exist, defaults should be returned."""
        rates = engine.get_current_rates()
        assert "TAUX_DIRECTEUR" in rates
        assert rates["TAUX_DIRECTEUR"]["rate_percent"] == 3.50
        assert rates["TAUX_PRET_MARGINAL"]["rate_percent"] == 5.50
        assert rates["TAUX_DEPOT"]["rate_percent"] == 1.50

    def test_set_taux_directeur(self, engine, db):
        """Setting taux directeur should auto-adjust corridor."""
        result = engine.set_policy_rate("TAUX_DIRECTEUR", 4.00)

        assert len(result["rates_updated"]) == 3  # TD + corridor
        assert result["rates_updated"][0]["new"] == 4.00

        # Verify corridor
        rates = engine.get_current_rates()
        assert rates["TAUX_DIRECTEUR"]["rate_percent"] == 4.00
        assert rates["TAUX_PRET_MARGINAL"]["rate_percent"] == 6.00  # +200bp
        assert rates["TAUX_DEPOT"]["rate_percent"] == 2.00            # -200bp

    def test_set_taux_directeur_supersedes_old(self, engine, db):
        """Setting a new rate should supersede the old one."""
        engine.set_policy_rate("TAUX_DIRECTEUR", 3.50)
        engine.set_policy_rate("TAUX_DIRECTEUR", 4.25)

        # Only one current rate
        current = db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_DIRECTEUR",
            CbdcPolicyRate.is_current == True,
        ).all()
        assert len(current) == 1
        assert current[0].rate_percent == 4.25
        assert current[0].previous_rate_percent == 3.50

    def test_rate_history(self, engine, db):
        """Rate history should track changes across different dates."""
        from datetime import timedelta
        engine.set_policy_rate("TAUX_DIRECTEUR", 3.00, effective_date=date.today() - timedelta(days=60))
        engine.set_policy_rate("TAUX_DIRECTEUR", 3.50, effective_date=date.today() - timedelta(days=30))
        engine.set_policy_rate("TAUX_DIRECTEUR", 4.00, effective_date=date.today())

        history = engine.get_rate_history("TAUX_DIRECTEUR")
        assert len(history) == 3
        assert history[0]["rate_percent"] == 4.00  # most recent
        assert history[2]["rate_percent"] == 3.00  # oldest

    def test_invalid_rate_type_raises(self, engine):
        """Invalid rate type should raise ValueError."""
        with pytest.raises(ValueError):
            engine.set_policy_rate("INVALID_TYPE", 5.0)

    def test_corridor_floor_at_zero(self, engine):
        """Deposit rate should not go below zero."""
        engine.set_policy_rate("TAUX_DIRECTEUR", 1.50)  # corridor: 3.50 / -0.50
        rates = engine.get_current_rates()
        assert rates["TAUX_DEPOT"]["rate_percent"] >= 0.0


# ── 2. Reserve Requirement Tests ─────────────────────────────────────

class TestReserveRequirements:

    def test_compute_reserves_basic(self, engine, db):
        """Basic reserve computation: 3% of client deposits."""
        result = engine.compute_reserve_requirements()

        assert result["reserve_ratio_percent"] == 3.0  # default
        assert result["banks_assessed"] == 1  # SGBCI
        detail = result["bank_details"][0]

        # 3 retail wallets * 200,000 = 600,000 deposit base
        assert detail["deposit_base_ecfa"] == 600_000.0
        assert detail["required_ecfa"] == 18_000.0  # 3% of 600K
        assert detail["holding_ecfa"] == 500_000_000.0  # bank has 500M
        assert detail["is_compliant"] is True
        assert detail["surplus_ecfa"] > 0

    def test_deficient_bank(self, engine, db):
        """Bank with insufficient reserves should be flagged."""
        # Reduce bank balance to below required
        bank = db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == "bank-sgbci-001"
        ).first()
        bank.balance_ecfa = 10_000.0  # way below 18,000 required
        bank.available_balance_ecfa = 10_000.0
        db.commit()

        result = engine.compute_reserve_requirements()
        detail = result["bank_details"][0]

        assert detail["is_compliant"] is False
        assert detail["deficiency_ecfa"] > 0
        assert detail["daily_penalty_ecfa"] > 0

    def test_set_reserve_ratio(self, engine, db):
        """Changing reserve ratio should update computations."""
        engine.set_reserve_ratio(5.0)
        result = engine.compute_reserve_requirements()
        assert result["reserve_ratio_percent"] == 5.0

        detail = result["bank_details"][0]
        assert detail["required_ecfa"] == 30_000.0  # 5% of 600K


# ── 3. Standing Facility Tests ───────────────────────────────────────

class TestStandingFacilities:

    def test_lending_facility(self, engine, db):
        """Bank borrows from CB — wallet balance should increase."""
        bank = db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == "bank-sgbci-001"
        ).first()
        initial_balance = bank.balance_ecfa

        result = engine.open_lending_facility(
            bank_wallet_id="bank-sgbci-001",
            amount_ecfa=100_000_000.0,  # 100M XOF
            maturity="OVERNIGHT",
        )

        assert result["facility_type"] == "LENDING"
        assert result["amount_ecfa"] == 100_000_000.0
        assert result["rate_percent"] == 5.50  # default taux pret marginal
        assert result["interest_ecfa"] > 0
        assert result["bank_new_balance"] == initial_balance + 100_000_000.0

    def test_deposit_facility(self, engine, db):
        """Bank deposits at CB — wallet balance should decrease."""
        bank = db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == "bank-sgbci-001"
        ).first()
        initial_balance = bank.balance_ecfa

        result = engine.open_deposit_facility(
            bank_wallet_id="bank-sgbci-001",
            amount_ecfa=50_000_000.0,
        )

        assert result["facility_type"] == "DEPOSIT"
        assert result["rate_percent"] == 1.50  # default taux depot
        assert result["bank_new_balance"] == initial_balance - 50_000_000.0

    def test_deposit_insufficient_balance(self, engine, db):
        """Deposit facility should fail if bank has insufficient balance."""
        with pytest.raises(ValueError, match="Insufficient balance"):
            engine.open_deposit_facility(
                bank_wallet_id="bank-sgbci-001",
                amount_ecfa=999_999_999_999.0,
            )

    def test_facility_maturation(self, engine, db):
        """Matured facilities should be processed and interest settled."""
        # Open a lending facility with past maturity
        engine.open_lending_facility(
            bank_wallet_id="bank-sgbci-001",
            amount_ecfa=10_000_000.0,
            maturity="OVERNIGHT",
        )

        # Force the maturity to the past
        facility = db.query(CbdcStandingFacility).filter(
            CbdcStandingFacility.status == "active"
        ).first()
        facility.matures_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        result = engine.mature_facilities()
        assert result["facilities_matured"] == 1
        assert result["total_interest_ecfa"] > 0

        # Facility should now be matured
        facility = db.query(CbdcStandingFacility).filter(
            CbdcStandingFacility.facility_id == facility.facility_id
        ).first()
        assert facility.status == "matured"

    def test_lending_with_collateral(self, engine, db):
        """Lending with collateral should pledge the asset."""
        coll = CbdcEligibleCollateral(
            collateral_id="coll-001",
            asset_class="BCEAO_BOND",
            asset_description="BCEAO 5Y Bond 2029",
            face_value_ecfa=200_000_000.0,
            market_value_ecfa=195_000_000.0,
            haircut_percent=5.0,
            collateral_value_ecfa=185_250_000.0,
            is_eligible=True,
            effective_date=date.today(),
        )
        db.add(coll)
        db.commit()

        result = engine.open_lending_facility(
            bank_wallet_id="bank-sgbci-001",
            amount_ecfa=100_000_000.0,
            collateral_id="coll-001",
        )

        assert result["facility_id"]

        # Collateral should be pledged
        coll = db.query(CbdcEligibleCollateral).filter(
            CbdcEligibleCollateral.collateral_id == "coll-001"
        ).first()
        assert coll.is_pledged is True


# ── 4. Interest & Demurrage Tests ────────────────────────────────────

class TestInterestDemurrage:

    def test_interest_accrual_with_policy(self, engine, db):
        """Active INTEREST policy should credit wallets."""
        policy = CbdcPolicy(
            policy_id=str(uuid.uuid4()),
            policy_name="Retail Inclusion Interest",
            policy_type="INTEREST",
            conditions=json.dumps({
                "annual_rate_percent": 2.0,
                "min_balance_ecfa": 10_000.0,
                "max_balance_ecfa": 2_000_000.0,
            }),
            wallet_types="RETAIL",
            is_active=True,
            effective_from=datetime.utcnow() - timedelta(days=1),
            created_by="admin",
        )
        db.add(policy)
        db.commit()

        result = engine.apply_daily_interest()
        assert result["wallets_affected"] == 3  # 3 retail wallets
        assert result["total_interest_paid_ecfa"] > 0
        assert result["total_demurrage_collected_ecfa"] == 0

    def test_demurrage_above_threshold(self, engine, db):
        """DEMURRAGE policy should debit wallets above threshold."""
        # Give one wallet a large balance
        wallet = db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == "retail-ci-000"
        ).first()
        wallet.balance_ecfa = 10_000_000.0
        wallet.available_balance_ecfa = 10_000_000.0
        wallet.balance_limit_ecfa = 999_999_999.0
        db.commit()

        policy = CbdcPolicy(
            policy_id=str(uuid.uuid4()),
            policy_name="Hoarding Demurrage",
            policy_type="DEMURRAGE",
            conditions=json.dumps({
                "annual_rate_percent": 6.0,
                "threshold_ecfa": 5_000_000.0,
            }),
            wallet_types="RETAIL",
            is_active=True,
            effective_from=datetime.utcnow() - timedelta(days=1),
            created_by="admin",
        )
        db.add(policy)
        db.commit()

        result = engine.apply_daily_interest()
        assert result["total_demurrage_collected_ecfa"] > 0
        assert result["wallets_affected"] >= 1

    def test_no_interest_without_policy(self, engine):
        """No interest/demurrage applied if no active policies."""
        result = engine.apply_daily_interest()
        assert result["wallets_affected"] == 0
        assert result["total_interest_paid_ecfa"] == 0


# ── 5. Money Supply Tests ────────────────────────────────────────────

class TestMoneySupply:

    def test_compute_money_supply_basic(self, engine, db):
        """M1 should equal sum of retail + merchant + agent balances."""
        result = engine.compute_money_supply("CI")

        # 3 retail * 200K = 600K, no merchant/agent
        assert result["m1_narrow_money_ecfa"] == 600_000.0
        # M2 = M1 + bank = 600K + 500M
        assert result["m2_broad_money_ecfa"] == 500_600_000.0
        assert result["breakdown"]["retail_ecfa"] == 600_000.0
        assert result["breakdown"]["commercial_bank_ecfa"] == 500_000_000.0
        assert result["total_wallets"] >= 5  # CB + bank + 3 retail

    def test_money_supply_all_waemu(self, engine):
        """Compute across all countries."""
        result = engine.compute_money_supply()
        assert result["country_code"] == "ALL_WAEMU"
        assert result["m1_narrow_money_ecfa"] >= 0

    def test_reserve_multiplier(self, engine, db):
        """Reserve multiplier should be M2/M0."""
        # Simulate minting: make CB balance negative (= issuance)
        cb = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == "cb-ci-001").first()
        cb.balance_ecfa = -1_000_000_000.0  # minted 1B XOF
        db.commit()

        result = engine.compute_money_supply("CI")
        assert result["m0_base_money_ecfa"] == 1_000_000_000.0
        assert result["reserve_multiplier"] > 0


# ── 6. Policy Decision Tests ─────────────────────────────────────────

class TestPolicyDecisions:

    def test_record_decision(self, engine, db):
        """Recording a CPM decision should apply rate changes."""
        result = engine.record_policy_decision(
            meeting_date=date.today(),
            decision_summary="Increase taux directeur by 50bp to combat inflation",
            rationale="Inflation rose to 5.2%, above 3% target. WAEMU growth at 6.1%.",
            taux_directeur=4.00,
            taux_pret_marginal=6.00,
            taux_depot=2.00,
            reserve_ratio=3.0,
            inflation_rate=5.2,
            gdp_growth=6.1,
            votes_for=7,
            votes_against=1,
            votes_abstain=0,
        )

        assert result["decision_id"]
        assert result["rates"]["taux_directeur"] == 4.00
        assert result["status"] == "decided"

        # Verify the rates were actually applied
        rates = engine.get_current_rates()
        assert rates["TAUX_DIRECTEUR"]["rate_percent"] == 4.00

    def test_decision_history(self, engine, db):
        """Decision history should return past decisions."""
        engine.record_policy_decision(
            meeting_date=date.today() - timedelta(days=90),
            decision_summary="Hold rates steady",
            rationale="Inflation within target band.",
            taux_directeur=3.50,
            taux_pret_marginal=5.50,
            taux_depot=1.50,
            reserve_ratio=3.0,
        )
        engine.record_policy_decision(
            meeting_date=date.today(),
            decision_summary="Raise rates",
            rationale="Inflation above target.",
            taux_directeur=4.00,
            taux_pret_marginal=6.00,
            taux_depot=2.00,
            reserve_ratio=3.0,
        )

        history = engine.get_decision_history()
        assert len(history) == 2
        assert history[0]["taux_directeur"] == 4.00  # most recent first

    def test_decision_with_reserve_change(self, engine, db):
        """Decision that changes reserve ratio should update it."""
        engine.record_policy_decision(
            meeting_date=date.today(),
            decision_summary="Tighten monetary policy",
            rationale="Raise reserve ratio to cool credit growth.",
            taux_directeur=3.50,
            taux_pret_marginal=5.50,
            taux_depot=1.50,
            reserve_ratio=5.0,  # raised from 3.0
        )

        assert engine.get_current_reserve_ratio() == 5.0


# ── 7. Double-Entry Integrity for Facility Operations ────────────────

class TestFacilityLedgerIntegrity:

    def test_lending_creates_ledger_entries(self, engine, db):
        """Lending facility should create DEBIT + CREDIT entries."""
        engine.open_lending_facility(
            bank_wallet_id="bank-sgbci-001",
            amount_ecfa=10_000_000.0,
        )

        entries = db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.tx_type == "FACILITY_LENDING"
        ).all()

        assert len(entries) == 2
        types = {e.entry_type for e in entries}
        assert types == {"DEBIT", "CREDIT"}

        # Sum should be zero (double-entry invariant)
        debit_sum = sum(e.amount_ecfa for e in entries if e.entry_type == "DEBIT")
        credit_sum = sum(e.amount_ecfa for e in entries if e.entry_type == "CREDIT")
        assert debit_sum == credit_sum

    def test_interest_creates_ledger_entries(self, engine, db):
        """Interest accrual should create ledger entries."""
        policy = CbdcPolicy(
            policy_id=str(uuid.uuid4()),
            policy_name="Test Interest",
            policy_type="INTEREST",
            conditions=json.dumps({
                "annual_rate_percent": 5.0,
                "min_balance_ecfa": 0.0,
            }),
            wallet_types="RETAIL",
            is_active=True,
            effective_from=datetime.utcnow() - timedelta(days=1),
            created_by="admin",
        )
        db.add(policy)
        db.commit()

        engine.apply_daily_interest()

        interest_entries = db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.tx_type == "INTEREST_CREDIT"
        ).all()
        assert len(interest_entries) > 0
        # Each interest payment = 1 DEBIT (from CB) + 1 CREDIT (to wallet)
        assert len(interest_entries) % 2 == 0
