"""
AfriCredit/MFI — Microfinance Institution Models for WASI Backend.

Provides financial inclusion for West African entrepreneurs:
  - Market traders, farmers, women entrepreneurs, informal sector workers
  - Micro-loans (50,000 — 3,000,000 XOF)
  - SME loans (3,000,001 — 50,000,000 XOF)
  - Agricultural loans (seasonal, grace period during harvest)
  - Group solidarity loans (tontine-compatible)

Key metrics tracked:
  - PAR30 / PAR90 (Portfolio at Risk)
  - Operational Self-Sufficiency (OSS > 110% target)
  - Cost per loan disbursed

Currency: XOF (CFA Franc). Amounts stored as integers (centimes).
Regulatory: BCEAO microfinance regulations (UEMOA zone).
"""
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, DateTime, Date,
    Boolean, Text, ForeignKey, UniqueConstraint, Enum,
)
from sqlalchemy.orm import relationship
from datetime import timezone, datetime
from src.database.models import Base


# ---------------------------------------------------------------------------
# Loan product types
# ---------------------------------------------------------------------------
LOAN_PRODUCTS = {
    "MICRO": {"min_xof": 50_000, "max_xof": 3_000_000, "max_term_months": 24},
    "SME": {"min_xof": 3_000_001, "max_xof": 50_000_000, "max_term_months": 60},
    "AGRICULTURAL": {"min_xof": 50_000, "max_xof": 10_000_000, "max_term_months": 18},
    "GROUP_SOLIDARITY": {"min_xof": 25_000, "max_xof": 5_000_000, "max_term_months": 12},
}

# Sector classifications for credit scoring
BORROWER_SECTORS = [
    "market_trade", "agriculture", "livestock", "artisan", "transport",
    "food_processing", "tailoring", "construction", "retail", "services",
]


# ---------------------------------------------------------------------------
# 1. MicrofinanceClient — Borrower profile + KYC
# ---------------------------------------------------------------------------
class MicrofinanceClient(Base):
    """
    Registered microfinance client (borrower).
    KYC levels: BASIC (phone+name), STANDARD (ID document), FULL (address+income proof).
    """
    __tablename__ = "mfi_clients"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Identity
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_hash = Column(String(64), nullable=False, index=True)  # SHA-256 of phone
    gender = Column(String(1))  # M / F
    date_of_birth = Column(Date)
    id_type = Column(String(30))  # CNIB | PASSPORT | VOTER_CARD
    id_number_hash = Column(String(64))  # SHA-256 of ID number

    # Location
    country_code = Column(String(2), nullable=False, index=True)
    city = Column(String(100))
    neighborhood = Column(String(100))

    # Business info
    business_name = Column(String(200))
    sector = Column(String(50))  # from BORROWER_SECTORS
    business_description = Column(Text)
    monthly_revenue_xof = Column(Integer, default=0)  # estimated monthly revenue
    years_in_business = Column(Float, default=0)

    # KYC
    kyc_level = Column(String(10), default="BASIC")  # BASIC | STANDARD | FULL
    kyc_verified_at = Column(DateTime)

    # Group membership (for solidarity loans)
    group_id = Column(Integer, ForeignKey("mfi_solidarity_groups.id"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    credit_score = Column(Float)  # 0-100, updated per scoring run
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    loans = relationship("MicroLoan", back_populates="client")
    group = relationship("SolidarityGroup", back_populates="members")
    user = relationship("User")


# ---------------------------------------------------------------------------
# 2. SolidarityGroup — Tontine-compatible group lending
# ---------------------------------------------------------------------------
class SolidarityGroup(Base):
    """
    Group of borrowers who co-guarantee each other's loans.
    Tontine model: if one defaults, group is collectively responsible.
    Minimum 5 members, maximum 30.
    """
    __tablename__ = "mfi_solidarity_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_name = Column(String(200), nullable=False)
    country_code = Column(String(2), nullable=False, index=True)
    city = Column(String(100))
    sector = Column(String(50))  # primary sector of group

    leader_client_id = Column(Integer, nullable=True)  # group leader
    member_count = Column(Integer, default=0)
    max_members = Column(Integer, default=30)

    # Performance
    total_loans_disbursed = Column(Integer, default=0)
    total_amount_disbursed_xof = Column(Integer, default=0)
    default_count = Column(Integer, default=0)
    group_score = Column(Float, default=50.0)  # 0-100

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    members = relationship("MicrofinanceClient", back_populates="group")


# ---------------------------------------------------------------------------
# 3. MicroLoan — Loan lifecycle
# ---------------------------------------------------------------------------
class MicroLoan(Base):
    """
    Individual micro-loan record.

    Lifecycle: APPLICATION → UNDER_REVIEW → APPROVED/REJECTED →
               DISBURSED → ACTIVE → REPAID/DEFAULTED/WRITTEN_OFF

    Interest methods:
      FLAT — interest on original principal for entire term
      DECLINING — interest on remaining balance each period
    """
    __tablename__ = "mfi_loans"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("mfi_clients.id"), nullable=False, index=True)
    loan_number = Column(String(20), unique=True, nullable=False, index=True)

    # Product
    product_type = Column(String(20), nullable=False)  # MICRO | SME | AGRICULTURAL | GROUP_SOLIDARITY
    purpose = Column(String(200))

    # Amounts (stored as integers = centimes XOF, display as XOF)
    principal_xof = Column(Integer, nullable=False)
    interest_rate_annual_pct = Column(Float, nullable=False)  # e.g. 18.0 for 18%
    interest_method = Column(String(10), default="DECLINING")  # FLAT | DECLINING

    # Terms
    term_months = Column(Integer, nullable=False)
    grace_period_months = Column(Integer, default=0)  # agricultural: grace during growing season
    repayment_frequency = Column(String(10), default="MONTHLY")  # WEEKLY | BIWEEKLY | MONTHLY

    # Disbursement
    disbursement_method = Column(String(20))  # MOBILE_MONEY | CASH | ECFA_WALLET
    disbursement_date = Column(Date)
    maturity_date = Column(Date)

    # Scoring at application
    application_score = Column(Float)  # 0-100 at time of application
    scoring_components = Column(Text, default="{}")  # JSON: 7 components

    # Collateral
    collateral_type = Column(String(50))  # NONE | INVENTORY | EQUIPMENT | GUARANTOR | GROUP_SOLIDARITY
    collateral_value_xof = Column(Integer, default=0)
    guarantor_client_id = Column(Integer, nullable=True)

    # Status
    status = Column(String(20), default="APPLICATION", index=True)
    # APPLICATION | UNDER_REVIEW | APPROVED | REJECTED | DISBURSED | ACTIVE | REPAID | DEFAULTED | WRITTEN_OFF

    # Repayment tracking
    total_paid_xof = Column(Integer, default=0)
    total_interest_paid_xof = Column(Integer, default=0)
    total_fees_paid_xof = Column(Integer, default=0)
    outstanding_balance_xof = Column(Integer, default=0)
    days_overdue = Column(Integer, default=0)
    last_payment_date = Column(Date)

    # Committee decision
    reviewed_by = Column(String(100))  # committee member name
    review_date = Column(DateTime)
    review_notes = Column(Text)
    rejection_reason = Column(String(200))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    client = relationship("MicrofinanceClient", back_populates="loans")
    repayments = relationship("LoanRepayment", back_populates="loan")
    schedule = relationship("RepaymentSchedule", back_populates="loan")


# ---------------------------------------------------------------------------
# 4. RepaymentSchedule — Expected payment plan
# ---------------------------------------------------------------------------
class RepaymentSchedule(Base):
    """
    Generated repayment schedule for a loan.
    One row per installment (e.g., 12 rows for a 12-month loan).
    """
    __tablename__ = "mfi_repayment_schedule"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("mfi_loans.id"), nullable=False, index=True)

    installment_number = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False, index=True)

    principal_due_xof = Column(Integer, nullable=False)
    interest_due_xof = Column(Integer, nullable=False)
    fees_due_xof = Column(Integer, default=0)
    total_due_xof = Column(Integer, nullable=False)

    # Tracking
    principal_paid_xof = Column(Integer, default=0)
    interest_paid_xof = Column(Integer, default=0)
    fees_paid_xof = Column(Integer, default=0)
    total_paid_xof = Column(Integer, default=0)

    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date)
    days_late = Column(Integer, default=0)

    loan = relationship("MicroLoan", back_populates="schedule")

    __table_args__ = (UniqueConstraint("loan_id", "installment_number"),)


# ---------------------------------------------------------------------------
# 5. LoanRepayment — Actual payments received
# ---------------------------------------------------------------------------
class LoanRepayment(Base):
    """
    Individual repayment transaction against a loan.
    """
    __tablename__ = "mfi_repayments"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("mfi_loans.id"), nullable=False, index=True)

    payment_date = Column(Date, nullable=False, index=True)
    amount_xof = Column(Integer, nullable=False)
    principal_portion_xof = Column(Integer, default=0)
    interest_portion_xof = Column(Integer, default=0)
    fees_portion_xof = Column(Integer, default=0)
    penalty_xof = Column(Integer, default=0)  # late payment penalty

    payment_method = Column(String(20))  # MOBILE_MONEY | CASH | ECFA_WALLET
    reference_number = Column(String(50))
    received_by = Column(String(100))  # agent/teller name

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    loan = relationship("MicroLoan", back_populates="repayments")


# ---------------------------------------------------------------------------
# 6. MFIPortfolioSnapshot — Daily portfolio health metrics
# ---------------------------------------------------------------------------
class MFIPortfolioSnapshot(Base):
    """
    Daily snapshot of the microfinance portfolio for management reporting.
    Tracks PAR30, PAR90, OSS, and other key MFI metrics.
    """
    __tablename__ = "mfi_portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(Date, nullable=False, unique=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # Portfolio size
    total_clients = Column(Integer, default=0)
    active_loans = Column(Integer, default=0)
    total_outstanding_xof = Column(Integer, default=0)
    total_disbursed_xof = Column(Integer, default=0)

    # Portfolio quality
    par30_pct = Column(Float, default=0.0)  # Portfolio at Risk > 30 days (target < 5%)
    par90_pct = Column(Float, default=0.0)  # Portfolio at Risk > 90 days
    write_off_ratio_pct = Column(Float, default=0.0)

    # Operational metrics
    oss_pct = Column(Float, default=0.0)  # Operational Self-Sufficiency (target > 110%)
    cost_per_loan_xof = Column(Integer, default=0)
    avg_loan_size_xof = Column(Integer, default=0)

    # Demographics
    women_pct = Column(Float, default=0.0)  # % of female borrowers
    rural_pct = Column(Float, default=0.0)  # % of rural borrowers
    youth_pct = Column(Float, default=0.0)  # % of borrowers under 35

    # Sector breakdown (JSON)
    sector_distribution = Column(Text, default="{}")

    computed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 7. MFIAuditLog — Compliance audit trail
# ---------------------------------------------------------------------------
class MFIAuditLog(Base):
    """
    Audit trail for all loan decisions and financial operations.
    Required by BCEAO microfinance regulations.
    """
    __tablename__ = "mfi_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    # LOAN_APPLICATION | LOAN_APPROVAL | LOAN_REJECTION | DISBURSEMENT |
    # REPAYMENT | DEFAULT_FLAG | WRITE_OFF | KYC_UPDATE | SCORE_UPDATE

    entity_type = Column(String(30), nullable=False)  # CLIENT | LOAN | GROUP | REPAYMENT
    entity_id = Column(Integer, nullable=False)
    actor = Column(String(100))  # user/system who performed action
    details = Column(Text, default="{}")  # JSON with action details
    ip_address = Column(String(45))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
