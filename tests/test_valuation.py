"""
WASI DCF Valuation — Integration Tests

Tests the 12-step DCF valuation engine, target CRUD, financial statement
submission, scenario analysis, and sensitivity table generation.
"""
import pytest
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import Base, Country, CountryIndex, MacroIndicator
from src.engines.valuation_engine import ValuationEngine
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=True)


# ── Helpers ──────────────────────────────────────────────────────

def _register_and_login(username="val_user", email="val@test.com", password="ValPass123"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_target(token, **overrides):
    payload = {
        "entity_type": "COMPANY",
        "name": "Dangote Cement",
        "ticker": "DANGCEM.NGX",
        "exchange_code": "NGX",
        "country_code": "NG",
        "sector": "manufacturing",
        "currency": "NGN",
        "shares_outstanding": 17_040_507_405,
        "current_share_price": 290.0,
        "net_debt_usd": 2_500_000_000,
    }
    payload.update(overrides)
    resp = client.post("/api/v3/valuation/targets", json=payload, headers=_auth(token))
    return resp


def _submit_financials(token, target_id, year, revenue, ebit=None, **kw):
    payload = {
        "fiscal_year": year,
        "statement_type": "ACTUAL",
        "revenue_usd": revenue,
        "ebit_usd": ebit or revenue * 0.20,
        "ebitda_usd": (ebit or revenue * 0.20) + revenue * 0.05,
        "depreciation_amortization_usd": revenue * 0.05,
        "tax_rate_pct": 30.0,
        "capex_usd": revenue * 0.08,
        "change_in_nwc_usd": revenue * 0.02,
        "total_debt_usd": 3_000_000_000,
        "cash_equivalents_usd": 500_000_000,
    }
    payload.update(kw)
    return client.post(
        f"/api/v3/valuation/targets/{target_id}/financials",
        json=payload, headers=_auth(token),
    )


def _seed_macro(db, country_code="NG"):
    country = db.query(Country).filter(Country.code == country_code).first()
    if not country:
        return
    for yr in [2022, 2023, 2024]:
        db.add(MacroIndicator(
            country_id=country.id,
            year=yr,
            gdp_growth_pct=3.5 + (yr - 2022) * 0.3,
            inflation_pct=18.0 - (yr - 2022) * 2.0,
            debt_gdp_pct=38.0 + (yr - 2022),
            current_account_gdp_pct=-1.5,
            gdp_usd_billions=450.0 + (yr - 2022) * 20.0,
            data_source="test_seed",
            is_projection=False,
            confidence=0.85,
        ))
    db.commit()


# ── Target CRUD Tests ────────────────────────────────────────────

def test_create_company_target():
    token = _register_and_login("crud1", "crud1@t.com", "Pass1234")
    resp = _create_target(token)
    assert resp.status_code == 201
    data = resp.json()
    assert data["entity_type"] == "COMPANY"
    assert data["name"] == "Dangote Cement"
    assert data["country_code"] == "NG"
    assert data["shares_outstanding"] == 17_040_507_405


def test_create_country_target():
    token = _register_and_login("crud2", "crud2@t.com", "Pass1234")
    resp = _create_target(
        token, entity_type="COUNTRY", name="Nigeria Economy",
        ticker=None, exchange_code=None, shares_outstanding=None,
        current_share_price=None, net_debt_usd=None,
    )
    assert resp.status_code == 201
    assert resp.json()["entity_type"] == "COUNTRY"


def test_create_infrastructure_target():
    token = _register_and_login("crud3", "crud3@t.com", "Pass1234")
    resp = _create_target(
        token, entity_type="INFRASTRUCTURE", name="Lagos-Abidjan Highway",
        ticker=None, exchange_code=None, shares_outstanding=None,
        current_share_price=None, net_debt_usd=1_200_000_000,
        total_project_cost_usd=3_500_000_000,
        project_start_date="2024-01-01", project_end_date="2028-12-31",
    )
    assert resp.status_code == 201
    assert resp.json()["entity_type"] == "INFRASTRUCTURE"


def test_list_targets():
    token = _register_and_login("crud4", "crud4@t.com", "Pass1234")
    _create_target(token, name="Target A")
    _create_target(token, name="Target B")
    resp = client.get("/api/v3/valuation/targets", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_get_target():
    token = _register_and_login("crud5", "crud5@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    resp = client.get(f"/api/v3/valuation/targets/{tid}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["target_id"] == tid


def test_update_target():
    token = _register_and_login("crud6", "crud6@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    resp = client.put(
        f"/api/v3/valuation/targets/{tid}",
        json={"current_share_price": 310.0},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["current_share_price"] == 310.0


def test_delete_target():
    token = _register_and_login("crud7", "crud7@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    resp = client.delete(f"/api/v3/valuation/targets/{tid}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    # Verify it no longer shows in list
    resp = client.get("/api/v3/valuation/targets", headers=_auth(token))
    assert resp.json()["total"] == 0


# ── Financial Statement Tests ────────────────────────────────────

def test_submit_financials():
    token = _register_and_login("fin1", "fin1@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    resp = _submit_financials(token, tid, 2023, 5_000_000_000)
    assert resp.status_code == 201
    assert resp.json()["fiscal_year"] == 2023


def test_get_financials():
    token = _register_and_login("fin2", "fin2@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)
    _submit_financials(token, tid, 2024, 6_000_000_000)
    resp = client.get(f"/api/v3/valuation/targets/{tid}/financials", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_upsert_financials():
    token = _register_and_login("fin3", "fin3@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2023, 5_000_000_000)
    resp = _submit_financials(token, tid, 2023, 5_500_000_000)
    assert resp.status_code == 201
    assert resp.json()["revenue_usd"] == 5_500_000_000


# ── DCF Valuation Tests ─────────────────────────────────────────

def test_run_dcf_company():
    token = _register_and_login("dcf1", "dcf1@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)
    _submit_financials(token, tid, 2024, 6_000_000_000)

    resp = client.post(
        "/api/v3/valuation/run",
        json={"target_id": tid, "projection_years": 5, "include_sensitivity": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:1000]}"
    data = resp.json()

    # Verify all 12 steps are reflected
    assert data["entity_type"] == "COMPANY"
    assert len(data["scenarios"]) == 3
    assert data["blended"]["scenario"] == "BLENDED"
    assert data["blended"]["enterprise_value_usd"] > 0
    assert data["blended"]["equity_value_usd"] > 0
    assert data["narrative"]
    assert data["analyst_review_required"] is True

    # Verify projections exist (Steps 2-6)
    base = data["scenarios"][1]  # BASE is second
    assert base["scenario"] == "BASE"
    assert len(base["projections"]) == 5
    assert base["projections"][0]["pv_fcf_usd"] > 0

    # Verify terminal value (Steps 7-8)
    assert base["terminal_value"]["gordon_tv_usd"] > 0
    assert base["terminal_value"]["exit_tv_usd"] > 0

    # Verify sensitivity table
    assert data["sensitivity_table"] is not None
    assert len(data["sensitivity_table"]) > 0


def test_run_dcf_insufficient_data():
    token = _register_and_login("dcf2", "dcf2@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2024, 6_000_000_000)

    resp = client.post(
        "/api/v3/valuation/run",
        json={"target_id": tid},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_scenario_analysis():
    token = _register_and_login("dcf3", "dcf3@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)

    resp = client.post(
        "/api/v3/valuation/run",
        json={
            "target_id": tid,
            "scenario_weights": {"BULL": 0.20, "BASE": 0.60, "BEAR": 0.20},
            "include_sensitivity": False,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()

    # BULL EV > BASE EV > BEAR EV
    bull = next(s for s in data["scenarios"] if s["scenario"] == "BULL")
    base = next(s for s in data["scenarios"] if s["scenario"] == "BASE")
    bear = next(s for s in data["scenarios"] if s["scenario"] == "BEAR")
    assert bull["enterprise_value_usd"] > base["enterprise_value_usd"]
    assert base["enterprise_value_usd"] > bear["enterprise_value_usd"]


def test_run_country_dcf():
    token = _register_and_login("dcf4", "dcf4@t.com", "Pass1234")
    db = TestingSessionLocal()
    try:
        _seed_macro(db, "NG")
    finally:
        db.close()

    resp = client.post(
        "/api/v3/valuation/country/NG",
        json={"projection_years": 5, "include_sensitivity": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_type"] == "COUNTRY"
    assert data["country_code"] == "NG"
    assert data["blended"]["enterprise_value_usd"] > 0


def test_get_result():
    token = _register_and_login("dcf5", "dcf5@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)

    run_resp = client.post(
        "/api/v3/valuation/run",
        json={"target_id": tid, "include_sensitivity": False},
        headers=_auth(token),
    )
    result_id = run_resp.json()["result_id"]

    resp = client.get(f"/api/v3/valuation/results/{result_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["result_id"] == result_id


def test_get_target_results():
    token = _register_and_login("dcf6", "dcf6@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)

    client.post(
        "/api/v3/valuation/run",
        json={"target_id": tid, "include_sensitivity": False},
        headers=_auth(token),
    )

    resp = client.get(f"/api/v3/valuation/targets/{tid}/results", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] > 0


def test_sensitivity_endpoint():
    token = _register_and_login("dcf7", "dcf7@t.com", "Pass1234")
    tid = _create_target(token).json()["target_id"]
    _submit_financials(token, tid, 2022, 4_000_000_000)
    _submit_financials(token, tid, 2023, 5_000_000_000)

    run_resp = client.post(
        "/api/v3/valuation/run",
        json={"target_id": tid, "include_sensitivity": True},
        headers=_auth(token),
    )
    result_id = run_resp.json()["result_id"]

    resp = client.get(f"/api/v3/valuation/sensitivity/{result_id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total_cells"] > 0


def test_unauthorized_target_access():
    token_a = _register_and_login("authA", "authA@t.com", "Pass1234")
    token_b = _register_and_login("authB", "authB@t.com", "Pass1234")

    tid = _create_target(token_a).json()["target_id"]

    resp = client.get(f"/api/v3/valuation/targets/{tid}", headers=_auth(token_b))
    assert resp.status_code == 404


# ── Engine Unit Tests (Pure Math) ────────────────────────────────

class TestValuationEngine:
    engine = ValuationEngine()

    def test_wacc_calculation(self):
        result = self.engine.calculate_wacc("NG", political_risk=6.5, wasi_index=50.0)
        assert 5.0 < result["wacc_pct"] < 25.0
        assert result["beta"] == 1.30
        assert result["risk_free_rate_pct"] == 4.05
        assert result["equity_risk_premium_pct"] == 4.25

    def test_wacc_custom_overrides(self):
        result = self.engine.calculate_wacc(
            "NG", custom_beta=1.0, custom_eq_ratio=0.60, custom_tax_rate=0.25,
        )
        assert result["beta"] == 1.0
        assert result["equity_ratio_pct"] == 60.0
        assert result["corporate_tax_rate_pct"] == 25.0

    def test_project_fcfs(self):
        fcfs = self.engine.project_free_cash_flows(
            base_revenue=1_000_000,
            base_ebit_margin=0.20,
            base_da_pct=0.05,
            base_capex_pct=0.08,
            base_nwc_change_pct=0.02,
            tax_rate=0.25,
            revenue_growth_rates=[0.10, 0.08, 0.06, 0.05, 0.04],
            projection_years=5,
        )
        assert len(fcfs) == 5
        assert fcfs[0]["revenue_usd"] == pytest.approx(1_100_000, rel=0.01)
        assert fcfs[0]["fcf_usd"] > 0
        # Revenue should grow each year
        for i in range(1, 5):
            assert fcfs[i]["revenue_usd"] > fcfs[i - 1]["revenue_usd"]

    def test_discount_mid_year_convention(self):
        fcfs = [{"year": 1, "fcf_usd": 100_000}]
        discounted = self.engine.discount_fcfs(fcfs, wacc=0.10, mid_year=True)
        # Mid-year: 1/(1.10)^0.5 ≈ 0.9535
        assert discounted[0]["discount_factor"] == pytest.approx(0.9535, rel=0.01)
        # Year-end would be 1/(1.10)^1.0 ≈ 0.9091
        fcfs2 = [{"year": 1, "fcf_usd": 100_000}]
        discounted2 = self.engine.discount_fcfs(fcfs2, wacc=0.10, mid_year=False)
        assert discounted2[0]["discount_factor"] == pytest.approx(0.9091, rel=0.01)

    def test_terminal_value_gordon(self):
        tv = self.engine.calculate_terminal_value(
            last_year_fcf=100_000,
            last_year_ebitda=150_000,
            wacc=0.10,
            terminal_growth=0.03,
            exit_multiple=10.0,
            projection_years=5,
        )
        # Gordon: 100k * 1.03 / (0.10 - 0.03) = 1,471,428.57
        assert tv["gordon_tv_usd"] == pytest.approx(1_471_428.57, rel=0.01)
        # Exit: 150k * 10 = 1,500,000
        assert tv["exit_tv_usd"] == pytest.approx(1_500_000, rel=0.01)

    def test_gordon_guard_tg_exceeds_wacc(self):
        tv = self.engine.calculate_terminal_value(
            last_year_fcf=100_000,
            last_year_ebitda=150_000,
            wacc=0.05,
            terminal_growth=0.06,  # tg > wacc
            projection_years=5,
        )
        # Should cap tg at wacc - 1%
        assert tv["terminal_growth_pct"] == pytest.approx(4.0, rel=0.01)

    def test_equity_value_with_shares(self):
        result = self.engine.calculate_equity_value(
            pv_fcfs_total=500_000_000,
            pv_terminal_gordon=1_000_000_000,
            pv_terminal_exit=1_200_000_000,
            net_debt=300_000_000,
            shares_outstanding=100_000_000,
            gordon_weight=0.50,
            current_share_price=10.0,
        )
        # Blended PV terminal = 0.5 * 1B + 0.5 * 1.2B = 1.1B
        # EV = 500M + 1.1B = 1.6B
        # Equity = 1.6B - 300M = 1.3B
        # Price = 1.3B / 100M = 13.0
        assert result["enterprise_value_usd"] == pytest.approx(1_600_000_000, rel=0.01)
        assert result["equity_value_usd"] == pytest.approx(1_300_000_000, rel=0.01)
        assert result["implied_share_price"] == pytest.approx(13.0, rel=0.01)
        assert result["upside_pct"] == pytest.approx(30.0, rel=0.01)

    def test_full_dcf_pipeline(self):
        wacc = self.engine.calculate_wacc("CI")
        financials = {
            "base_revenue": 500_000_000,
            "base_ebit_margin": 0.18,
            "base_da_pct": 0.04,
            "base_capex_pct": 0.07,
            "base_nwc_change_pct": 0.015,
            "tax_rate": 0.25,
            "revenue_growth_rates": [0.12, 0.10, 0.08, 0.06, 0.05],
            "net_debt": 100_000_000,
            "shares_outstanding": 50_000_000,
            "current_share_price": 15.0,
        }
        result = self.engine.run_dcf(financials=financials, wacc_params=wacc)
        assert result["scenario"] == "BASE"
        assert result["enterprise_value_usd"] > 0
        assert result["equity_value_usd"] > 0
        assert result["implied_share_price"] is not None
        assert len(result["projections"]) == 5

    def test_scenario_bull_gt_base_gt_bear(self):
        wacc = self.engine.calculate_wacc("GH")
        financials = {
            "base_revenue": 200_000_000,
            "base_ebit_margin": 0.15,
            "base_da_pct": 0.05,
            "base_capex_pct": 0.08,
            "base_nwc_change_pct": 0.02,
            "tax_rate": 0.25,
            "revenue_growth_rates": [0.10, 0.08, 0.06, 0.05, 0.04],
            "net_debt": 50_000_000,
            "shares_outstanding": 20_000_000,
            "current_share_price": 8.0,
        }
        result = self.engine.run_scenario_analysis(financials=financials, wacc_params=wacc)
        assert result["scenarios"]["BULL"]["enterprise_value_usd"] > result["scenarios"]["BASE"]["enterprise_value_usd"]
        assert result["scenarios"]["BASE"]["enterprise_value_usd"] > result["scenarios"]["BEAR"]["enterprise_value_usd"]
        assert result["blended"]["scenario"] == "BLENDED"

    def test_country_financials_adapter(self):
        macro = [
            {"year": 2022, "gdp_usd_billions": 400, "gdp_growth_pct": 3.0, "inflation_pct": 15.0, "debt_gdp_pct": 35, "is_projection": False},
            {"year": 2023, "gdp_usd_billions": 420, "gdp_growth_pct": 3.5, "inflation_pct": 14.0, "debt_gdp_pct": 37, "is_projection": False},
            {"year": 2024, "gdp_usd_billions": 450, "gdp_growth_pct": 4.0, "inflation_pct": 12.0, "debt_gdp_pct": 38, "is_projection": False},
        ]
        result = self.engine.prepare_country_financials(macro)
        assert result["base_revenue"] == pytest.approx(450_000_000_000, rel=0.01)
        assert len(result["revenue_growth_rates"]) == 5
        assert result["revenue_growth_rates"][0] > 0
