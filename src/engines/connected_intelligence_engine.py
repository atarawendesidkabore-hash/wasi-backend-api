"""Bridge DEX and microfinance data into one intelligence view."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.database.etf_models import EtfProduct
from src.database.investment_models import InvestmentPortfolio, StockHolding, StockOrder
from src.database.microloan_models import MicroLoan, MicrofinanceClient


ACTIVE_LOAN_STATUSES = {"APPROVED", "DISBURSED", "ACTIVE"}


class ConnectedIntelligenceEngine:
    """Build a unified user-level summary across DEX and MFI modules."""

    @staticmethod
    def build_overview(db: Session, user_id: int) -> dict:
        dex = ConnectedIntelligenceEngine._build_dex_summary(db, user_id)
        microfinance = ConnectedIntelligenceEngine._build_microfinance_summary(db, user_id)
        recommendations = ConnectedIntelligenceEngine._build_recommendations(dex, microfinance)

        diversification_score = 100.0 if len(dex["category_exposure"]) >= 3 else 70.0 if len(dex["category_exposure"]) == 2 else 45.0 if dex["holding_count"] else 0.0
        portfolio_score = 100.0 if dex["unrealized_pnl_xof"] >= 0 else 65.0
        collection_score = 100.0 if microfinance["active_loan_count"] == 0 else max(
            20.0,
            100.0 - (microfinance["overdue_loan_count"] / max(microfinance["active_loan_count"], 1) * 100.0),
        )
        repayment_score = microfinance["repayment_rate_pct"] if microfinance["client_count"] else 0.0

        active_scores = [score for score in [diversification_score, portfolio_score, collection_score, repayment_score] if score > 0]
        connected_score = round(sum(active_scores) / len(active_scores), 1) if active_scores else 0.0

        return {
            "user_id": user_id,
            "connected_score": connected_score,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dex": dex,
            "microfinance": microfinance,
            "recommendations": recommendations,
        }

    @staticmethod
    def _build_dex_summary(db: Session, user_id: int) -> dict:
        portfolio = (
            db.query(InvestmentPortfolio)
            .filter(InvestmentPortfolio.user_id == user_id)
            .first()
        )
        holdings = portfolio.holdings if portfolio else []
        orders_30d = 0
        if portfolio:
            orders_30d = (
                db.query(func.count(StockOrder.id))
                .filter(
                    StockOrder.user_id == user_id,
                    StockOrder.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
                )
                .scalar()
                or 0
            )

        etf_map = {
            item.ticker: item
            for item in db.query(EtfProduct).filter(EtfProduct.is_active == True).all()
        }

        holding_rows = []
        category_totals: dict[str, float] = {}
        invested_total = 0.0
        current_total = 0.0

        for holding in holdings:
            current_nav = float(holding.avg_buy_price or 0.0)
            category = None
            etf = etf_map.get(holding.index_name)
            if etf:
                current_nav = float(etf.nav_xof or current_nav)
                category = etf.category

            current_value = round(float(holding.units or 0.0) * current_nav, 2)
            invested = round(float(holding.total_cost or 0.0), 2)
            pnl = round(current_value - invested, 2)
            invested_total += invested
            current_total += current_value

            label = category or holding.exchange_code
            category_totals[label] = category_totals.get(label, 0.0) + current_value

            holding_rows.append(
                {
                    "ticker": holding.index_name,
                    "category": category,
                    "units": round(float(holding.units or 0.0), 6),
                    "average_cost_xof": round(float(holding.avg_buy_price or 0.0), 2),
                    "current_nav_xof": round(current_nav, 2),
                    "current_value_xof": current_value,
                    "unrealized_pnl_xof": pnl,
                }
            )

        holding_rows.sort(key=lambda item: item["current_value_xof"], reverse=True)
        current_total = round(current_total, 2)
        category_exposure = [
            {
                "category": category,
                "current_value_xof": round(value, 2),
                "weight_pct": round((value / current_total * 100.0), 2) if current_total else 0.0,
            }
            for category, value in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
        ]

        return {
            "holding_count": len(holding_rows),
            "order_count_30d": int(orders_30d),
            "invested_xof": round(invested_total, 2),
            "current_value_xof": current_total,
            "unrealized_pnl_xof": round(current_total - invested_total, 2),
            "top_holding_ticker": holding_rows[0]["ticker"] if holding_rows else None,
            "category_exposure": category_exposure,
            "holdings": holding_rows,
        }

    @staticmethod
    def _build_microfinance_summary(db: Session, user_id: int) -> dict:
        clients = (
            db.query(MicrofinanceClient)
            .filter(MicrofinanceClient.user_id == user_id, MicrofinanceClient.is_active == True)
            .all()
        )
        client_ids = [client.id for client in clients]
        if not client_ids:
            return {
                "client_count": 0,
                "active_loan_count": 0,
                "total_principal_xof": 0.0,
                "outstanding_balance_xof": 0.0,
                "overdue_loan_count": 0,
                "par30_xof": 0.0,
                "repaid_amount_xof": 0.0,
                "repayment_rate_pct": 0.0,
                "top_sector": None,
            }

        loans = db.query(MicroLoan).filter(MicroLoan.client_id.in_(client_ids)).all()
        active_loans = [loan for loan in loans if loan.status in ACTIVE_LOAN_STATUSES]
        total_principal = round(sum(float(loan.principal_xof or 0.0) for loan in loans), 2)
        outstanding_balance = round(sum(float(loan.outstanding_balance_xof or 0.0) for loan in active_loans), 2)
        overdue_loans = [loan for loan in active_loans if int(loan.days_overdue or 0) > 0]
        par30_xof = round(
            sum(float(loan.outstanding_balance_xof or 0.0) for loan in active_loans if int(loan.days_overdue or 0) >= 30),
            2,
        )
        repaid_amount = round(sum(float(loan.total_paid_xof or 0.0) for loan in loans), 2)
        repayment_rate = round((repaid_amount / total_principal * 100.0), 2) if total_principal else 0.0

        sector_counts: dict[str, int] = {}
        for client in clients:
            sector = client.sector or "unknown"
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        top_sector = max(sector_counts, key=sector_counts.get) if sector_counts else None

        return {
            "client_count": len(clients),
            "active_loan_count": len(active_loans),
            "total_principal_xof": total_principal,
            "outstanding_balance_xof": outstanding_balance,
            "overdue_loan_count": len(overdue_loans),
            "par30_xof": par30_xof,
            "repaid_amount_xof": repaid_amount,
            "repayment_rate_pct": repayment_rate,
            "top_sector": top_sector,
        }

    @staticmethod
    def _build_recommendations(dex: dict, microfinance: dict) -> list[dict]:
        recommendations: list[dict] = []

        if dex["holding_count"] == 0:
            recommendations.append(
                {
                    "priority": 1,
                    "domain": "dex",
                    "title": "Open a starter DEX allocation",
                    "detail": "No DEX exposure is linked yet. Add one ETF position so intelligence can compare market performance against your loan portfolio.",
                }
            )
        elif len(dex["category_exposure"]) < 2:
            recommendations.append(
                {
                    "priority": 1,
                    "domain": "dex",
                    "title": "Diversify beyond one DEX category",
                    "detail": "Your DEX portfolio is concentrated in a single category. Adding a second ETF category will reduce concentration risk in the intelligence view.",
                }
            )

        if microfinance["overdue_loan_count"] > 0:
            recommendations.append(
                {
                    "priority": 1,
                    "domain": "microfinance",
                    "title": "Prioritize overdue loan recovery",
                    "detail": f"{microfinance['overdue_loan_count']} active loan(s) are overdue. Collections should come before new disbursement growth.",
                }
            )
        elif microfinance["client_count"] == 0:
            recommendations.append(
                {
                    "priority": 2,
                    "domain": "microfinance",
                    "title": "Link your first borrower portfolio",
                    "detail": "No microfinance clients are attached to this user yet. Register borrowers to surface portfolio risk and repayment intelligence.",
                }
            )

        if dex["holding_count"] > 0 and microfinance["client_count"] > 0:
            recommendations.append(
                {
                    "priority": 2,
                    "domain": "intelligence",
                    "title": "Use intelligence as a treasury bridge",
                    "detail": "Track DEX unrealized P&L beside MFI repayment health to decide when liquidity should stay invested versus support loan book expansion.",
                }
            )

        return sorted(recommendations, key=lambda item: (item["priority"], item["domain"]))
