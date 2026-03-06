# Pilot #1 — Live Tracking Log

**Client:** ________________________________
**Account:** _________________________________pilot
**Pilot start (Day 0):** ___/___/2026
**Pilot end (Day 14):** ___/___/2026
**Account Manager:** ________________________________
**Status:** NOT STARTED

---

## Timeline

```
Day 0          Day 3          Day 5          Day 7          Day 14
  |              |              |              |              |
KICKOFF      CHECKPOINT     NPS SURVEY    MID-REVIEW     DECISION
4 calls OK   20+ calls      async email   30 min call    GO/EXT/STOP
             3+ endpoints   NPS >= 6      usage review
```

---

## Day 0 — Kickoff

**Date:** ___/___/2026
**Status:** [ ] NOT DONE / [ ] DONE

### Pre-Kickoff Verification (ops team, before call)

| Check | Command | Result | Pass |
|-------|---------|--------|------|
| API health | `curl https://wasi-backend-api.onrender.com/api/health` | | [ ] |
| Client account exists | `POST /api/auth/login` with client creds | | [ ] |
| Credits = 100 | `GET /api/auth/me` → x402_balance | | [ ] |
| Indices live | `GET /api/indices/latest` → 16 countries | | [ ] |

### Kickoff Call Log

| Item | Notes |
|------|-------|
| Attendees | |
| Client use case confirmed | |
| Integration method (REST/webhook/embedded) | |
| Countries of interest | |
| Questions raised | |
| Action items | |

### Day 0 Gate — Client Must Complete

| # | Task | Endpoint | HTTP | Pass |
|---|------|----------|------|------|
| 1 | Login | POST /api/auth/login | | [ ] |
| 2 | Fetch indices | GET /api/indices/latest | | [ ] |
| 3 | Fetch FX | GET /v1/market/fx?base=XOF&symbols=EUR,USD | | [ ] |
| 4 | Check balance | GET /api/auth/me | | [ ] |

**Day 0 verdict:** [ ] PASS — all 4 tasks completed / [ ] BLOCKED — escalate

---

## Day 3 — First Checkpoint

**Date:** ___/___/2026
**Status:** [ ] NOT DONE / [ ] DONE

### Evidence Collection

```bash
# Run KPI snapshot
bash scripts/pilot-kpi-snapshot.sh [client_username] [client_password]
```

### Day 3 KPIs

| KPI | Target | Actual | Pass |
|-----|--------|--------|------|
| Total API calls | >= 20 | | [ ] |
| Distinct endpoints used | >= 3 | | [ ] |
| Client-reported errors | 0 | | [ ] |
| Credits remaining | > 50 (50%) | | [ ] |
| Client satisfaction (1-5) | >= 3 | | [ ] |

### Day 3 Notes

| Item | Detail |
|------|--------|
| Endpoints used | |
| Integration progress | |
| Issues encountered | |
| Support tickets opened | |
| Feedback received | |

**Day 3 verdict:** [ ] ON TRACK / [ ] AT RISK — action: _______________

**If AT RISK:** Schedule emergency support session before Day 5.

---

## Day 5 — NPS Survey (async)

**Date sent:** ___/___/2026
**Date received:** ___/___/2026
**Status:** [ ] NOT SENT / [ ] SENT / [ ] RECEIVED

### Survey Responses

| # | Question | Response |
|---|----------|----------|
| 1 | Which endpoints are you using most? | |
| 2 | What data is most valuable for your business? | |
| 3 | Any reliability issues encountered? | |
| 4 | Would you recommend WASI? (NPS 0-10) | **Score: ___** |
| 5 | Are you considering paid conversion? | Yes / Maybe / No |

### NPS Classification

| Score | Category |
|-------|----------|
| 9-10 | Promoter |
| 7-8 | Passive |
| 0-6 | Detractor |

**Client NPS category:** _______________

---

## Day 7 — Mid-Pilot Review

**Date:** ___/___/2026
**Status:** [ ] NOT DONE / [ ] DONE

### Evidence Collection

```bash
# Run KPI snapshot
bash scripts/pilot-kpi-snapshot.sh [client_username] [client_password]
```

### Day 7 KPIs

| KPI | Target | Actual | Pass |
|-----|--------|--------|------|
| Total API calls | >= 50 | | [ ] |
| Distinct endpoints used | >= 5 | | [ ] |
| Uptime during pilot | >= 99% | | [ ] |
| Client-reported errors | < 3 | | [ ] |
| Credits remaining | > 0 | | [ ] |
| NPS score (from Day 5) | >= 7 | | [ ] |

### Review Call Log

| Item | Notes |
|------|-------|
| Attendees | |
| Usage patterns observed | |
| Most valuable features | |
| Missing features / gaps | |
| Reliability feedback | |
| Pricing discussion | |
| Conversion intent | Strong / Maybe / No |
| Blockers to conversion | |
| Action items | |

**Day 7 verdict:** [ ] STRONG — likely GO / [ ] MODERATE — may extend / [ ] WEAK — likely stop

---

## Day 14 — Final Decision

**Date:** ___/___/2026
**Status:** [ ] NOT DONE / [ ] DONE

### Final KPI Snapshot

```bash
bash scripts/pilot-kpi-snapshot.sh [client_username] [client_password]
```

### Day 14 KPIs

| KPI | Target | Actual | Pass |
|-----|--------|--------|------|
| Total API calls | >= 100 | | [ ] |
| Distinct endpoints used | >= 5 | | [ ] |
| Uptime during pilot | >= 99% | | [ ] |
| Client-reported errors | < 3 | | [ ] |
| NPS score | >= 7 | | [ ] |
| Conversion intent | Yes | | [ ] |

### Decision

| Criteria | GO | EXTEND | STOP |
|----------|----|--------|------|
| API calls | >= 100 | 50-99 | < 50 |
| NPS | >= 8 | 6-7 | < 6 |
| Conversion intent | Yes | Maybe | No |

**DECISION: [ ] GO / [ ] EXTEND / [ ] STOP**

### Approvals

| Role | Name | Decision | Date | Signature |
|------|------|----------|------|-----------|
| Account Manager | | | | |
| CTO / Tech Lead | | | | |
| CEO / Founder | | | | |

**Unanimous required for GO. Any dissent triggers EXTEND with documented blockers.**

---

## Post-Decision Actions

### If GO

| # | Action | Owner | Deadline | Done |
|---|--------|-------|----------|------|
| 1 | Client selects plan (Pro/Business/Enterprise) | AM | D+1 | [ ] |
| 2 | Payment method setup (PayDunya/Stripe) | AM + Eng | D+3 | [ ] |
| 3 | First payment processed | Client | D+5 | [ ] |
| 4 | Account tier upgraded | Eng | D+5 | [ ] |
| 5 | Production SLA activated | AM | D+5 | [ ] |
| 6 | Client added to monitoring alerts | Eng | D+5 | [ ] |
| 7 | Weekly exec dashboard starts tracking | AM | D+7 | [ ] |

### If EXTEND

| # | Action | Owner | Deadline | Done |
|---|--------|-------|----------|------|
| 1 | Top up credits to 500 | Eng | D+0 | [ ] |
| 2 | Document blockers to resolve | AM | D+1 | [ ] |
| 3 | Set new checkpoint date | AM | D+1 | [ ] |
| 4 | Address each blocker | Eng | D+7 | [ ] |
| 5 | Re-run Day 14 gate at extension end | AM | D+14/21 | [ ] |

### If STOP

| # | Action | Owner | Deadline | Done |
|---|--------|-------|----------|------|
| 1 | Send thank-you + feedback request | AM | D+1 | [ ] |
| 2 | Deactivate pilot credentials | Eng | D+3 | [ ] |
| 3 | Archive this tracking log | AM | D+3 | [ ] |
| 4 | Log lessons learned below | AM | D+5 | [ ] |
| 5 | Schedule 30-day re-engagement | AM | D+30 | [ ] |
| 6 | Schedule 90-day re-engagement | AM | D+90 | [ ] |

---

## Status Summary for Approvers

*Copy this section to the approval email at Day 14.*

```
PILOT #1 STATUS SUMMARY
========================
Client:     [____________]
Duration:   Day 0 (___/___) to Day 14 (___/___/2026)
API Calls:  ___ total
Endpoints:  ___ distinct
Uptime:     ____%
NPS Score:  ___
Credits:    ___ remaining / 100 allocated
Errors:     ___ client-reported

Day 3 gate:   PASS / FAIL
Day 5 NPS:    ___ (Promoter / Passive / Detractor)
Day 7 intent: Strong / Maybe / No

RECOMMENDATION: GO / EXTEND / STOP
REASON: ________________________________

Prepared by: [AM name]
Date: ___/___/2026
```

---

## Lessons Learned (fill after closure)

| Category | Observation | Action for Pilot #2 |
|----------|-------------|---------------------|
| Onboarding | | |
| Data quality | | |
| Performance | | |
| Support | | |
| Pricing | | |
| Product gaps | | |
