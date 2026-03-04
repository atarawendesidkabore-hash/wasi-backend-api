"""
eCFA CBDC Models for WASI Backend.

Account-based Central Bank Digital Currency platform for WAEMU/BCEAO.
17 models covering the full CBDC lifecycle:
  - Wallet hierarchy (Central Bank → Commercial Bank → Agent → Merchant → Retail)
  - Double-entry immutable ledger with hash chains
  - Tiered KYC/AML compliance
  - Programmable money policies (spending restrictions, expiry, demurrage)
  - Batch settlement with STAR-UEMOA RTGS hooks
  - Merchant acceptance network
  - Offline vouchers for rural connectivity gaps
  - Monetary aggregates with M0/M1/M2 breakdown for BCEAO reporting
  - FX rates for cross-border ECOWAS settlement
  - BCEAO monetary policy instruments:
    • Policy rate decisions (taux directeur, prêt marginal, dépôt)
    • Reserve requirements (réserves obligatoires)
    • Standing facilities (guichet de prêt marginal / dépôt)
    • Monetary Policy Committee decisions with audit trail
    • Eligible collateral framework with haircut schedules

eCFA is pegged 1:1 to XOF (CFA Franc). 1 EUR = 655.957 XOF.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime
from src.database.models import Base


# ---------------------------------------------------------------------------
# KYC Tier Limits (BCEAO-aligned)
# ---------------------------------------------------------------------------
# Tier 0: Anonymous        — 50,000 XOF/day,   200,000 XOF balance
# Tier 1: Phone-verified   — 500,000 XOF/day,  2,000,000 XOF balance
# Tier 2: ID-verified      — 5,000,000 XOF/day, 10,000,000 XOF balance
# Tier 3: Full KYC (inst.) — Unlimited

KYC_TIER_LIMITS = {
    0: {"daily": 50_000.0, "balance": 200_000.0},
    1: {"daily": 500_000.0, "balance": 2_000_000.0},
    2: {"daily": 5_000_000.0, "balance": 10_000_000.0},
    3: {"daily": float("inf"), "balance": float("inf")},
}


# ---------------------------------------------------------------------------
# 1. CbdcWallet — Hierarchical wallet accounts
# ---------------------------------------------------------------------------
class CbdcWallet(Base):
    __tablename__ = "cbdc_wallets"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(String(36), unique=True, nullable=False, index=True)

    # Ownership
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    phone_hash = Column(String(64), nullable=True, index=True)

    # Classification
    wallet_type = Column(String(20), nullable=False, index=True)
    # CENTRAL_BANK | COMMERCIAL_BANK | AGENT | MERCHANT | RETAIL
    institution_code = Column(String(20), nullable=True)
    institution_name = Column(String(200), nullable=True)

    # Balance (XOF — 1 eCFA = 1 XOF)
    balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)
    available_balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)
    hold_amount_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0, nullable=False)

    # KYC tier
    kyc_tier = Column(Integer, default=0, nullable=False)
    daily_limit_ecfa = Column(Numeric(18, 2, asdecimal=False), default=50_000.0)
    balance_limit_ecfa = Column(Numeric(18, 2, asdecimal=False), default=200_000.0)

    # Daily tracking
    daily_spent_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    daily_reset_date = Column(Date, nullable=True)

    # Status
    status = Column(String(20), default="active", nullable=False)
    # active | frozen | suspended | closed | pending_kyc
    freeze_reason = Column(String(255), nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    frozen_by = Column(String(36), nullable=True)

    # Freeze appeal mechanism (psychological safety: users can contest freezes)
    appeal_status = Column(String(20), nullable=True)
    # PENDING | UNDER_REVIEW | APPROVED | DENIED | None
    appeal_reason = Column(Text, nullable=True)
    appeal_submitted_at = Column(DateTime, nullable=True)
    auto_unfreeze_date = Column(Date, nullable=True)

    # Cryptographic identity
    public_key_hex = Column(String(128), nullable=True)
    key_version = Column(Integer, default=1)

    # PIN for USSD auth (bcrypt hash)
    pin_hash = Column(String(255), nullable=True)
    pin_attempts = Column(Integer, default=0)
    pin_locked_until = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_activity_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", backref="cbdc_wallets")
    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint("phone_hash", "country_id", "wallet_type",
                         name="uq_wallet_phone_country_type"),
    )


# ---------------------------------------------------------------------------
# 2. CbdcLedgerEntry — Immutable double-entry ledger
# ---------------------------------------------------------------------------
class CbdcLedgerEntry(Base):
    __tablename__ = "cbdc_ledger_entries"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(String(36), unique=True, nullable=False, index=True)
    transaction_id = Column(String(36), nullable=False, index=True)

    # Account
    wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id"),
                       nullable=False, index=True)

    # Entry type
    entry_type = Column(String(6), nullable=False)  # DEBIT | CREDIT
    amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    balance_after_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)

    # Classification
    tx_type = Column(String(30), nullable=False, index=True)
    # MINT | BURN | TRANSFER_P2P | TRANSFER_P2B | MERCHANT_PAYMENT |
    # GOV_DISBURSEMENT | SALARY | SUBSIDY | ESCROW_LOCK | ESCROW_RELEASE |
    # SETTLEMENT | FEE | REVERSAL | CASH_IN | CASH_OUT | CROSS_BORDER

    counterparty_wallet_id = Column(String(36), nullable=True)
    reference = Column(String(100), nullable=True)
    memo = Column(String(500), nullable=True)

    # Metadata
    country_code = Column(String(2), nullable=False, index=True)
    channel = Column(String(20), default="API")
    # API | USSD | BANK_GATEWAY | BATCH | ADMIN

    # Compliance markers
    aml_screened = Column(Boolean, default=False)
    aml_alert_id = Column(Integer, nullable=True)
    policy_id = Column(Integer, nullable=True)

    # Hash chain for tamper detection
    entry_hash = Column(String(64), nullable=False)
    prev_entry_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    wallet = relationship("CbdcWallet", foreign_keys=[wallet_id])


# ---------------------------------------------------------------------------
# 3. CbdcTransaction — User-facing transaction record
# ---------------------------------------------------------------------------
class CbdcTransaction(Base):
    __tablename__ = "cbdc_transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(36), unique=True, nullable=False, index=True)

    # Parties
    sender_wallet_id = Column(String(36), nullable=True, index=True)
    receiver_wallet_id = Column(String(36), nullable=True, index=True)

    # Amount
    amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    fee_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)

    # Classification
    tx_type = Column(String(30), nullable=False, index=True)
    channel = Column(String(20), default="API")

    # Status
    status = Column(String(20), default="pending", nullable=False, index=True)
    # pending | completed | failed | reversed | expired | held
    failure_reason = Column(String(255), nullable=True)

    # Cross-border
    is_cross_border = Column(Boolean, default=False)
    sender_country = Column(String(2), nullable=True)
    receiver_country = Column(String(2), nullable=True)

    # Programmable money
    policy_id = Column(Integer, nullable=True)
    spending_category = Column(String(50), nullable=True)
    # FOOD | HEALTH | EDUCATION | ANY
    expires_at = Column(DateTime, nullable=True)

    # Compliance
    aml_status = Column(String(20), default="pending")
    # pending | cleared | flagged | blocked
    kyc_tier_at_time = Column(Integer, nullable=True)

    # ED25519 signature
    sender_signature = Column(String(200), nullable=True)

    # COBOL interop
    cobol_ref = Column(String(35), nullable=True)

    # Timestamps
    initiated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    completed_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# 4. CbdcKycRecord — Tiered identity verification
# ---------------------------------------------------------------------------
class CbdcKycRecord(Base):
    __tablename__ = "cbdc_kyc_records"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id"),
                       nullable=False, index=True)

    tier_requested = Column(Integer, nullable=False)
    tier_granted = Column(Integer, nullable=True)

    # Identity data (encrypted at rest in production)
    id_type = Column(String(30), nullable=True)
    # PHONE_OTP | NATIONAL_ID | PASSPORT | ECOWAS_CARD | VOTER_ID | COMPANY_REG
    id_number_hash = Column(String(64), nullable=True)
    id_country = Column(String(2), nullable=True)
    full_name_encrypted = Column(Text, nullable=True)  # AES-256-GCM
    date_of_birth_hash = Column(String(64), nullable=True)

    # Outcome
    status = Column(String(20), default="pending", nullable=False)
    # pending | approved | rejected | expired | under_review
    verified_by = Column(String(50), nullable=True)
    rejection_reason = Column(String(255), nullable=True)

    # Risk scoring
    risk_score = Column(Float, nullable=True)  # 0.0 - 1.0
    pep_check = Column(Boolean, default=False)
    sanctions_check = Column(Boolean, default=False)

    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    wallet = relationship("CbdcWallet")


# ---------------------------------------------------------------------------
# 5. CbdcAmlAlert — AML/CFT screening alerts
# ---------------------------------------------------------------------------
class CbdcAmlAlert(Base):
    __tablename__ = "cbdc_aml_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(36), unique=True, nullable=False, index=True)

    wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id"),
                       nullable=False, index=True)
    transaction_id = Column(String(36), nullable=True, index=True)

    alert_type = Column(String(30), nullable=False, index=True)
    # VELOCITY | STRUCTURING | CROSS_BORDER | DORMANT |
    # BLACKLIST | ROUND_TRIP | SMURFING
    severity = Column(String(10), nullable=False)
    # LOW | MEDIUM | HIGH | CRITICAL

    description = Column(Text, nullable=False)
    evidence = Column(Text, nullable=True)  # JSON

    # Resolution
    status = Column(String(20), default="open", nullable=False, index=True)
    # open | under_review | escalated | resolved_clear | resolved_sar | false_positive
    assigned_to = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Regulatory
    sar_filed = Column(Boolean, default=False)
    sar_reference = Column(String(50), nullable=True)
    reporting_authority = Column(String(50), default="CENTIF")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    resolved_at = Column(DateTime, nullable=True)

    wallet = relationship("CbdcWallet")


# ---------------------------------------------------------------------------
# 6. CbdcPolicy — Programmable money rules
# ---------------------------------------------------------------------------
class CbdcPolicy(Base):
    __tablename__ = "cbdc_policies"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(String(36), unique=True, nullable=False, index=True)

    policy_name = Column(String(200), nullable=False)
    policy_type = Column(String(30), nullable=False, index=True)
    # SPENDING_RESTRICTION | EXPIRY | DEMURRAGE | INTEREST | ESCROW | VELOCITY_CAP

    # Conditions (JSON)
    conditions = Column(Text, nullable=False)

    # Scope
    country_codes = Column(String(50), nullable=True)
    wallet_types = Column(String(100), nullable=True)

    # Lifecycle
    is_active = Column(Boolean, default=True)
    effective_from = Column(DateTime, nullable=False)
    effective_until = Column(DateTime, nullable=True)

    created_by = Column(String(36), nullable=False)
    approved_by = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    cobol_policy_code = Column(String(10), nullable=True)


# ---------------------------------------------------------------------------
# 7. CbdcSettlement — Batch settlement records
# ---------------------------------------------------------------------------
class CbdcSettlement(Base):
    __tablename__ = "cbdc_settlements"

    id = Column(Integer, primary_key=True, index=True)
    settlement_id = Column(String(36), unique=True, nullable=False, index=True)

    settlement_type = Column(String(20), nullable=False)
    # DOMESTIC_NET | CROSS_BORDER_NET | RTGS_GROSS | MERCHANT_BATCH

    # Participants
    bank_a_code = Column(String(20), nullable=False)
    bank_b_code = Column(String(20), nullable=True)

    # Amounts
    gross_amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    net_amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    direction = Column(String(10), nullable=False)
    # A_TO_B | B_TO_A | BALANCED

    transaction_count = Column(Integer, nullable=False)

    # Countries
    country_codes = Column(String(50), nullable=False)
    is_cross_border = Column(Boolean, default=False)

    # Status
    status = Column(String(20), default="pending", nullable=False)
    # pending | submitted | confirmed | failed | reconciled
    star_uemoa_ref = Column(String(50), nullable=True)

    # Window
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    settled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 8. CbdcMerchant — Merchant acceptance registry
# ---------------------------------------------------------------------------
class CbdcMerchant(Base):
    __tablename__ = "cbdc_merchants"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(String(36), unique=True, nullable=False, index=True)
    wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id"),
                       nullable=False, index=True)

    business_name = Column(String(200), nullable=False)
    business_type = Column(String(50), nullable=False)
    # GROCERY | PHARMACY | FUEL | TELECOM | UTILITY | TRANSPORT |
    # RESTAURANT | MARKET | OTHER
    category_code = Column(String(10), nullable=False)

    country_code = Column(String(2), nullable=False, index=True)
    city = Column(String(100), nullable=True)
    gps_lat = Column(Float, nullable=True)
    gps_lon = Column(Float, nullable=True)

    # Payment acceptance
    ussd_code = Column(String(20), nullable=True)
    qr_payload = Column(String(500), nullable=True)

    # Settlement
    settlement_bank_code = Column(String(20), nullable=True)
    settlement_frequency = Column(String(20), default="daily")

    status = Column(String(20), default="active")
    kyc_tier = Column(Integer, default=2)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    wallet = relationship("CbdcWallet")


# ---------------------------------------------------------------------------
# 9. CbdcAuditLog — Immutable audit trail
# ---------------------------------------------------------------------------
class CbdcAuditLog(Base):
    __tablename__ = "cbdc_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(String(36), unique=True, nullable=False, index=True)

    event_type = Column(String(50), nullable=False, index=True)
    # WALLET_CREATED | WALLET_FROZEN | WALLET_UNFROZEN | KYC_SUBMITTED |
    # KYC_APPROVED | KYC_REJECTED | POLICY_CREATED | POLICY_ACTIVATED |
    # SETTLEMENT_SUBMITTED | ADMIN_LOGIN | KEY_ROTATED | AML_ALERT_CREATED |
    # AML_ALERT_RESOLVED | PIN_CHANGED | PIN_LOCKED | MINT_EXECUTED |
    # BURN_EXECUTED

    # Actor
    actor_wallet_id = Column(String(36), nullable=True)
    actor_ip = Column(String(45), nullable=True)
    actor_channel = Column(String(20), nullable=True)

    # Target
    target_wallet_id = Column(String(36), nullable=True, index=True)
    target_entity_type = Column(String(30), nullable=True)
    target_entity_id = Column(String(36), nullable=True)

    # Details (JSON)
    details = Column(Text, nullable=True)

    # Integrity
    entry_hash = Column(String(64), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# ---------------------------------------------------------------------------
# 10. CbdcOfflineVoucher — Store-and-forward for rural connectivity
# ---------------------------------------------------------------------------
class CbdcOfflineVoucher(Base):
    __tablename__ = "cbdc_offline_vouchers"

    id = Column(Integer, primary_key=True, index=True)
    voucher_id = Column(String(36), unique=True, nullable=False, index=True)
    voucher_hash = Column(String(64), unique=True, nullable=False, index=True)

    sender_wallet_id = Column(String(36), nullable=False, index=True)
    receiver_phone_hash = Column(String(64), nullable=False)
    amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)

    # Cryptographic proof
    sender_signature = Column(String(200), nullable=False)
    nonce = Column(String(32), nullable=False)

    # Status
    status = Column(String(20), default="issued", nullable=False)
    # issued | redeemed | expired | cancelled | double_spend_rejected

    issued_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # max 72 hours
    redeemed_at = Column(DateTime, nullable=True)
    reconciled_transaction_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 11. CbdcMonetaryAggregate — Daily BCEAO reporting snapshots
# ---------------------------------------------------------------------------
class CbdcMonetaryAggregate(Base):
    __tablename__ = "cbdc_monetary_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # Aggregate balances
    total_ecfa_circulation = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    retail_balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    merchant_balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    bank_balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    agent_balance_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Flow metrics
    total_minted_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_burned_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_p2p_volume_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_merchant_volume_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_cross_border_volume_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Activity
    active_wallets = Column(Integer, default=0)
    new_wallets = Column(Integer, default=0)
    total_transactions = Column(Integer, default=0)

    # ── Money supply breakdown (BCEAO standard) ──────────────────────
    # M0 = base money = eCFA minted - eCFA burned (CB liability)
    m0_base_money_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    # M1 = M0 in circulation = retail + merchant + agent balances (demand deposits)
    m1_narrow_money_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    # M2 = M1 + commercial bank reserve balances (broad money)
    m2_broad_money_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Reserve position
    total_required_reserves_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_held_reserves_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    reserve_compliance_ratio = Column(Float, default=0.0)  # held / required

    # Standing facility usage
    total_lending_facility_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_deposit_facility_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Policy rates snapshot (at time of aggregate)
    taux_directeur_percent = Column(Float, nullable=True)
    taux_pret_marginal_percent = Column(Float, nullable=True)
    taux_depot_percent = Column(Float, nullable=True)

    # Velocity of money (M * V = P * Q)
    velocity = Column(Float, nullable=True)

    # Interest/demurrage applied this day
    total_interest_paid_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_demurrage_collected_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    total_reserve_penalties_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("snapshot_date", "country_code",
                         name="uq_monetary_agg_date_country"),
    )


# ---------------------------------------------------------------------------
# 12. CbdcFxRate — eCFA exchange rates for cross-border settlement
# ---------------------------------------------------------------------------
class CbdcFxRate(Base):
    __tablename__ = "cbdc_fx_rates"

    id = Column(Integer, primary_key=True, index=True)

    base_currency = Column(String(5), default="XOF", nullable=False)
    target_currency = Column(String(5), nullable=False, index=True)
    rate = Column(Numeric(12, 6, asdecimal=False), nullable=False)
    inverse_rate = Column(Numeric(12, 6, asdecimal=False), nullable=False)

    effective_date = Column(Date, nullable=False, index=True)
    source = Column(String(50), default="BCEAO")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("target_currency", "effective_date",
                         name="uq_fx_rate_currency_date"),
    )


# ---------------------------------------------------------------------------
# 13. CbdcPolicyRate — BCEAO key interest rates (taux directeur etc.)
# ---------------------------------------------------------------------------
# BCEAO sets three key rates for the entire WAEMU zone:
#   - TAUX_DIRECTEUR: Main policy rate (taux minimum de soumission aux appels d'offres)
#   - TAUX_PRET_MARGINAL: Marginal lending facility rate (guichet de prêt marginal)
#   - TAUX_DEPOT: Deposit facility rate (rémunération des dépôts)
#   - TAUX_RESERVE: Remuneration rate on required reserves
# These rates drive all other rates in the system.
class CbdcPolicyRate(Base):
    __tablename__ = "cbdc_policy_rates"

    id = Column(Integer, primary_key=True, index=True)
    rate_id = Column(String(36), unique=True, nullable=False, index=True)

    rate_type = Column(String(30), nullable=False, index=True)
    # TAUX_DIRECTEUR | TAUX_PRET_MARGINAL | TAUX_DEPOT | TAUX_RESERVE

    rate_percent = Column(Float, nullable=False)  # e.g. 3.50 means 3.50%
    previous_rate_percent = Column(Float, nullable=True)

    # Decision context
    decision_id = Column(String(36), nullable=True, index=True)
    decided_by = Column(String(200), nullable=True)  # "Comité de Politique Monétaire"
    rationale = Column(Text, nullable=True)

    # Lifecycle
    effective_date = Column(Date, nullable=False, index=True)
    announced_date = Column(Date, nullable=True)
    superseded_date = Column(Date, nullable=True)  # when replaced by newer rate
    is_current = Column(Boolean, default=True, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("rate_type", "effective_date",
                         name="uq_policy_rate_type_date"),
    )


# ---------------------------------------------------------------------------
# 14. CbdcReserveRequirement — Per-bank reserve obligation tracking
# ---------------------------------------------------------------------------
# BCEAO imposes reserve ratios on commercial banks. In the eCFA system,
# COMMERCIAL_BANK wallets must maintain a minimum percentage of their
# total client deposits as a reserve balance held at the CENTRAL_BANK.
class CbdcReserveRequirement(Base):
    __tablename__ = "cbdc_reserve_requirements"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(String(36), unique=True, nullable=False, index=True)

    # Which bank
    bank_wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id", ondelete="CASCADE"),
                            nullable=False, index=True)
    institution_code = Column(String(20), nullable=False)
    country_code = Column(String(2), nullable=False, index=True)

    # Requirement
    required_ratio_percent = Column(Float, nullable=False)  # e.g. 3.0 = 3%
    deposit_base_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)  # total client deposits
    required_amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)  # ratio * deposit_base
    current_holding_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)  # actual reserve held

    # Compliance
    surplus_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)  # positive = excess reserve
    deficiency_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)  # positive = shortfall
    is_compliant = Column(Boolean, default=True, index=True)

    # Penalty
    penalty_rate_percent = Column(Float, default=3.5)  # rate on deficiency
    accrued_penalty_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Remuneration on required reserves (at TAUX_RESERVE)
    remuneration_rate_percent = Column(Float, default=0.0)
    accrued_remuneration_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Period
    computation_date = Column(Date, nullable=False, index=True)
    maintenance_period_start = Column(Date, nullable=False)
    maintenance_period_end = Column(Date, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    bank_wallet = relationship("CbdcWallet", foreign_keys=[bank_wallet_id])

    __table_args__ = (
        UniqueConstraint("bank_wallet_id", "computation_date",
                         name="uq_reserve_req_bank_date"),
    )


# ---------------------------------------------------------------------------
# 15. CbdcStandingFacility — Central bank lending/deposit windows
# ---------------------------------------------------------------------------
# BCEAO operates two standing facilities:
#   - LENDING: banks borrow overnight at taux de prêt marginal (policy rate + spread)
#   - DEPOSIT: banks deposit excess at taux de dépôt (policy rate - spread)
# These set the corridor ceiling and floor for interbank rates.
class CbdcStandingFacility(Base):
    __tablename__ = "cbdc_standing_facilities"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(String(36), unique=True, nullable=False, index=True)

    facility_type = Column(String(20), nullable=False, index=True)
    # LENDING | DEPOSIT | EMERGENCY_LIQUIDITY

    # Borrower / depositor
    bank_wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id", ondelete="CASCADE"),
                            nullable=False, index=True)
    institution_code = Column(String(20), nullable=False)

    # Terms
    amount_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    rate_percent = Column(Float, nullable=False)  # derived from policy rate
    interest_ecfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)  # accrued interest

    # Collateral (for lending)
    collateral_asset_id = Column(String(36), nullable=True)
    collateral_value_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=True)
    haircut_percent = Column(Float, nullable=True)

    # Lifecycle
    maturity = Column(String(20), default="OVERNIGHT")  # OVERNIGHT | 7_DAY | 28_DAY
    opened_at = Column(DateTime, nullable=False)
    matures_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active", nullable=False)
    # active | matured | repaid | defaulted

    # Ledger link
    open_transaction_id = Column(String(36), nullable=True)
    close_transaction_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    bank_wallet = relationship("CbdcWallet", foreign_keys=[bank_wallet_id])


# ---------------------------------------------------------------------------
# 16. CbdcMonetaryPolicyDecision — Committee decision records
# ---------------------------------------------------------------------------
# The Comité de Politique Monétaire (CPM) meets quarterly. Each decision
# is recorded with full audit trail including vote breakdown and rationale.
class CbdcMonetaryPolicyDecision(Base):
    __tablename__ = "cbdc_monetary_policy_decisions"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(String(36), unique=True, nullable=False, index=True)

    # Meeting
    meeting_date = Column(Date, nullable=False, index=True)
    meeting_type = Column(String(30), default="QUARTERLY")
    # QUARTERLY | EXTRAORDINARY | EMERGENCY

    # Decision
    decision_summary = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)

    # Rates decided (snapshot of all rates after this decision)
    taux_directeur = Column(Float, nullable=False)
    taux_pret_marginal = Column(Float, nullable=False)
    taux_depot = Column(Float, nullable=False)
    reserve_ratio_percent = Column(Float, nullable=False)

    # Previous rates (for comparison)
    prev_taux_directeur = Column(Float, nullable=True)
    prev_taux_pret_marginal = Column(Float, nullable=True)
    prev_taux_depot = Column(Float, nullable=True)
    prev_reserve_ratio_percent = Column(Float, nullable=True)

    # Economic context
    inflation_rate_percent = Column(Float, nullable=True)
    gdp_growth_percent = Column(Float, nullable=True)
    ecfa_circulation_total = Column(Numeric(18, 2, asdecimal=False), nullable=True)
    ecfa_velocity = Column(Float, nullable=True)

    # Vote
    votes_for = Column(Integer, nullable=True)
    votes_against = Column(Integer, nullable=True)
    votes_abstain = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), default="decided", nullable=False)
    # decided | published | implemented | superseded
    effective_date = Column(Date, nullable=False)
    published_at = Column(DateTime, nullable=True)
    implemented_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 17. CbdcEligibleCollateral — Collateral framework for lending facilities
# ---------------------------------------------------------------------------
# Banks borrowing from the standing facility must pledge eligible collateral.
# Each asset class has a haircut schedule set by BCEAO.
class CbdcEligibleCollateral(Base):
    __tablename__ = "cbdc_eligible_collateral"

    id = Column(Integer, primary_key=True, index=True)
    collateral_id = Column(String(36), unique=True, nullable=False, index=True)

    asset_class = Column(String(50), nullable=False, index=True)
    # ECFA_TREASURY_BILL | BCEAO_BOND | GOVT_BOND | CORPORATE_BOND | BANK_DEPOSIT

    asset_description = Column(String(200), nullable=False)
    issuer = Column(String(100), nullable=True)  # "BCEAO" | "Trésor CI" | bank name
    issuer_country = Column(String(2), nullable=True)

    # Valuation
    face_value_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    market_value_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    haircut_percent = Column(Float, nullable=False)  # e.g. 5.0 = 5%
    collateral_value_ecfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)  # market * (1 - haircut)

    # Rating
    min_credit_rating = Column(String(10), nullable=True)  # "BBB-" etc.
    maturity_date = Column(Date, nullable=True)

    # Ownership
    owner_wallet_id = Column(String(36), ForeignKey("cbdc_wallets.wallet_id", ondelete="SET NULL"),
                             nullable=True, index=True)
    is_pledged = Column(Boolean, default=False)  # currently used as collateral
    pledged_to_facility_id = Column(String(36), nullable=True)

    # Status
    is_eligible = Column(Boolean, default=True, index=True)
    suspended_reason = Column(String(200), nullable=True)

    effective_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner_wallet = relationship("CbdcWallet", foreign_keys=[owner_wallet_id])
