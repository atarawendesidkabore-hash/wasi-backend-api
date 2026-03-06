"""
AfriCredit/MFI Routes — /api/v3/mfi/

Microfinance institution management endpoints.
All endpoints require authentication. Credit costs noted per endpoint.

Endpoint groups:
  /clients     — Borrower registration + KYC
  /loans       — Loan application, scoring, approval, disbursement
  /repayments  — Payment recording
  /groups      — Solidarity group management
  /portfolio   — Portfolio health metrics (PAR30, OSS, impact)
  /tools       — Repayment schedule preview, scoring simulation
"""
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.database.microloan_models import (
    MicrofinanceClient, MicroLoan, RepaymentSchedule, LoanRepayment,
    MFIPortfolioSnapshot, MFIAuditLog, SolidarityGroup,
    LOAN_PRODUCTS,
)
from src.engines.microloan_engine import (
    micro_scorer, repayment_gen, portfolio_analytics,
)
from src.schemas.microloan import (
    ClientCreateRequest, LoanApplicationRequest, LoanDecisionRequest,
    RepaymentRequest, GroupCreateRequest, SchedulePreviewRequest,
)
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v3/mfi", tags=["AfriCredit/MFI"])
limiter = Limiter(key_func=get_remote_address)


def _hash(value: str) -> str:
    """SHA-256 hash for PII fields."""
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_loan_number() -> str:
    """Generate unique loan number: MFI-YYYYMMDD-XXXX."""
    today = date.today().strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:4].upper()
    return f"MFI-{today}-{short_id}"


def _audit(db: Session, action: str, entity_type: str, entity_id: int,
           actor: str, details: dict | None = None):
    """Write audit log entry."""
    db.add(MFIAuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        details=json.dumps(details or {}),
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/clients")
@limiter.limit("10/minute")
async def register_client(
    request: Request,
    req: ClientCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Register a new microfinance client. 2 credits."""
    deduct_credits(current_user, db, "/api/v3/mfi/clients", cost_multiplier=2.0)

    # Check duplicate phone
    phone_hash = _hash(req.phone)
    existing = db.query(MicrofinanceClient).filter(
        MicrofinanceClient.phone_hash == phone_hash
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Client with this phone already registered")

    client = MicrofinanceClient(
        user_id=current_user.id,
        first_name=req.first_name,
        last_name=req.last_name,
        phone_hash=phone_hash,
        gender=req.gender,
        date_of_birth=req.date_of_birth,
        id_type=req.id_type,
        id_number_hash=_hash(req.id_number) if req.id_number else None,
        country_code=req.country_code.upper(),
        city=req.city,
        neighborhood=req.neighborhood,
        business_name=req.business_name,
        sector=req.sector,
        business_description=req.business_description,
        monthly_revenue_xof=req.monthly_revenue_xof or 0,
        years_in_business=req.years_in_business or 0,
        kyc_level="STANDARD" if req.id_type else "BASIC",
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    _audit(db, "CLIENT_REGISTRATION", "CLIENT", client.id,
           current_user.username, {"country": req.country_code})
    db.commit()

    return {
        "success": True,
        "data": {
            "client_id": client.id,
            "name": f"{client.first_name} {client.last_name}",
            "country_code": client.country_code,
            "kyc_level": client.kyc_level,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/clients/{client_id}")
async def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get client profile. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/mfi/clients/{client_id}", cost_multiplier=1.0)

    client = db.query(MicrofinanceClient).filter(
        MicrofinanceClient.id == client_id
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    active_loans = db.query(MicroLoan).filter(
        MicroLoan.client_id == client_id,
        MicroLoan.status.in_(["ACTIVE", "DISBURSED"]),
    ).count()

    return {
        "success": True,
        "data": {
            "id": client.id,
            "first_name": client.first_name,
            "last_name": client.last_name,
            "country_code": client.country_code,
            "city": client.city,
            "sector": client.sector,
            "business_name": client.business_name,
            "monthly_revenue_xof": client.monthly_revenue_xof,
            "years_in_business": client.years_in_business,
            "kyc_level": client.kyc_level,
            "credit_score": client.credit_score,
            "active_loans": active_loans,
            "group_id": client.group_id,
            "is_active": client.is_active,
            "created_at": str(client.created_at),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/clients")
async def list_clients(
    country_code: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List clients with optional filters. 1 credit."""
    deduct_credits(current_user, db, "/api/v3/mfi/clients", cost_multiplier=1.0)

    query = db.query(MicrofinanceClient).filter(MicrofinanceClient.is_active == True)
    if country_code:
        query = query.filter(MicrofinanceClient.country_code == country_code.upper())
    if sector:
        query = query.filter(MicrofinanceClient.sector == sector)

    total = query.count()
    clients = query.order_by(MicrofinanceClient.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "data": [
            {
                "id": c.id,
                "name": f"{c.first_name} {c.last_name}",
                "country_code": c.country_code,
                "sector": c.sector,
                "kyc_level": c.kyc_level,
                "credit_score": c.credit_score,
            }
            for c in clients
        ],
        "total": total,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LOAN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/loans/apply")
@limiter.limit("5/minute")
async def apply_for_loan(
    request: Request,
    req: LoanApplicationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a loan application with automatic credit scoring. 5 credits.
    Returns score, components, and recommendation.
    """
    deduct_credits(current_user, db, "/api/v3/mfi/loans/apply", cost_multiplier=5.0)

    client = db.query(MicrofinanceClient).filter(
        MicrofinanceClient.id == req.client_id
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Validate product constraints
    product = LOAN_PRODUCTS.get(req.product_type)
    if not product:
        raise HTTPException(status_code=422, detail=f"Invalid product type: {req.product_type}")

    if req.principal_xof < product["min_xof"] or req.principal_xof > product["max_xof"]:
        raise HTTPException(
            status_code=422,
            detail=f"Amount {req.principal_xof:,} XOF outside {req.product_type} range "
                   f"({product['min_xof']:,} — {product['max_xof']:,} XOF)",
        )

    if req.term_months > product["max_term_months"]:
        raise HTTPException(
            status_code=422,
            detail=f"Term {req.term_months} months exceeds max {product['max_term_months']} for {req.product_type}",
        )

    # Default interest rate by product if not specified
    default_rates = {
        "MICRO": 24.0, "SME": 18.0, "AGRICULTURAL": 15.0, "GROUP_SOLIDARITY": 20.0,
    }
    rate = req.interest_rate_annual_pct or default_rates.get(req.product_type, 24.0)

    # Create loan record
    loan = MicroLoan(
        client_id=client.id,
        loan_number=_generate_loan_number(),
        product_type=req.product_type,
        purpose=req.purpose,
        principal_xof=req.principal_xof,
        interest_rate_annual_pct=rate,
        interest_method=req.interest_method,
        term_months=req.term_months,
        grace_period_months=req.grace_period_months,
        repayment_frequency=req.repayment_frequency,
        collateral_type=req.collateral_type,
        collateral_value_xof=req.collateral_value_xof or 0,
        guarantor_client_id=req.guarantor_client_id,
        disbursement_method=req.disbursement_method,
        outstanding_balance_xof=req.principal_xof,
        status="APPLICATION",
    )
    db.add(loan)
    db.flush()  # get loan.id

    # Run credit scoring
    score_result = micro_scorer.score(client, loan, db)
    loan.application_score = score_result["score"]
    loan.scoring_components = json.dumps(score_result["components"])

    # Update client credit score
    client.credit_score = score_result["score"]

    # Auto-advance status based on score
    if score_result["is_vetoed"]:
        loan.status = "REJECTED"
        loan.rejection_reason = "; ".join(score_result["vetoes"])
    else:
        loan.status = "UNDER_REVIEW"

    _audit(db, "LOAN_APPLICATION", "LOAN", loan.id, current_user.username, {
        "principal_xof": req.principal_xof,
        "product": req.product_type,
        "score": score_result["score"],
        "vetoed": score_result["is_vetoed"],
    })
    db.commit()
    db.refresh(loan)

    return {
        "success": True,
        "data": {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "status": loan.status,
            "principal_xof": loan.principal_xof,
            "product_type": loan.product_type,
            "scoring": {
                "score": score_result["score"],
                "components": score_result["components"],
                "vetoes": score_result["vetoes"],
                "recommendation": score_result["recommendation"],
            },
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/loans/{loan_id}/decision")
@limiter.limit("10/minute")
async def loan_decision(
    request: Request,
    loan_id: int,
    req: LoanDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Approve or reject a loan application. 3 credits.
    Only loans in UNDER_REVIEW status can be decided.
    """
    deduct_credits(current_user, db, f"/api/v3/mfi/loans/{loan_id}/decision", cost_multiplier=3.0)

    loan = db.query(MicroLoan).filter(MicroLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != "UNDER_REVIEW":
        raise HTTPException(status_code=409, detail=f"Loan status is {loan.status}, not UNDER_REVIEW")

    now = datetime.now(timezone.utc)

    if req.decision == "APPROVE":
        loan.status = "APPROVED"
        loan.reviewed_by = req.reviewer_name
        loan.review_date = now
        loan.review_notes = req.notes

        # Generate repayment schedule
        schedule = repayment_gen.generate(
            principal_xof=loan.principal_xof,
            annual_rate_pct=loan.interest_rate_annual_pct,
            term_months=loan.term_months,
            grace_months=loan.grace_period_months,
            method=loan.interest_method,
            start_date=date.today(),
            frequency=loan.repayment_frequency,
        )

        for item in schedule:
            db.add(RepaymentSchedule(
                loan_id=loan.id,
                installment_number=item["installment_number"],
                due_date=item["due_date"],
                principal_due_xof=item["principal_due_xof"],
                interest_due_xof=item["interest_due_xof"],
                total_due_xof=item["total_due_xof"],
            ))

        # Set maturity date
        if schedule:
            loan.maturity_date = schedule[-1]["due_date"]

        action = "LOAN_APPROVAL"
    elif req.decision == "REJECT":
        loan.status = "REJECTED"
        loan.reviewed_by = req.reviewer_name
        loan.review_date = now
        loan.review_notes = req.notes
        loan.rejection_reason = req.rejection_reason or "Committee decision"
        action = "LOAN_REJECTION"
    else:
        raise HTTPException(status_code=422, detail="Decision must be APPROVE or REJECT")

    _audit(db, action, "LOAN", loan.id, current_user.username, {
        "decision": req.decision,
        "reviewer": req.reviewer_name,
    })
    db.commit()

    return {
        "success": True,
        "data": {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "status": loan.status,
            "reviewed_by": loan.reviewed_by,
            "maturity_date": str(loan.maturity_date) if loan.maturity_date else None,
        },
        "timestamp": now.isoformat(),
    }


@router.post("/loans/{loan_id}/disburse")
@limiter.limit("5/minute")
async def disburse_loan(
    request: Request,
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark loan as disbursed. 3 credits.
    Only APPROVED loans can be disbursed.
    """
    deduct_credits(current_user, db, f"/api/v3/mfi/loans/{loan_id}/disburse", cost_multiplier=3.0)

    loan = db.query(MicroLoan).filter(MicroLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != "APPROVED":
        raise HTTPException(status_code=409, detail=f"Loan status is {loan.status}, not APPROVED")

    loan.status = "ACTIVE"
    loan.disbursement_date = date.today()

    _audit(db, "DISBURSEMENT", "LOAN", loan.id, current_user.username, {
        "amount_xof": loan.principal_xof,
        "method": loan.disbursement_method,
    })
    db.commit()

    return {
        "success": True,
        "data": {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "status": "ACTIVE",
            "disbursement_date": str(loan.disbursement_date),
            "principal_xof": loan.principal_xof,
            "disbursement_method": loan.disbursement_method or "CASH",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/loans/{loan_id}")
async def get_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get loan details with repayment schedule. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/mfi/loans/{loan_id}", cost_multiplier=1.0)

    loan = db.query(MicroLoan).filter(MicroLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    schedule = (
        db.query(RepaymentSchedule)
        .filter(RepaymentSchedule.loan_id == loan_id)
        .order_by(RepaymentSchedule.installment_number)
        .all()
    )

    return {
        "success": True,
        "data": {
            "id": loan.id,
            "loan_number": loan.loan_number,
            "client_id": loan.client_id,
            "product_type": loan.product_type,
            "purpose": loan.purpose,
            "principal_xof": loan.principal_xof,
            "interest_rate_annual_pct": loan.interest_rate_annual_pct,
            "interest_method": loan.interest_method,
            "term_months": loan.term_months,
            "grace_period_months": loan.grace_period_months,
            "status": loan.status,
            "outstanding_balance_xof": loan.outstanding_balance_xof,
            "total_paid_xof": loan.total_paid_xof,
            "days_overdue": loan.days_overdue,
            "disbursement_date": str(loan.disbursement_date) if loan.disbursement_date else None,
            "maturity_date": str(loan.maturity_date) if loan.maturity_date else None,
            "application_score": loan.application_score,
            "scoring_components": json.loads(loan.scoring_components or "{}"),
            "collateral_type": loan.collateral_type,
            "collateral_value_xof": loan.collateral_value_xof,
            "schedule": [
                {
                    "installment": s.installment_number,
                    "due_date": str(s.due_date),
                    "principal_due_xof": s.principal_due_xof,
                    "interest_due_xof": s.interest_due_xof,
                    "total_due_xof": s.total_due_xof,
                    "is_paid": s.is_paid,
                    "paid_date": str(s.paid_date) if s.paid_date else None,
                    "days_late": s.days_late,
                }
                for s in schedule
            ],
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/loans")
async def list_loans(
    status: Optional[str] = None,
    country_code: Optional[str] = None,
    product_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List loans with filters. 1 credit."""
    deduct_credits(current_user, db, "/api/v3/mfi/loans", cost_multiplier=1.0)

    query = db.query(MicroLoan)
    if status:
        query = query.filter(MicroLoan.status == status.upper())
    if product_type:
        query = query.filter(MicroLoan.product_type == product_type.upper())
    if country_code:
        query = query.join(MicrofinanceClient).filter(
            MicrofinanceClient.country_code == country_code.upper()
        )

    total = query.count()
    loans = query.order_by(MicroLoan.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "data": [
            {
                "id": l.id,
                "loan_number": l.loan_number,
                "client_id": l.client_id,
                "product_type": l.product_type,
                "principal_xof": l.principal_xof,
                "status": l.status,
                "outstanding_balance_xof": l.outstanding_balance_xof,
                "days_overdue": l.days_overdue,
                "application_score": l.application_score,
            }
            for l in loans
        ],
        "total": total,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REPAYMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/repayments")
@limiter.limit("20/minute")
async def record_repayment(
    request: Request,
    req: RepaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a loan repayment. 2 credits.
    Automatically allocates payment to next due installment(s).
    """
    deduct_credits(current_user, db, "/api/v3/mfi/repayments", cost_multiplier=2.0)

    loan = db.query(MicroLoan).filter(MicroLoan.id == req.loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status not in ("ACTIVE", "DISBURSED"):
        raise HTTPException(status_code=409, detail=f"Cannot accept payment for loan status: {loan.status}")

    # Find unpaid installments in order
    unpaid = (
        db.query(RepaymentSchedule)
        .filter(
            RepaymentSchedule.loan_id == loan.id,
            RepaymentSchedule.is_paid == False,
        )
        .order_by(RepaymentSchedule.installment_number)
        .all()
    )

    remaining_payment = req.amount_xof
    principal_allocated = 0
    interest_allocated = 0

    for inst in unpaid:
        if remaining_payment <= 0:
            break

        needed = inst.total_due_xof - inst.total_paid_xof
        payment = min(remaining_payment, needed)

        # Allocate: interest first, then principal
        int_needed = inst.interest_due_xof - inst.interest_paid_xof
        int_payment = min(payment, int_needed)
        inst.interest_paid_xof += int_payment
        interest_allocated += int_payment

        prin_payment = payment - int_payment
        inst.principal_paid_xof += prin_payment
        principal_allocated += prin_payment

        inst.total_paid_xof += payment
        remaining_payment -= payment

        if inst.total_paid_xof >= inst.total_due_xof:
            inst.is_paid = True
            inst.paid_date = date.today()
            # Calculate days late
            if date.today() > inst.due_date:
                inst.days_late = (date.today() - inst.due_date).days

    # Update loan totals
    loan.total_paid_xof = (loan.total_paid_xof or 0) + req.amount_xof
    loan.total_interest_paid_xof = (loan.total_interest_paid_xof or 0) + interest_allocated
    loan.outstanding_balance_xof = max(0, (loan.outstanding_balance_xof or 0) - principal_allocated)
    loan.last_payment_date = date.today()

    # Check if fully repaid
    if loan.outstanding_balance_xof <= 0:
        loan.status = "REPAID"
        loan.outstanding_balance_xof = 0

    # Record repayment transaction
    repayment = LoanRepayment(
        loan_id=loan.id,
        payment_date=date.today(),
        amount_xof=req.amount_xof,
        principal_portion_xof=principal_allocated,
        interest_portion_xof=interest_allocated,
        payment_method=req.payment_method,
        reference_number=req.reference_number,
        received_by=req.received_by,
    )
    db.add(repayment)

    _audit(db, "REPAYMENT", "LOAN", loan.id, current_user.username, {
        "amount_xof": req.amount_xof,
        "principal": principal_allocated,
        "interest": interest_allocated,
        "method": req.payment_method,
    })
    db.commit()
    db.refresh(repayment)

    return {
        "success": True,
        "data": {
            "repayment_id": repayment.id,
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "amount_xof": req.amount_xof,
            "principal_allocated_xof": principal_allocated,
            "interest_allocated_xof": interest_allocated,
            "outstanding_balance_xof": loan.outstanding_balance_xof,
            "loan_status": loan.status,
            "overpayment_xof": remaining_payment if remaining_payment > 0 else 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GROUP ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/groups")
async def create_group(
    req: GroupCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a solidarity group. 1 credit."""
    deduct_credits(current_user, db, "/api/v3/mfi/groups", cost_multiplier=1.0)

    group = SolidarityGroup(
        group_name=req.group_name,
        country_code=req.country_code.upper(),
        city=req.city,
        sector=req.sector,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    return {
        "success": True,
        "data": {"group_id": group.id, "group_name": group.group_name},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/groups/{group_id}/members/{client_id}")
async def add_member_to_group(
    group_id: int,
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a client to a solidarity group. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/mfi/groups/{group_id}/members", cost_multiplier=1.0)

    group = db.query(SolidarityGroup).filter(SolidarityGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.member_count >= group.max_members:
        raise HTTPException(status_code=409, detail=f"Group full ({group.max_members} members max)")

    client = db.query(MicrofinanceClient).filter(MicrofinanceClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if client.group_id:
        raise HTTPException(status_code=409, detail="Client already in a group")

    client.group_id = group.id
    group.member_count += 1
    db.commit()

    return {
        "success": True,
        "data": {
            "group_id": group.id,
            "client_id": client.id,
            "member_count": group.member_count,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/portfolio/{country_code}")
async def get_portfolio_health(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Portfolio health metrics for a country. 3 credits.
    Includes PAR30, PAR90, OSS, demographics, sector breakdown.
    """
    deduct_credits(current_user, db, f"/api/v3/mfi/portfolio/{country_code}", cost_multiplier=3.0)

    result = portfolio_analytics.compute_snapshot(db, country_code.upper())
    return {
        "success": True,
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/portfolio/{country_code}/impact")
async def get_impact_dashboard(
    country_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Impact metrics: loans disbursed, women financed, sectors reached. 2 credits.
    """
    deduct_credits(current_user, db, f"/api/v3/mfi/portfolio/{country_code}/impact", cost_multiplier=2.0)

    cc = country_code.upper()

    # Total loans disbursed
    disbursed_count = (
        db.query(func.count(MicroLoan.id))
        .join(MicrofinanceClient)
        .filter(
            MicrofinanceClient.country_code == cc,
            MicroLoan.status.in_(["ACTIVE", "DISBURSED", "REPAID"]),
        )
        .scalar()
    ) or 0

    total_volume = (
        db.query(func.coalesce(func.sum(MicroLoan.principal_xof), 0))
        .join(MicrofinanceClient)
        .filter(
            MicrofinanceClient.country_code == cc,
            MicroLoan.status.in_(["ACTIVE", "DISBURSED", "REPAID"]),
        )
        .scalar()
    ) or 0

    # Women borrowers
    total_borrowers = (
        db.query(func.count(func.distinct(MicroLoan.client_id)))
        .join(MicrofinanceClient)
        .filter(MicrofinanceClient.country_code == cc)
        .scalar()
    ) or 0

    women_borrowers = (
        db.query(func.count(func.distinct(MicroLoan.client_id)))
        .join(MicrofinanceClient)
        .filter(
            MicrofinanceClient.country_code == cc,
            MicrofinanceClient.gender == "F",
        )
        .scalar()
    ) or 0

    # Sector distribution
    sector_rows = (
        db.query(
            MicrofinanceClient.sector,
            func.count(MicroLoan.id),
            func.sum(MicroLoan.principal_xof),
        )
        .join(MicroLoan, MicroLoan.client_id == MicrofinanceClient.id)
        .filter(MicrofinanceClient.country_code == cc)
        .group_by(MicrofinanceClient.sector)
        .all()
    )

    sectors = {
        row[0] or "unknown": {"loans": row[1], "volume_xof": row[2] or 0}
        for row in sector_rows
    }

    return {
        "success": True,
        "data": {
            "country_code": cc,
            "total_loans_disbursed": disbursed_count,
            "total_volume_xof": total_volume,
            "total_borrowers": total_borrowers,
            "women_borrowers": women_borrowers,
            "women_pct": round(women_borrowers / total_borrowers * 100, 1) if total_borrowers else 0,
            "sectors": sectors,
            "data_label": "[LIVE]" if disbursed_count > 0 else "[DEMO]",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/tools/schedule-preview")
async def preview_repayment_schedule(
    req: SchedulePreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Preview repayment schedule without creating a loan. 1 credit.
    Useful for client-facing simulations.
    """
    deduct_credits(current_user, db, "/api/v3/mfi/tools/schedule-preview", cost_multiplier=1.0)

    schedule = repayment_gen.generate(
        principal_xof=req.principal_xof,
        annual_rate_pct=req.annual_rate_pct,
        term_months=req.term_months,
        grace_months=req.grace_months,
        method=req.method,
        frequency=req.frequency,
    )

    total_interest = sum(s["interest_due_xof"] for s in schedule)
    total_repayment = sum(s["total_due_xof"] for s in schedule)

    return {
        "success": True,
        "data": {
            "principal_xof": req.principal_xof,
            "total_interest_xof": total_interest,
            "total_repayment_xof": total_repayment,
            "effective_cost_pct": round(total_interest / req.principal_xof * 100, 2) if req.principal_xof else 0,
            "installments": len(schedule),
            "schedule": [
                {
                    "n": s["installment_number"],
                    "due": str(s["due_date"]),
                    "principal": s["principal_due_xof"],
                    "interest": s["interest_due_xof"],
                    "total": s["total_due_xof"],
                    "balance": s["remaining_balance_xof"],
                }
                for s in schedule
            ],
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/tools/products")
async def list_loan_products(
    current_user: User = Depends(get_current_user),
):
    """List available loan products with min/max amounts. No credit cost."""
    return {
        "success": True,
        "data": {
            product_type: {
                "min_xof": limits["min_xof"],
                "max_xof": limits["max_xof"],
                "max_term_months": limits["max_term_months"],
                "min_xof_formatted": f"{limits['min_xof']:,} XOF",
                "max_xof_formatted": f"{limits['max_xof']:,} XOF",
            }
            for product_type, limits in LOAN_PRODUCTS.items()
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
