# WASI Pilot Onboarding Runbook

**Version:** 1.0 | **Effective:** 2026-03-06
**Audience:** WASI operations team + pilot account manager

---

## Overview

This runbook covers the full lifecycle of onboarding a pilot client from
first contact to paid conversion. Each checkpoint has explicit pass/fail
criteria and escalation paths.

---

## Pre-Onboarding (Day -3 to Day -1)

### Intake Checklist

| Item | Owner | Done |
|------|-------|------|
| Client company name + sector | Account Manager | [ ] |
| Primary technical contact (name, email, phone) | AM | [ ] |
| Expected use case (credit scoring, market intel, advisory, USSD) | AM | [ ] |
| Expected API call volume (daily estimate) | AM | [ ] |
| Integration method (REST direct, webhook, embedded) | AM | [ ] |
| Preferred language (FR/EN) | AM | [ ] |
| Data jurisdictions of interest (country codes) | AM | [ ] |
| NDA signed (if required) | Legal | [ ] |

### Account Provisioning

```bash
# 1. Register pilot account on production
curl -X POST https://wasi-backend-api.onrender.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "<client_slug>_pilot",
    "email": "<client_email>",
    "password": "<generated_password>"
  }'

# 2. Note the returned user ID and initial balance (10 credits)

# 3. Top up to pilot allocation (100 credits recommended)
# Requires admin access — use Render dashboard or admin endpoint
```

### Pilot Credit Allocation

| Tier | Credits | Duration | Cost |
|------|---------|----------|------|
| Evaluation | 10 | 3 days | Free |
| Pilot | 100 | 14 days | Free |
| Extended Pilot | 500 | 30 days | Negotiable |
| Production | Pay-as-you-go | Ongoing | Per pricing grid |

---

## Day 0 — Kickoff

### Deliverables to Client

1. **API credentials** (username + temporary password, force change on first login)
2. **Endpoint reference card** (top 10 endpoints with curl examples)
3. **Trust pack** (production readiness certificate + security audit)
4. **Support channel** (WhatsApp group or email)

### Technical Walkthrough (30 min call)

Agenda:
1. Login + token flow (5 min)
2. Live demo: fetch indices, composite, FX rates (10 min)
3. Credit system explanation (5 min)
4. Client's specific use case mapping to endpoints (10 min)

### Verification — Client Must Complete

| Task | Endpoint | Expected | Pass |
|------|----------|----------|------|
| Login | POST /api/auth/login | 200 + token | [ ] |
| Fetch indices | GET /api/indices/latest | 16 countries | [ ] |
| Fetch FX | GET /v1/market/fx?base=XOF&symbols=EUR,USD | rates array | [ ] |
| Check balance | GET /api/auth/me | x402_balance > 0 | [ ] |

**Day 0 gate:** All 4 tasks completed by client. If blocked, escalate to engineering.

---

## Day 1-2 — Integration

### Client Integration Support

| Integration Type | Guidance |
|-----------------|----------|
| REST direct | Provide curl + Python/JS snippets |
| Webhook | Client provides callback URL, we configure alerts |
| Embedded dashboard | Provide wasiApi.js reference implementation |
| USSD | Provide menu tree + session flow documentation |

### Common Integration Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Token expired | 401 on all calls | Re-login, token lasts 3600s |
| Credits exhausted | 402 Payment Required | Top up or reduce call frequency |
| CORS blocked | Browser console error | Add client origin to CORS_ORIGINS |
| Rate limited | 429 Too Many Requests | Reduce to < 60 calls/min |
| Stale data | Same values for days | Check scheduler status, trigger refresh |

### Monitoring (operations team)

```bash
# Check client's credit consumption
# (requires DB access or admin endpoint)

# Check API health
curl -s https://wasi-backend-api.onrender.com/api/health

# Run KPI snapshot
bash scripts/pilot-kpi-snapshot.sh
```

---

## Day 3 — First Checkpoint

### Review Call (15 min)

Agenda:
1. Integration status — is the client calling the API successfully?
2. Data quality feedback — are the indices/signals useful?
3. Missing features or endpoints?
4. Credit burn rate — on track or need adjustment?

### Day 3 KPIs

| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| Successful API calls | >= 20 | ___ | [ ] |
| Distinct endpoints used | >= 3 | ___ | [ ] |
| Client-reported errors | 0 | ___ | [ ] |
| Credits remaining | > 50% of allocation | ___ | [ ] |
| Client satisfaction (1-5) | >= 3 | ___ | [ ] |

**Day 3 gate:** If client has < 20 successful calls or satisfaction < 3,
schedule emergency support session before Day 5.

---

## Day 5 — Mid-Pilot Check (async)

Send client a brief survey:

1. Which endpoints are you using most?
2. What data is most valuable for your business?
3. Any reliability issues encountered?
4. Would you recommend WASI to a colleague? (NPS 0-10)
5. Are you considering paid conversion?

---

## Day 7 — Final Checkpoint

### Review Call (30 min)

Agenda:
1. Full usage review (endpoints, volume, patterns)
2. Data quality assessment
3. Pricing discussion for paid tier
4. Conversion decision: GO / EXTEND / STOP

### Day 7 KPIs

| KPI | Target | Actual | Status |
|-----|--------|--------|--------|
| Total API calls | >= 100 | ___ | [ ] |
| Distinct endpoints used | >= 5 | ___ | [ ] |
| Uptime during pilot | >= 99% | ___ | [ ] |
| Client-reported errors | < 3 | ___ | [ ] |
| Credits remaining | > 0 (not blocked) | ___ | [ ] |
| NPS score | >= 7 | ___ | [ ] |
| Conversion intent | Yes / Maybe / No | ___ | [ ] |

### Decision Matrix

| Signal | Action |
|--------|--------|
| NPS >= 8 + conversion intent | Proceed to billing activation |
| NPS 6-7 + maybe | Offer 14-day extension, address blockers |
| NPS < 6 or no intent | Post-mortem, improve product, re-engage later |
| Zero API calls after Day 3 | Client ghosted — close pilot, schedule follow-up in 30 days |

---

## Post-Pilot — Conversion

### If GO: Billing Activation

1. Create paid account (see `billing-activation-sop.md`)
2. Migrate pilot username or create production credentials
3. Set up recurring credit top-up or subscription
4. Remove pilot credit cap
5. Add client to production monitoring alerts

### If EXTEND: Pilot Extension

1. Top up credits to 500
2. Set new checkpoint at Day 14 or Day 21
3. Document specific blockers to resolve
4. Re-run this runbook from Day 7 checkpoint at extension end

### If STOP: Graceful Closure

1. Thank client, collect detailed feedback
2. Archive pilot data (usage logs, feedback, NPS)
3. Schedule 30-day and 90-day re-engagement touchpoints
4. Update CRM/pipeline status

---

## Escalation Matrix

| Severity | Trigger | Response Time | Owner |
|----------|---------|---------------|-------|
| P1 — API down | Health check fails | 15 min | Engineering |
| P2 — Data stale | No index update > 24h | 2 hours | Engineering |
| P3 — Client blocked | 402/401 errors | 4 hours | AM + Engineering |
| P4 — Feature request | Client wants new endpoint | Next sprint | Product |
