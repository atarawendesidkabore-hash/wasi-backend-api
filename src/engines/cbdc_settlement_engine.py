"""
eCFA CBDC Settlement Engine — Batch Settlement with Bilateral Netting.

Settlement windows:
  - Domestic:     Every 15 minutes — net inter-bank eCFA flows
  - Cross-border: Every 4 hours — net WAEMU inter-country flows
  - Merchant:     Daily — batch merchant settlements to their banks

Netting reduces gross settlement volume by 60-80%.

STAR-UEMOA integration: generates RTGS instruction messages in BCEAO format.
"""
import uuid
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.cbdc_models import (
    CbdcTransaction, CbdcSettlement, CbdcWallet, CbdcMonetaryAggregate,
)
from src.utils.cbdc_audit import log_settlement_submitted

logger = logging.getLogger(__name__)


class CbdcSettlementEngine:
    """Batch settlement with bilateral netting for eCFA CBDC."""

    def __init__(self, db: Session):
        self.db = db

    def run_domestic_settlement(self, window_minutes: int = 15) -> dict:
        """Run domestic inter-bank netting settlement.

        Groups all completed transactions by (sender_bank, receiver_bank) pair,
        computes net position, and creates settlement records.
        """
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)

        # Find unsettled domestic transactions between bank wallets
        txs = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.initiated_at >= window_start,
            CbdcTransaction.status == "completed",
            CbdcTransaction.is_cross_border == False,
            CbdcTransaction.tx_type.notin_(["MINT", "BURN"]),
        ).all()

        if not txs:
            return {"settlements": 0, "transactions_netted": 0}

        # Group by bank pair (using sender/receiver institution codes)
        bank_flows = defaultdict(lambda: {"a_to_b": 0.0, "b_to_a": 0.0, "count": 0})

        for tx in txs:
            sender_bank = self._get_settlement_bank(tx.sender_wallet_id)
            receiver_bank = self._get_settlement_bank(tx.receiver_wallet_id)

            if not sender_bank or not receiver_bank or sender_bank == receiver_bank:
                continue

            # Normalize pair key (alphabetical order)
            pair = tuple(sorted([sender_bank, receiver_bank]))
            if sender_bank == pair[0]:
                bank_flows[pair]["a_to_b"] += tx.amount_ecfa
            else:
                bank_flows[pair]["b_to_a"] += tx.amount_ecfa
            bank_flows[pair]["count"] += 1

        # Create settlement records
        settlements_created = 0
        total_netted = 0

        for (bank_a, bank_b), flows in bank_flows.items():
            gross = flows["a_to_b"] + flows["b_to_a"]
            net = abs(flows["a_to_b"] - flows["b_to_a"])

            if flows["a_to_b"] > flows["b_to_a"]:
                direction = "A_TO_B"
            elif flows["b_to_a"] > flows["a_to_b"]:
                direction = "B_TO_A"
            else:
                direction = "BALANCED"

            settlement = CbdcSettlement(
                settlement_id=str(uuid.uuid4()),
                settlement_type="DOMESTIC_NET",
                bank_a_code=bank_a,
                bank_b_code=bank_b,
                gross_amount_ecfa=gross,
                net_amount_ecfa=net,
                direction=direction,
                transaction_count=flows["count"],
                country_codes=self._get_bank_country(bank_a),
                is_cross_border=False,
                status="pending",
                window_start=window_start,
                window_end=now,
            )
            self.db.add(settlement)

            log_settlement_submitted(
                self.db, settlement.settlement_id, "DOMESTIC_NET", net
            )

            settlements_created += 1
            total_netted += flows["count"]

        self.db.commit()

        netting_ratio = 0.0
        if settlements_created > 0:
            total_gross = sum(f["a_to_b"] + f["b_to_a"] for f in bank_flows.values())
            total_net = sum(abs(f["a_to_b"] - f["b_to_a"]) for f in bank_flows.values())
            netting_ratio = 1.0 - (total_net / total_gross) if total_gross > 0 else 0.0

        return {
            "settlements": settlements_created,
            "transactions_netted": total_netted,
            "netting_ratio": round(netting_ratio, 4),
            "window": f"{window_start.isoformat()} to {now.isoformat()}",
        }

    def run_cross_border_settlement(self) -> dict:
        """Run cross-border WAEMU inter-country netting (every 4 hours)."""
        now = datetime.utcnow()
        window_start = now - timedelta(hours=4)

        txs = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.initiated_at >= window_start,
            CbdcTransaction.status == "completed",
            CbdcTransaction.is_cross_border == True,
        ).all()

        if not txs:
            return {"settlements": 0, "transactions_netted": 0}

        # Group by country pair
        country_flows = defaultdict(lambda: {"a_to_b": 0.0, "b_to_a": 0.0, "count": 0})

        for tx in txs:
            if not tx.sender_country or not tx.receiver_country:
                continue
            pair = tuple(sorted([tx.sender_country, tx.receiver_country]))
            if tx.sender_country == pair[0]:
                country_flows[pair]["a_to_b"] += tx.amount_ecfa
            else:
                country_flows[pair]["b_to_a"] += tx.amount_ecfa
            country_flows[pair]["count"] += 1

        settlements_created = 0
        for (cc_a, cc_b), flows in country_flows.items():
            gross = flows["a_to_b"] + flows["b_to_a"]
            net = abs(flows["a_to_b"] - flows["b_to_a"])
            direction = "A_TO_B" if flows["a_to_b"] > flows["b_to_a"] else (
                "B_TO_A" if flows["b_to_a"] > flows["a_to_b"] else "BALANCED"
            )

            settlement = CbdcSettlement(
                settlement_id=str(uuid.uuid4()),
                settlement_type="CROSS_BORDER_NET",
                bank_a_code=f"BCEAO_{cc_a}",
                bank_b_code=f"BCEAO_{cc_b}",
                gross_amount_ecfa=gross,
                net_amount_ecfa=net,
                direction=direction,
                transaction_count=flows["count"],
                country_codes=f"{cc_a},{cc_b}",
                is_cross_border=True,
                status="pending",
                window_start=window_start,
                window_end=now,
            )
            self.db.add(settlement)
            log_settlement_submitted(
                self.db, settlement.settlement_id, "CROSS_BORDER_NET", net
            )
            settlements_created += 1

        self.db.commit()
        return {
            "settlements": settlements_created,
            "transactions_netted": sum(f["count"] for f in country_flows.values()),
        }

    def compute_monetary_aggregates(self, country_code: str) -> dict:
        """Compute daily monetary aggregates for BCEAO reporting."""
        from datetime import date
        today = date.today()

        # Check if already computed today
        existing = self.db.query(CbdcMonetaryAggregate).filter(
            CbdcMonetaryAggregate.snapshot_date == today,
            CbdcMonetaryAggregate.country_code == country_code,
        ).first()

        from src.database.models import Country
        country = self.db.query(Country).filter(Country.code == country_code).first()
        if not country:
            return {"error": f"Country {country_code} not found"}

        # Calculate balances by wallet type
        wallet_balances = self.db.query(
            CbdcWallet.wallet_type,
            func.sum(CbdcWallet.balance_ecfa),
            func.count(CbdcWallet.id),
        ).filter(
            CbdcWallet.country_id == country.id,
            CbdcWallet.status == "active",
        ).group_by(CbdcWallet.wallet_type).all()

        retail = 0.0
        merchant = 0.0
        bank = 0.0
        agent = 0.0
        active_wallets = 0

        for wtype, balance, count in wallet_balances:
            bal = balance or 0.0
            if wtype == "RETAIL":
                retail = bal
            elif wtype == "MERCHANT":
                merchant = bal
            elif wtype in ("COMMERCIAL_BANK", "CENTRAL_BANK"):
                bank = bal
            elif wtype == "AGENT":
                agent = bal
            active_wallets += count

        total_circulation = retail + merchant + agent  # exclude bank reserves

        # Daily transaction volumes
        today_start = datetime.combine(today, datetime.min.time())
        today_txs = self.db.query(CbdcTransaction).filter(
            CbdcTransaction.initiated_at >= today_start,
            CbdcTransaction.status == "completed",
            (CbdcTransaction.sender_country == country_code) |
            (CbdcTransaction.receiver_country == country_code),
        ).all()

        p2p_vol = sum(tx.amount_ecfa for tx in today_txs if tx.tx_type == "TRANSFER_P2P")
        merchant_vol = sum(tx.amount_ecfa for tx in today_txs if tx.tx_type == "MERCHANT_PAYMENT")
        cb_vol = sum(tx.amount_ecfa for tx in today_txs if tx.is_cross_border)
        minted = sum(tx.amount_ecfa for tx in today_txs if tx.tx_type == "MINT")
        burned = sum(tx.amount_ecfa for tx in today_txs if tx.tx_type == "BURN")

        # Velocity = total volume / circulation
        total_vol = sum(tx.amount_ecfa for tx in today_txs)
        velocity = total_vol / total_circulation if total_circulation > 0 else 0.0

        # New wallets today
        new_wallets = self.db.query(CbdcWallet).filter(
            CbdcWallet.country_id == country.id,
            CbdcWallet.created_at >= today_start,
        ).count()

        # ── M0 / M1 / M2 computation ────────────────────────────────
        # M0 = net issuance (minted - burned, cumulative)
        from src.database.cbdc_models import CbdcLedgerEntry, CbdcPolicyRate, CbdcReserveRequirement, CbdcStandingFacility
        total_ever_minted = self.db.query(
            func.coalesce(func.sum(CbdcTransaction.amount_ecfa), 0.0)
        ).filter(CbdcTransaction.tx_type == "MINT",
                 CbdcTransaction.status == "completed",
                 CbdcTransaction.sender_country == country_code).scalar() or 0.0
        total_ever_burned = self.db.query(
            func.coalesce(func.sum(CbdcTransaction.amount_ecfa), 0.0)
        ).filter(CbdcTransaction.tx_type == "BURN",
                 CbdcTransaction.status == "completed",
                 CbdcTransaction.receiver_country == country_code).scalar() or 0.0
        m0 = total_ever_minted - total_ever_burned

        m1 = total_circulation  # retail + merchant + agent
        m2 = m1 + bank          # + commercial bank reserves

        # Reserve position
        reserves = self.db.query(CbdcReserveRequirement).filter(
            CbdcReserveRequirement.country_code == country_code,
            CbdcReserveRequirement.computation_date == today,
        ).all()
        total_req_reserves = sum(r.required_amount_ecfa for r in reserves)
        total_held_reserves = sum(r.current_holding_ecfa for r in reserves)
        reserve_compliance = (total_held_reserves / total_req_reserves) if total_req_reserves > 0 else 1.0

        # Facility usage
        active_lending = self.db.query(
            func.coalesce(func.sum(CbdcStandingFacility.amount_ecfa), 0.0)
        ).filter(CbdcStandingFacility.facility_type == "LENDING",
                 CbdcStandingFacility.status == "active").scalar() or 0.0
        active_deposits = self.db.query(
            func.coalesce(func.sum(CbdcStandingFacility.amount_ecfa), 0.0)
        ).filter(CbdcStandingFacility.facility_type == "DEPOSIT",
                 CbdcStandingFacility.status == "active").scalar() or 0.0

        # Current policy rates
        td_rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_DIRECTEUR",
            CbdcPolicyRate.is_current == True,
        ).first()
        pm_rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_PRET_MARGINAL",
            CbdcPolicyRate.is_current == True,
        ).first()
        dep_rate = self.db.query(CbdcPolicyRate).filter(
            CbdcPolicyRate.rate_type == "TAUX_DEPOT",
            CbdcPolicyRate.is_current == True,
        ).first()

        agg_data = {
            "snapshot_date": today,
            "country_code": country_code,
            "total_ecfa_circulation": total_circulation,
            "retail_balance_ecfa": retail,
            "merchant_balance_ecfa": merchant,
            "bank_balance_ecfa": bank,
            "agent_balance_ecfa": agent,
            "total_minted_ecfa": minted,
            "total_burned_ecfa": burned,
            "total_p2p_volume_ecfa": p2p_vol,
            "total_merchant_volume_ecfa": merchant_vol,
            "total_cross_border_volume_ecfa": cb_vol,
            "active_wallets": active_wallets,
            "new_wallets": new_wallets,
            "total_transactions": len(today_txs),
            "m0_base_money_ecfa": round(m0, 2),
            "m1_narrow_money_ecfa": round(m1, 2),
            "m2_broad_money_ecfa": round(m2, 2),
            "total_required_reserves_ecfa": round(total_req_reserves, 2),
            "total_held_reserves_ecfa": round(total_held_reserves, 2),
            "reserve_compliance_ratio": round(reserve_compliance, 4),
            "total_lending_facility_ecfa": round(active_lending, 2),
            "total_deposit_facility_ecfa": round(active_deposits, 2),
            "taux_directeur_percent": td_rate.rate_percent if td_rate else None,
            "taux_pret_marginal_percent": pm_rate.rate_percent if pm_rate else None,
            "taux_depot_percent": dep_rate.rate_percent if dep_rate else None,
            "velocity": round(velocity, 4),
            "total_interest_paid_ecfa": 0.0,
            "total_demurrage_collected_ecfa": 0.0,
            "total_reserve_penalties_ecfa": 0.0,
        }

        if existing:
            for key, val in agg_data.items():
                if key != "snapshot_date":
                    setattr(existing, key, val)
        else:
            self.db.add(CbdcMonetaryAggregate(**agg_data))

        self.db.commit()
        return agg_data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_settlement_bank(self, wallet_id: str | None) -> str | None:
        """Get the settlement bank code for a wallet."""
        if not wallet_id:
            return None
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.wallet_id == wallet_id
        ).first()
        if not wallet:
            return None
        if wallet.wallet_type in ("COMMERCIAL_BANK", "CENTRAL_BANK"):
            return wallet.institution_code or wallet.wallet_type
        # For retail/merchant/agent, find their linked bank
        return wallet.institution_code or "BCEAO"

    def _get_bank_country(self, bank_code: str) -> str:
        """Get country code for a bank."""
        wallet = self.db.query(CbdcWallet).filter(
            CbdcWallet.institution_code == bank_code
        ).first()
        if wallet and wallet.country:
            return wallet.country.code
        return "XX"
