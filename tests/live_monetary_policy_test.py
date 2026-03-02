"""
Live integration test: proves the server boots, BCEAO rates seed,
and all 16 monetary policy endpoints return real responses.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Delete old DB so tables recreate with new schema
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wasi.db")
for f in [db_path, db_path + "-shm", db_path + "-wal"]:
    try:
        if os.path.exists(f):
            os.remove(f)
            print(f"Deleted {os.path.basename(f)}")
    except PermissionError:
        print(f"Warning: could not delete {os.path.basename(f)} (in use)")

from fastapi.testclient import TestClient
from src.main import app

# Use context manager to trigger app lifespan (init_db, seed, bootstrap)
client = TestClient(app, raise_server_exceptions=False)
client.__enter__()

passed = 0
failed = 0


def check(label, response, expected_status=200, check_fn=None):
    global passed, failed
    ok = response.status_code == expected_status
    detail = ""
    if ok and check_fn:
        try:
            ok = check_fn(response.json())
        except Exception as e:
            ok = False
            detail = f" ({e})"
    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
        detail = detail or f" (got {response.status_code}, body: {response.text[:200]})"
    print(f"  [{status}] {label}{detail}")
    return response


# Step 1: Register + login to get auth token
print("\n=== Step 1: Auth ===")
reg = client.post("/api/auth/register", json={
    "username": "bceao_admin",
    "email": "admin@bceao.int",
    "password": "SecurePass123!",
})
print(f"  Register: {reg.status_code}")

login = client.post("/api/auth/login", data={
    "username": "bceao_admin",
    "password": "SecurePass123!",
})
token = login.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}
print(f"  Login: {login.status_code} (token={'OK' if token else 'MISSING'})")

# Top up credits
topup = client.post("/api/payment/topup", json={
    "amount": 10000.0,
    "reference_id": "BCEAO-TEST-001",
}, headers=headers)
print(f"  Topup: {topup.status_code}")


# Step 2: Monetary Policy Endpoints
print("\n=== Step 2: Policy Rates ===")

# GET current rates - check all 3 rate types present with numeric values
check("GET /rates/current", client.get(
    "/api/v3/ecfa/monetary-policy/rates/current", headers=headers
), check_fn=lambda j: (
    "TAUX_DIRECTEUR" in j
    and "TAUX_PRET_MARGINAL" in j
    and "TAUX_DEPOT" in j
    and isinstance(j["TAUX_DIRECTEUR"]["rate_percent"], (int, float))
))

# SET new taux directeur — response is SetPolicyRateResponse with rates_updated list
check("POST /rates/set (TD=4.25%)", client.post(
    "/api/v3/ecfa/monetary-policy/rates/set", headers=headers,
    json={
        "rate_type": "TAUX_DIRECTEUR",
        "new_rate_percent": 4.25,
        "rationale": "Inflation targeting - tightening cycle",
    }
), check_fn=lambda j: (
    isinstance(j.get("rates_updated"), list)
    and any(r["rate_type"] == "TAUX_DIRECTEUR" and r["new"] == 4.25 for r in j["rates_updated"])
))

# Verify corridor auto-adjusted (TD ± 200bp)
check("GET /rates/current (corridor=TD+/-200bp)", client.get(
    "/api/v3/ecfa/monetary-policy/rates/current", headers=headers
), check_fn=lambda j: (
    j.get("TAUX_DIRECTEUR", {}).get("rate_percent") == 4.25
    and j.get("TAUX_PRET_MARGINAL", {}).get("rate_percent") == 6.25
    and j.get("TAUX_DEPOT", {}).get("rate_percent") == 2.25
))

# Rate history
check("GET /rates/history/TAUX_DIRECTEUR", client.get(
    "/api/v3/ecfa/monetary-policy/rates/history/TAUX_DIRECTEUR", headers=headers
), check_fn=lambda j: j.get("rate_type") == "TAUX_DIRECTEUR" and len(j.get("history", [])) >= 1)


print("\n=== Step 3: Reserve Requirements ===")

# Response is ReserveRequirementResponse with reserve_ratio_percent
check("GET /reserves/status", client.get(
    "/api/v3/ecfa/monetary-policy/reserves/status", headers=headers
), check_fn=lambda j: "reserve_ratio_percent" in j and "banks_assessed" in j)

# Response is SetPolicyRateResponse (same as rates/set)
check("POST /reserves/set-ratio (5%)", client.post(
    "/api/v3/ecfa/monetary-policy/reserves/set-ratio", headers=headers,
    json={"new_ratio_percent": 5.0}
), check_fn=lambda j: (
    isinstance(j.get("rates_updated"), list)
    and any(r["rate_type"] == "TAUX_RESERVE" and r["new"] == 5.0 for r in j["rates_updated"])
))


print("\n=== Step 4: Standing Facilities ===")

# These return 400 (no bank wallets in live DB)
check("POST /facility/lending/open (400 no bank)", client.post(
    "/api/v3/ecfa/monetary-policy/facility/lending/open", headers=headers,
    json={"bank_wallet_id": "nonexistent", "amount_ecfa": 1000000, "maturity": "OVERNIGHT"}
), expected_status=400)

check("POST /facility/deposit/open (400 no bank)", client.post(
    "/api/v3/ecfa/monetary-policy/facility/deposit/open", headers=headers,
    json={"bank_wallet_id": "nonexistent", "amount_ecfa": 1000000}
), expected_status=400)

check("POST /facility/mature (0 matured)", client.post(
    "/api/v3/ecfa/monetary-policy/facility/mature", headers=headers
), check_fn=lambda j: j.get("facilities_matured") == 0)


print("\n=== Step 5: Interest & Demurrage ===")

check("POST /interest/apply-daily", client.post(
    "/api/v3/ecfa/monetary-policy/interest/apply-daily", headers=headers
), check_fn=lambda j: "wallets_affected" in j)


print("\n=== Step 6: Money Supply ===")

# Fields are m0_base_money_ecfa, m1_narrow_money_ecfa, m2_broad_money_ecfa
check("GET /money-supply", client.get(
    "/api/v3/ecfa/monetary-policy/money-supply", headers=headers
), check_fn=lambda j: (
    "m0_base_money_ecfa" in j
    and "m1_narrow_money_ecfa" in j
    and "m2_broad_money_ecfa" in j
    and "reserve_multiplier" in j
))

check("GET /money-supply/CI", client.get(
    "/api/v3/ecfa/monetary-policy/money-supply/CI", headers=headers
), check_fn=lambda j: "m0_base_money_ecfa" in j and j.get("country_code") == "CI")

check("GET /aggregates/CI", client.get(
    "/api/v3/ecfa/monetary-policy/aggregates/CI", headers=headers
), check_fn=lambda j: "policy_rates" in j and "reserve_position" in j)


print("\n=== Step 7: Policy Decisions ===")

# PolicyDecisionRequest requires all 4 rate fields
check("POST /decision/record (CPM meeting)", client.post(
    "/api/v3/ecfa/monetary-policy/decision/record", headers=headers,
    json={
        "meeting_date": "2026-03-01",
        "decision_summary": "Maintain current rates amid stable inflation",
        "rationale": "Inflation at 2.1% within target band. GDP growth solid at 6.2%.",
        "taux_directeur": 4.25,
        "taux_pret_marginal": 6.25,
        "taux_depot": 2.25,
        "reserve_ratio": 5.0,
        "inflation_rate": 2.1,
        "gdp_growth": 6.2,
        "votes_for": 7,
        "votes_against": 1,
        "votes_abstain": 1,
    }
), check_fn=lambda j: j.get("status") == "decided")

check("GET /decision/history", client.get(
    "/api/v3/ecfa/monetary-policy/decision/history", headers=headers
), check_fn=lambda j: isinstance(j, list) and len(j) >= 1)


print("\n=== Step 8: Collateral Framework ===")

# Create a wallet for FK satisfaction
from src.database.connection import SessionLocal
from src.database.cbdc_models import CbdcWallet
db = SessionLocal()
existing = db.query(CbdcWallet).filter(CbdcWallet.wallet_id == "bank-test-coll").first()
if not existing:
    from src.utils.cbdc_crypto import hash_pin
    w = CbdcWallet(
        wallet_id="bank-test-coll",
        user_id=1,
        country_id=1,
        phone_hash="collateral_test_hash",
        wallet_type="COMMERCIAL_BANK",
        balance_ecfa=0,
        available_balance_ecfa=0,
        kyc_tier=3,
        daily_limit_ecfa=999999999,
        pin_hash=hash_pin("1234"),
        public_key_hex="aabbcc",
        status="active",
    )
    db.add(w)
    db.commit()
db.close()

check("POST /collateral/register", client.post(
    "/api/v3/ecfa/monetary-policy/collateral/register", headers=headers,
    json={
        "asset_class": "BCEAO_BOND",
        "asset_description": "BCEAO 5Y Bond 2026",
        "issuer": "BCEAO",
        "issuer_country": "SN",
        "face_value_ecfa": 1000000000,
        "market_value_ecfa": 980000000,
        "haircut_percent": 5.0,
        "owner_wallet_id": "bank-test-coll",
    }
), check_fn=lambda j: j.get("asset_class") == "BCEAO_BOND" and j.get("haircut_percent") == 5.0)

check("GET /collateral/list", client.get(
    "/api/v3/ecfa/monetary-policy/collateral/list", headers=headers
), check_fn=lambda j: isinstance(j, list) and len(j) >= 1)


# Final summary
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("\nAll 17 monetary policy endpoint checks verified!")
