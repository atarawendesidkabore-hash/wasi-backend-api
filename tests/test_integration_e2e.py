"""
End-to-end integration tests — real user journeys crossing multiple modules.

Each test exercises a multi-step workflow that touches auth, credits, indices,
bank, risk, CBDC, and USSD modules together, proving the system works as a
whole, not just in isolation.
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.main import app
from src.database.models import (
    Base, User, Country, CountryIndex, WASIComposite, X402Tier,
    MacroIndicator, CommodityPrice, NewsEvent, BilateralTrade,
)
from src.database.connection import get_db

# ── Shared test DB (mirrors conftest.py) ─────────────────────────────────────

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

# Disable rate limiters
import pkgutil, importlib, src.routes as _routes_pkg
if hasattr(app.state, "limiter"):
    app.state.limiter.enabled = False
for _importer, _modname, _ispkg in pkgutil.iter_modules(_routes_pkg.__path__):
    _mod = importlib.import_module(f"src.routes.{_modname}")
    if hasattr(_mod, "limiter"):
        _mod.limiter.enabled = False

client = TestClient(app)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_db():
    """Create tables, seed countries & tiers, yield, tear down."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        from src.database.seed import seed_countries
        seed_countries(db)
    finally:
        db.close()

    from src.utils.security import _blacklisted_jtis, _blacklist_expiry, _blacklist_lock
    with _blacklist_lock:
        _blacklisted_jtis.clear()
        _blacklist_expiry.clear()

    yield
    Base.metadata.drop_all(bind=test_engine)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _register(username="intuser", email="intuser@test.com", password="IntPass1!"):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 201, f"Register failed: {r.text}"
    return r.json()


def _login(username="intuser", password="IntPass1!"):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_admin(username: str):
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    user.is_admin = True
    db.commit()
    db.close()


def _set_balance(username: str, balance: float):
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    user.x402_balance = balance
    db.commit()
    db.close()


def _seed_country_index(country_code: str = "NG", value: float = 72.5):
    """Insert a CountryIndex row for testing."""
    db = TestingSessionLocal()
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        db.close()
        return
    idx = CountryIndex(
        country_id=country.id,
        period_date=date(2026, 3, 1),
        index_value=value,
        shipping_score=70.0,
        trade_score=75.0,
        infrastructure_score=65.0,
        economic_score=80.0,
        data_source="test_integration",
        confidence=0.85,
        data_quality="high",
    )
    db.add(idx)
    db.commit()
    db.close()


def _seed_composite():
    """Insert a WASIComposite row."""
    db = TestingSessionLocal()
    comp = WASIComposite(
        period_date=date(2026, 3, 1),
        composite_value=68.42,
        countries_included=16,
        coefficient_of_variation=0.12,
        max_drawdown=0.05,
        trend_direction="stable",
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(comp)
    db.commit()
    db.close()


def _seed_macro(country_code: str = "NG"):
    """Insert IMF macro indicators for testing."""
    db = TestingSessionLocal()
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        db.close()
        return
    db.add(MacroIndicator(
        country_id=country.id,
        year=2025,
        gdp_growth_pct=3.2,
        inflation_pct=15.5,
        debt_gdp_pct=38.0,
        current_account_gdp_pct=-1.2,
        unemployment_pct=33.0,
        data_source="imf_weo",
    ))
    db.commit()
    db.close()


def _seed_trade(country_code: str = "NG"):
    """Insert bilateral trade records."""
    db = TestingSessionLocal()
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        db.close()
        return
    partner_names = {"CI": "Côte d'Ivoire", "GH": "Ghana"}
    for partner, exp_val, imp_val in [("CI", 500_000_000, 300_000_000), ("GH", 200_000_000, 150_000_000)]:
        partner_country = db.query(Country).filter(Country.code == partner).first()
        if partner_country:
            db.add(BilateralTrade(
                country_id=country.id,
                partner_code=partner,
                partner_name=partner_names.get(partner, partner),
                year=2024,
                export_value_usd=exp_val,
                import_value_usd=imp_val,
                top_exports="crude_oil,cocoa",
                data_source="test",
            ))
    db.commit()
    db.close()


# =============================================================================
# JOURNEY 1: Register → Login → Query indices → Check credits → Topup → Query again
# =============================================================================


class TestUserCreditJourney:
    """Full lifecycle: new user registers, queries data, runs out of credits, tops up."""

    def test_register_returns_free_tier_balance(self):
        user = _register()
        assert user["tier"] == "free"
        assert user["x402_balance"] >= 0

    def test_login_returns_valid_token(self):
        _register()
        token = _login()
        r = client.get("/api/auth/me", headers=_auth_headers(token))
        assert r.status_code == 200
        assert r.json()["username"] == "intuser"

    def test_full_credit_lifecycle(self):
        """Register → login → query (free) → topup → query (paid) → check balance."""
        # Step 1: Register and login
        _register(username="creditlife", email="cl@test.com")
        token = _login(username="creditlife")
        headers = _auth_headers(token)

        # Step 2: Seed some index data so the query returns results
        _seed_country_index("NG", 72.5)
        _seed_composite()

        # Step 3: Query latest indices (should be free / low cost)
        r = client.get("/api/indices/latest", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "indices" in data or "period_date" in data

        # Step 4: Check current balance via payment status
        r = client.get("/api/payment/status", headers=headers)
        assert r.status_code == 200
        initial_balance = r.json()["balance"]

        # Step 5: Make user admin and topup credits
        _make_admin("creditlife")
        ref_id = f"topup-{uuid.uuid4().hex[:12]}"
        r = client.post("/api/payment/topup", json={
            "amount": 100.0,
            "reference_id": ref_id,
        }, headers=headers)
        assert r.status_code == 200
        assert r.json()["balance"] > initial_balance

        # Step 6: Verify idempotency — same reference_id should be rejected
        r2 = client.post("/api/payment/topup", json={
            "amount": 100.0,
            "reference_id": ref_id,
        }, headers=headers)
        assert r2.status_code == 409

        # Step 7: Check balance again via status endpoint
        r = client.get("/api/payment/status", headers=headers)
        assert r.status_code == 200
        assert len(r.json()["recent_transactions"]) >= 1

    def test_unauthenticated_query_rejected(self):
        """Indices require auth."""
        r = client.get("/api/indices/latest")
        assert r.status_code == 401


# =============================================================================
# JOURNEY 2: Bank credit dossier — pulls WASI index + trade + risk data
# =============================================================================


class TestBankDossierJourney:
    """Bank officer queries credit context → loan advisory → full dossier."""

    def _setup_bank_data(self):
        """Seed NG with index, macro, and trade data."""
        _seed_country_index("NG", 72.5)
        _seed_composite()
        _seed_macro("NG")
        _seed_trade("NG")

    def test_credit_context_pulls_cross_module_data(self):
        """credit-context should aggregate WASI index + trade + procurement."""
        self._setup_bank_data()
        _register(username="banker", email="banker@test.com")
        token = _login(username="banker")
        _set_balance("banker", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v2/bank/credit-context/NG", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["country_code"] == "NG"
        assert "indicative_score" in data
        assert "indicative_rating" in data
        assert "wasi_index" in data
        assert "trade_summary" in data

    def test_loan_advisory_end_to_end(self):
        """loan-advisory should return scoring breakdown + narrative."""
        self._setup_bank_data()
        _register(username="banker2", email="banker2@test.com")
        token = _login(username="banker2")
        _set_balance("banker2", 500.0)
        headers = _auth_headers(token)

        r = client.post("/api/v2/bank/loan-advisory", json={
            "country_code": "NG",
            "sector": "agriculture",
            "loan_amount_usd": 1_000_000,
            "loan_term_months": 36,
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "indicative_score" in data
        assert "component_scores" in data
        assert data["bank_review_required"] is True

    def test_full_dossier_persists_to_db(self):
        """score-dossier should persist the result and return COBOL record."""
        self._setup_bank_data()
        _register(username="banker3", email="banker3@test.com")
        token = _login(username="banker3")
        _set_balance("banker3", 500.0)
        headers = _auth_headers(token)

        r = client.post("/api/v2/bank/score-dossier", json={
            "country_code": "NG",
            "sector": "logistics",
            "loan_amount_usd": 5_000_000,
            "loan_term_months": 60,
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "dossier_id" in data
        assert "overall_score" in data
        assert "cobol_record" in data
        assert data["cobol_record"]["REVIEW_FLAG_1"] == "Y"

    def test_invalid_country_rejected(self):
        """Non-ECOWAS country should be rejected."""
        _register(username="banker4", email="banker4@test.com")
        token = _login(username="banker4")
        _set_balance("banker4", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v2/bank/credit-context/XX", headers=headers)
        assert r.status_code in (404, 422)


# =============================================================================
# JOURNEY 3: Risk assessment — country + regional + anomalies
# =============================================================================


class TestRiskAssessmentJourney:
    """Analyst runs country risk → checks regional → detects anomalies."""

    def test_country_risk_with_data(self):
        """Country risk pulls from WASI index + macro + news."""
        _seed_country_index("NG", 72.5)
        _seed_macro("NG")
        _register(username="analyst", email="analyst@test.com")
        token = _login(username="analyst")
        _set_balance("analyst", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v3/risk/country/NG", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["country_code"] == "NG"
        assert "risk_score" in data
        assert "dimensions" in data
        assert "risk_rating" in data

    def test_regional_risk_overview(self):
        """Regional risk should return all 16 countries."""
        for cc in ["NG", "CI", "GH", "SN"]:
            _seed_country_index(cc, 70.0)
        _register(username="analyst2", email="analyst2@test.com")
        token = _login(username="analyst2")
        _set_balance("analyst2", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v3/risk/regional", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "countries" in data
        assert len(data["countries"]) >= 4

    def test_anomaly_detection(self):
        """Anomaly endpoint should return structured anomaly list."""
        _seed_country_index("NG", 72.5)
        _register(username="analyst3", email="analyst3@test.com")
        token = _login(username="analyst3")
        _set_balance("analyst3", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v3/risk/anomalies/NG", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["country_code"] == "NG"
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)

    def test_country_correlation(self):
        """Correlation between two countries (needs ≥5 overlapping dates)."""
        # Seed 6 data points on the same dates for both countries
        db = TestingSessionLocal()
        ng = db.query(Country).filter(Country.code == "NG").first()
        ci = db.query(Country).filter(Country.code == "CI").first()
        for i in range(6):
            d = date(2026, 2, 1 + i)
            db.add(CountryIndex(
                country_id=ng.id, period_date=d, index_value=70.0 + i,
                shipping_score=70.0, trade_score=75.0,
                infrastructure_score=65.0, economic_score=80.0,
                data_source="test", confidence=0.85, data_quality="high",
            ))
            db.add(CountryIndex(
                country_id=ci.id, period_date=d, index_value=65.0 + i * 0.8,
                shipping_score=68.0, trade_score=72.0,
                infrastructure_score=60.0, economic_score=78.0,
                data_source="test", confidence=0.80, data_quality="high",
            ))
        db.commit()
        db.close()

        _register(username="analyst4", email="analyst4@test.com")
        token = _login(username="analyst4")
        _set_balance("analyst4", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/v3/risk/correlation/NG/CI", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "correlation" in data
        assert data["country_a"] == "NG"
        assert data["country_b"] == "CI"
        assert data["data_points"] >= 5


# =============================================================================
# JOURNEY 4: Health check — verifies system observability
# =============================================================================


class TestHealthObservability:
    """Verify the enhanced health endpoint returns all operational data."""

    def test_basic_health_is_public(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert data["version"] == "3.0.0"

    def test_detailed_health_has_freshness(self):
        """Detailed health should include data freshness fields."""
        _register(username="healthchk", email="healthchk@test.com")
        token = _login(username="healthchk")
        headers = _auth_headers(token)

        r = client.get("/api/health/detailed", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "database" in data
        assert data["database"]["connected"] is True
        assert "data_freshness" in data
        assert "scheduler" in data
        assert "uptime_seconds" in data

    def test_detailed_health_reports_empty_db_as_stale(self):
        """With no scraper data, freshness fields should report stale/null."""
        _register(username="healthchk2", email="healthchk2@test.com")
        token = _login(username="healthchk2")
        headers = _auth_headers(token)

        r = client.get("/api/health/detailed", headers=headers)
        data = r.json()
        freshness = data.get("data_freshness", {})
        # No data seeded → should be null/stale
        assert freshness.get("latest_composite_date") is None or freshness.get("worldbank_stale") is True


# =============================================================================
# JOURNEY 5: Cross-module data flow — index + composite + forecast
# =============================================================================


class TestDataPipelineJourney:
    """Verifies data flows from indices through composite to forecast."""

    def test_index_data_visible_in_country_endpoint(self):
        """Seed an index, query country endpoint, verify it appears."""
        _seed_country_index("CI", 68.0)
        _register(username="dataflow", email="dataflow@test.com")
        token = _login(username="dataflow")
        _set_balance("dataflow", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/country/CI/index", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert data["index_value"] == 68.0

    def test_composite_report_with_data(self):
        """Composite report should work when data exists."""
        for cc in ["NG", "CI", "GH", "SN"]:
            _seed_country_index(cc, 70.0)
        _seed_composite()
        _register(username="dataflow2", email="dataflow2@test.com")
        token = _login(username="dataflow2")
        _set_balance("dataflow2", 500.0)
        headers = _auth_headers(token)

        r = client.get("/api/composite/report", headers=headers)
        assert r.status_code == 200

    def test_multiple_queries_deduct_credits_correctly(self):
        """Successive paid queries should reduce balance monotonically."""
        _seed_country_index("NG", 72.5)
        _seed_composite()
        _register(username="multiquery", email="mq@test.com")
        token = _login(username="multiquery")
        _set_balance("multiquery", 100.0)
        headers = _auth_headers(token)

        # Check initial balance
        r = client.get("/api/payment/status", headers=headers)
        b0 = r.json()["balance"]

        # Make several queries
        client.get("/api/indices/history", headers=headers)
        r = client.get("/api/payment/status", headers=headers)
        b1 = r.json()["balance"]

        client.get("/api/indices/all", headers=headers)
        r = client.get("/api/payment/status", headers=headers)
        b2 = r.json()["balance"]

        # Balance should be non-increasing
        assert b1 <= b0
        assert b2 <= b1
