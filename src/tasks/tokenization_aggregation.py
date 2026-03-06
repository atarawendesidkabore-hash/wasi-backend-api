"""
Tokenization Data Aggregation & Payment Disbursement Tasks.

run_tokenization_aggregation()  — Compute daily aggregates for all 16 countries
run_payment_disbursement()      — Batch process queued payments
seed_tokenization_demo_data()   — Seed demo data for development

Schedule:
  - Aggregation: every 4 hours
  - Disbursement: daily at 20:00 UTC
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import threading
import uuid
from datetime import timezone, date, datetime, timedelta

from src.database.connection import SessionLocal
from src.database.models import Country
from src.database.tokenization_models import (
    DataToken, DailyActivityDeclaration, BusinessDataSubmission,
    TaxCreditLedger, ContractMilestone, MilestoneVerification,
    FasoMeaboWorker, WorkerCheckIn, PaymentDisbursement,
    TokenizationDailyAggregate,
)
from src.config import settings
from src.engines.tokenization_engine import PaymentDisbursementEngine

logger = logging.getLogger(__name__)
_tokenization_lock = threading.Lock()

# 16 ECOWAS countries with expected daily activity volumes
COUNTRY_ACTIVITY_SCALE = {
    # Primary: high volume
    "NG": 80, "CI": 60, "GH": 50, "SN": 40,
    # Secondary: medium volume
    "BF": 25, "ML": 20, "GN": 20, "BJ": 15, "TG": 15,
    # Tertiary: low volume
    "NE": 8, "MR": 6, "GW": 5, "SL": 5, "LR": 5, "GM": 4, "CV": 3,
}


def run_tokenization_aggregation(db=None, target_date: date = None) -> dict:
    """
    Compute daily TokenizationDailyAggregate for all 16 ECOWAS countries.
    If target_date is provided, only aggregates that date; otherwise discovers all dates.
    """
    if not _tokenization_lock.acquire(blocking=False):
        logger.warning("tokenization_aggregation: previous run still in progress, skipping")
        return {"skipped": True}

    from sqlalchemy import func, distinct, union_all, select

    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        if target_date:
            all_dates = [target_date]
        else:
            # Discover dates with tokenization data (last 7 days only)
            cutoff = date.today() - timedelta(days=7)
            date_queries = [
                select(DailyActivityDeclaration.period_date.label("d")).where(DailyActivityDeclaration.period_date >= cutoff),
                select(BusinessDataSubmission.period_date.label("d")).where(BusinessDataSubmission.period_date >= cutoff),
                select(WorkerCheckIn.check_in_date.label("d")).where(WorkerCheckIn.check_in_date >= cutoff),
            ]
            combined = union_all(*date_queries).subquery()
            all_dates = sorted(
                set(r[0] for r in db.query(combined.c.d).distinct().all() if r[0])
            )

        if not all_dates:
            return {
                "status": "no_data",
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

        # Get active countries
        countries = db.query(Country).filter(Country.is_active.is_(True)).all()
        country_map = {c.id: c.code for c in countries}

        total_processed = 0

        for agg_date in all_dates:
            # End-of-day boundary for date-aware Pillar 3 filtering
            agg_date_end = datetime.combine(agg_date, datetime.max.time())

            for country in countries:
                cid = country.id

                # Pillar 1: Citizen data
                citizen_count = (
                    db.query(func.count(DailyActivityDeclaration.id))
                    .filter(
                        DailyActivityDeclaration.country_id == cid,
                        DailyActivityDeclaration.period_date == agg_date,
                    )
                    .scalar()
                ) or 0

                unique_reporters = (
                    db.query(func.count(distinct(DailyActivityDeclaration.phone_hash)))
                    .filter(
                        DailyActivityDeclaration.country_id == cid,
                        DailyActivityDeclaration.period_date == agg_date,
                    )
                    .scalar()
                ) or 0

                citizen_paid = (
                    db.query(func.coalesce(func.sum(DailyActivityDeclaration.payment_amount_cfa), 0.0))
                    .filter(
                        DailyActivityDeclaration.country_id == cid,
                        DailyActivityDeclaration.period_date == agg_date,
                    )
                    .scalar()
                ) or 0.0

                # Pillar 2: Business data
                biz_count = (
                    db.query(func.count(BusinessDataSubmission.id))
                    .filter(
                        BusinessDataSubmission.country_id == cid,
                        BusinessDataSubmission.period_date == agg_date,
                    )
                    .scalar()
                ) or 0

                biz_credits = (
                    db.query(func.coalesce(func.sum(BusinessDataSubmission.tax_credit_earned_cfa), 0.0))
                    .filter(
                        BusinessDataSubmission.country_id == cid,
                        BusinessDataSubmission.period_date == agg_date,
                    )
                    .scalar()
                ) or 0.0

                # Pillar 3: Contracts & workers (date-aware)
                contracts_active = (
                    db.query(func.count(distinct(ContractMilestone.contract_id)))
                    .filter(
                        ContractMilestone.country_id == cid,
                        ContractMilestone.status.in_(["pending", "in_progress", "submitted"]),
                        ContractMilestone.created_at <= agg_date_end,
                    )
                    .scalar()
                ) or 0

                milestones_done = (
                    db.query(func.count(ContractMilestone.id))
                    .filter(
                        ContractMilestone.country_id == cid,
                        ContractMilestone.status.in_(["verified", "paid"]),
                        ContractMilestone.updated_at <= agg_date_end,
                    )
                    .scalar()
                ) or 0

                workers_in = (
                    db.query(func.count(WorkerCheckIn.id))
                    .filter(
                        WorkerCheckIn.check_in_date == agg_date,
                        WorkerCheckIn.worker_id.in_(
                            db.query(FasoMeaboWorker.id).filter(FasoMeaboWorker.country_id == cid)
                        ),
                    )
                    .scalar()
                ) or 0

                # Skip countries with zero activity
                if citizen_count == 0 and biz_count == 0 and workers_in == 0:
                    continue

                # Score calculations (0-100)
                expected = COUNTRY_ACTIVITY_SCALE.get(country.code, 10)

                citizen_score = min(100.0, (citizen_count / max(expected, 1)) * 100)
                business_score = min(100.0, (biz_count / max(expected * 0.1, 1)) * 100)
                contract_score = min(100.0, (milestones_done / max(contracts_active, 1)) * 100) if contracts_active > 0 else 50.0

                # Composite: citizen 40% + business 30% + contract 30%
                composite = (
                    citizen_score * 0.40 +
                    business_score * 0.30 +
                    contract_score * 0.30
                )

                # Cross-validation stats
                cross_val = (
                    db.query(func.count(DailyActivityDeclaration.id))
                    .filter(
                        DailyActivityDeclaration.country_id == cid,
                        DailyActivityDeclaration.period_date == agg_date,
                        DailyActivityDeclaration.is_cross_validated.is_(True),
                    )
                    .scalar()
                ) or 0
                cv_pct = (cross_val / citizen_count * 100) if citizen_count > 0 else 0.0

                avg_conf = min(0.90, 0.30 + 0.05 * unique_reporters)

                # Upsert aggregate
                existing = (
                    db.query(TokenizationDailyAggregate)
                    .filter(
                        TokenizationDailyAggregate.country_id == cid,
                        TokenizationDailyAggregate.period_date == agg_date,
                    )
                    .first()
                )

                if existing:
                    existing.citizen_reports_count = citizen_count
                    existing.citizen_unique_reporters = unique_reporters
                    existing.citizen_total_paid_cfa = citizen_paid
                    existing.citizen_data_score = citizen_score
                    existing.business_submissions_count = biz_count
                    existing.business_tax_credits_cfa = biz_credits
                    existing.business_data_score = business_score
                    existing.contracts_active = contracts_active
                    existing.milestones_verified = milestones_done
                    existing.workers_checked_in = workers_in
                    existing.contract_score = contract_score
                    existing.tokenization_composite_score = composite
                    existing.avg_confidence = avg_conf
                    existing.cross_validated_pct = cv_pct
                    existing.confidence = avg_conf
                    existing.calculated_at = datetime.now(timezone.utc)
                else:
                    agg = TokenizationDailyAggregate(
                        country_id=cid,
                        period_date=agg_date,
                        citizen_reports_count=citizen_count,
                        citizen_unique_reporters=unique_reporters,
                        citizen_total_paid_cfa=citizen_paid,
                        citizen_data_score=citizen_score,
                        business_submissions_count=biz_count,
                        business_tax_credits_cfa=biz_credits,
                        business_data_score=business_score,
                        contracts_active=contracts_active,
                        milestones_verified=milestones_done,
                        workers_checked_in=workers_in,
                        contract_score=contract_score,
                        tokenization_composite_score=composite,
                        avg_confidence=avg_conf,
                        cross_validated_pct=cv_pct,
                        confidence=avg_conf,
                    )
                    db.add(agg)

                total_processed += 1

        db.commit()

        return {
            "status": "completed",
            "period_dates": len(all_dates),
            "countries_processed": total_processed,
            "date_range": f"{all_dates[0]} to {all_dates[-1]}",
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        logger.error("Tokenization aggregation failed: %s", exc)
        db.rollback()
        return {
            "status": "error",
            "error": str(exc),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if own_session:
            db.close()
        _tokenization_lock.release()


def run_payment_disbursement(db=None) -> dict:
    """Batch process all queued tokenization payments."""
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        engine = PaymentDisbursementEngine(db)
        result = engine.process_batch()
        logger.info(
            "Payment disbursement: %d completed, %d failed",
            result.get("completed", 0), result.get("failed", 0),
        )
        return result
    except Exception as exc:
        logger.error("Payment disbursement failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if own_session:
            db.close()


# ══════════════════════════════════════════════════════════════════════
#  Demo Data Seeder
# ══════════════════════════════════════════════════════════════════════

ACTIVITY_TYPES = [
    "FARM_WORK", "MARKET_PRICE", "CROP_YIELD", "ROAD_CONDITION",
    "WEATHER", "WATER_ACCESS", "HEALTH_FACILITY", "SCHOOL_STATUS",
]

ACTIVITY_PAYMENTS = {
    "FARM_WORK": 100, "MARKET_PRICE": 75, "CROP_YIELD": 150,
    "ROAD_CONDITION": 50, "WEATHER": 50, "WATER_ACCESS": 75,
    "HEALTH_FACILITY": 200, "SCHOOL_STATUS": 100,
}

BUSINESS_TYPES = [
    "AGRICULTURE", "TRADING", "TRANSPORT", "MANUFACTURING",
    "SERVICES", "MINING", "RETAIL",
]

METRIC_TYPES_BY_TIER = {
    "A": ["CUSTOMS_DECLARATION", "BANK_STATEMENT"],
    "B": ["SALES_VOLUME", "INVENTORY_LEVEL", "SUPPLIER_COUNT", "TRADE_VOLUME"],
    "C": ["EMPLOYEE_COUNT", "ACTIVITY_REPORT"],
}

SKILL_TYPES = ["MASON", "CARPENTER", "LABORER", "ELECTRICIAN", "PLUMBER", "WELDER", "DRIVER", "OTHER"]
SKILL_RATES = {
    "MASON": 3500, "CARPENTER": 3000, "LABORER": 2500, "ELECTRICIAN": 4000,
    "PLUMBER": 3500, "WELDER": 4000, "DRIVER": 3500, "OTHER": 2500,
}

REGIONS_BY_COUNTRY = {
    "NG": ["Lagos", "Kano", "Abuja", "Port Harcourt"],
    "CI": ["Abidjan", "Bouaké", "Yamoussoukro", "San Pedro"],
    "GH": ["Accra", "Kumasi", "Tema", "Tamale"],
    "SN": ["Dakar", "Thiès", "Saint-Louis", "Ziguinchor"],
    "BF": ["Ouagadougou", "Bobo-Dioulasso", "Koudougou", "Ouahigouya"],
    "ML": ["Bamako", "Sikasso", "Mopti", "Ségou"],
    "GN": ["Conakry", "Nzérékoré", "Kankan", "Kindia"],
    "BJ": ["Cotonou", "Porto-Novo", "Parakou", "Abomey"],
    "TG": ["Lomé", "Kara", "Sokodé", "Atakpamé"],
    "NE": ["Niamey", "Zinder", "Maradi", "Agadez"],
    "MR": ["Nouakchott", "Nouadhibou"],
    "GW": ["Bissau", "Bafatá"],
    "SL": ["Freetown", "Bo"],
    "LR": ["Monrovia", "Buchanan"],
    "GM": ["Banjul", "Serekunda"],
    "CV": ["Praia", "Mindelo"],
}

CONTRACT_NAMES = [
    "Route nationale RN{n} — tronçon {region}",
    "Centre de santé de {region}",
    "École primaire de {region}",
    "Pont sur la rivière — {region}",
    "Marché central de {region}",
    "Forage hydraulique — {region}",
    "Electrification rurale — {region}",
]


def seed_tokenization_demo_data(db=None) -> int:
    """
    Seed demo tokenization data for all 16 ECOWAS countries.
    Volume proportional to WASI country weight.
    Returns total records created.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        # Check if data exists in any tokenization table
        existing = (
            db.query(DailyActivityDeclaration).count()
            + db.query(DataToken).filter(DataToken.pillar == "CITIZEN_DATA").count()
        )
        if existing > 0:
            logger.info("Tokenization demo data exists (%d records) — skipping", existing)
            return 0

        count = 0
        today = date.today()

        # Get all countries
        countries = {
            c.code: c for c in db.query(Country).filter(Country.is_active.is_(True)).all()
        }
        if not countries:
            logger.warning("No active countries found — cannot seed tokenization data")
            return 0

        # ── Pillar 1: Citizen activity declarations (30 days) ─────────
        logger.info("Seeding citizen activity declarations...")
        for cc, scale in COUNTRY_ACTIVITY_SCALE.items():
            country = countries.get(cc)
            if not country:
                continue

            regions = REGIONS_BY_COUNTRY.get(cc, ["Capital"])
            for day_offset in range(30):
                target_date = today - timedelta(days=day_offset)
                n_reports = max(1, int(scale * random.uniform(0.7, 1.3)))

                for i in range(n_reports):
                    phone = f"+{cc}{random.randint(700000000, 799999999)}"
                    phone_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), phone.encode("utf-8"), hashlib.sha256).hexdigest()
                    act_type = random.choice(ACTIVITY_TYPES)
                    region = random.choice(regions)
                    payment = ACTIVITY_PAYMENTS[act_type]

                    decl = DailyActivityDeclaration(
                        country_id=country.id,
                        period_date=target_date,
                        phone_hash=phone_hash,
                        activity_type=act_type,
                        location_name=region,
                        location_region=region,
                        quantity_value=round(random.uniform(10, 5000), 1) if act_type in ("CROP_YIELD", "MARKET_PRICE") else None,
                        quantity_unit="kg" if act_type == "CROP_YIELD" else ("CFA/kg" if act_type == "MARKET_PRICE" else None),
                        payment_amount_cfa=payment,
                        payment_status="paid" if day_offset > 1 else "approved",
                        confidence=round(random.uniform(0.30, 0.70), 2),
                        is_cross_validated=random.random() > 0.6,
                    )
                    db.add(decl)

                    token = DataToken(
                        token_id=str(uuid.uuid4()),
                        country_id=country.id,
                        pillar="CITIZEN_DATA",
                        token_type=act_type,
                        contributor_phone_hash=phone_hash,
                        token_value_cfa=payment,
                        token_value_usd=round(payment / 610.0, 4),
                        location_name=region,
                        status="paid" if day_offset > 1 else "validated",
                        confidence=decl.confidence,
                        data_quality="medium" if decl.confidence >= 0.50 else "low",
                        period_date=target_date,
                    )
                    db.add(token)
                    count += 2

            if count % 1000 == 0:
                db.flush()

        db.flush()
        logger.info("Seeded %d citizen activity records", count)

        # ── Pillar 2: Business data submissions (7 days, primary + secondary) ──
        logger.info("Seeding business data submissions...")
        biz_count = 0
        for cc in ["NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ", "TG"]:
            country = countries.get(cc)
            if not country:
                continue

            scale = COUNTRY_ACTIVITY_SCALE[cc]
            n_businesses = max(2, scale // 5)

            for day_offset in range(7):
                target_date = today - timedelta(days=day_offset)

                for b in range(n_businesses):
                    biz_phone = f"+{cc}BIZ{b:04d}"
                    biz_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), biz_phone.encode("utf-8"), hashlib.sha256).hexdigest()
                    biz_type = random.choice(BUSINESS_TYPES)
                    tier = random.choice(["A", "B", "C"])
                    metric = random.choice(METRIC_TYPES_BY_TIER[tier])
                    declared_val = round(random.uniform(100_000, 10_000_000), 0)
                    rate = {"A": 15.0, "B": 10.0, "C": 5.0}[tier]
                    credit = min(declared_val * rate / 100, 5_000_000)

                    sub = BusinessDataSubmission(
                        country_id=country.id,
                        period_date=target_date,
                        business_phone_hash=biz_hash,
                        business_type=biz_type,
                        data_tier=tier,
                        metrics=json.dumps({"declared_value_cfa": declared_val}),
                        metric_type=metric,
                        tax_credit_rate_pct=rate,
                        tax_credit_earned_cfa=credit,
                        confidence=round(random.uniform(0.50, 0.85), 2),
                    )
                    db.add(sub)
                    db.flush()

                    ledger = TaxCreditLedger(
                        country_id=country.id,
                        business_phone_hash=biz_hash,
                        fiscal_year=target_date.year,
                        credit_type="EARNED",
                        tier=tier,
                        amount_cfa=credit,
                        cumulative_earned_cfa=credit,
                        submission_id=sub.id,
                    )
                    db.add(ledger)

                    token = DataToken(
                        token_id=str(uuid.uuid4()),
                        country_id=country.id,
                        pillar="BUSINESS_DATA",
                        token_type=metric,
                        contributor_phone_hash=biz_hash,
                        token_value_cfa=credit,
                        token_value_usd=round(credit / 610.0, 2),
                        location_name=biz_type,
                        status="validated",
                        confidence=sub.confidence,
                        data_quality="medium",
                        period_date=target_date,
                    )
                    db.add(token)
                    biz_count += 3

        db.flush()
        count += biz_count
        logger.info("Seeded %d business data records", biz_count)

        # ── Pillar 3: Contracts, milestones, workers, check-ins ───────
        logger.info("Seeding contracts and workers...")
        contract_count = 0

        for cc in COUNTRY_ACTIVITY_SCALE:
            country = countries.get(cc)
            if not country:
                continue

            regions = REGIONS_BY_COUNTRY.get(cc, ["Capital"])
            scale = COUNTRY_ACTIVITY_SCALE[cc]
            n_contracts = max(1, scale // 10)

            # Create contracts + milestones
            for c in range(n_contracts):
                contract_id = str(uuid.uuid4())
                region = random.choice(regions)
                name_template = random.choice(CONTRACT_NAMES)
                contract_name = name_template.format(n=random.randint(1, 20), region=region)
                contractor_phone = f"+{cc}CONT{c:03d}"
                contractor_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), contractor_phone.encode("utf-8"), hashlib.sha256).hexdigest()

                n_milestones = random.randint(3, 6)
                for m in range(1, n_milestones + 1):
                    ms_value = round(random.uniform(5_000_000, 50_000_000), 0)
                    status = random.choice(["pending", "in_progress", "submitted", "verified", "paid"])

                    ms = ContractMilestone(
                        country_id=country.id,
                        contract_id=contract_id,
                        contract_name=contract_name,
                        contractor_phone_hash=contractor_hash,
                        milestone_number=m,
                        description=f"Étape {m}: {contract_name}",
                        value_cfa=ms_value,
                        location_name=region,
                        location_region=region,
                        expected_start_date=today - timedelta(days=90 - m * 15),
                        expected_end_date=today - timedelta(days=90 - m * 15 - 14),
                        status=status,
                        verification_count=random.randint(0, 5) if status in ("submitted", "verified", "paid") else 0,
                        confidence=round(random.uniform(0.40, 0.90), 2) if status in ("verified", "paid") else 0.0,
                        payment_released=status == "paid",
                    )
                    db.add(ms)
                    contract_count += 1

                    # Add verifications for submitted/verified milestones
                    if status in ("submitted", "verified", "paid"):
                        db.flush()
                        for v in range(random.randint(2, 5)):
                            v_phone = f"+{cc}VER{c:03d}{m}{v}"
                            v_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), v_phone.encode("utf-8"), hashlib.sha256).hexdigest()
                            v_type = random.choices(
                                ["CITIZEN", "INSPECTOR", "CONTRACTOR"],
                                weights=[6, 3, 1],
                            )[0]

                            verif = MilestoneVerification(
                                milestone_id=ms.id,
                                verifier_phone_hash=v_hash,
                                verifier_type=v_type,
                                vote=random.choice(["APPROVE", "APPROVE", "APPROVE", "PARTIAL"]),
                                completion_pct=round(random.uniform(60, 100), 0),
                                credibility_weight={"CITIZEN": 1.0, "INSPECTOR": 3.0, "CONTRACTOR": 0.5}[v_type],
                            )
                            db.add(verif)
                            contract_count += 1

            # Create workers
            n_workers = max(2, scale // 4)
            for w in range(n_workers):
                w_phone = f"+{cc}WRK{w:04d}"
                w_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), w_phone.encode("utf-8"), hashlib.sha256).hexdigest()
                skill = random.choice(SKILL_TYPES)

                worker = FasoMeaboWorker(
                    country_id=country.id,
                    phone_hash=w_hash,
                    country_code=cc,
                    skill_type=skill,
                    daily_rate_cfa=SKILL_RATES[skill],
                    total_days_worked=random.randint(0, 60),
                    total_earned_cfa=SKILL_RATES[skill] * random.randint(0, 60),
                )
                db.add(worker)
                db.flush()

                # Worker check-ins (7 days)
                for day_offset in range(7):
                    if random.random() > 0.7:  # 70% attendance
                        continue
                    checkin_date = today - timedelta(days=day_offset)

                    # Pick a random contract from this country
                    contract = (
                        db.query(ContractMilestone)
                        .filter(ContractMilestone.country_id == country.id)
                        .first()
                    )
                    if not contract:
                        continue

                    ci = WorkerCheckIn(
                        worker_id=worker.id,
                        contract_id=contract.contract_id,
                        check_in_date=checkin_date,
                        check_in_time=datetime.now(timezone.utc),
                        location_name=random.choice(regions),
                        daily_rate_cfa=worker.daily_rate_cfa,
                        payment_status="paid" if day_offset > 1 else "approved",
                        verified=random.random() > 0.3,
                    )
                    db.add(ci)
                    contract_count += 1

                contract_count += 1  # worker itself

        db.flush()
        count += contract_count
        logger.info("Seeded %d contract/worker records", contract_count)

        # ── Payment disbursements (sample) ────────────────────────────
        logger.info("Seeding payment disbursements...")
        pay_count = 0
        for cc in ["NG", "CI", "GH", "SN", "BF"]:
            country = countries.get(cc)
            if not country:
                continue

            for day_offset in range(7):
                target_date = today - timedelta(days=day_offset)
                for _ in range(random.randint(5, 20)):
                    phone = f"+{cc}{random.randint(700000000, 799999999)}"
                    phone_hash = hmac.new(settings.SECRET_KEY.encode("utf-8"), phone.encode("utf-8"), hashlib.sha256).hexdigest()
                    p_type = random.choice(["CITIZEN_DATA_INCOME", "WORKER_WAGE"])
                    pillar = "CITIZEN_DATA" if p_type == "CITIZEN_DATA_INCOME" else "FASO_MEABO"
                    amt = random.choice([50, 75, 100, 150, 200, 2500, 3000, 3500])

                    disb = PaymentDisbursement(
                        disbursement_id=str(uuid.uuid4()),
                        country_id=country.id,
                        recipient_phone_hash=phone_hash,
                        amount_cfa=amt,
                        amount_usd=round(amt / 610.0, 4),
                        payment_type=p_type,
                        pillar=pillar,
                        mobile_money_provider=random.choice(["ORANGE_MONEY", "MTN_MOMO", "WAVE"]),
                        status="completed" if day_offset > 0 else "queued",
                        batch_date=target_date,
                        completed_at=datetime.now(timezone.utc) if day_offset > 0 else None,
                    )
                    db.add(disb)
                    pay_count += 1

        db.flush()
        count += pay_count
        logger.info("Seeded %d payment records", pay_count)

        try:
            db.commit()
        except Exception as commit_exc:
            logger.warning("Demo seed commit failed (partial data?): %s — rolling back", commit_exc)
            db.rollback()
            return 0
        logger.info("Total tokenization demo records seeded: %d", count)
        return count

    except Exception as exc:
        logger.error("Tokenization demo seeding failed: %s", exc)
        db.rollback()
        return 0
    finally:
        if own_session:
            db.close()
