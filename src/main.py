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
from src.middleware.x402_payment_verification import RequestLoggingMiddleware
from src.middleware.request_id import RequestIdMiddleware
from src.middleware.error_handler import GlobalErrorHandlerMiddleware
from src.bootstrap import run_bootstrap
from src.tasks.composite_update import start_scheduler, stop_scheduler
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
from src.routes.engagement import router as engagement_router
from src.routes.royalty import router as royalty_router
from src.routes.intelligence import router as intelligence_router
from src.routes.microloan import router as microloan_router
from src.routes.sovereign import router as sovereign_router
from src.routes.v1_guardrails import router as v1_guardrails_router

from src.utils.logging_config import setup_logging
setup_logging(debug=settings.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WASI Backend API...")
    init_db()

    if settings.LIGHT_STARTUP:
        logger.info("LIGHT_STARTUP=True — skipping all seeding/bootstrap for fast startup")
    else:
        import asyncio
        def _sync_bootstrap():
            db = SessionLocal()
            try:
                run_bootstrap(db)
            finally:
                db.close()
        await asyncio.to_thread(_sync_bootstrap)

    start_scheduler()
    logger.info("Application startup complete. Docs: http://localhost:8000/docs")
    yield

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
    # Read-only GET prefixes whose data updates at most every few minutes
    _CACHEABLE_PREFIXES = (
        "/api/indices/", "/api/country/", "/api/composite/report",
        "/api/v2/transport/", "/api/v2/data/commodities/latest",
        "/api/v2/data/macro/", "/api/v2/data/status",
        "/api/v3/forecast/", "/api/v4/forecast/",
        "/api/health",
    )

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        # Smart caching: read-only data endpoints are cacheable, everything else is no-store
        path = request.url.path
        if request.method == "GET" and any(path.startswith(p) for p in self._CACHEABLE_PREFIXES):
            response.headers["Cache-Control"] = "public, max-age=300"
        else:
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

# ── API Version Registry ──────────────────────────────────────────────────────
# /api/       — Core: auth, health, indices, composite, payments, analytics
#               Stable. No breaking changes planned.
# /api/v2/    — Extended: transport, bank, data, USSD, signals, markets
#               Stable. New endpoints may be added.
# /api/v3/    — Financial: eCFA CBDC, tokenization, forecast v1, legislative,
#               valuation, FX, corridors, alerts, reconciliation, world news
#               Stable. Active development.
# /api/v4/    — Advanced: forecast v2 (adaptive ensemble, backtesting, scenarios)
#               Experimental. May change without notice.
# ──────────────────────────────────────────────────────────────────────────────
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
app.include_router(engagement_router)
app.include_router(royalty_router)
app.include_router(intelligence_router)
app.include_router(microloan_router)
app.include_router(sovereign_router)
app.include_router(v1_guardrails_router)


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
