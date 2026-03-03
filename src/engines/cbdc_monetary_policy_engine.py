"""
eCFA CBDC Monetary Policy Engine — BCEAO Central Bank Operations.

This engine gives BCEAO the levers to steer the eCFA economy:

  1. Policy rate management (taux directeur, prêt marginal, dépôt)
  2. Reserve requirement enforcement on commercial banks
  3. Standing facility operations (lending/deposit windows)
  4. Interest accrual and demurrage application
  5. M0/M1/M2 money supply computation
  6. Monetary policy decision recording

BCEAO Monetary Policy Framework (real-world reference):
  - Taux directeur (main policy rate): currently 3.50% (Dec 2024)
  - Taux de prêt marginal: taux directeur + 200bp = 5.50%
  - Taux de dépôt: taux directeur - 200bp = 1.50%  (corridor ±200bp)
  - Reserve ratio: 3% of deposits (was 5% before 2012)
  - Maintenance period: 28 days (monthly)
  - Remuneration on reserves: 0% (BCEAO does not remunerate reserves)

All operations produce audit trail entries and ledger transactions.
"""
import uuid
import json
import logging
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from src.database.cbdc_models import (
    CbdcWallet, CbdcLedgerEntry, CbdcTransaction, CbdcPolicy,
    CbdcPolicyRate, CbdcReserveRequirement, CbdcStandingFacility,
    CbdcMonetaryPolicyDecision, CbdcEligibleCollateral,
    CbdcMonetaryAggregate, KYC_TIER_LIMITS,
)
from src.utils.cbdc_audit import log_audit_event

logger = logging.getLogger(__name__)

# BCEAO corridor width (basis points from taux directeur)
CORRIDOR_SPREAD_BP = 200  # ±200bp

# Default BCEAO rates (as of Dec 2024)
DEFAULT_TAUX_DIRECTEUR = 3.50
DEFAULT_RESERVE_RATIO = 3.0

# Demurrage threshold — only apply to holdings above this
DEMURRAGE_THRESHOLD_XOF = 5_000_000.0

# Maintenance period for reserves (days)
RESERVE_MAINTENANCE_PERIOD_DAYS = 28


class CbdcMonetaryPolicyEngine:
    """Central bank monetary policy operations for eCFA."""

    def __init__(self, db: Session):
        self.db = db

    # ==================================================================
    # 1. POLICY RATE MANAGEMENT
    # ==================================================================

    def get_current_rates(self) -> dict:
        """Get all current BCEAO policy rates."""
        rates = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.is_current == True
        ).all()

        result = {}
        for r in rates:
            result[r.rate_type] = {
                "rate_id": r.rate_id,
                "rate_percent": r.rate_percent,
                "effective_date": r.effective_date.isoformat(),
                "decided_by": r.decided_by,
            }

        # Fill defaults if no rates set yet
        if "TAUX_DIRECTEUR" not in result:
            result["TAUX_DIRECTEUR"] = {
                "rate_percent": DEFAULT_TAUX_DIRECTEUR,
                "effective_date": date.today().isoformat(),
                "decided_by": "SYSTEM_DEFAULT",
            }
        if "TAUX_PRET_MARGINAL" not in result:
            td = result["TAUX_DIRECTEUR"]["rate_percent"]
            result["TAUX_PRET_MARGINAL"] = {
                "rate_percent": td + CORRIDOR_SPREAD_BP / 100,
                "effective_date": date.today().isoformat(),
                "decided_by": "DERIVED",
            }
        if "TAUX_DEPOT" not in result:
            td = result["TAUX_DIRECTEUR"]["rate_percent"]
            result["TAUX_DEPOT"] = {
                "rate_percent": max(0.0, td - CORRIDOR_SPREAD_BP / 100),
                "effective_date": date.today().isoformat(),
                "decided_by": "DERIVED",
            }

        return result

    def get_taux_directeur(self) -> float:
        """Get current main policy rate."""
        rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_DIRECTEUR",
            CbdcPolicyRate.is_current == True,
        ).first()
        return rate.rate_percent if rate else DEFAULT_TAUX_DIRECTEUR

    def set_policy_rate(self, rate_type: str, new_rate_percent: float,
                        decision_id: str | None = None,
                        decided_by: str = "Comité de Politique Monétaire",
                        rationale: str | None = None,
                        effective_date: date | None = None) -> dict:
        """Set a new policy rate (supersedes the current one).

        When taux_directeur changes, the corridor rates auto-adjust:
          - taux_pret_marginal = taux_directeur + 2.00%
          - taux_depot = taux_directeur - 2.00%
        """
        valid_types = {"TAUX_DIRECTEUR", "TAUX_PRET_MARGINAL",
                       "TAUX_DEPOT", "TAUX_RESERVE"}
        if rate_type not in valid_types:
            raise ValueError(f"Invalid rate_type. Must be one of: {valid_types}")

        # Bounds validation — BCEAO rates must be within realistic range
        RATE_BOUNDS = {
            "TAUX_DIRECTEUR": (-1.0, 25.0),
            "TAUX_PRET_MARGINAL": (-1.0, 30.0),
            "TAUX_DEPOT": (-2.0, 20.0),
            "TAUX_RESERVE": (0.0, 50.0),
        }
        low, high = RATE_BOUNDS[rate_type]
        if not (low <= new_rate_percent <= high):
            raise ValueError(
                f"{rate_type} must be between {low}% and {high}% (got {new_rate_percent}%)"
            )

        eff_date = effective_date or date.today()

        # Supersede old rate
        old_rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == rate_type,
            CbdcPolicyRate.is_current == True,
        ).first()

        old_rate_pct = None
        if old_rate:
            old_rate.is_current = False
            old_rate.superseded_date = eff_date
            old_rate_pct = old_rate.rate_percent

        # Check for same-day update (reuse row to avoid unique constraint violation)
        existing_today = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == rate_type,
            CbdcPolicyRate.effective_date == eff_date,
            CbdcPolicyRate.is_current == False,
        ).first()
        if existing_today:
            existing_today.rate_percent = new_rate_percent
            existing_today.previous_rate_percent = old_rate_pct
            existing_today.decision_id = decision_id
            existing_today.decided_by = decided_by
            existing_today.rationale = rationale
            existing_today.is_current = True
            existing_today.superseded_date = None
            new_rate = existing_today
        else:
            new_rate = CbdcPolicyRate(
                rate_id=str(uuid.uuid4()),
                rate_type=rate_type,
                rate_percent=new_rate_percent,
                previous_rate_percent=old_rate_pct,
                decision_id=decision_id,
                decided_by=decided_by,
                rationale=rationale,
                effective_date=eff_date,
                announced_date=date.today(),
                is_current=True,
            )
            self.db.add(new_rate)

        # Auto-adjust corridor if taux directeur changed
        rates_set = [{"rate_type": rate_type, "new": new_rate_percent,
                      "old": old_rate_pct}]
        if rate_type == "TAUX_DIRECTEUR":
            corridor_rates = self._adjust_corridor(
                new_rate_percent, decision_id, decided_by, eff_date
            )
            rates_set.extend(corridor_rates)

        log_audit_event(
            self.db, "POLICY_RATE_CHANGED",
            actor_channel="ADMIN",
            target_entity_type="policy_rate",
            target_entity_id=new_rate.rate_id,
            details={
                "rate_type": rate_type,
                "new_rate": new_rate_percent,
                "old_rate": old_rate_pct,
                "effective_date": eff_date.isoformat(),
            },
        )

        self.db.commit()

        return {
            "rates_updated": rates_set,
            "effective_date": eff_date.isoformat(),
            "decided_by": decided_by,
        }

    def _adjust_corridor(self, taux_directeur: float,
                         decision_id: str | None, decided_by: str,
                         eff_date: date) -> list[dict]:
        """Auto-adjust lending and deposit facility rates around taux directeur."""
        spread = CORRIDOR_SPREAD_BP / 100  # 2.00%
        corridor_updates = []

        for rtype, rate_val in [
            ("TAUX_PRET_MARGINAL", taux_directeur + spread),
            ("TAUX_DEPOT", max(0.0, taux_directeur - spread)),
        ]:
            old = self.db.query(CbdcPolicyRate).filter(
                CbdcPolicyRate.rate_type == rtype,
                CbdcPolicyRate.is_current == True,
            ).first()
            old_pct = old.rate_percent if old else None
            if old:
                old.is_current = False
                old.superseded_date = eff_date

            # Check if a rate already exists for this type+date (same-day update)
            existing_today = self.db.query(CbdcPolicyRate).filter(
                CbdcPolicyRate.rate_type == rtype,
                CbdcPolicyRate.effective_date == eff_date,
                CbdcPolicyRate.is_current == False,
            ).first()
            if existing_today:
                # Reuse the existing record
                existing_today.rate_percent = rate_val
                existing_today.previous_rate_percent = old_pct
                existing_today.decision_id = decision_id
                existing_today.decided_by = f"DERIVED from {decided_by}"
                existing_today.is_current = True
                existing_today.superseded_date = None
            else:
                new = CbdcPolicyRate(
                    rate_id=str(uuid.uuid4()),
                    rate_type=rtype,
                    rate_percent=rate_val,
                    previous_rate_percent=old_pct,
                    decision_id=decision_id,
                    decided_by=f"DERIVED from {decided_by}",
                    effective_date=eff_date,
                    announced_date=date.today(),
                    is_current=True,
                )
                self.db.add(new)

            corridor_updates.append({
                "rate_type": rtype, "new": rate_val, "old": old_pct,
            })

        return corridor_updates

    def get_rate_history(self, rate_type: str, limit: int = 20) -> list[dict]:
        """Get historical rate changes for a given rate type."""
        rates = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == rate_type
        ).order_by(CbdcPolicyRate.effective_date.desc()).limit(limit).all()

        return [{
            "rate_id": r.rate_id,
            "rate_percent": r.rate_percent,
            "previous_rate_percent": r.previous_rate_percent,
            "effective_date": r.effective_date.isoformat(),
            "is_current": r.is_current,
            "decided_by": r.decided_by,
        } for r in rates]

    # ==================================================================
    # 2. RESERVE REQUIREMENT MANAGEMENT
    # ==================================================================

    def set_reserve_ratio(self, new_ratio_percent: float,
                          decided_by: str = "Comité de Politique Monétaire") -> dict:
        """Set the reserve ratio for all commercial banks.

        This updates the TAUX_RESERVE policy rate and triggers
        recomputation of all bank reserve requirements.
        """
        result = self.set_policy_rate(
            "TAUX_RESERVE", new_ratio_percent,
            decided_by=decided_by,
            rationale=f"Reserve ratio set to {new_ratio_percent}%",
        )
        return result

    def get_current_reserve_ratio(self) -> float:
        """Get the current reserve requirement ratio."""
        rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_RESERVE",
            CbdcPolicyRate.is_current == True,
        ).first()
        return rate.rate_percent if rate else DEFAULT_RESERVE_RATIO

    def compute_reserve_requirements(self) -> dict:
        """Compute reserve requirements for all commercial banks.

        For each COMMERCIAL_BANK wallet:
          1. Sum all client wallet balances linked to this bank (deposit_base)
          2. required_reserves = deposit_base × reserve_ratio
          3. Compare with bank's actual eCFA balance at CENTRAL_BANK
          4. Flag deficiency or surplus
        """
        ratio = self.get_current_reserve_ratio()
        today = date.today()
        period_start = today - timedelta(days=RESERVE_MAINTENANCE_PERIOD_DAYS)

        # Get all commercial bank wallets
        bank_wallets = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_type == "COMMERCIAL_BANK",
            CbdcWallet.status == "active",
        ).all()

        results = []
        for bank in bank_wallets:
            # Deposit base = sum of all RETAIL + MERCHANT + AGENT wallets
            # linked to this bank (by institution_code)
            deposit_base = self.db.query(
                func.coalesce(func.sum(CbdcWallet.balance_ecfa), 0.0)
            ).filter(
                CbdcWallet.institution_code == bank.institution_code,
                CbdcWallet.wallet_type.in_(["RETAIL", "MERCHANT", "AGENT"]),
                CbdcWallet.status == "active",
            ).scalar() or 0.0

            required = deposit_base * (ratio / 100.0)
            holding = bank.balance_ecfa  # bank's own balance = its reserves
            surplus = max(0.0, holding - required)
            deficiency = max(0.0, required - holding)
            is_compliant = holding >= required

            # Penalty on deficiency (annualized, computed daily)
            td = self.get_taux_directeur()
            penalty_rate = td + 1.0  # penalty = policy rate + 100bp
            daily_penalty = (deficiency * (penalty_rate / 100.0)) / 365.0

            # Remuneration on required reserves
            rem_rate_obj = self.db.query(CbdcPolicyRate).filter(
                CbdcPolicyRate.rate_type == "TAUX_RESERVE",
                CbdcPolicyRate.is_current == True,
            ).first()
            rem_rate = 0.0  # BCEAO traditionally doesn't remunerate
            if rem_rate_obj and rem_rate_obj.rate_percent != ratio:
                # Check if there's a separate remuneration rate
                pass  # rem_rate stays 0 by default

            # Upsert requirement record
            existing = self.db.query(CbdcReserveRequirement).filter(
                CbdcReserveRequirement.bank_wallet_id == bank.wallet_id,
                CbdcReserveRequirement.computation_date == today,
            ).first()

            if existing:
                existing.required_ratio_percent = ratio
                existing.deposit_base_ecfa = deposit_base
                existing.required_amount_ecfa = required
                existing.current_holding_ecfa = holding
                existing.surplus_ecfa = surplus
                existing.deficiency_ecfa = deficiency
                existing.is_compliant = is_compliant
                existing.penalty_rate_percent = penalty_rate
                existing.accrued_penalty_ecfa = daily_penalty
                existing.remuneration_rate_percent = rem_rate
                req = existing
            else:
                req = CbdcReserveRequirement(
                    requirement_id=str(uuid.uuid4()),
                    bank_wallet_id=bank.wallet_id,
                    institution_code=bank.institution_code or "UNKNOWN",
                    country_code=bank.country.code if bank.country else "XX",
                    required_ratio_percent=ratio,
                    deposit_base_ecfa=deposit_base,
                    required_amount_ecfa=required,
                    current_holding_ecfa=holding,
                    surplus_ecfa=surplus,
                    deficiency_ecfa=deficiency,
                    is_compliant=is_compliant,
                    penalty_rate_percent=penalty_rate,
                    accrued_penalty_ecfa=daily_penalty,
                    remuneration_rate_percent=rem_rate,
                    accrued_remuneration_ecfa=0.0,
                    computation_date=today,
                    maintenance_period_start=period_start,
                    maintenance_period_end=today,
                )
                self.db.add(req)

            results.append({
                "institution_code": bank.institution_code,
                "wallet_id": bank.wallet_id,
                "deposit_base_ecfa": deposit_base,
                "required_ecfa": round(required, 2),
                "holding_ecfa": holding,
                "surplus_ecfa": round(surplus, 2),
                "deficiency_ecfa": round(deficiency, 2),
                "is_compliant": is_compliant,
                "daily_penalty_ecfa": round(daily_penalty, 2),
            })

        self.db.commit()

        total_required = sum(r["required_ecfa"] for r in results)
        total_held = sum(r["holding_ecfa"] for r in results)
        non_compliant = sum(1 for r in results if not r["is_compliant"])

        return {
            "reserve_ratio_percent": ratio,
            "banks_assessed": len(results),
            "banks_non_compliant": non_compliant,
            "total_required_ecfa": round(total_required, 2),
            "total_held_ecfa": round(total_held, 2),
            "system_surplus_ecfa": round(total_held - total_required, 2),
            "computation_date": today.isoformat(),
            "bank_details": results,
        }

    # ==================================================================
    # 3. STANDING FACILITY OPERATIONS
    # ==================================================================

    def open_lending_facility(self, bank_wallet_id: str, amount_ecfa: float,
                              maturity: str = "OVERNIGHT",
                              collateral_id: str | None = None) -> dict:
        """Bank borrows from BCEAO at taux de prêt marginal.

        The central bank credits the bank's wallet (creates eCFA liquidity).
        Bank must repay principal + interest at maturity.
        """
        bank = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == bank_wallet_id,
            CbdcWallet.wallet_type == "COMMERCIAL_BANK",
        ).first()
        if not bank:
            raise ValueError("Wallet not found or not a commercial bank")

        # Get lending rate
        rates = self.get_current_rates()
        lending_rate = rates["TAUX_PRET_MARGINAL"]["rate_percent"]

        # Check collateral if required
        collateral_value = 0.0
        haircut = 0.0
        if collateral_id:
            coll = self.db.query(CbdcEligibleCollateral).filter(
                CbdcEligibleCollateral.collateral_id == collateral_id,
                CbdcEligibleCollateral.is_eligible == True,
                CbdcEligibleCollateral.is_pledged == False,
            ).first()
            if not coll:
                raise ValueError("Collateral not found, not eligible, or already pledged")
            if coll.collateral_value_ecfa < amount_ecfa:
                raise ValueError(
                    f"Collateral value ({coll.collateral_value_ecfa:.0f}) "
                    f"insufficient for loan ({amount_ecfa:.0f})"
                )
            collateral_value = coll.collateral_value_ecfa
            haircut = coll.haircut_percent
            coll.is_pledged = True
            coll.pledged_to_facility_id = None  # will update below

        # Calculate maturity and interest
        now = datetime.utcnow()
        maturity_days = {"OVERNIGHT": 1, "7_DAY": 7, "28_DAY": 28}.get(maturity, 1)
        matures_at = now + timedelta(days=maturity_days)
        interest = amount_ecfa * (lending_rate / 100.0) * (maturity_days / 365.0)

        # Create facility record
        facility = CbdcStandingFacility(
            facility_id=str(uuid.uuid4()),
            facility_type="LENDING",
            bank_wallet_id=bank_wallet_id,
            institution_code=bank.institution_code or "UNKNOWN",
            amount_ecfa=amount_ecfa,
            rate_percent=lending_rate,
            interest_ecfa=round(interest, 2),
            collateral_asset_id=collateral_id,
            collateral_value_ecfa=collateral_value if collateral_id else None,
            haircut_percent=haircut if collateral_id else None,
            maturity=maturity,
            opened_at=now,
            matures_at=matures_at,
            status="active",
        )
        self.db.add(facility)

        if collateral_id:
            coll.pledged_to_facility_id = facility.facility_id

        # Credit the bank's wallet (inject liquidity)
        cb_wallet = self._get_country_cb_wallet(bank)
        if cb_wallet:
            self._facility_ledger_entry(
                cb_wallet.wallet_id, bank_wallet_id, amount_ecfa,
                "FACILITY_LENDING", facility.facility_id
            )

        log_audit_event(
            self.db, "FACILITY_OPENED",
            actor_wallet_id=bank_wallet_id,
            target_entity_type="standing_facility",
            target_entity_id=facility.facility_id,
            actor_channel="ADMIN",
            details={
                "facility_type": "LENDING",
                "amount_ecfa": amount_ecfa,
                "rate_percent": lending_rate,
                "interest_ecfa": round(interest, 2),
                "maturity": maturity,
                "collateral_id": collateral_id,
            },
        )

        self.db.commit()

        return {
            "facility_id": facility.facility_id,
            "facility_type": "LENDING",
            "amount_ecfa": amount_ecfa,
            "rate_percent": lending_rate,
            "interest_ecfa": round(interest, 2),
            "maturity": maturity,
            "matures_at": matures_at.isoformat(),
            "bank_new_balance": bank.balance_ecfa,
        }

    def open_deposit_facility(self, bank_wallet_id: str,
                              amount_ecfa: float) -> dict:
        """Bank deposits excess liquidity at BCEAO at taux de dépôt.

        The bank's wallet is debited, central bank is credited.
        Bank earns interest at the deposit facility rate.
        """
        bank = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == bank_wallet_id,
            CbdcWallet.wallet_type == "COMMERCIAL_BANK",
        ).first()
        if not bank:
            raise ValueError("Wallet not found or not a commercial bank")
        if bank.available_balance_ecfa < amount_ecfa:
            raise ValueError("Insufficient balance for deposit")

        rates = self.get_current_rates()
        deposit_rate = rates["TAUX_DEPOT"]["rate_percent"]

        now = datetime.utcnow()
        matures_at = now + timedelta(days=1)  # overnight by default
        interest = amount_ecfa * (deposit_rate / 100.0) / 365.0

        facility = CbdcStandingFacility(
            facility_id=str(uuid.uuid4()),
            facility_type="DEPOSIT",
            bank_wallet_id=bank_wallet_id,
            institution_code=bank.institution_code or "UNKNOWN",
            amount_ecfa=amount_ecfa,
            rate_percent=deposit_rate,
            interest_ecfa=round(interest, 2),
            maturity="OVERNIGHT",
            opened_at=now,
            matures_at=matures_at,
            status="active",
        )
        self.db.add(facility)

        # Debit bank, credit CB (park liquidity)
        cb_wallet = self._get_country_cb_wallet(bank)
        if cb_wallet:
            self._facility_ledger_entry(
                bank_wallet_id, cb_wallet.wallet_id, amount_ecfa,
                "FACILITY_DEPOSIT", facility.facility_id
            )

        log_audit_event(
            self.db, "FACILITY_OPENED",
            actor_wallet_id=bank_wallet_id,
            target_entity_type="standing_facility",
            target_entity_id=facility.facility_id,
            actor_channel="ADMIN",
            details={
                "facility_type": "DEPOSIT",
                "amount_ecfa": amount_ecfa,
                "rate_percent": deposit_rate,
                "interest_ecfa": round(interest, 2),
            },
        )

        self.db.commit()

        return {
            "facility_id": facility.facility_id,
            "facility_type": "DEPOSIT",
            "amount_ecfa": amount_ecfa,
            "rate_percent": deposit_rate,
            "interest_ecfa": round(interest, 2),
            "matures_at": matures_at.isoformat(),
            "bank_new_balance": bank.balance_ecfa,
        }

    def mature_facilities(self) -> dict:
        """Process all matured standing facilities.

        For LENDING: debit bank principal + interest, credit CB.
        For DEPOSIT: credit bank principal + interest, debit CB.
        Release pledged collateral.
        """
        now = datetime.utcnow()
        matured = self.db.query(CbdcStandingFacility).filter(
            CbdcStandingFacility.status == "active",
            CbdcStandingFacility.matures_at <= now,
        ).all()

        processed = 0
        total_interest = 0.0

        for f in matured:
            cb_wallet = self._get_cb_wallet_for_bank(f.bank_wallet_id)
            if not cb_wallet:
                continue

            repay_amount = f.amount_ecfa + f.interest_ecfa
            total_interest += f.interest_ecfa

            if f.facility_type == "LENDING":
                # Bank repays: debit bank, credit CB
                self._facility_ledger_entry(
                    f.bank_wallet_id, cb_wallet.wallet_id, repay_amount,
                    "FACILITY_REPAYMENT", f.facility_id
                )
            elif f.facility_type == "DEPOSIT":
                # CB returns deposit + interest: debit CB, credit bank
                self._facility_ledger_entry(
                    cb_wallet.wallet_id, f.bank_wallet_id, repay_amount,
                    "FACILITY_RETURN", f.facility_id
                )

            # Release collateral
            if f.collateral_asset_id:
                coll = self.db.query(CbdcEligibleCollateral).filter(
                    CbdcEligibleCollateral.collateral_id == f.collateral_asset_id
                ).first()
                if coll:
                    coll.is_pledged = False
                    coll.pledged_to_facility_id = None

            f.status = "matured"
            f.closed_at = now
            processed += 1

        self.db.commit()

        return {
            "facilities_matured": processed,
            "total_interest_ecfa": round(total_interest, 2),
        }

    # ==================================================================
    # 4. INTEREST ACCRUAL & DEMURRAGE
    # ==================================================================

    def apply_daily_interest(self) -> dict:
        """Apply daily interest to eligible wallets.

        BCEAO can use this for:
          - Positive interest on small retail balances (financial inclusion)
          - Demurrage (negative interest) on large hoarded balances
          - Reserve remuneration (if policy decides to remunerate)

        Uses CbdcPolicy records of type INTEREST or DEMURRAGE.
        """
        today = date.today()
        total_interest_paid = 0.0
        total_demurrage_collected = 0.0
        wallets_affected = 0

        # Get active INTEREST policies
        interest_policies = self.db.query(CbdcPolicy).filter(
            CbdcPolicy.policy_type == "INTEREST",
            CbdcPolicy.is_active == True,
        ).all()

        for policy in interest_policies:
            conditions = json.loads(policy.conditions) if policy.conditions else {}
            annual_rate = conditions.get("annual_rate_percent", 0.0)
            min_balance = conditions.get("min_balance_ecfa", 0.0)
            max_balance = conditions.get("max_balance_ecfa", float("inf"))
            wallet_types = policy.wallet_types.split(",") if policy.wallet_types else ["RETAIL"]

            if annual_rate <= 0:
                continue

            daily_rate = annual_rate / 365.0 / 100.0

            wallets = self.db.query(CbdcWallet).filter(
                CbdcWallet.wallet_type.in_(wallet_types),
                CbdcWallet.status == "active",
                CbdcWallet.balance_ecfa >= min_balance,
                CbdcWallet.balance_ecfa <= max_balance,
            ).all()

            for w in wallets:
                interest_amount = round(w.balance_ecfa * daily_rate, 2)
                if interest_amount < 0.01:
                    continue

                cb_wallet = self._get_country_cb_wallet(w)
                if cb_wallet:
                    self._facility_ledger_entry(
                        cb_wallet.wallet_id, w.wallet_id, interest_amount,
                        "INTEREST_CREDIT", policy.policy_id
                    )
                    total_interest_paid += interest_amount
                    wallets_affected += 1

        # Get active DEMURRAGE policies
        demurrage_policies = self.db.query(CbdcPolicy).filter(
            CbdcPolicy.policy_type == "DEMURRAGE",
            CbdcPolicy.is_active == True,
        ).all()

        for policy in demurrage_policies:
            conditions = json.loads(policy.conditions) if policy.conditions else {}
            annual_rate = conditions.get("annual_rate_percent", 0.5)
            threshold = conditions.get("threshold_ecfa", DEMURRAGE_THRESHOLD_XOF)
            wallet_types = policy.wallet_types.split(",") if policy.wallet_types else ["RETAIL", "MERCHANT"]

            daily_rate = annual_rate / 365.0 / 100.0

            wallets = self.db.query(CbdcWallet).filter(
                CbdcWallet.wallet_type.in_(wallet_types),
                CbdcWallet.status == "active",
                CbdcWallet.balance_ecfa > threshold,
            ).all()

            for w in wallets:
                # Demurrage only on amount above threshold
                taxable = w.balance_ecfa - threshold
                demurrage_amount = round(taxable * daily_rate, 2)
                if demurrage_amount < 0.01:
                    continue

                cb_wallet = self._get_country_cb_wallet(w)
                if cb_wallet:
                    self._facility_ledger_entry(
                        w.wallet_id, cb_wallet.wallet_id, demurrage_amount,
                        "DEMURRAGE_DEBIT", policy.policy_id
                    )
                    total_demurrage_collected += demurrage_amount
                    wallets_affected += 1

        self.db.commit()

        return {
            "date": today.isoformat(),
            "wallets_affected": wallets_affected,
            "total_interest_paid_ecfa": round(total_interest_paid, 2),
            "total_demurrage_collected_ecfa": round(total_demurrage_collected, 2),
            "net_ecfa": round(total_demurrage_collected - total_interest_paid, 2),
        }

    # ==================================================================
    # 5. MONEY SUPPLY COMPUTATION (M0 / M1 / M2)
    # ==================================================================

    def compute_money_supply(self, country_code: str | None = None) -> dict:
        """Compute M0, M1, M2 money supply aggregates.

        BCEAO definitions applied to eCFA:
          M0 (base money) = total eCFA minted - total eCFA burned
                          = net CB issuance (CB wallet negative balance = M0)
          M1 (narrow money) = retail + merchant + agent balances
                            = eCFA in active circulation
          M2 (broad money) = M1 + commercial bank reserve balances
                           = total eCFA in the system

        Reserve multiplier = M2 / M0 (should be close to 1.0 for CBDC,
        since banks can't create eCFA — only CB can mint).
        """
        filters = [CbdcWallet.status == "active"]
        if country_code:
            from src.database.models import Country
            country = self.db.query(Country).filter(
                Country.code == country_code
            ).first()
            if country:
                filters.append(CbdcWallet.country_id == country.id)

        # Query balances by wallet type
        wallet_sums = self.db.query(
            CbdcWallet.wallet_type,
            func.coalesce(func.sum(CbdcWallet.balance_ecfa), 0.0),
            func.count(CbdcWallet.id),
        ).filter(*filters).group_by(CbdcWallet.wallet_type).all()

        breakdown = {}
        for wtype, total_bal, count in wallet_sums:
            breakdown[wtype] = {"balance_ecfa": total_bal or 0.0, "count": count}

        retail = breakdown.get("RETAIL", {}).get("balance_ecfa", 0.0)
        merchant = breakdown.get("MERCHANT", {}).get("balance_ecfa", 0.0)
        agent = breakdown.get("AGENT", {}).get("balance_ecfa", 0.0)
        bank = breakdown.get("COMMERCIAL_BANK", {}).get("balance_ecfa", 0.0)
        cb = breakdown.get("CENTRAL_BANK", {}).get("balance_ecfa", 0.0)

        # M0 = negative of CB balance (CB balance is negative because
        # every mint debits CB, every burn credits CB)
        m0 = abs(cb) if cb < 0 else 0.0

        # M1 = demand deposits in circulation
        m1 = retail + merchant + agent

        # M2 = M1 + bank reserves
        m2 = m1 + bank

        # Reserve multiplier
        multiplier = m2 / m0 if m0 > 0 else 0.0

        # Velocity (from today's transactions)
        today_start = datetime.combine(date.today(), datetime.min.time())
        vol_filters = [
            CbdcTransaction.initiated_at >= today_start,
            CbdcTransaction.status == "completed",
        ]
        if country_code:
            vol_filters.append(
                (CbdcTransaction.sender_country == country_code) |
                (CbdcTransaction.receiver_country == country_code)
            )
        daily_volume = self.db.query(
            func.coalesce(func.sum(CbdcTransaction.amount_ecfa), 0.0)
        ).filter(*vol_filters).scalar() or 0.0

        velocity = daily_volume / m1 if m1 > 0 else 0.0

        return {
            "country_code": country_code or "ALL_WAEMU",
            "date": date.today().isoformat(),
            "m0_base_money_ecfa": round(m0, 2),
            "m1_narrow_money_ecfa": round(m1, 2),
            "m2_broad_money_ecfa": round(m2, 2),
            "reserve_multiplier": round(multiplier, 4),
            "breakdown": {
                "retail_ecfa": round(retail, 2),
                "merchant_ecfa": round(merchant, 2),
                "agent_ecfa": round(agent, 2),
                "commercial_bank_ecfa": round(bank, 2),
                "central_bank_ecfa": round(cb, 2),
            },
            "daily_volume_ecfa": round(daily_volume, 2),
            "velocity": round(velocity, 4),
            "total_wallets": sum(v["count"] for v in breakdown.values()),
        }

    # ==================================================================
    # 6. MONETARY POLICY DECISION RECORDING
    # ==================================================================

    def record_policy_decision(self, meeting_date: date,
                               decision_summary: str,
                               rationale: str,
                               taux_directeur: float,
                               taux_pret_marginal: float,
                               taux_depot: float,
                               reserve_ratio: float,
                               meeting_type: str = "QUARTERLY",
                               inflation_rate: float | None = None,
                               gdp_growth: float | None = None,
                               votes_for: int | None = None,
                               votes_against: int | None = None,
                               votes_abstain: int | None = None,
                               effective_date: date | None = None) -> dict:
        """Record a Comité de Politique Monétaire decision.

        This creates the decision record AND applies all rate changes.
        """
        eff_date = effective_date or meeting_date
        decision_id = str(uuid.uuid4())

        # Get current rates for comparison
        current_rates = self.get_current_rates()
        prev_td = current_rates.get("TAUX_DIRECTEUR", {}).get("rate_percent")
        prev_pm = current_rates.get("TAUX_PRET_MARGINAL", {}).get("rate_percent")
        prev_dep = current_rates.get("TAUX_DEPOT", {}).get("rate_percent")
        prev_rr = self.get_current_reserve_ratio()

        # Get circulation data for context
        money_supply = self.compute_money_supply()

        decision = CbdcMonetaryPolicyDecision(
            decision_id=decision_id,
            meeting_date=meeting_date,
            meeting_type=meeting_type,
            decision_summary=decision_summary,
            rationale=rationale,
            taux_directeur=taux_directeur,
            taux_pret_marginal=taux_pret_marginal,
            taux_depot=taux_depot,
            reserve_ratio_percent=reserve_ratio,
            prev_taux_directeur=prev_td,
            prev_taux_pret_marginal=prev_pm,
            prev_taux_depot=prev_dep,
            prev_reserve_ratio_percent=prev_rr,
            inflation_rate_percent=inflation_rate,
            gdp_growth_percent=gdp_growth,
            ecfa_circulation_total=money_supply["m1_narrow_money_ecfa"],
            ecfa_velocity=money_supply["velocity"],
            votes_for=votes_for,
            votes_against=votes_against,
            votes_abstain=votes_abstain,
            status="decided",
            effective_date=eff_date,
        )
        self.db.add(decision)

        # Apply rate changes
        decided_by = "Comité de Politique Monétaire"
        if taux_directeur != prev_td:
            self.set_policy_rate(
                "TAUX_DIRECTEUR", taux_directeur,
                decision_id=decision_id, decided_by=decided_by,
                effective_date=eff_date,
            )
        if reserve_ratio != prev_rr:
            self.set_policy_rate(
                "TAUX_RESERVE", reserve_ratio,
                decision_id=decision_id, decided_by=decided_by,
                effective_date=eff_date,
            )

        log_audit_event(
            self.db, "MONETARY_POLICY_DECISION",
            actor_channel="ADMIN",
            target_entity_type="policy_decision",
            target_entity_id=decision_id,
            details={
                "meeting_date": meeting_date.isoformat(),
                "taux_directeur": taux_directeur,
                "reserve_ratio": reserve_ratio,
                "changed_td": taux_directeur != prev_td,
                "changed_rr": reserve_ratio != prev_rr,
            },
        )

        self.db.commit()

        return {
            "decision_id": decision_id,
            "meeting_date": meeting_date.isoformat(),
            "effective_date": eff_date.isoformat(),
            "rates": {
                "taux_directeur": taux_directeur,
                "taux_pret_marginal": taux_pret_marginal,
                "taux_depot": taux_depot,
                "reserve_ratio": reserve_ratio,
            },
            "changes": {
                "taux_directeur_delta": round(taux_directeur - (prev_td or taux_directeur), 2),
                "reserve_ratio_delta": round(reserve_ratio - (prev_rr or reserve_ratio), 2),
            },
            "status": "decided",
        }

    def get_decision_history(self, limit: int = 10) -> list[dict]:
        """Get history of monetary policy decisions."""
        decisions = self.db.query(CbdcMonetaryPolicyDecision).order_by(
            CbdcMonetaryPolicyDecision.meeting_date.desc()
        ).limit(limit).all()

        return [{
            "decision_id": d.decision_id,
            "meeting_date": d.meeting_date.isoformat(),
            "meeting_type": d.meeting_type,
            "decision_summary": d.decision_summary,
            "taux_directeur": d.taux_directeur,
            "taux_pret_marginal": d.taux_pret_marginal,
            "taux_depot": d.taux_depot,
            "reserve_ratio_percent": d.reserve_ratio_percent,
            "inflation_rate_percent": d.inflation_rate_percent,
            "status": d.status,
            "effective_date": d.effective_date.isoformat(),
        } for d in decisions]

    # ==================================================================
    # ENHANCED MONETARY AGGREGATES (M0/M1/M2 + policy context)
    # ==================================================================

    def compute_enhanced_monetary_aggregates(self, country_code: str) -> dict:
        """Compute monetary aggregates with M0/M1/M2 and policy rate context.

        Extends the basic settlement engine aggregates with central bank data.
        """
        money_supply = self.compute_money_supply(country_code)
        rates = self.get_current_rates()

        # Reserve position for this country
        reserves = self.db.query(CbdcReserveRequirement).filter(
            CbdcReserveRequirement.country_code == country_code,
            CbdcReserveRequirement.computation_date == date.today(),
        ).all()

        total_required = sum(r.required_amount_ecfa for r in reserves)
        total_held = sum(r.current_holding_ecfa for r in reserves)

        # Standing facility usage
        active_lending = self.db.query(
            func.coalesce(func.sum(CbdcStandingFacility.amount_ecfa), 0.0)
        ).filter(
            CbdcStandingFacility.facility_type == "LENDING",
            CbdcStandingFacility.status == "active",
        ).scalar() or 0.0

        active_deposit = self.db.query(
            func.coalesce(func.sum(CbdcStandingFacility.amount_ecfa), 0.0)
        ).filter(
            CbdcStandingFacility.facility_type == "DEPOSIT",
            CbdcStandingFacility.status == "active",
        ).scalar() or 0.0

        return {
            **money_supply,
            "policy_rates": {
                "taux_directeur": rates.get("TAUX_DIRECTEUR", {}).get("rate_percent"),
                "taux_pret_marginal": rates.get("TAUX_PRET_MARGINAL", {}).get("rate_percent"),
                "taux_depot": rates.get("TAUX_DEPOT", {}).get("rate_percent"),
            },
            "reserve_position": {
                "total_required_ecfa": round(total_required, 2),
                "total_held_ecfa": round(total_held, 2),
                "compliance_ratio": round(total_held / total_required, 4) if total_required > 0 else 1.0,
            },
            "facility_usage": {
                "lending_outstanding_ecfa": round(active_lending, 2),
                "deposit_outstanding_ecfa": round(active_deposit, 2),
                "net_facility_position_ecfa": round(active_lending - active_deposit, 2),
            },
        }

    # ==================================================================
    # HELPERS
    # ==================================================================

    def _get_country_cb_wallet(self, wallet: CbdcWallet) -> CbdcWallet | None:
        """Get the central bank wallet for a wallet's country."""
        return self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_type == "CENTRAL_BANK",
            CbdcWallet.country_id == wallet.country_id,
        ).first()

    def _get_cb_wallet_for_bank(self, bank_wallet_id: str) -> CbdcWallet | None:
        """Get the CB wallet for a bank's country."""
        bank = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == bank_wallet_id
        ).first()
        if not bank:
            return None
        return self._get_country_cb_wallet(bank)

    def _facility_ledger_entry(self, debit_wallet_id: str,
                                credit_wallet_id: str,
                                amount: float, tx_type: str,
                                reference: str) -> None:
        """Create a double-entry ledger record for facility operations.

        Lightweight version — directly mutates balances and creates entries.
        For facility ops we skip PIN/limit checks (CB-to-bank operations).
        """
        from src.utils.cbdc_crypto import compute_entry_hash
        now = datetime.utcnow()

        # Lock wallets in sorted order
        ids = sorted([debit_wallet_id, credit_wallet_id])
        w1 = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == ids[0]
        ).with_for_update().first()
        w2 = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == ids[1]
        ).with_for_update().first()

        if not w1 or not w2:
            return

        debit_w = w1 if w1.wallet_id == debit_wallet_id else w2
        credit_w = w1 if w1.wallet_id == credit_wallet_id else w2

        tx_id = str(uuid.uuid4())

        # Get previous hashes
        last_debit = self.db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == debit_wallet_id
        ).order_by(CbdcLedgerEntry.created_at.desc()).first()
        last_credit = self.db.query(CbdcLedgerEntry).filter(
            CbdcLedgerEntry.wallet_id == credit_wallet_id
        ).order_by(CbdcLedgerEntry.created_at.desc()).first()

        debit_prev = last_debit.entry_hash if last_debit else None
        credit_prev = last_credit.entry_hash if last_credit else None

        # DEBIT
        debit_w.balance_ecfa -= amount
        debit_w.available_balance_ecfa -= amount

        debit_hash = compute_entry_hash(
            debit_wallet_id, "DEBIT", amount, debit_w.balance_ecfa,
            tx_type, debit_prev, now.isoformat()
        )
        self.db.add(CbdcLedgerEntry(
            entry_id=str(uuid.uuid4()),
            transaction_id=tx_id,
            wallet_id=debit_wallet_id,
            entry_type="DEBIT",
            amount_ecfa=amount,
            balance_after_ecfa=debit_w.balance_ecfa,
            tx_type=tx_type,
            counterparty_wallet_id=credit_wallet_id,
            reference=reference,
            country_code=debit_w.country.code if debit_w.country else "XX",
            channel="ADMIN",
            entry_hash=debit_hash,
            prev_entry_hash=debit_prev,
            created_at=now,
        ))

        # CREDIT
        credit_w.balance_ecfa += amount
        credit_w.available_balance_ecfa += amount

        credit_hash = compute_entry_hash(
            credit_wallet_id, "CREDIT", amount, credit_w.balance_ecfa,
            tx_type, credit_prev, now.isoformat()
        )
        self.db.add(CbdcLedgerEntry(
            entry_id=str(uuid.uuid4()),
            transaction_id=tx_id,
            wallet_id=credit_wallet_id,
            entry_type="CREDIT",
            amount_ecfa=amount,
            balance_after_ecfa=credit_w.balance_ecfa,
            tx_type=tx_type,
            counterparty_wallet_id=debit_wallet_id,
            reference=reference,
            country_code=credit_w.country.code if credit_w.country else "XX",
            channel="ADMIN",
            entry_hash=credit_hash,
            prev_entry_hash=credit_prev,
            created_at=now,
        ))
