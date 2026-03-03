"""
Data Tokenization Models — 3 Pillars across 16 ECOWAS countries.

Pillar 1: Citizen Data Income (UBDI) — daily activity declarations
Pillar 2: Business Tax Credits (CITD) — business data submissions
Pillar 3: Faso Meabo Contract Acceleration — milestones + worker check-ins
"""

from datetime import timezone, datetime, date
from sqlalchemy import (
    Column, Integer, Float, Numeric, String, Text, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from src.database.models import Base


# ---------------------------------------------------------------------------
# Model 1: DataToken — core tokenized data record
# ---------------------------------------------------------------------------
class DataToken(Base):
    __tablename__ = "data_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(String(36), unique=True, nullable=False, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    # Classification
    pillar = Column(String(20), nullable=False, index=True)
    # CITIZEN_DATA | BUSINESS_DATA | FASO_MEABO
    token_type = Column(String(30), nullable=False, index=True)
    # ACTIVITY_REPORT | MARKET_PRICE | CROP_YIELD | ROAD_CONDITION |
    # WEATHER | WATER_ACCESS | HEALTH_FACILITY | SCHOOL_STATUS |
    # SALES_DATA | INVENTORY | SUPPLIER | TRADE_VOLUME | EMPLOYEE_COUNT |
    # MILESTONE_VERIFY | WORKER_CHECKIN

    # Contributor (privacy: SHA-256 hashed phone)
    contributor_phone_hash = Column(String(64), nullable=False, index=True)

    # Value
    token_value_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    token_value_usd = Column(Numeric(18, 2, asdecimal=False))

    # Location
    location_name = Column(String(200))
    location_lat = Column(Float)
    location_lon = Column(Float)

    # Raw payload
    raw_data = Column(Text)

    # Status lifecycle: pending → validated → paid → rejected → expired
    status = Column(String(20), default="pending", nullable=False, index=True)

    # Cross-validation
    validation_count = Column(Integer, default=0)
    confidence = Column(Float, default=0.30)
    data_quality = Column(String(10), default="low")

    # Payment tracking
    payment_id = Column(Integer, nullable=True)
    paid_at = Column(DateTime, nullable=True)

    period_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint(
            "contributor_phone_hash", "token_type", "period_date", "location_name",
            name="uq_data_token_contributor_type_date_location",
        ),
    )


# ---------------------------------------------------------------------------
# Model 2: DailyActivityDeclaration — Pillar 1 citizen reports
# ---------------------------------------------------------------------------
class DailyActivityDeclaration(Base):
    __tablename__ = "daily_activity_declarations"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    phone_hash = Column(String(64), nullable=False, index=True)

    # Activity: FARM_WORK | MARKET_PRICE | CROP_YIELD | ROAD_CONDITION |
    #           WEATHER | WATER_ACCESS | HEALTH_FACILITY | SCHOOL_STATUS
    activity_type = Column(String(30), nullable=False, index=True)
    activity_details = Column(Text)  # JSON
    location_name = Column(String(200))
    location_region = Column(String(100))

    # Quantitative (optional)
    quantity_value = Column(Float)
    quantity_unit = Column(String(30))
    price_local = Column(Numeric(18, 2, asdecimal=False))
    local_currency = Column(String(5))

    # Payment
    payment_amount_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    payment_status = Column(String(20), default="pending")
    # pending | approved | paid | rejected
    payment_provider = Column(String(20))

    # Cross-validation
    validation_count = Column(Integer, default=0)
    confidence = Column(Float, default=0.30)
    is_cross_validated = Column(Boolean, default=False)

    # Security signal
    proof_of_life_flag = Column(Boolean, default=True)

    data_source = Column(String(30), default="ussd_declaration")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint(
            "phone_hash", "activity_type", "period_date", "location_name",
            name="uq_activity_decl_phone_type_date_loc",
        ),
    )


# ---------------------------------------------------------------------------
# Model 3: BusinessDataSubmission — Pillar 2 business monthly data
# ---------------------------------------------------------------------------
class BusinessDataSubmission(Base):
    __tablename__ = "business_data_submissions"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    business_phone_hash = Column(String(64), nullable=False, index=True)
    business_type = Column(String(50), nullable=False)
    # AGRICULTURE | TRADING | TRANSPORT | MANUFACTURING | SERVICES | MINING | RETAIL

    # Tier: A (customs/bank, 15%) | B (sales/inventory, 10%) | C (employee/activity, 5%)
    data_tier = Column(String(1), nullable=False)

    # Metrics (JSON)
    metrics = Column(Text, nullable=False)
    metric_type = Column(String(30), nullable=False)
    # CUSTOMS_DECLARATION | BANK_STATEMENT | SALES_VOLUME | INVENTORY_LEVEL |
    # SUPPLIER_COUNT | TRADE_VOLUME | EMPLOYEE_COUNT | ACTIVITY_REPORT

    # Tax credit
    tax_credit_rate_pct = Column(Float, nullable=False)
    tax_credit_earned_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Validation
    validation_status = Column(String(20), default="submitted")
    # submitted | under_review | validated | rejected
    confidence = Column(Float, default=0.50)
    validated_at = Column(DateTime)

    data_source = Column(String(30), default="ussd_business")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint(
            "business_phone_hash", "metric_type", "period_date",
            name="uq_biz_submission_phone_metric_date",
        ),
    )


# ---------------------------------------------------------------------------
# Model 4: TaxCreditLedger — per-business fiscal year credit tracking
# ---------------------------------------------------------------------------
class TaxCreditLedger(Base):
    __tablename__ = "tax_credit_ledger"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    business_phone_hash = Column(String(64), nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=False, index=True)

    # EARNED | USED | EXPIRED
    credit_type = Column(String(20), nullable=False)
    tier = Column(String(1), nullable=False)  # A | B | C
    amount_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)

    # Running totals
    cumulative_earned_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    cumulative_used_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    # Caps: 25% of tax liability, max 5M CFA/business/year
    tax_liability_cfa = Column(Numeric(18, 2, asdecimal=False))
    cap_pct = Column(Float, default=25.0)
    cap_absolute_cfa = Column(Numeric(18, 2, asdecimal=False), default=5_000_000.0)

    submission_id = Column(Integer, ForeignKey("business_data_submissions.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint(
            "business_phone_hash", "fiscal_year", "submission_id",
            name="uq_tax_credit_phone_year_submission",
        ),
    )


# ---------------------------------------------------------------------------
# Model 5: ContractMilestone — Pillar 3 government contract milestones
# ---------------------------------------------------------------------------
class ContractMilestone(Base):
    __tablename__ = "contract_milestones"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    contract_id = Column(String(36), nullable=False, index=True)
    contract_name = Column(String(300), nullable=False)
    contractor_phone_hash = Column(String(64), nullable=False, index=True)

    milestone_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    value_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    location_name = Column(String(200))
    location_region = Column(String(100))

    expected_start_date = Column(Date)
    expected_end_date = Column(Date)
    actual_start_date = Column(Date)
    actual_end_date = Column(Date)

    # pending | in_progress | submitted | verified | paid | disputed | cancelled
    status = Column(String(20), default="pending", nullable=False, index=True)

    verification_count = Column(Integer, default=0)
    verification_required = Column(Integer, default=3)
    confidence = Column(Float, default=0.0)

    payment_released = Column(Boolean, default=False)
    payment_released_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint("contract_id", "milestone_number",
                         name="uq_contract_milestone_number"),
    )


# ---------------------------------------------------------------------------
# Model 6: MilestoneVerification — citizen/inspector verification votes
# ---------------------------------------------------------------------------
class MilestoneVerification(Base):
    __tablename__ = "milestone_verifications"

    id = Column(Integer, primary_key=True, index=True)
    milestone_id = Column(Integer, ForeignKey("contract_milestones.id"), nullable=False, index=True)

    verifier_phone_hash = Column(String(64), nullable=False, index=True)
    # CITIZEN | INSPECTOR | CONTRACTOR
    verifier_type = Column(String(20), nullable=False)

    # APPROVE | REJECT | PARTIAL
    vote = Column(String(10), nullable=False)
    completion_pct = Column(Float)
    evidence = Column(Text)  # JSON

    location_lat = Column(Float)
    location_lon = Column(Float)

    # Credibility: CITIZEN=1.0, INSPECTOR=3.0, CONTRACTOR=0.5
    credibility_weight = Column(Float, default=1.0)

    verified_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    milestone = relationship("ContractMilestone")

    __table_args__ = (
        UniqueConstraint("milestone_id", "verifier_phone_hash",
                         name="uq_verification_milestone_verifier"),
    )


# ---------------------------------------------------------------------------
# Model 7: FasoMeaboWorker — community laborer registry
# ---------------------------------------------------------------------------
class FasoMeaboWorker(Base):
    __tablename__ = "faso_meabo_workers"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    phone_hash = Column(String(64), nullable=False, index=True)
    country_code = Column(String(2), nullable=False, index=True)

    # MASON | CARPENTER | LABORER | ELECTRICIAN | PLUMBER | WELDER | DRIVER | OTHER
    skill_type = Column(String(30), nullable=False)
    daily_rate_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)

    is_active = Column(Boolean, default=True)
    total_days_worked = Column(Integer, default=0)
    total_earned_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)

    current_contract_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint("phone_hash", "country_code",
                         name="uq_worker_phone_country"),
    )


# ---------------------------------------------------------------------------
# Model 8: WorkerCheckIn — daily work attendance
# ---------------------------------------------------------------------------
class WorkerCheckIn(Base):
    __tablename__ = "worker_check_ins"

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("faso_meabo_workers.id"), nullable=False, index=True)
    contract_id = Column(String(36), nullable=False, index=True)
    milestone_id = Column(Integer, ForeignKey("contract_milestones.id"), nullable=True)

    check_in_date = Column(Date, nullable=False, index=True)
    check_in_time = Column(DateTime, nullable=False)

    location_lat = Column(Float)
    location_lon = Column(Float)
    location_name = Column(String(200))

    verified = Column(Boolean, default=False)
    verified_by_phone_hash = Column(String(64))

    daily_rate_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    # pending | approved | paid | rejected
    payment_status = Column(String(20), default="pending")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    worker = relationship("FasoMeaboWorker")

    __table_args__ = (
        UniqueConstraint("worker_id", "contract_id", "check_in_date",
                         name="uq_checkin_worker_contract_date"),
    )


# ---------------------------------------------------------------------------
# Model 9: PaymentDisbursement — payment records for all 3 pillars
# ---------------------------------------------------------------------------
class PaymentDisbursement(Base):
    __tablename__ = "payment_disbursements"

    id = Column(Integer, primary_key=True, index=True)
    disbursement_id = Column(String(36), unique=True, nullable=False, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)

    recipient_phone_hash = Column(String(64), nullable=False, index=True)
    amount_cfa = Column(Numeric(18, 2, asdecimal=False), nullable=False)
    amount_usd = Column(Numeric(18, 2, asdecimal=False))

    # CITIZEN_DATA_INCOME | TAX_CREDIT | WORKER_WAGE | MILESTONE_RELEASE
    payment_type = Column(String(30), nullable=False, index=True)
    # CITIZEN_DATA | BUSINESS_DATA | FASO_MEABO
    pillar = Column(String(20), nullable=False)

    # Mobile money
    mobile_money_provider = Column(String(20))
    mobile_money_ref = Column(String(100))

    # eCFA integration
    ecfa_transaction_id = Column(String(36))

    # queued | processing | completed | failed | cancelled
    status = Column(String(20), default="queued", nullable=False, index=True)
    failure_reason = Column(String(255))

    batch_id = Column(String(36), index=True)
    batch_date = Column(Date)

    queued_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime)
    completed_at = Column(DateTime)

    country = relationship("Country")


# ---------------------------------------------------------------------------
# Model 10: TokenizationDailyAggregate — daily country-level scores
# ---------------------------------------------------------------------------
class TokenizationDailyAggregate(Base):
    __tablename__ = "tokenization_daily_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)

    # Pillar 1
    citizen_reports_count = Column(Integer, default=0)
    citizen_unique_reporters = Column(Integer, default=0)
    citizen_total_paid_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    citizen_data_score = Column(Float)  # 0-100

    # Pillar 2
    business_submissions_count = Column(Integer, default=0)
    business_tax_credits_cfa = Column(Numeric(18, 2, asdecimal=False), default=0.0)
    business_data_score = Column(Float)  # 0-100

    # Pillar 3
    contracts_active = Column(Integer, default=0)
    milestones_verified = Column(Integer, default=0)
    workers_checked_in = Column(Integer, default=0)
    contract_score = Column(Float)  # 0-100

    # Composite: citizen 40% + business 30% + contract 30%
    tokenization_composite_score = Column(Float)

    # Cross-validation health
    avg_confidence = Column(Float, default=0.0)
    cross_validated_pct = Column(Float, default=0.0)

    confidence = Column(Float, default=0.30)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    country = relationship("Country")

    __table_args__ = (
        UniqueConstraint("country_id", "period_date",
                         name="uq_tokenization_aggregate_country_date"),
    )
