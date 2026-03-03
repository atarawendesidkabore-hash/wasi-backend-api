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
auth_limiter.enabled = False
bank_limiter.enabled = False
cbdc_payments_limiter.enabled = False
valuation_limiter.enabled = False


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables, seed countries, yield, then drop."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        seed_countries(db)
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)
