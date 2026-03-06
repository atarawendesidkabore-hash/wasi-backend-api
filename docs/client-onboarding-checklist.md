# Client Pilot Onboarding Checklist

**Target:** First paying client on WASI v4.0.0
**Prerequisites:** Go-Live validated, 24h monitoring window clear

---

## Phase 1 — Account Setup

- [ ] Create client account via `/api/auth/register`
- [ ] Upgrade tier to `pro` in DB (`UPDATE users SET tier='pro' WHERE username='...'`)
- [ ] Load initial credits via admin topup (minimum 100 credits recommended)
- [ ] Generate and share API credentials (username + password, client generates JWT via /api/auth/login)
- [ ] Provide API base URL: `https://wasi-backend-api.onrender.com`

## Phase 2 — API Access Verification

Client should test these endpoints in order:

| Step | Endpoint | Credits | Expected |
|------|----------|---------|----------|
| 1 | `POST /api/auth/login` | 0 | JWT token |
| 2 | `GET /api/auth/me` | 0 | Account + balance |
| 3 | `GET /api/health` | 0 | status=healthy |
| 4 | `GET /v1/market/fx?base=XOF&symbols=EUR,USD` | 1 | Live FX rates |
| 5 | `POST /v1/credit/decision` | 5 | Score + decision |
| 6 | `GET /api/indices/latest` | 1 | WASI composite index |
| 7 | `GET /api/country/{code}/index` | 1 | Country-level index |

## Phase 3 — Credit Decision Integration

### Request format
```json
POST /v1/credit/decision
{
  "country": "CI",
  "loan_type": "projet",
  "components": {
    "pays": 70,
    "politique": 60,
    "sectoriel": 65,
    "flux": 72,
    "corridor": 68,
    "emprunteur": 75,
    "change": 62
  }
}
```

### Component guide (0-100 scale)
| Component | Description | Weight |
|-----------|-------------|--------|
| pays | Country macro risk | 20% |
| politique | Political stability | 15% |
| sectoriel | Sector/industry risk | 15% |
| flux | Trade flow health | 15% |
| corridor | Corridor connectivity | 10% |
| emprunteur | Borrower profile | 15% |
| change | FX/currency risk | 10% |

### Decision outcomes
| Proposal | Score range | Action |
|----------|------------|--------|
| APPROVE | >= 75 | Proceed (human review still required) |
| REVIEW | 55-74 | Additional due diligence recommended |
| REJECT | < 55 | Do not proceed |
| VETOED | N/A | Sovereign veto active (BF/ML/NE/GN on dette_souveraine) |

### Valid loan types
`projet`, `trade_finance`, `dette_souveraine`, `private_equity`, `court_terme`, `credit_bail`, `microfinance`

### Valid countries (ECOWAS 16)
NG, CI, GH, SN, BF, ML, GN, BJ, TG, NE, MR, GW, SL, LR, GM, CV

## Phase 4 — Credit Monitoring

- [ ] Client receives API docs (Swagger at `$BASE/docs`)
- [ ] Set up credit balance alerts (check `/api/auth/me` for `x402_balance`)
- [ ] Agree on credit topup process (admin-initiated, minimum 50 credits)
- [ ] Define monthly usage review cadence

## Phase 5 — Production Guardrails

**Mandatory disclaimers on every response:**
- `"Advisory only. Decision finale = validation humaine"`
- `human_review_required: true` (always)

**Client must acknowledge:**
- [ ] WASI scores are advisory, not binding credit decisions
- [ ] Human review is mandatory before any loan approval
- [ ] Sovereign vetoes (BF/ML/NE/GN) are non-negotiable on dette_souveraine
- [ ] FX rates are live but indicative (source: open.er-api.com)
- [ ] AI financial analysis (cloud mode) requires ANTHROPIC_API_KEY configured

## Phase 6 — Support & Escalation

| Issue | Contact | SLA |
|-------|---------|-----|
| API down / 5xx | DevOps | 1h response |
| Credit balance issue | Admin | 4h response |
| Data quality concern | Data team | 24h response |
| Feature request | Product | Next sprint review |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| GET /v1/market/fx | 30/minute |
| POST /v1/credit/decision | 20/minute |
| POST /v1/ai/financial-analysis | 15/minute |
