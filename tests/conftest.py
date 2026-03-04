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

# Disable ALL rate limiters during tests (auto-discovered)
import pkgutil
import importlib
import src.routes as _routes_pkg

if hasattr(app.state, "limiter"):
    app.state.limiter.enabled = False
for _importer, _modname, _ispkg in pkgutil.iter_modules(_routes_pkg.__path__):
    _mod = importlib.import_module(f"src.routes.{_modname}")
    if hasattr(_mod, "limiter"):
        _mod.limiter.enabled = False


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
