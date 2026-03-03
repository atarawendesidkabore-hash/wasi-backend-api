"""
Data Tokenization Engine — 3 pillars across 16 ECOWAS countries.

TokenizationEngine     — create/validate/price data tokens
CrossValidationEngine  — cross-check reports, detect anomalies
PaymentDisbursementEngine — batch mobile-money / eCFA disbursements
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import Country
from src.database.tokenization_models import (
    DataToken, DailyActivityDeclaration, BusinessDataSubmission,
    TaxCreditLedger, ContractMilestone, MilestoneVerification,
    FasoMeaboWorker, WorkerCheckIn, PaymentDisbursement,
)

logger = logging.getLogger(__name__)

# ── Payment rates per activity type (CFA) ─────────────────────────────
ACTIVITY_PAYMENTS_CFA = {
    "FARM_WORK": 100,
    "MARKET_PRICE": 75,
    "CROP_YIELD": 150,
    "ROAD_CONDITION": 50,
    "WEATHER": 50,
    "WATER_ACCESS": 75,
    "HEALTH_FACILITY": 200,
    "SCHOOL_STATUS": 100,
}

# ── Tier classification for business data ──────────────────────────────
METRIC_TO_TIER = {
    "CUSTOMS_DECLARATION": "A",
    "BANK_STATEMENT": "A",
    "SALES_VOLUME": "B",
    "INVENTORY_LEVEL": "B",
    "SUPPLIER_COUNT": "B",
    "TRADE_VOLUME": "B",
    "EMPLOYEE_COUNT": "C",
    "ACTIVITY_REPORT": "C",
}

TIER_CREDIT_RATES = {"A": 15.0, "B": 10.0, "C": 5.0}

# ── FX rates (same as ussd_engine) ────────────────────────────────────
DEFAULT_FX_RATES = {
    "XOF": 610.0, "NGN": 1550.0, "GHS": 15.0, "GNF": 8600.0,
    "SLE": 22.0, "LRD": 192.0, "GMD": 70.0, "MRU": 40.0, "CVE": 102.0,
}

COUNTRY_CURRENCY = {
    "CI": "XOF", "SN": "XOF", "ML": "XOF", "BF": "XOF",
    "BJ": "XOF", "TG": "XOF", "NE": "XOF", "GW": "XOF",
    "NG": "NGN", "GH": "GHS", "GN": "GNF", "SL": "SLE",
    "LR": "LRD", "GM": "GMD", "MR": "MRU", "CV": "CVE",
}

# Default MoMo provider per country
DEFAULT_PROVIDER = {
    "CI": "ORANGE_MONEY", "SN": "ORANGE_MONEY", "ML": "ORANGE_MONEY",
    "BF": "ORANGE_MONEY", "NE": "ORANGE_MONEY", "GW": "ORANGE_MONEY",
    "NG": "MTN_MOMO", "GH": "MTN_MOMO",
    "BJ": "MOOV_MONEY", "TG": "MOOV_MONEY",
    "GN": "ORANGE_MONEY", "SL": "ORANGE_MONEY",
    "LR": "MTN_MOMO", "GM": "WAVE", "MR": "MOOV_MONEY", "CV": "WAVE",
}

# Credibility weights for milestone verification
CREDIBILITY = {"CITIZEN": 1.0, "INSPECTOR": 3.0, "CONTRACTOR": 0.5}


def _to_usd(amount_local: float, currency: str) -> float:
    rate = DEFAULT_FX_RATES.get(currency, 1.0)
    return round(amount_local / rate, 2) if rate > 0 else 0.0


# ══════════════════════════════════════════════════════════════════════
#  TokenizationEngine — create / validate / price tokens
# ══════════════════════════════════════════════════════════════════════
class TokenizationEngine:

    def __init__(self, db: Session):
        self.db = db

    # ── helpers ────────────────────────────────────────────────────────

    def _get_country_id(self, country_code: str) -> Optional[int]:
        country = (
            self.db.query(Country)
            .filter(Country.code == country_code.upper())
            .first()
        )
        return country.id if country else None

    # ── Pillar 1: Citizen data income ─────────────────────────────────

    def create_citizen_token(
        self,
        country_code: str,
        phone_hash: str,
        activity_type: str,
        location_name: str,
        location_region: str = None,
        quantity_value: float = None,
        quantity_unit: str = None,
        price_local: float = None,
        details: str = None,
    ) -> dict:
        country_id = self._get_country_id(country_code)
        if not country_id:
            return {"error": f"Unknown country: {country_code}"}

        today = date.today()
        currency = COUNTRY_CURRENCY.get(country_code, "XOF")
        payment_cfa = ACTIVITY_PAYMENTS_CFA.get(activity_type, 50)

        # Upsert activity declaration
        existing = (
            self.db.query(DailyActivityDeclaration)
            .filter(
                DailyActivityDeclaration.phone_hash == phone_hash,
                DailyActivityDeclaration.activity_type == activity_type,
                DailyActivityDeclaration.period_date == today,
                DailyActivityDeclaration.location_name == location_name,
            )
            .first()
        )

        if existing:
            # Update with additional details
            if quantity_value is not None and existing.quantity_value is not None:
                n = existing.validation_count or 1
                existing.quantity_value = (
                    (existing.quantity_value * n + quantity_value) / (n + 1)
                )
            existing.validation_count = (existing.validation_count or 0) + 1
            existing.confidence = min(0.90, 0.30 + 0.10 * existing.validation_count)
            self.db.flush()
            return {
                "status": "updated",
                "declaration_id": existing.id,
                "payment_cfa": 0,  # no double-pay
                "confidence": existing.confidence,
            }

        decl = DailyActivityDeclaration(
            country_id=country_id,
            period_date=today,
            phone_hash=phone_hash,
            activity_type=activity_type,
            activity_details=details,
            location_name=location_name,
            location_region=location_region,
            quantity_value=quantity_value,
            quantity_unit=quantity_unit,
            price_local=price_local,
            local_currency=currency,
            payment_amount_cfa=payment_cfa,
            payment_status="approved",
            confidence=0.30,
        )
        self.db.add(decl)
        self.db.flush()

        # Create DataToken
        token = DataToken(
            token_id=str(uuid.uuid4()),
            country_id=country_id,
            pillar="CITIZEN_DATA",
            token_type=activity_type,
            contributor_phone_hash=phone_hash,
            token_value_cfa=payment_cfa,
            token_value_usd=_to_usd(payment_cfa, "XOF"),
            location_name=location_name,
            raw_data=details,
            status="validated",
            confidence=0.30,
            data_quality="low",
            period_date=today,
        )
        self.db.add(token)
        self.db.commit()

        return {
            "status": "created",
            "declaration_id": decl.id,
            "token_id": token.token_id,
            "activity_type": activity_type,
            "payment_cfa": payment_cfa,
            "confidence": 0.30,
        }

    # ── Pillar 2: Business tax credits ────────────────────────────────

    def create_business_token(
        self,
        country_code: str,
        business_phone_hash: str,
        business_type: str,
        metric_type: str,
        metrics_json: str,
        period_date: date = None,
    ) -> dict:
        country_id = self._get_country_id(country_code)
        if not country_id:
            return {"error": f"Unknown country: {country_code}"}

        p_date = period_date or date.today()
        tier = METRIC_TO_TIER.get(metric_type, "C")
        credit_rate = TIER_CREDIT_RATES[tier]

        # Parse metrics to compute credit value
        try:
            metrics = json.loads(metrics_json) if isinstance(metrics_json, str) else metrics_json
        except (json.JSONDecodeError, TypeError):
            metrics = {}

        # Credit = rate% × declared value
        declared_value = float(metrics.get("declared_value_cfa", 0))
        raw_credit = declared_value * (credit_rate / 100.0)

        # Cap enforcement
        fiscal_year = p_date.year
        cumulative = (
            self.db.query(func.coalesce(func.sum(TaxCreditLedger.amount_cfa), 0.0))
            .filter(
                TaxCreditLedger.business_phone_hash == business_phone_hash,
                TaxCreditLedger.fiscal_year == fiscal_year,
                TaxCreditLedger.credit_type == "EARNED",
            )
            .scalar()
        ) or 0.0

        cap_absolute = 5_000_000.0
        remaining = max(0, cap_absolute - cumulative)
        credit_earned = min(raw_credit, remaining)

        # Upsert submission
        existing = (
            self.db.query(BusinessDataSubmission)
            .filter(
                BusinessDataSubmission.business_phone_hash == business_phone_hash,
                BusinessDataSubmission.metric_type == metric_type,
                BusinessDataSubmission.period_date == p_date,
            )
            .first()
        )

        if existing:
            existing.metrics = metrics_json
            existing.tax_credit_earned_cfa = credit_earned
            existing.confidence = min(0.90, existing.confidence + 0.10)
            self.db.flush()
            sub_id = existing.id
        else:
            sub = BusinessDataSubmission(
                country_id=country_id,
                period_date=p_date,
                business_phone_hash=business_phone_hash,
                business_type=business_type,
                data_tier=tier,
                metrics=metrics_json,
                metric_type=metric_type,
                tax_credit_rate_pct=credit_rate,
                tax_credit_earned_cfa=credit_earned,
                confidence=0.50,
            )
            self.db.add(sub)
            self.db.flush()
            sub_id = sub.id

        # Tax credit ledger entry
        if credit_earned > 0:
            ledger = TaxCreditLedger(
                country_id=country_id,
                business_phone_hash=business_phone_hash,
                fiscal_year=fiscal_year,
                credit_type="EARNED",
                tier=tier,
                amount_cfa=credit_earned,
                cumulative_earned_cfa=cumulative + credit_earned,
                submission_id=sub_id,
            )
            self.db.add(ledger)

        # DataToken
        token = DataToken(
            token_id=str(uuid.uuid4()),
            country_id=country_id,
            pillar="BUSINESS_DATA",
            token_type=metric_type,
            contributor_phone_hash=business_phone_hash,
            token_value_cfa=credit_earned,
            token_value_usd=_to_usd(credit_earned, "XOF"),
            location_name=business_type,
            raw_data=metrics_json,
            status="validated",
            confidence=0.50,
            data_quality="medium",
            period_date=p_date,
        )
        self.db.add(token)
        self.db.commit()

        return {
            "status": "created",
            "submission_id": sub_id,
            "token_id": token.token_id,
            "tier": tier,
            "credit_rate_pct": credit_rate,
            "credit_earned_cfa": credit_earned,
            "cumulative_earned_cfa": cumulative + credit_earned,
            "cap_remaining_cfa": cap_absolute - (cumulative + credit_earned),
        }

    # ── Pillar 3: Worker check-in ─────────────────────────────────────

    def create_worker_checkin(
        self,
        worker_phone_hash: str,
        contract_id: str,
        country_code: str,
        location_name: str = None,
        location_lat: float = None,
        location_lon: float = None,
    ) -> dict:
        worker = (
            self.db.query(FasoMeaboWorker)
            .filter(FasoMeaboWorker.phone_hash == worker_phone_hash)
            .first()
        )
        if not worker:
            return {"error": "Worker not registered"}

        today = date.today()

        # Duplicate check
        existing = (
            self.db.query(WorkerCheckIn)
            .filter(
                WorkerCheckIn.worker_id == worker.id,
                WorkerCheckIn.contract_id == contract_id,
                WorkerCheckIn.check_in_date == today,
            )
            .first()
        )
        if existing:
            return {"error": "Already checked in today", "check_in_id": existing.id}

        checkin = WorkerCheckIn(
            worker_id=worker.id,
            contract_id=contract_id,
            check_in_date=today,
            check_in_time=datetime.utcnow(),
            location_lat=location_lat,
            location_lon=location_lon,
            location_name=location_name,
            daily_rate_cfa=worker.daily_rate_cfa,
            payment_status="approved",
        )
        self.db.add(checkin)

        # Update worker stats
        worker.total_days_worked = (worker.total_days_worked or 0) + 1
        worker.total_earned_cfa = (worker.total_earned_cfa or 0) + worker.daily_rate_cfa
        worker.current_contract_id = contract_id

        # DataToken
        token = DataToken(
            token_id=str(uuid.uuid4()),
            country_id=worker.country_id,
            pillar="FASO_MEABO",
            token_type="WORKER_CHECKIN",
            contributor_phone_hash=worker_phone_hash,
            token_value_cfa=worker.daily_rate_cfa,
            token_value_usd=_to_usd(worker.daily_rate_cfa, "XOF"),
            location_name=location_name,
            status="validated",
            confidence=0.60,
            data_quality="medium",
            period_date=today,
        )
        self.db.add(token)
        self.db.commit()

        return {
            "status": "checked_in",
            "check_in_id": checkin.id,
            "token_id": token.token_id,
            "daily_rate_cfa": worker.daily_rate_cfa,
            "total_days": worker.total_days_worked,
        }

    # ── Pillar 3: Milestone verification ──────────────────────────────

    def submit_milestone_verification(
        self,
        milestone_id: int,
        verifier_phone_hash: str,
        verifier_type: str,
        vote: str,
        completion_pct: float = None,
        evidence_json: str = None,
        location_lat: float = None,
        location_lon: float = None,
    ) -> dict:
        milestone = (
            self.db.query(ContractMilestone)
            .filter(ContractMilestone.id == milestone_id)
            .first()
        )
        if not milestone:
            return {"error": "Milestone not found"}

        # Duplicate check
        existing = (
            self.db.query(MilestoneVerification)
            .filter(
                MilestoneVerification.milestone_id == milestone_id,
                MilestoneVerification.verifier_phone_hash == verifier_phone_hash,
            )
            .first()
        )
        if existing:
            return {"error": "Already verified", "verification_id": existing.id}

        weight = CREDIBILITY.get(verifier_type, 1.0)

        verification = MilestoneVerification(
            milestone_id=milestone_id,
            verifier_phone_hash=verifier_phone_hash,
            verifier_type=verifier_type,
            vote=vote,
            completion_pct=completion_pct,
            evidence=evidence_json,
            location_lat=location_lat,
            location_lon=location_lon,
            credibility_weight=weight,
        )
        self.db.add(verification)

        # Update milestone
        milestone.verification_count = (milestone.verification_count or 0) + 1

        # Compute weighted confidence from all verifications
        all_verifs = (
            self.db.query(MilestoneVerification)
            .filter(MilestoneVerification.milestone_id == milestone_id)
            .all()
        )
        total_weight = sum(v.credibility_weight for v in all_verifs) + weight
        approve_weight = sum(
            v.credibility_weight for v in all_verifs if v.vote == "APPROVE"
        )
        if vote == "APPROVE":
            approve_weight += weight

        milestone.confidence = round(approve_weight / total_weight, 4) if total_weight > 0 else 0.0

        # Auto-verify if threshold met
        auto_verified = False
        if (
            milestone.verification_count >= milestone.verification_required
            and milestone.confidence >= 0.60
            and milestone.status in ("submitted", "in_progress")
        ):
            milestone.status = "verified"
            auto_verified = True

        # DataToken for the verifier (citizen governance token)
        token = DataToken(
            token_id=str(uuid.uuid4()),
            country_id=milestone.country_id,
            pillar="FASO_MEABO",
            token_type="MILESTONE_VERIFY",
            contributor_phone_hash=verifier_phone_hash,
            token_value_cfa=50,  # small reward for civic participation
            token_value_usd=_to_usd(50, "XOF"),
            location_name=milestone.location_name,
            status="validated",
            confidence=milestone.confidence,
            data_quality="medium",
            period_date=date.today(),
        )
        self.db.add(token)
        self.db.commit()

        return {
            "status": "verified" if auto_verified else "recorded",
            "verification_id": verification.id,
            "milestone_status": milestone.status,
            "verification_count": milestone.verification_count,
            "confidence": milestone.confidence,
            "auto_verified": auto_verified,
        }

    # ── Token pricing ─────────────────────────────────────────────────

    @staticmethod
    def price_token(token_type: str, activity_type: str = None) -> float:
        if activity_type and activity_type in ACTIVITY_PAYMENTS_CFA:
            return ACTIVITY_PAYMENTS_CFA[activity_type]
        if token_type == "WORKER_CHECKIN":
            return 2500  # default daily rate
        if token_type == "MILESTONE_VERIFY":
            return 50
        return 50  # minimum token value


# ══════════════════════════════════════════════════════════════════════
#  CrossValidationEngine — cross-check citizen reports
# ══════════════════════════════════════════════════════════════════════
class CrossValidationEngine:

    def __init__(self, db: Session):
        self.db = db

    def validate_citizen_reports(
        self, country_id: int, period_date: date, activity_type: str = None
    ) -> dict:
        query = self.db.query(DailyActivityDeclaration).filter(
            DailyActivityDeclaration.country_id == country_id,
            DailyActivityDeclaration.period_date == period_date,
        )
        if activity_type:
            query = query.filter(DailyActivityDeclaration.activity_type == activity_type)

        declarations = query.all()
        if not declarations:
            return {"validated": 0, "total": 0}

        # Group by (location_region, activity_type)
        from collections import defaultdict
        region_groups = defaultdict(list)
        for d in declarations:
            key = (d.location_region or "UNKNOWN", d.activity_type)
            region_groups[key].append(d)

        validated = 0
        for key, group in region_groups.items():
            unique_reporters = len(set(d.phone_hash for d in group))
            if unique_reporters >= 3:
                # Cross-validated: boost confidence for all in group
                for d in group:
                    d.is_cross_validated = True
                    d.confidence = min(0.90, 0.40 + 0.10 * unique_reporters)
                    d.validation_count = unique_reporters
                validated += len(group)

        self.db.commit()

        return {
            "validated": validated,
            "total": len(declarations),
            "regions_checked": len(region_groups),
            "period_date": str(period_date),
        }

    def detect_anomalies(self, country_id: int, period_date: date) -> list:
        from datetime import timedelta

        # 30-day rolling average for price-type reports
        start = period_date - timedelta(days=30)
        history = (
            self.db.query(
                DailyActivityDeclaration.activity_type,
                DailyActivityDeclaration.location_region,
                func.avg(DailyActivityDeclaration.quantity_value).label("avg_val"),
                func.count().label("cnt"),
            )
            .filter(
                DailyActivityDeclaration.country_id == country_id,
                DailyActivityDeclaration.period_date.between(start, period_date - timedelta(days=1)),
                DailyActivityDeclaration.quantity_value.isnot(None),
            )
            .group_by(
                DailyActivityDeclaration.activity_type,
                DailyActivityDeclaration.location_region,
            )
            .all()
        )

        avg_map = {(r.activity_type, r.location_region): r.avg_val for r in history}

        # Today's reports
        today = (
            self.db.query(DailyActivityDeclaration)
            .filter(
                DailyActivityDeclaration.country_id == country_id,
                DailyActivityDeclaration.period_date == period_date,
                DailyActivityDeclaration.quantity_value.isnot(None),
            )
            .all()
        )

        anomalies = []
        for d in today:
            key = (d.activity_type, d.location_region)
            avg = avg_map.get(key)
            if avg and avg > 0:
                deviation = abs(d.quantity_value - avg) / avg
                if deviation > 1.0:  # >100% deviation
                    anomalies.append({
                        "declaration_id": d.id,
                        "activity_type": d.activity_type,
                        "region": d.location_region,
                        "reported_value": d.quantity_value,
                        "avg_value": round(avg, 2),
                        "deviation_pct": round(deviation * 100, 1),
                    })

        return anomalies

    def validate_milestone_claims(self, contract_id: str, milestone_number: int) -> dict:
        milestone = (
            self.db.query(ContractMilestone)
            .filter(
                ContractMilestone.contract_id == contract_id,
                ContractMilestone.milestone_number == milestone_number,
            )
            .first()
        )
        if not milestone:
            return {"error": "Milestone not found"}

        verifications = (
            self.db.query(MilestoneVerification)
            .filter(MilestoneVerification.milestone_id == milestone.id)
            .all()
        )

        if not verifications:
            return {
                "milestone_id": milestone.id,
                "verifications": 0,
                "confidence": 0.0,
                "consensus": "NO_DATA",
            }

        total_weight = sum(v.credibility_weight for v in verifications)
        approve_weight = sum(v.credibility_weight for v in verifications if v.vote == "APPROVE")
        reject_weight = sum(v.credibility_weight for v in verifications if v.vote == "REJECT")

        confidence = approve_weight / total_weight if total_weight > 0 else 0.0

        if confidence >= 0.70:
            consensus = "APPROVED"
        elif reject_weight / total_weight >= 0.50:
            consensus = "REJECTED"
        else:
            consensus = "INCONCLUSIVE"

        return {
            "milestone_id": milestone.id,
            "contract_id": contract_id,
            "verifications": len(verifications),
            "confidence": round(confidence, 4),
            "consensus": consensus,
            "approve_weight": approve_weight,
            "reject_weight": reject_weight,
        }


# ══════════════════════════════════════════════════════════════════════
#  PaymentDisbursementEngine — batch payments
# ══════════════════════════════════════════════════════════════════════
class PaymentDisbursementEngine:

    def __init__(self, db: Session):
        self.db = db

    def queue_citizen_payment(
        self, phone_hash: str, amount_cfa: float, country_id: int,
        country_code: str = None, provider: str = None,
    ) -> PaymentDisbursement:
        prov = provider or DEFAULT_PROVIDER.get(country_code or "", "ORANGE_MONEY")

        disbursement = PaymentDisbursement(
            disbursement_id=str(uuid.uuid4()),
            country_id=country_id,
            recipient_phone_hash=phone_hash,
            amount_cfa=amount_cfa,
            amount_usd=_to_usd(amount_cfa, "XOF"),
            payment_type="CITIZEN_DATA_INCOME",
            pillar="CITIZEN_DATA",
            mobile_money_provider=prov,
            status="queued",
            batch_date=date.today(),
        )
        self.db.add(disbursement)
        self.db.flush()
        return disbursement

    def queue_worker_payment(
        self, worker_id: int, daily_rate_cfa: float,
        contract_id: str, country_id: int,
    ) -> PaymentDisbursement:
        worker = self.db.query(FasoMeaboWorker).get(worker_id)
        phone_hash = worker.phone_hash if worker else "unknown"
        cc = worker.country_code if worker else ""

        disbursement = PaymentDisbursement(
            disbursement_id=str(uuid.uuid4()),
            country_id=country_id,
            recipient_phone_hash=phone_hash,
            amount_cfa=daily_rate_cfa,
            amount_usd=_to_usd(daily_rate_cfa, "XOF"),
            payment_type="WORKER_WAGE",
            pillar="FASO_MEABO",
            mobile_money_provider=DEFAULT_PROVIDER.get(cc, "ORANGE_MONEY"),
            status="queued",
            batch_date=date.today(),
        )
        self.db.add(disbursement)
        self.db.flush()
        return disbursement

    def queue_milestone_release(self, milestone_id: int) -> Optional[PaymentDisbursement]:
        milestone = self.db.query(ContractMilestone).get(milestone_id)
        if not milestone or milestone.status != "verified":
            return None

        country = self.db.query(Country).get(milestone.country_id)
        cc = country.code if country else ""

        disbursement = PaymentDisbursement(
            disbursement_id=str(uuid.uuid4()),
            country_id=milestone.country_id,
            recipient_phone_hash=milestone.contractor_phone_hash,
            amount_cfa=milestone.value_cfa,
            amount_usd=_to_usd(milestone.value_cfa, "XOF"),
            payment_type="MILESTONE_RELEASE",
            pillar="FASO_MEABO",
            mobile_money_provider=DEFAULT_PROVIDER.get(cc, "ORANGE_MONEY"),
            status="queued",
            batch_date=date.today(),
        )
        self.db.add(disbursement)

        milestone.payment_released = True
        milestone.payment_released_at = datetime.utcnow()
        milestone.status = "paid"

        self.db.flush()
        return disbursement

    def process_batch(self, batch_date: date = None) -> dict:
        target = batch_date or date.today()
        batch_id = str(uuid.uuid4())

        pending = (
            self.db.query(PaymentDisbursement)
            .filter(
                PaymentDisbursement.status == "queued",
                PaymentDisbursement.batch_date <= target,
            )
            .all()
        )

        completed = 0
        failed = 0
        total_cfa = 0.0

        for p in pending:
            p.batch_id = batch_id
            p.processed_at = datetime.utcnow()

            # Try eCFA wallet first
            ecfa_ok = self._try_ecfa_payment(p)
            if ecfa_ok:
                p.status = "completed"
                p.completed_at = datetime.utcnow()
                completed += 1
                total_cfa += p.amount_cfa
                continue

            # Fallback: mobile money stub
            ref = self._stub_mobile_money_send(
                p.recipient_phone_hash, p.amount_cfa, p.mobile_money_provider
            )
            if ref:
                p.mobile_money_ref = ref
                p.status = "completed"
                p.completed_at = datetime.utcnow()
                completed += 1
                total_cfa += p.amount_cfa
            else:
                p.status = "failed"
                p.failure_reason = "Mobile money stub failed"
                failed += 1

        self.db.commit()

        return {
            "batch_id": batch_id,
            "batch_date": str(target),
            "total_processed": completed + failed,
            "completed": completed,
            "failed": failed,
            "total_cfa": total_cfa,
        }

    def _try_ecfa_payment(self, payment: PaymentDisbursement) -> bool:
        """Try to pay via eCFA wallet. Returns True if successful."""
        try:
            from src.database.cbdc_models import CbdcWallet
            wallet = (
                self.db.query(CbdcWallet)
                .filter(
                    CbdcWallet.phone_hash == payment.recipient_phone_hash,
                    CbdcWallet.status == "active",
                )
                .first()
            )
            if not wallet:
                return False

            # Find government disbursement wallet
            gov_wallet = (
                self.db.query(CbdcWallet)
                .filter(
                    CbdcWallet.wallet_type == "CENTRAL_BANK",
                    CbdcWallet.status == "active",
                )
                .first()
            )
            if not gov_wallet or gov_wallet.available_balance_ecfa < payment.amount_cfa:
                return False

            from src.engines.cbdc_ledger_engine import CbdcLedgerEngine
            ledger = CbdcLedgerEngine(self.db)
            result = ledger.transfer(
                sender_wallet_id=gov_wallet.wallet_id,
                receiver_wallet_id=wallet.wallet_id,
                amount_ecfa=payment.amount_cfa,
                tx_type="GOV_DISBURSEMENT",
                channel="BATCH",
            )
            payment.ecfa_transaction_id = result.get("transaction_id")
            return True
        except Exception as exc:
            logger.debug("eCFA payment failed for %s: %s", payment.disbursement_id, exc)
            return False

    @staticmethod
    def _stub_mobile_money_send(phone_hash: str, amount: float, provider: str) -> str:
        """Stub — returns a mock reference. Real API integration in Phase 2."""
        return f"MOMO-{provider}-{uuid.uuid4().hex[:12].upper()}"
