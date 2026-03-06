# Release v4.0.0 — V1 Guardrails + Sovereign Veto + Data Truth

**Date:** 2026-03-06
**Tag:** `v4.0.0`
**Commit:** `6ba7b0e` + migration `3f13bb8da8a7`

---

## What's new

### V1 Credit Guardrails (`/v1/`)
- `GET /v1/market/fx` — live FX rates via open.er-api.com (XOF base)
- `POST /v1/credit/decision` — 7-component expert scoring, sovereign veto for BF/ML/NE/GN
- `POST /v1/ai/financial-analysis` — local (ollama) or cloud (Sonnet 4.6) mode with mandatory disclaimer

### Sovereign Veto Engine (`/api/v1/sovereign/`)
- BCEAO authority enforcement: FULL_BLOCK / PARTIAL severity
- Issue/revoke operations (admin only)
- Veto types: SANCTIONS, DEBT_CEILING, MONETARY_POLICY, POLITICAL_CRISIS, AML_CFT

### Data Truth Engine (`/api/v1/data-truth/`)
- Cross-source validation with divergence detection
- Audit trail with z-score analysis and staleness tracking

### Bugfixes
- Fixed recursion in `_get_engine()` (composite.py, composite_update.py)
- Fixed indentation error in news_sweep.py
- Removed `from __future__ import annotations` in v1_guardrails.py (caused Pydantic ForwardRef 422 on all POST)
- Removed rogue `_gen.py`/`_write_files.py`/`_write_db.py` scripts

---

## DB Migration

**Migration ID:** `3f13bb8da8a7`
**New tables:** `sovereign_vetoes`, `data_truth_audits`
**Destructive:** No (additive only)

```bash
alembic upgrade head
```

Render.yaml `preDeployCommand` already runs `alembic upgrade head` automatically.

---

## Deployment (Render)

### Pre-deploy checklist
1. Verify `ANTHROPIC_API_KEY` is set in Render dashboard (required for `/v1/ai/financial-analysis` cloud mode)
2. `SKIP_SCRAPERS=true` remains set for safe startup
3. `SCHEDULER_ENABLED=true` for background tasks

### Deploy
Push to main triggers automatic Render deploy:
```bash
git push origin main
```

### Manual deploy (if needed)
```bash
# Via Render CLI
render deploy --service wasi-backend-api
```

---

## Smoke Tests (post-deploy)

Run against the live URL (replace `$BASE` with your Render URL):

```bash
BASE="https://wasi-backend-api.onrender.com"

# 1. Health check
curl -s "$BASE/api/health" | jq .status
# Expected: "ok"

# 2. Register test user
curl -s -X POST "$BASE/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"smoke_test","email":"smoke@test.com","password":"SmokeTest123"}' \
  | jq .username
# Expected: "smoke_test"

# 3. Login
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" \
  -d "username=smoke_test&password=SmokeTest123" \
  | jq -r .access_token)
echo "Token: ${TOKEN:0:20}..."

# 4. Top up credits
curl -s -X POST "$BASE/api/payment/topup" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount":50,"reference_id":"smoke-deploy"}' \
  | jq .new_balance

# 5. FX market (V1)
curl -s "$BASE/v1/market/fx?base=XOF&symbols=EUR,USD" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '{base, data_mode, rates_count: (.rates | length)}'
# Expected: {"base":"XOF","data_mode":"live","rates_count":2}

# 6. Credit decision (V1)
curl -s -X POST "$BASE/v1/credit/decision" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"country":"CI","loan_type":"projet","components":{"pays":70,"politique":60,"sectoriel":65,"flux":72,"corridor":68,"emprunteur":75,"change":62}}' \
  | jq '{decision_proposal, veto_applied, human_review_required}'
# Expected: {"decision_proposal":"REVIEW","veto_applied":false,"human_review_required":true}

# 7. Sovereign veto test (BF + dette_souveraine)
curl -s -X POST "$BASE/v1/credit/decision" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"country":"BF","loan_type":"dette_souveraine","components":{"pays":70,"politique":60,"sectoriel":65,"flux":72,"corridor":68,"emprunteur":75,"change":62}}' \
  | jq '{decision_proposal, veto_applied, veto_reason}'
# Expected: {"decision_proposal":"VETOED","veto_applied":true,"veto_reason":"dette_souveraine blocked for BF/ML/NE/GN"}

# 8. Financial analysis (local mode)
curl -s -X POST "$BASE/v1/ai/financial-analysis" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Analyse risque CI trade finance","context_data":{},"confidentiality_mode":"local"}' \
  | jq '{model_used, human_review_required}'
# Expected: {"model_used":"ollama/llama3.2","human_review_required":true}

echo "--- SMOKE TESTS COMPLETE ---"
```

---

## Rollback Plan

### If migration fails
```bash
# Revert to previous migration
alembic downgrade fcc02d8e6e64
```

### If app fails after deploy
```bash
# Option A: Revert to previous commit on Render
git revert HEAD --no-edit
git push origin main

# Option B: Manual rollback on Render dashboard
# Go to: Dashboard > wasi-backend-api > Manual Deploy > select commit 0013fc0
```

### Rollback verification
After rollback, confirm:
```bash
curl -s "$BASE/api/health" | jq .status
# Must return "ok"

curl -s "$BASE/api/indices/latest" -H "Authorization: Bearer $TOKEN" | jq .country_code
# Must return data
```

---

## Test Results (pre-deploy)

| Test file | Result |
|-----------|--------|
| `tests/test_v1_guardrails.py` | 8/8 passed |
| `tests/test_bank.py` | 13/13 passed |
| `tests/test_chat.py` | 8/8 passed |
| **Total validated** | **31/31** |
