"""Seed demo DEX and microfinance data for the connected intelligence UI."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.database.etf_models import EtfProduct
from src.database.investment_models import InvestmentPortfolio, StockHolding, StockOrder
from src.database.microloan_models import MicrofinanceClient, MicroLoan
from src.database.models import User


DEMO_ETFS = [
    {
        "ticker": "WASI-GROWTH",
        "name": "WASI Growth ETF",
        "category": "BROAD",
        "underlying_type": "composite",
        "description": "Broad exposure to WASI growth signals.",
        "nav_xof": 12500.0,
        "nav_usd": 20.5,
    },
    {
        "ticker": "WASI-TRADE",
        "name": "WASI Trade Momentum ETF",
        "category": "SECTOR",
        "underlying_type": "sub_index",
        "description": "Trade corridor and freight momentum basket.",
        "nav_xof": 9100.0,
        "nav_usd": 14.9,
    },
    {
        "ticker": "WASI-UEMOA",
        "name": "WASI UEMOA Zone ETF",
        "category": "REGIONAL",
        "underlying_type": "country_group",
        "description": "Regional allocation across the XOF corridor.",
        "nav_xof": 10450.0,
        "nav_usd": 17.1,
    },
]


class DemoSeedEngine:
    """Create stable demo records for one user."""

    @staticmethod
    def bootstrap(db: Session, user: User) -> dict:
        DemoSeedEngine._ensure_demo_etfs(db)
        portfolio = DemoSeedEngine._ensure_demo_portfolio(db, user)
        mfi = DemoSeedEngine._ensure_demo_microfinance(db, user)
        db.commit()

        return {
            "success": True,
            "message": "Demo DEX and microfinance data is ready.",
            "portfolio_id": portfolio.id,
            "mfi_client_count": mfi["client_count"],
            "loan_count": mfi["loan_count"],
            "tickers": [item["ticker"] for item in DEMO_ETFS],
        }

    @staticmethod
    def _ensure_demo_etfs(db: Session) -> None:
        for item in DEMO_ETFS:
            existing = db.query(EtfProduct).filter(EtfProduct.ticker == item["ticker"]).first()
            if existing:
                existing.name = item["name"]
                existing.category = item["category"]
                existing.description = item["description"]
                existing.underlying_type = item["underlying_type"]
                existing.nav_xof = item["nav_xof"]
                existing.nav_usd = item["nav_usd"]
                existing.is_active = True
                existing.nav_updated_at = datetime.now(timezone.utc)
            else:
                db.add(
                    EtfProduct(
                        ticker=item["ticker"],
                        name=item["name"],
                        category=item["category"],
                        description=item["description"],
                        underlying_type=item["underlying_type"],
                        nav_xof=item["nav_xof"],
                        nav_usd=item["nav_usd"],
                        is_active=True,
                        nav_updated_at=datetime.now(timezone.utc),
                    )
                )
        db.flush()

    @staticmethod
    def _ensure_demo_portfolio(db: Session, user: User) -> InvestmentPortfolio:
        portfolio = db.query(InvestmentPortfolio).filter(InvestmentPortfolio.user_id == user.id).first()
        if not portfolio:
            portfolio = InvestmentPortfolio(user_id=user.id, total_invested=0.0)
            db.add(portfolio)
            db.flush()

        holdings_config = [
            {"ticker": "WASI-GROWTH", "units": 8.0, "avg_buy_price": 11800.0},
            {"ticker": "WASI-TRADE", "units": 15.0, "avg_buy_price": 8700.0},
            {"ticker": "WASI-UEMOA", "units": 11.0, "avg_buy_price": 10200.0},
        ]

        total_cost = 0.0
        for idx, item in enumerate(holdings_config, start=1):
            cost = round(item["units"] * item["avg_buy_price"], 2)
            total_cost += cost
            holding = (
                db.query(StockHolding)
                .filter(
                    StockHolding.portfolio_id == portfolio.id,
                    StockHolding.exchange_code == "ETF",
                    StockHolding.index_name == item["ticker"],
                )
                .first()
            )
            if holding:
                holding.units = item["units"]
                holding.avg_buy_price = item["avg_buy_price"]
                holding.total_cost = cost
            else:
                db.add(
                    StockHolding(
                        portfolio_id=portfolio.id,
                        exchange_code="ETF",
                        index_name=item["ticker"],
                        units=item["units"],
                        avg_buy_price=item["avg_buy_price"],
                        total_cost=cost,
                    )
                )

            existing_order = (
                db.query(StockOrder)
                .filter(
                    StockOrder.portfolio_id == portfolio.id,
                    StockOrder.exchange_code == "ETF",
                    StockOrder.index_name == item["ticker"],
                    StockOrder.side == "BUY",
                )
                .first()
            )
            if not existing_order:
                db.add(
                    StockOrder(
                        portfolio_id=portfolio.id,
                        user_id=user.id,
                        exchange_code="ETF",
                        index_name=item["ticker"],
                        side="BUY",
                        units=item["units"],
                        price_per_unit=item["avg_buy_price"],
                        total_amount=cost,
                        status="EXECUTED",
                        settlement_status="SETTLED",
                        created_at=datetime.now(timezone.utc) - timedelta(days=idx * 6),
                    )
                )

        portfolio.total_invested = total_cost
        return portfolio

    @staticmethod
    def _ensure_demo_microfinance(db: Session, user: User) -> dict:
        clients_config = [
            {
                "slug": "awa-market",
                "first_name": "Awa",
                "last_name": "Traore",
                "country_code": "BF",
                "city": "Ouagadougou",
                "sector": "market_trade",
                "business_name": "Awa Cereals Hub",
                "monthly_revenue_xof": 420000,
                "years_in_business": 4,
                "loan": {
                    "loan_number": f"MFI-{user.id}-A01",
                    "principal_xof": 200000,
                    "term_months": 6,
                    "status": "ACTIVE",
                    "outstanding_balance_xof": 150000,
                    "total_paid_xof": 60000,
                    "days_overdue": 12,
                },
            },
            {
                "slug": "mariam-tailor",
                "first_name": "Mariam",
                "last_name": "Diallo",
                "country_code": "CI",
                "city": "Bouake",
                "sector": "tailoring",
                "business_name": "Mariam Stitch Studio",
                "monthly_revenue_xof": 580000,
                "years_in_business": 6,
                "loan": {
                    "loan_number": f"MFI-{user.id}-A02",
                    "principal_xof": 350000,
                    "term_months": 8,
                    "status": "ACTIVE",
                    "outstanding_balance_xof": 210000,
                    "total_paid_xof": 180000,
                    "days_overdue": 37,
                },
            },
            {
                "slug": "issa-farm",
                "first_name": "Issa",
                "last_name": "Kone",
                "country_code": "SN",
                "city": "Kaolack",
                "sector": "agriculture",
                "business_name": "Issa Harvest Supply",
                "monthly_revenue_xof": 730000,
                "years_in_business": 7,
                "loan": {
                    "loan_number": f"MFI-{user.id}-A03",
                    "principal_xof": 500000,
                    "term_months": 10,
                    "status": "REPAID",
                    "outstanding_balance_xof": 0,
                    "total_paid_xof": 545000,
                    "days_overdue": 0,
                },
            },
        ]

        count_clients = 0
        count_loans = 0
        for index, item in enumerate(clients_config, start=1):
            phone_hash = hashlib.sha256(f"demo-{user.id}-{item['slug']}".encode()).hexdigest()
            client = (
                db.query(MicrofinanceClient)
                .filter(MicrofinanceClient.user_id == user.id, MicrofinanceClient.phone_hash == phone_hash)
                .first()
            )
            if not client:
                client = MicrofinanceClient(
                    user_id=user.id,
                    first_name=item["first_name"],
                    last_name=item["last_name"],
                    phone_hash=phone_hash,
                    country_code=item["country_code"],
                    city=item["city"],
                    sector=item["sector"],
                    business_name=item["business_name"],
                    monthly_revenue_xof=item["monthly_revenue_xof"],
                    years_in_business=item["years_in_business"],
                    kyc_level="STANDARD",
                    credit_score=68 + (index * 6),
                    is_active=True,
                )
                db.add(client)
                db.flush()
            else:
                client.city = item["city"]
                client.sector = item["sector"]
                client.business_name = item["business_name"]
                client.monthly_revenue_xof = item["monthly_revenue_xof"]
                client.years_in_business = item["years_in_business"]
                client.kyc_level = "STANDARD"
                client.is_active = True

            loan_cfg = item["loan"]
            loan = db.query(MicroLoan).filter(MicroLoan.loan_number == loan_cfg["loan_number"]).first()
            if not loan:
                loan = MicroLoan(
                    client_id=client.id,
                    loan_number=loan_cfg["loan_number"],
                    product_type="MICRO",
                    purpose="WASI demo working capital",
                    principal_xof=loan_cfg["principal_xof"],
                    interest_rate_annual_pct=18.0,
                    term_months=loan_cfg["term_months"],
                    status=loan_cfg["status"],
                    outstanding_balance_xof=loan_cfg["outstanding_balance_xof"],
                    total_paid_xof=loan_cfg["total_paid_xof"],
                    days_overdue=loan_cfg["days_overdue"],
                    disbursement_method="ECFA_WALLET",
                    disbursement_date=date.today() - timedelta(days=80 + (index * 12)),
                    maturity_date=date.today() + timedelta(days=100 - (index * 15)),
                )
                db.add(loan)
            else:
                loan.status = loan_cfg["status"]
                loan.principal_xof = loan_cfg["principal_xof"]
                loan.outstanding_balance_xof = loan_cfg["outstanding_balance_xof"]
                loan.total_paid_xof = loan_cfg["total_paid_xof"]
                loan.days_overdue = loan_cfg["days_overdue"]
                loan.term_months = loan_cfg["term_months"]
                loan.disbursement_method = "ECFA_WALLET"

            count_clients += 1
            count_loans += 1

        return {"client_count": count_clients, "loan_count": count_loans}
