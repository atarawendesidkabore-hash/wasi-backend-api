"""
AfriCredit/MFI Engine — Credit scoring, repayment schedule, and portfolio analytics.

Credit Scoring (7 components, 100 points total):
  1. Payment History      (25 pts) — past loan repayment behavior
  2. Debt Ratio           (15 pts) — outstanding debt vs income
  3. Sector Risk          (10 pts) — sector-specific default rates
  4. Governance           (10 pts) — KYC level, group membership, business formality
  5. Collateral           (15 pts) — collateral value vs loan amount
  6. Cash Flow Stability  (15 pts) — revenue consistency, years in business
  7. Country Risk         (10 pts) — WASI index + political risk

AUTO-VETO conditions:
  - Client has active defaulted loan
  - Client is on sanctions list (placeholder)
  - Outstanding debt > 3x monthly revenue
  - KYC level BASIC for loans > 500,000 XOF
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import Country, CountryIndex
from src.database.microloan_models import (
    MicrofinanceClient, MicroLoan, RepaymentSchedule, LoanRepayment,
    MFIPortfolioSnapshot, MFIAuditLog, SolidarityGroup,
    LOAN_PRODUCTS,
)
from src.utils.wacc_params import POLITICAL_RISK

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sector default risk multipliers (1.0 = average, >1.0 = riskier)
# ---------------------------------------------------------------------------
SECTOR_RISK = {
    "market_trade": 0.85,
    "agriculture": 1.30,  # weather + seasonal risk
    "livestock": 1.25,
    "artisan": 0.95,
    "transport": 1.10,
    "food_processing": 0.90,
    "tailoring": 0.80,
    "construction": 1.20,
    "retail": 0.85,
    "services": 0.90,
}


# ---------------------------------------------------------------------------
# Credit Scoring Engine
# ---------------------------------------------------------------------------
class MicroCreditScorer:
    """
    7-component credit scoring adapted for microfinance borrowers.
    Returns a score 0-100 with component breakdown.
    """

    def score(self, client: MicrofinanceClient, loan: MicroLoan,
              db: Session) -> dict:
        """Score a loan application. Returns dict with score, components, vetoes."""
        components = {}
        vetoes = []

        # ── AUTO-VETO checks ─────────────────────────────────────────────
        # 1. Active defaulted loan
        active_default = (
            db.query(MicroLoan)
            .filter(
                MicroLoan.client_id == client.id,
                MicroLoan.status == "DEFAULTED",
            )
            .first()
        )
        if active_default:
            vetoes.append("Client has an active defaulted loan")

        # 2. Outstanding debt > 3x monthly revenue
        total_outstanding = (
            db.query(func.coalesce(func.sum(MicroLoan.outstanding_balance_xof), 0))
            .filter(
                MicroLoan.client_id == client.id,
                MicroLoan.status.in_(["ACTIVE", "DISBURSED"]),
            )
            .scalar()
        ) or 0
        if client.monthly_revenue_xof and client.monthly_revenue_xof > 0:
            debt_income = total_outstanding / client.monthly_revenue_xof
            if debt_income > 3.0:
                vetoes.append(
                    f"Debt-to-income ratio {debt_income:.1f}x exceeds 3x limit"
                )

        # 3. KYC insufficient for loan size
        if client.kyc_level == "BASIC" and loan.principal_xof > 500_000:
            vetoes.append(
                "KYC level BASIC insufficient for loans > 500,000 XOF"
            )

        # ── Component scoring ────────────────────────────────────────────

        # 1. Payment History (25 pts)
        past_loans = (
            db.query(MicroLoan)
            .filter(
                MicroLoan.client_id == client.id,
                MicroLoan.status.in_(["REPAID", "ACTIVE", "DEFAULTED"]),
            )
            .all()
        )
        if past_loans:
            repaid = sum(1 for l in past_loans if l.status == "REPAID")
            defaulted = sum(1 for l in past_loans if l.status == "DEFAULTED")
            total = len(past_loans)
            repay_ratio = repaid / total if total > 0 else 0
            history_pts = repay_ratio * 25.0
            if defaulted > 0:
                history_pts *= 0.5  # halve if any defaults
        else:
            history_pts = 12.5  # first-time borrower: neutral score

        components["payment_history"] = round(history_pts, 2)

        # 2. Debt Ratio (15 pts)
        if client.monthly_revenue_xof and client.monthly_revenue_xof > 0:
            # Include this new loan in ratio
            projected_debt = total_outstanding + loan.principal_xof
            ratio = projected_debt / (client.monthly_revenue_xof * 12)
            debt_pts = max(0.0, 15.0 * (1.0 - ratio))
        else:
            debt_pts = 7.5  # no revenue data: neutral
        components["debt_ratio"] = round(min(15.0, debt_pts), 2)

        # 3. Sector Risk (10 pts)
        sector_mult = SECTOR_RISK.get(client.sector or "", 1.0)
        sector_pts = 10.0 / sector_mult  # lower risk = higher score
        components["sector_risk"] = round(min(10.0, sector_pts), 2)

        # 4. Governance (10 pts)
        gov_pts = 0.0
        kyc_scores = {"BASIC": 2.0, "STANDARD": 5.0, "FULL": 8.0}
        gov_pts += kyc_scores.get(client.kyc_level or "BASIC", 2.0)
        if client.group_id:
            gov_pts += 2.0  # group membership bonus
        components["governance"] = round(min(10.0, gov_pts), 2)

        # 5. Collateral (15 pts)
        if loan.collateral_type and loan.collateral_type != "NONE":
            if loan.collateral_value_xof and loan.principal_xof > 0:
                coverage = loan.collateral_value_xof / loan.principal_xof
                collateral_pts = min(15.0, coverage * 15.0)
            else:
                collateral_pts = 5.0  # has collateral but no value assessed
            if loan.collateral_type == "GROUP_SOLIDARITY":
                collateral_pts = max(collateral_pts, 8.0)  # solidarity guarantee floor
        else:
            collateral_pts = 0.0
        components["collateral"] = round(collateral_pts, 2)

        # 6. Cash Flow Stability (15 pts)
        cf_pts = 0.0
        if client.years_in_business and client.years_in_business >= 3:
            cf_pts += 8.0
        elif client.years_in_business and client.years_in_business >= 1:
            cf_pts += 5.0
        else:
            cf_pts += 2.0

        if client.monthly_revenue_xof and client.monthly_revenue_xof > 0:
            # Revenue relative to loan: higher revenue = more capacity
            rev_ratio = (client.monthly_revenue_xof * loan.term_months) / loan.principal_xof
            cf_pts += min(7.0, rev_ratio * 3.5)
        components["cash_flow_stability"] = round(min(15.0, cf_pts), 2)

        # 7. Country Risk (10 pts)
        country = (
            db.query(Country)
            .filter(Country.code == client.country_code)
            .first()
        )
        if country:
            pol_risk = POLITICAL_RISK.get(country.code, 5.0)
            country_pts = 10.0 * (1.0 - pol_risk / 10.0)
        else:
            country_pts = 5.0  # neutral
        components["country_risk"] = round(country_pts, 2)

        # ── Total score ──────────────────────────────────────────────────
        total = sum(components.values())
        total = max(0.0, min(100.0, total))

        # If vetoed, score is capped at 0
        if vetoes:
            total = 0.0

        return {
            "score": round(total, 2),
            "components": components,
            "vetoes": vetoes,
            "is_vetoed": len(vetoes) > 0,
            "recommendation": self._recommendation(total, vetoes),
        }

    @staticmethod
    def _recommendation(score: float, vetoes: list) -> str:
        if vetoes:
            return "REJECT — " + "; ".join(vetoes)
        if score >= 70:
            return "APPROVE — strong credit profile"
        if score >= 50:
            return "REVIEW — moderate risk, committee decision required"
        if score >= 30:
            return "CAUTION — high risk, requires additional guarantees"
        return "REJECT — insufficient credit quality"


# ---------------------------------------------------------------------------
# Repayment Schedule Generator
# ---------------------------------------------------------------------------
class RepaymentGenerator:
    """
    Generates amortization schedules for micro-loans.
    Supports FLAT and DECLINING interest methods.
    """

    @staticmethod
    def generate(
        principal_xof: int,
        annual_rate_pct: float,
        term_months: int,
        grace_months: int = 0,
        method: str = "DECLINING",
        start_date: date | None = None,
        frequency: str = "MONTHLY",
    ) -> list[dict]:
        """
        Generate repayment schedule.

        Returns list of dicts with:
          installment_number, due_date, principal_due_xof, interest_due_xof,
          total_due_xof, remaining_balance_xof
        """
        if start_date is None:
            start_date = date.today()

        monthly_rate = annual_rate_pct / 100.0 / 12.0
        schedule = []
        remaining = principal_xof

        # Determine period delta
        if frequency == "WEEKLY":
            period_delta = timedelta(weeks=1)
            periods = term_months * 4  # approximate
            period_rate = annual_rate_pct / 100.0 / 52.0
        elif frequency == "BIWEEKLY":
            period_delta = timedelta(weeks=2)
            periods = term_months * 2
            period_rate = annual_rate_pct / 100.0 / 26.0
        else:  # MONTHLY
            period_delta = timedelta(days=30)
            periods = term_months
            period_rate = monthly_rate

        active_periods = periods - grace_months if frequency == "MONTHLY" else periods

        for i in range(1, periods + 1):
            due_date = start_date + period_delta * i

            if frequency == "MONTHLY" and i <= grace_months:
                # Grace period: interest only, no principal
                interest = int(remaining * period_rate)
                principal_payment = 0
            elif method == "FLAT":
                # Flat: equal total payments, interest on original principal
                principal_payment = int(principal_xof / active_periods)
                interest = int(principal_xof * period_rate)
            else:
                # Declining balance: interest on remaining, equal principal
                principal_payment = int(principal_xof / active_periods)
                interest = int(remaining * period_rate)

            # Last installment: adjust for rounding
            if i == periods:
                principal_payment = remaining

            total = principal_payment + interest
            remaining -= principal_payment

            schedule.append({
                "installment_number": i,
                "due_date": due_date,
                "principal_due_xof": principal_payment,
                "interest_due_xof": interest,
                "fees_due_xof": 0,
                "total_due_xof": total,
                "remaining_balance_xof": max(0, remaining),
            })

        return schedule


# ---------------------------------------------------------------------------
# Portfolio Analytics
# ---------------------------------------------------------------------------
class PortfolioAnalytics:
    """Compute PAR30, PAR90, OSS, and other MFI portfolio metrics."""

    @staticmethod
    def compute_snapshot(db: Session, country_code: str, snapshot_date: date | None = None) -> dict:
        """Compute portfolio health metrics for a country."""
        if snapshot_date is None:
            snapshot_date = date.today()

        # Active loans
        active_loans = (
            db.query(MicroLoan)
            .join(MicrofinanceClient)
            .filter(
                MicrofinanceClient.country_code == country_code,
                MicroLoan.status.in_(["ACTIVE", "DISBURSED"]),
            )
            .all()
        )

        total_outstanding = sum(l.outstanding_balance_xof or 0 for l in active_loans)
        total_clients = (
            db.query(func.count(MicrofinanceClient.id))
            .filter(
                MicrofinanceClient.country_code == country_code,
                MicrofinanceClient.is_active == True,
            )
            .scalar()
        ) or 0

        # PAR30: outstanding balance of loans >30 days overdue / total outstanding
        par30_balance = sum(
            l.outstanding_balance_xof or 0
            for l in active_loans
            if (l.days_overdue or 0) > 30
        )
        par30_pct = (par30_balance / total_outstanding * 100.0) if total_outstanding > 0 else 0.0

        # PAR90
        par90_balance = sum(
            l.outstanding_balance_xof or 0
            for l in active_loans
            if (l.days_overdue or 0) > 90
        )
        par90_pct = (par90_balance / total_outstanding * 100.0) if total_outstanding > 0 else 0.0

        # Average loan size
        avg_loan = (total_outstanding // len(active_loans)) if active_loans else 0

        # Demographics
        all_clients_for_loans = set()
        for l in active_loans:
            all_clients_for_loans.add(l.client_id)

        clients = (
            db.query(MicrofinanceClient)
            .filter(MicrofinanceClient.id.in_(all_clients_for_loans))
            .all()
        ) if all_clients_for_loans else []

        women = sum(1 for c in clients if c.gender == "F")
        women_pct = (women / len(clients) * 100.0) if clients else 0.0

        # Total disbursed (all time)
        total_disbursed = (
            db.query(func.coalesce(func.sum(MicroLoan.principal_xof), 0))
            .join(MicrofinanceClient)
            .filter(
                MicrofinanceClient.country_code == country_code,
                MicroLoan.status.in_(["ACTIVE", "DISBURSED", "REPAID", "DEFAULTED", "WRITTEN_OFF"]),
            )
            .scalar()
        ) or 0

        # Write-off ratio
        written_off = (
            db.query(func.coalesce(func.sum(MicroLoan.principal_xof), 0))
            .join(MicrofinanceClient)
            .filter(
                MicrofinanceClient.country_code == country_code,
                MicroLoan.status == "WRITTEN_OFF",
            )
            .scalar()
        ) or 0
        write_off_pct = (written_off / total_disbursed * 100.0) if total_disbursed > 0 else 0.0

        return {
            "snapshot_date": str(snapshot_date),
            "country_code": country_code,
            "total_clients": total_clients,
            "active_loans": len(active_loans),
            "total_outstanding_xof": total_outstanding,
            "total_disbursed_xof": total_disbursed,
            "par30_pct": round(par30_pct, 2),
            "par90_pct": round(par90_pct, 2),
            "write_off_ratio_pct": round(write_off_pct, 2),
            "avg_loan_size_xof": avg_loan,
            "women_pct": round(women_pct, 1),
            "par30_status": "GREEN" if par30_pct < 5.0 else "AMBER" if par30_pct < 10.0 else "RED",
        }


# Singleton instances
micro_scorer = MicroCreditScorer()
repayment_gen = RepaymentGenerator()
portfolio_analytics = PortfolioAnalytics()
