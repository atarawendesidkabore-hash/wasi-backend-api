import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

from src.config import settings
from src.database.connection import init_db, SessionLocal
from src.database.seed import seed_countries, seed_bilateral_trade, seed_stock_market_data
from src.middleware.x402_payment_verification import RequestLoggingMiddleware
from src.middleware.request_id import RequestIdMiddleware
from src.middleware.error_handler import GlobalErrorHandlerMiddleware
from src.routes.health import router as health_router
from src.routes.auth import router as auth_router
from src.routes.indices import router as indices_router
from src.routes.country import router as country_router
from src.routes.composite import router as composite_router
from src.routes.payment import router as payment_router
from src.routes.analytics import router as analytics_router
from src.routes.signals import router as signals_router
from src.routes.reports import router as reports_router
from src.routes.wallet import router as wallet_router
from src.routes.chat import router as chat_router
from src.routes.trade import router as trade_router
from src.routes.markets import router as markets_router
from src.routes.transport import router as transport_router
from src.routes.bank import router as bank_router
from src.routes.live_signals import router as live_signals_router
from src.routes.ml import router as ml_router
from src.routes.data_admin import router as data_admin_router
from src.routes.ussd import router as ussd_router
from src.routes.cbdc_wallet import router as cbdc_wallet_router
from src.routes.cbdc_transaction import router as cbdc_transaction_router
from src.routes.cbdc_admin import router as cbdc_admin_router
from src.routes.cbdc_monetary_policy import router as cbdc_monetary_policy_router
from src.routes.cbdc_payments import router as cbdc_payments_router
from src.routes.forecast import router as forecast_router
from src.routes.tokenization import router as tokenization_router
from src.routes.risk import router as risk_router
from src.routes.legislative import router as legislative_router
from src.routes.valuation import router as valuation_router
from src.routes.fx import router as fx_router
from src.routes.corridor import router as corridor_router
from src.routes.alerts import router as alerts_router
from src.routes.reconciliation import router as reconciliation_router
from src.routes.world_news import router as world_news_router
from src.routes.forecast_v4 import router as forecast_v4_router
from src.tasks.data_ingestion import ingest_all_csv_files
from src.tasks.composite_update import start_scheduler, stop_scheduler
from src.tasks.bceao_ingestion import ingest_bceao_data
from src.tasks.news_sweep import run_news_sweep
from src.database.seed import seed_transport_data, seed_road_data

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WASI Backend API...")

    # Initialize database tables
    init_db()

    if settings.LIGHT_STARTUP:
        logger.info("LIGHT_STARTUP=True — skipping all seeding/bootstrap for fast startup")
        yield
        return

    # Seed reference data
    db = SessionLocal()
    try:
        seed_countries(db)
        logger.info("Database seeded with 16 WASI countries and tier definitions")

        # Seed bilateral trade data (2022 annual estimates)
        n = seed_bilateral_trade(db)
        if n:
            logger.info("Seeded %d bilateral trade records", n)

        # Ingest any CSV files in the data/ directory
        ingestion_result = ingest_all_csv_files(db)
        if ingestion_result:
            logger.info("CSV ingestion complete: %s", ingestion_result)
        else:
            logger.info("No new CSV data to ingest")

        # Seed historical stock market data (NGX/GSE/BRVM 2019-2023)
        n_stocks = seed_stock_market_data(db)
        if n_stocks:
            logger.info("Seeded %d stock market records (NGX/GSE/BRVM)", n_stocks)

        # Enrich CI/SN/BJ/TG with BCEAO central-bank data
        bceao_result = ingest_bceao_data(db)
        logger.info(
            "BCEAO ingestion: fetched=%d updated=%d inserted=%d skipped=%d",
            bceao_result.get("records_fetched", 0),
            bceao_result.get("updated", 0),
            bceao_result.get("inserted", 0),
            bceao_result.get("skipped", 0),
        )

        # Seed transport data (SITARAIL + primary airport traffic)
        n_transport = seed_transport_data(db)
        if n_transport:
            logger.info("Seeded %d transport records (air/rail)", n_transport)

        # Seed road corridor data (ECOWAS 2024 key ground corridors)
        n_road = seed_road_data(db)
        if n_road:
            logger.info("Seeded %d road corridor records", n_road)

        # External data scrapers — skip in fast local dev mode
        if settings.SKIP_SCRAPERS:
            logger.info("SKIP_SCRAPERS=True — skipping all external API scrapers for fast startup")
            # Still register USSD providers (no network needed)
            try:
                import src.database.ussd_models  # noqa
                from src.tasks.ussd_real_scrapers import seed_ussd_providers
                seed_ussd_providers(db)
            except Exception:
                pass
        else:
            # World Bank bootstrap — run on first startup if no real WB data exists yet
            from src.database.models import CountryIndex, MacroIndicator, CommodityPrice
            wb_count = db.query(CountryIndex).filter(
                CountryIndex.data_source == "World Bank Open Data API"
            ).count()
            if wb_count == 0:
                logger.info("No World Bank data found — running initial WB scraper (may take ~90s)...")
                try:
                    from src.pipelines.scrapers.worldbank_scraper import run_worldbank_scraper
                    wb_result = run_worldbank_scraper(db=None)
                    logger.info(
                        "WB bootstrap complete: updated=%d errors=%d year=%s",
                        wb_result["updated"], wb_result["errors"], wb_result["data_year"]
                    )
                except Exception as exc:
                    logger.warning("WB bootstrap failed (non-fatal): %s", exc)
            else:
                logger.info("World Bank data already present (%d records) — skipping bootstrap", wb_count)

            # IMF bootstrap — run on first startup if no IMF macro data exists
            imf_count = db.query(MacroIndicator).filter(
                MacroIndicator.data_source == "imf_weo"
            ).count()
            if imf_count == 0:
                logger.info("No IMF data found — running initial IMF scraper...")
                try:
                    from src.pipelines.scrapers.imf_scraper import run_imf_scraper
                    imf_result = run_imf_scraper(db=None)
                    logger.info(
                        "IMF bootstrap complete: updated=%d errors=%d year=%s",
                        imf_result["updated"], imf_result["errors"], imf_result["data_year"]
                    )
                except Exception as exc:
                    logger.warning("IMF bootstrap failed (non-fatal): %s", exc)
            else:
                logger.info("IMF data already present (%d records) — skipping bootstrap", imf_count)

            # Commodity prices bootstrap — run once if no prices in DB
            commodity_count = db.query(CommodityPrice).count()
            if commodity_count == 0:
                logger.info("No commodity price data found — running initial Pink Sheet scraper...")
                try:
                    from src.pipelines.scrapers.commodity_scraper import run_commodity_scraper
                    comm_result = run_commodity_scraper(db=None)
                    logger.info(
                        "Commodity bootstrap complete: updated=%d errors=%d",
                        comm_result["updated"], comm_result["errors"]
                    )
                except Exception as exc:
                    logger.warning("Commodity bootstrap failed (non-fatal): %s", exc)
            else:
                logger.info("Commodity price data present (%d records) — skipping bootstrap", commodity_count)

            # USSD bootstrap — scrape real data from public APIs
            try:
                import src.database.ussd_models  # noqa: ensure USSD tables are created
                from src.database.ussd_models import USSDMobileMoneyFlow, USSDCommodityReport
                from src.tasks.ussd_real_scrapers import (
                    run_wfp_food_price_scraper,
                    run_bceao_mobile_money_scraper,
                    run_port_throughput_scraper,
                    run_ecowas_trade_scraper,
                    seed_ussd_providers,
                )
                from src.tasks.ussd_aggregation import run_ussd_aggregation

                # Always ensure providers are registered
                seed_ussd_providers(db)

                # Scrape real data on first startup if no USSD data exists
                ussd_mm_count = db.query(USSDMobileMoneyFlow).count()
                ussd_cp_count = db.query(USSDCommodityReport).count()
                if ussd_mm_count == 0 and ussd_cp_count == 0:
                    logger.info("No USSD data found — running real data scrapers...")
                    try:
                        wfp = run_wfp_food_price_scraper(db)
                        logger.info("WFP food prices: %d records", wfp.get("records_created", 0))
                    except Exception as e:
                        logger.warning("WFP scraper failed (non-fatal): %s", e)
                    try:
                        bceao = run_bceao_mobile_money_scraper(db)
                        logger.info("BCEAO mobile money: %d records", bceao.get("records_created", 0))
                    except Exception as e:
                        logger.warning("BCEAO MoMo scraper failed (non-fatal): %s", e)
                    try:
                        port = run_port_throughput_scraper(db)
                        logger.info("Port throughput: %d records", port.get("records_created", 0))
                    except Exception as e:
                        logger.warning("Port scraper failed (non-fatal): %s", e)
                    try:
                        trade = run_ecowas_trade_scraper(db)
                        logger.info("ECOWAS trade: %d records", trade.get("records_created", 0))
                    except Exception as e:
                        logger.warning("ECOWAS trade scraper failed (non-fatal): %s", e)

                    # Run aggregation after scraping
                    agg_result = run_ussd_aggregation(db)
                    logger.info("USSD aggregation: %s", agg_result.get("status"))
                else:
                    logger.info(
                        "USSD data already present (money=%d, commodity=%d) — skipping bootstrap",
                        ussd_mm_count, ussd_cp_count,
                    )
            except Exception as exc:
                logger.warning("USSD bootstrap failed (non-fatal): %s", exc)

            # ACLED bootstrap — apply fallback conflict signals on first startup
            try:
                from src.pipelines.scrapers.acled_scraper import run_acled_scraper
                acled_result = run_acled_scraper(db=None)
                logger.info(
                    "ACLED bootstrap: events_created=%d api_used=%s",
                    acled_result["events_created"], acled_result["api_used"]
                )
            except Exception as exc:
                logger.warning("ACLED bootstrap failed (non-fatal): %s", exc)

        # eCFA CBDC bootstrap — create treasury wallets for WAEMU countries
        try:
            from src.database.models import Country
            from src.database.cbdc_models import CbdcWallet, CbdcFxRate
            from src.utils.cbdc_crypto import generate_wallet_id
            from datetime import date as _date

            waemu_codes = ["CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW"]
            cb_count = 0
            for cc in waemu_codes:
                country = db.query(Country).filter(Country.code == cc).first()
                if not country:
                    continue
                existing = db.query(CbdcWallet).filter(
                    CbdcWallet.wallet_type == "CENTRAL_BANK",
                    CbdcWallet.country_id == country.id,
                ).first()
                if not existing:
                    wallet = CbdcWallet(
                        wallet_id=generate_wallet_id(),
                        country_id=country.id,
                        wallet_type="CENTRAL_BANK",
                        institution_code="BCEAO",
                        institution_name=f"BCEAO Treasury — {cc}",
                        kyc_tier=3,
                        daily_limit_ecfa=999_999_999_999.0,
                        balance_limit_ecfa=999_999_999_999.0,
                        status="active",
                    )
                    db.add(wallet)
                    cb_count += 1

            # Seed FX rates for non-XOF ECOWAS currencies
            fx_pairs = {
                "NGN": 2.54, "GHS": 0.041, "GNF": 14.10,
                "SLE": 0.036, "LRD": 0.315, "GMD": 0.115,
                "MRU": 0.066, "CVE": 0.167,
            }
            for currency, rate in fx_pairs.items():
                existing = db.query(CbdcFxRate).filter(
                    CbdcFxRate.target_currency == currency,
                    CbdcFxRate.effective_date == _date.today(),
                ).first()
                if not existing:
                    db.add(CbdcFxRate(
                        base_currency="XOF",
                        target_currency=currency,
                        rate=rate,
                        inverse_rate=round(1.0 / rate, 4) if rate else 0,
                        effective_date=_date.today(),
                        source="BCEAO_SEED",
                    ))

            # Seed default BCEAO policy rates (taux directeur + corridor)
            from src.database.cbdc_models import CbdcPolicyRate
            existing_td = db.query(CbdcPolicyRate).filter(
                CbdcPolicyRate.rate_type == "TAUX_DIRECTEUR",
                CbdcPolicyRate.is_current == True,
            ).first()
            if not existing_td:
                import uuid as _uuid
                _today = _date.today()
                default_rates = [
                    ("TAUX_DIRECTEUR", 3.50),
                    ("TAUX_PRET_MARGINAL", 5.50),
                    ("TAUX_DEPOT", 1.50),
                    ("TAUX_RESERVE", 3.00),
                ]
                for rtype, rval in default_rates:
                    db.add(CbdcPolicyRate(
                        rate_id=str(_uuid.uuid4()),
                        rate_type=rtype,
                        rate_percent=rval,
                        decided_by="BCEAO_SEED",
                        rationale="Default BCEAO rates as of December 2024",
                        effective_date=_today,
                        announced_date=_today,
                        is_current=True,
                    ))
                logger.info("eCFA bootstrap: seeded 4 default BCEAO policy rates")

            if cb_count > 0:
                db.commit()
                logger.info("eCFA bootstrap: created %d BCEAO treasury wallets + FX rates", cb_count)
            else:
                db.commit()
                logger.info("eCFA CBDC tables ready (treasury wallets already exist)")
        except Exception as exc:
            logger.warning("eCFA bootstrap failed (non-fatal): %s", exc)

        # Tokenization bootstrap — seed demo data if tables are empty
        try:
            from src.database.tokenization_models import DailyActivityDeclaration
            token_count = db.query(DailyActivityDeclaration).count()
            if token_count == 0:
                logger.info("No tokenization data found — seeding demo data...")
                from src.tasks.tokenization_aggregation import (
                    seed_tokenization_demo_data,
                    run_tokenization_aggregation,
                )
                n_tokens = seed_tokenization_demo_data(db)
                if n_tokens:
                    logger.info("Seeded %d tokenization demo records", n_tokens)
                    agg = run_tokenization_aggregation(db)
                    logger.info("Tokenization aggregation: %s", agg.get("status"))
            else:
                logger.info("Tokenization data present (%d records) — skipping", token_count)
        except Exception as exc:
            logger.warning("Tokenization bootstrap failed (non-fatal): %s", exc)

        # Legislative monitoring bootstrap — seed fallback legislation if table is empty
        try:
            import src.database.legislative_models  # noqa — ensure tables are created
            from src.database.legislative_models import LegislativeAct as _LegAct
            leg_count = db.query(_LegAct).count()
            if leg_count == 0:
                logger.info("No legislative data found — seeding fallback legislation...")
                from src.pipelines.scrapers.legislative_scraper import (
                    FALLBACK_LEGISLATION, _upsert_act, _generate_external_id,
                )
                from src.engines.legislative_engine import LegislativeImpactEngine
                from src.database.models import Country as _Country
                _cmap = {c.code: c for c in db.query(_Country).filter(_Country.is_active == True).all()}
                _summary = {"acts_found": 0, "sessions_found": 0, "errors": 0,
                            "countries_covered": [], "sources_used": ["fallback_seed"]}
                for item in FALLBACK_LEGISLATION:
                    _upsert_act(db, _cmap, {
                        **item,
                        "external_id": _generate_external_id("fallback", item["iso2"], item["act_number"]),
                        "source": "fallback_seed", "source_url": "",
                    }, _summary)
                # Score all acts
                leg_engine = LegislativeImpactEngine(db)
                unscored = db.query(_LegAct).filter(_LegAct.estimated_magnitude == 0.0).all()
                for act in unscored:
                    leg_engine.score_and_update_act(act)
                    if abs(act.estimated_magnitude) > 5.0:
                        leg_engine.emit_news_event(act)
                logger.info("Legislative bootstrap: seeded %d acts, scored %d",
                            _summary["acts_found"], len(unscored))
            else:
                logger.info("Legislative data present (%d acts) — skipping bootstrap", leg_count)
        except Exception as exc:
            logger.warning("Legislative bootstrap failed (non-fatal): %s", exc)

        # FX Analytics bootstrap — seed initial rates if no data exists
        try:
            from src.database.fx_models import FxDailyRate
            fx_count = db.query(FxDailyRate).count()
            if fx_count == 0:
                logger.info("No FX rate data found — seeding fallback rates...")
                from src.pipelines.scrapers.fx_scraper import _seed_fallback_rates
                _seed_fallback_rates(db)
                logger.info("FX bootstrap complete: fallback rates seeded")
            else:
                logger.info("FX daily rate data present (%d records) — skipping bootstrap", fx_count)
        except Exception as exc:
            logger.warning("FX Analytics bootstrap failed (non-fatal): %s", exc)

        # ── Corridor bootstrap ───────────────────────────────────────
        try:
            from src.engines.corridor_engine import seed_corridors
            seeded = seed_corridors(db)
            if seeded > 0:
                logger.info("Corridor bootstrap complete: %d corridors seeded", seeded)
            else:
                logger.info("Corridor data present — skipping bootstrap")
        except Exception as exc:
            logger.warning("Corridor bootstrap failed (non-fatal): %s", exc)

        # ── Data integrity bootstrap ─────────────────────────────────
        try:
            from src.engines.reconciliation_engine import seed_source_health
            seed_source_health(db)
        except Exception as exc:
            logger.warning("Integrity bootstrap failed (non-fatal): %s", exc)

    finally:
        db.close()

    # Start background scheduler for periodic composite recalculation + news sweep
    start_scheduler()

    logger.info("Application startup complete. Docs: http://localhost:8000/docs")
    yield

    # Shutdown
    stop_scheduler()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="WASI Backend API",
    description=(
        "West African Shipping & Economic Intelligence Platform. "
        "Provides composite shipping indices, country-level analytics, "
        "and x402 credit-based access control."
    ),
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        response.headers["Cache-Control"] = "no-store"
        return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GlobalErrorHandlerMiddleware)
app.add_middleware(RequestIdMiddleware)

# Register all routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(indices_router)
app.include_router(country_router)
app.include_router(composite_router)
app.include_router(payment_router)
app.include_router(analytics_router)
app.include_router(signals_router)
app.include_router(reports_router)
app.include_router(wallet_router)
app.include_router(chat_router)
app.include_router(trade_router)
app.include_router(markets_router)
app.include_router(transport_router)
app.include_router(bank_router)
app.include_router(live_signals_router)
app.include_router(ml_router)
app.include_router(data_admin_router)
app.include_router(ussd_router)
app.include_router(cbdc_wallet_router)
app.include_router(cbdc_transaction_router)
app.include_router(cbdc_admin_router)
app.include_router(cbdc_monetary_policy_router)
app.include_router(cbdc_payments_router)
app.include_router(forecast_router)
app.include_router(tokenization_router)
app.include_router(risk_router)
app.include_router(legislative_router)
app.include_router(valuation_router)
app.include_router(fx_router)
app.include_router(corridor_router)
app.include_router(alerts_router)
app.include_router(reconciliation_router)
app.include_router(world_news_router)
app.include_router(forecast_v4_router)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "WASI Backend API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.DEBUG,
    )
