"""
Shared test fixtures for the WASI Backend API test suite.

Uses an in-memory SQLite database with StaticPool so all sessions share
the same connection. Rate limiters are disabled to avoid 429 errors.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.main import app
from src.database.models import Base
from src.database.connection import get_db
from src.database.seed import seed_countries

# ── Shared in-memory test database ───────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Disable all rate limiters during tests
if hasattr(app.state, "limiter"):
    app.state.limiter.enabled = False
from src.routes.auth import limiter as auth_limiter
from src.routes.bank import limiter as bank_limiter
from src.routes.cbdc_payments import limiter as cbdc_payments_limiter
from src.routes.valuation import limiter as valuation_limiter
from src.routes.fx import limiter as fx_limiter
from src.routes.corridor import limiter as corridor_limiter
auth_limiter.enabled = False
bank_limiter.enabled = False
cbdc_payments_limiter.enabled = False
valuation_limiter.enabled = False
fx_limiter.enabled = False
corridor_limiter.enabled = False
from src.routes.reconciliation import limiter as reconciliation_limiter
reconciliation_limiter.enabled = False
from src.routes.alerts import limiter as alerts_limiter
from src.routes.analytics import limiter as analytics_limiter
from src.routes.cbdc_monetary_policy import limiter as cbdc_monetary_policy_limiter
from src.routes.cbdc_transaction import limiter as cbdc_transaction_limiter
from src.routes.cbdc_wallet import limiter as cbdc_wallet_limiter
from src.routes.cbdc_admin import limiter as cbdc_admin_limiter
from src.routes.chat import limiter as chat_limiter
from src.routes.country import limiter as country_limiter
from src.routes.composite import limiter as composite_limiter
from src.routes.data_admin import limiter as data_admin_limiter
from src.routes.forecast import limiter as forecast_limiter
from src.routes.health import limiter as health_limiter
from src.routes.indices import limiter as indices_limiter
from src.routes.legislative import limiter as legislative_limiter
from src.routes.live_signals import limiter as live_signals_limiter
from src.routes.markets import limiter as markets_limiter
from src.routes.ml import limiter as ml_limiter
from src.routes.payment import limiter as payment_limiter
from src.routes.reports import limiter as reports_limiter
from src.routes.risk import limiter as risk_limiter
from src.routes.signals import limiter as signals_limiter
from src.routes.tokenization import limiter as tokenization_limiter
from src.routes.trade import limiter as trade_limiter
from src.routes.transport import limiter as transport_limiter
from src.routes.ussd import limiter as ussd_limiter
from src.routes.wallet import limiter as wallet_limiter
alerts_limiter.enabled = False
analytics_limiter.enabled = False
cbdc_monetary_policy_limiter.enabled = False
cbdc_transaction_limiter.enabled = False
cbdc_wallet_limiter.enabled = False
cbdc_admin_limiter.enabled = False
chat_limiter.enabled = False
country_limiter.enabled = False
composite_limiter.enabled = False
data_admin_limiter.enabled = False
forecast_limiter.enabled = False
health_limiter.enabled = False
indices_limiter.enabled = False
legislative_limiter.enabled = False
live_signals_limiter.enabled = False
markets_limiter.enabled = False
ml_limiter.enabled = False
payment_limiter.enabled = False
reports_limiter.enabled = False
risk_limiter.enabled = False
signals_limiter.enabled = False
tokenization_limiter.enabled = False
trade_limiter.enabled = False
transport_limiter.enabled = False
ussd_limiter.enabled = False
wallet_limiter.enabled = False
from src.routes.world_news import limiter as world_news_limiter
world_news_limiter.enabled = False
from src.routes.forecast_v4 import limiter as forecast_v4_limiter
forecast_v4_limiter.enabled = False


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables, seed countries, yield, then drop."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        seed_countries(db)
    finally:
        db.close()

    # Clear in-memory token blacklist between tests
    from src.utils.security import _blacklisted_jtis, _blacklist_expiry, _blacklist_lock
    with _blacklist_lock:
        _blacklisted_jtis.clear()
        _blacklist_expiry.clear()

    yield
    Base.metadata.drop_all(bind=test_engine)
