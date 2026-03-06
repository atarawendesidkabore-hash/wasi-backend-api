"""
WASI Backend API -- Sovereign Veto + Data Truth Integration Tests

Tests for /api/v1/sovereign/ and /api/v1/data-truth/ endpoints.
Also tests veto enforcement on /api/v2/bank/ credit endpoints.
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, Country, CountryIndex
from src.database.sovereign_models import SovereignVeto, DataTruthAudit
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


def _register_and_login(username="sovuser", email="sov@test.com", password="SovPass123"):
    client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _topup(token, amount=200.0):
    client.post("/api/payment/topup", json={"amount": amount, "reference_id": "sov-test"}, headers=_auth(token))


def _make_admin(username="sovuser"):
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    user.is_admin = True
    db.commit()
    db.close()


def test_sovereign_check_requires_auth():
    resp = client.get("/api/v1/sovereign/check/NG")
    assert resp.status_code == 401


def test_sovereign_check_no_veto():
    token = _register_and_login()
    _topup(token)
    resp = client.get("/api/v1/sovereign/check/NG", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["blocked"] is False
    assert data["vetoes"] == []


def test_sovereign_list_empty():
    token = _register_and_login("sov2", "sov2@t.com")
    _topup(token)
    resp = client.get("/api/v1/sovereign/list", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_issue_veto_requires_admin():
    token = _register_and_login("sov3", "sov3@t.com")
    _topup(token)
    resp = client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "ML", "veto_type": "SANCTIONS",
        "reason": "Test sanctions on Mali for coup",
        "issued_by": "BCEAO", "effective_date": str(date.today()),
    })
    assert resp.status_code == 403


def test_issue_and_check_full_block():
    token = _register_and_login("sov4", "sov4@t.com")
    _topup(token)
    _make_admin("sov4")
    resp = client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "ML", "veto_type": "POLITICAL_CRISIS",
        "reason": "Military coup - unconstitutional government change",
        "issued_by": "ECOWAS Council", "effective_date": str(date.today()),
        "severity": "FULL_BLOCK",
    })
    assert resp.status_code == 200
    veto_id = resp.json()["veto_id"]
    assert veto_id > 0

    # Now check should show blocked
    resp2 = client.get("/api/v1/sovereign/check/ML", headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["data"]["blocked"] is True

    # List should show 1 veto
    resp3 = client.get("/api/v1/sovereign/list?country_code=ML", headers=_auth(token))
    assert resp3.json()["count"] == 1


def test_veto_blocks_bank_score_dossier():
    token = _register_and_login("sov5", "sov5@t.com")
    _topup(token, 500)
    _make_admin("sov5")
    # Issue FULL_BLOCK on BF
    client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "BF", "veto_type": "POLITICAL_CRISIS",
        "reason": "Unconstitutional government change in Burkina Faso",
        "issued_by": "BCEAO", "effective_date": str(date.today()),
    })
    # Try score-dossier on BF -> should be 403
    resp = client.post("/api/v2/bank/score-dossier", headers=_auth(token), json={
        "country_code": "BF", "sector": "mining",
        "loan_amount_usd": 1000000, "loan_term_months": 24,
    })
    assert resp.status_code == 403
    assert "SOVEREIGN VETO" in resp.json()["detail"]


def test_veto_blocks_loan_advisory():
    token = _register_and_login("sov6", "sov6@t.com")
    _topup(token, 500)
    _make_admin("sov6")
    client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "NE", "veto_type": "SANCTIONS",
        "reason": "International sanctions on Niger Republic",
        "issued_by": "UN Security Council", "effective_date": str(date.today()),
    })
    resp = client.post("/api/v2/bank/loan-advisory", headers=_auth(token), json={
        "country_code": "NE", "sector": "agriculture",
        "loan_amount_usd": 500000, "loan_term_months": 12,
    })
    assert resp.status_code == 403


def test_revoke_veto_then_credit_works():
    token = _register_and_login("sov7", "sov7@t.com")
    _topup(token, 500)
    _make_admin("sov7")
    # Issue veto on TG
    r1 = client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "TG", "veto_type": "DEBT_CEILING",
        "reason": "Togo exceeds UEMOA 70pct debt-to-GDP ceiling",
        "issued_by": "BCEAO", "effective_date": str(date.today()),
    })
    vid = r1.json()["veto_id"]
    # Revoke it
    r2 = client.post("/api/v1/sovereign/revoke", headers=_auth(token), json={
        "veto_id": vid, "revoked_by": "BCEAO Governor",
    })
    assert r2.status_code == 200
    # Now check should be unblocked
    r3 = client.get("/api/v1/sovereign/check/TG", headers=_auth(token))
    assert r3.json()["data"]["blocked"] is False


def test_partial_veto_with_cap():
    token = _register_and_login("sov8", "sov8@t.com")
    _topup(token, 500)
    _make_admin("sov8")
    client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "GN", "veto_type": "MONETARY_POLICY",
        "reason": "BCEAO tightening - cap Guinea loans at 500K USD",
        "issued_by": "BCEAO", "effective_date": str(date.today()),
        "severity": "PARTIAL", "max_loan_cap_usd": 500000,
    })
    # Check with amount under cap -> not blocked
    r1 = client.get("/api/v1/sovereign/check/GN?loan_amount_usd=100000", headers=_auth(token))
    assert r1.json()["data"]["blocked"] is False
    assert r1.json()["data"]["partial"] is True
    # Check with amount over cap -> blocked
    r2 = client.get("/api/v1/sovereign/check/GN?loan_amount_usd=1000000", headers=_auth(token))
    assert r2.json()["data"]["blocked"] is True


# -- Data Truth Tests --

def test_data_truth_check_requires_auth():
    resp = client.get("/api/v1/data-truth/check/NG")
    assert resp.status_code == 401


def test_data_truth_check_ok():
    token = _register_and_login("dt1", "dt1@t.com")
    _topup(token)
    resp = client.get("/api/v1/data-truth/check/NG", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "checks" in data
    assert "adjusted_confidence" in data


def test_data_truth_unknown_country():
    token = _register_and_login("dt2", "dt2@t.com")
    _topup(token)
    resp = client.get("/api/v1/data-truth/check/XX", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["pass"] is False


def test_cross_source_audit():
    token = _register_and_login("dt3", "dt3@t.com")
    _topup(token)
    resp = client.post("/api/v1/data-truth/cross-source", headers=_auth(token), json={
        "country_code": "NG", "metric_name": "gdp_growth",
        "source_a": "world_bank", "source_b": "imf",
        "value_a": 3.2, "value_b": 3.5,
    })
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "AGREE"
    assert resp.json()["audit_id"] > 0


def test_cross_source_diverge():
    token = _register_and_login("dt4", "dt4@t.com")
    _topup(token)
    resp = client.post("/api/v1/data-truth/cross-source", headers=_auth(token), json={
        "country_code": "CI", "metric_name": "inflation",
        "source_a": "world_bank", "source_b": "bceao",
        "value_a": 5.0, "value_b": 12.0,
    })
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "DIVERGE"


def test_list_truth_audits():
    token = _register_and_login("dt5", "dt5@t.com")
    _topup(token)
    # Create an audit first
    client.post("/api/v1/data-truth/cross-source", headers=_auth(token), json={
        "country_code": "GH", "metric_name": "index_value",
        "source_a": "wasi", "source_b": "world_bank",
        "value_a": 65.0, "value_b": 64.0,
    })
    resp = client.get("/api/v1/data-truth/audits/GH", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


# -- Unit tests for engine functions --

from src.engines.data_truth_engine import check_cross_source, check_staleness, check_anomaly
from datetime import datetime, timezone


def test_g5_cross_source_agree():
    r = check_cross_source(100.0, 105.0, "a", "b")
    assert r["verdict"] == "AGREE"
    assert r["divergence_pct"] < 15.0


def test_g5_cross_source_diverge():
    r = check_cross_source(100.0, 200.0, "a", "b")
    assert r["verdict"] == "DIVERGE"
    assert r["confidence_penalty"] > 0


def test_g6_fresh_data():
    ts = datetime.now(timezone.utc)
    r = check_staleness(ts, "test")
    assert r["verdict"] == "FRESH"
    assert r["confidence_penalty"] == 0.0


def test_g6_stale_data():
    ts = datetime.now(timezone.utc) - timedelta(days=60)
    r = check_staleness(ts, "test")
    assert r["verdict"] == "STALE"


def test_g6_expired_data():
    ts = datetime.now(timezone.utc) - timedelta(days=120)
    r = check_staleness(ts, "test")
    assert r["verdict"] == "EXPIRED"
    assert r["confidence_penalty"] == 0.50


def test_g6_none_timestamp():
    r = check_staleness(None, "test")
    assert r["verdict"] == "EXPIRED"


def test_g7_normal():
    r = check_anomaly(50.0, [48, 49, 50, 51, 52], "idx")
    assert r["verdict"] == "NORMAL"


def test_g7_anomaly_reject():
    r = check_anomaly(100.0, [50, 50, 50, 50, 50], "idx")
    assert r["verdict"] == "ANOMALY_REJECT"
    assert r["confidence_penalty"] == 0.50


def test_g7_insufficient_data():
    r = check_anomaly(50.0, [48, 49], "idx")
    assert r["verdict"] == "INSUFFICIENT_DATA"


# -- Guardrails endpoint tests --

def test_guardrails_requires_auth():
    resp = client.get("/api/v1/sovereign/guardrails/NG")
    assert resp.status_code == 401


def test_guardrails_unknown_country():
    token = _register_and_login("gr1", "gr1@t.com")
    _topup(token, 500)
    resp = client.get("/api/v1/sovereign/guardrails/XX", headers=_auth(token))
    assert resp.status_code == 404


def test_guardrails_valid_response_structure():
    token = _register_and_login("gr2", "gr2@t.com")
    _topup(token, 500)
    # Seed a country so the endpoint does not 404
    db = TestingSessionLocal()
    from src.database.models import Country
    if not db.query(Country).filter(Country.code == "NG").first():
        db.add(Country(code="NG", name="Nigeria", region="West Africa", weight=0.28))
        db.commit()
    db.close()
    resp = client.get("/api/v1/sovereign/guardrails/NG", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "country_code" in data
    assert "data_truth_g5_g6_g7" in data
    assert "sovereign_veto" in data
    assert "combined" in data
    assert "advisory" in data
    assert data["advisory"] == "Advisory only. Decision finale = validation humaine."


def test_guardrails_with_active_veto():
    token = _register_and_login("gr3", "gr3@t.com")
    _topup(token, 500)
    _make_admin("gr3")
    # Seed country
    db = TestingSessionLocal()
    from src.database.models import Country
    if not db.query(Country).filter(Country.code == "CI").first():
        db.add(Country(code="CI", name="Cote d'Ivoire", region="West Africa", weight=0.22))
        db.commit()
    db.close()
    # Issue veto
    client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "CI", "veto_type": "SANCTIONS",
        "reason": "Test sanctions on Cote d'Ivoire",
        "issued_by": "ECOWAS", "effective_date": str(date.today()),
    })
    # Check guardrails
    resp = client.get("/api/v1/sovereign/guardrails/CI", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["combined"]["blocked"] is True
    assert data["combined"]["human_review_required"] is True


def test_veto_with_legal_basis():
    token = _register_and_login("gr4", "gr4@t.com")
    _topup(token, 500)
    _make_admin("gr4")
    resp = client.post("/api/v1/sovereign/issue", headers=_auth(token), json={
        "country_code": "SN", "veto_type": "DEBT_CEILING",
        "reason": "Senegal exceeds UEMOA 70pct debt-to-GDP ceiling",
        "issued_by": "BCEAO", "effective_date": str(date.today()),
        "legal_basis": "Article 61 Traite UEMOA",
    })
    assert resp.status_code == 200
    assert resp.json()["veto_id"] > 0
