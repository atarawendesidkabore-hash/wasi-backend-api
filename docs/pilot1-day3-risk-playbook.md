# Pilot #1 — Day 3 Risk Playbook

**Purpose:** Pre-defined remediation actions for every AT RISK trigger at Day 3.
React in < 1 hour. No improvisation needed.

---

## Risk Matrix Overview

| # | Risk | Trigger | Severity | Owner |
|---|------|---------|----------|-------|
| R1 | Low API usage | < 20 calls by Day 3 | HIGH | AM |
| R2 | Narrow endpoint breadth | < 3 distinct endpoints | MEDIUM | AM |
| R3 | Low satisfaction | Client score < 3/5 | HIGH | AM + CTO |
| R4 | Latency drift | p95 > 2,000ms | MEDIUM | Engineering |
| R5 | Data gaps | Key endpoint returns empty/stale | HIGH | Engineering |
| R6 | Credit exhaustion | Balance < 10 credits | MEDIUM | AM + Eng |
| R7 | Client silent | Zero calls since Day 1 | CRITICAL | AM |
| R8 | Auth/integration failure | Client cannot login or gets 4xx | HIGH | Engineering |

---

## R1 — Low API Usage (< 20 calls by Day 3)

**Trigger:** Total API calls < 20 at Day 3 checkpoint
**Root causes:** Integration delayed, wrong priorities, unclear value, technical blocker

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Call client within 1h — ask directly: "What's blocking you?" | AM | 1h |
| 2 | Classify blocker: technical / priorities / unclear value | AM | 1h |
| 3a | If technical: schedule 30-min screen share to debug integration | Eng | 4h |
| 3b | If priorities: reschedule pilot start, pause credit timer | AM | 4h |
| 3c | If unclear value: re-demo with client's specific data needs | AM | 4h |
| 4 | Send 3 ready-to-run curl commands tailored to client's use case | Eng | 2h |
| 5 | Follow up at Day 4 — if still < 10 calls, escalate to CTO | AM | 24h |

**Recovery target:** >= 30 calls by Day 5 (catch-up pace)
**Escalation:** If zero calls by Day 4 → treat as R7 (Client Silent)

---

## R2 — Narrow Endpoint Breadth (< 3 distinct endpoints)

**Trigger:** Client only uses 1-2 endpoints by Day 3
**Root causes:** Client unaware of other endpoints, single use case, integration scope limited

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Identify which endpoints client is using | Eng | 30min |
| 2 | Map client's stated use case to 3-5 relevant endpoints | AM | 1h |
| 3 | Send personalized "Did you know?" email with examples | AM | 2h |
| 4 | Include curl commands + expected output for each suggested endpoint | Eng | 2h |
| 5 | Offer 15-min call to walk through additional endpoints | AM | 4h |

**Example mapping:**

| Client Use Case | Suggested Endpoints |
|----------------|---------------------|
| Credit risk | indices + bank/credit-context + macro + composite |
| Market intel | indices + markets + commodities + FX + signals |
| Trade finance | indices + country history + corridors + FX |
| Advisory | composite + forecast + macro + signals + news |

**Recovery target:** >= 4 distinct endpoints by Day 5
**Escalation:** None — medium severity, resolve via guidance

---

## R3 — Low Satisfaction (score < 3/5)

**Trigger:** Client rates experience below 3 out of 5 at Day 3
**Root causes:** Data not useful, performance issues, unmet expectations, poor support

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Call client within 1h — structured debrief | AM + CTO | 1h |
| 2 | Ask: "What did you expect that you didn't get?" | AM | 1h |
| 3 | Document every complaint verbatim | AM | 1h |
| 4 | Classify issues: data / performance / expectations / support | CTO | 2h |
| 5 | For each issue, commit to specific fix + deadline | CTO | 4h |
| 6 | Send written summary: "Here's what we heard + what we're fixing" | AM | 4h |
| 7 | Re-check satisfaction at Day 5 | AM | 48h |

**Issue-specific actions:**

| Complaint | Fix | ETA |
|-----------|-----|-----|
| "Data is outdated" | Run targeted scraper refresh, explain update schedule | 2h |
| "Too slow" | Check Render health, consider paid tier, investigate p95 | 4h |
| "Not the data I need" | Map client needs to existing endpoints or log as gap | 4h |
| "Hard to integrate" | Provide code snippets in client's language (Python/JS/cURL) | 4h |
| "No support response" | Acknowledge failure, assign dedicated contact | 1h |

**Recovery target:** Satisfaction >= 3 by Day 5
**Escalation:** If satisfaction stays < 3 at Day 5, CEO briefing + consider pilot extension or graceful stop

---

## R4 — Latency Drift (p95 > 2,000ms)

**Trigger:** KPI snapshot shows p95 response time exceeding 2,000ms
**Root causes:** Render cold start, DB query slow, scraper running, free tier limits

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Run `pilot-kpi-snapshot.sh` — capture all 10 endpoint latencies | Eng | 15min |
| 2 | Identify which endpoints are slow (> 2s) | Eng | 15min |
| 3 | Check Render dashboard for: memory, CPU, recent deploys | Eng | 30min |
| 4 | If cold start: implement keep-alive ping (cron every 10min) | Eng | 1h |
| 5 | If DB slow: check for missing indexes, N+1 queries | Eng | 2h |
| 6 | If systemic: consider upgrading Render plan (free → starter) | CTO | 4h |
| 7 | Notify client if degradation is temporary | AM | 1h |

**Keep-alive implementation:**
```bash
# Add to cron or external monitor (UptimeRobot, cron-job.org)
*/10 * * * * curl -s https://wasi-backend-api.onrender.com/api/health > /dev/null
```

**Recovery target:** p95 < 2,000ms within 4 hours
**Escalation:** If p95 > 5,000ms for > 1 hour, P1 incident — CTO takes ownership

---

## R5 — Data Gaps (endpoint returns empty or stale)

**Trigger:** Key endpoint returns empty array, N/D, or data older than expected freshness
**Root causes:** Scraper failed, scheduler stopped, DB empty for specific country/period

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Identify affected endpoint + country/data | Eng | 15min |
| 2 | Check if scraper ran: query DB for latest record timestamps | Eng | 30min |
| 3 | Check scheduler: is APScheduler running? | Eng | 30min |
| 4 | If scraper failed: re-run manually via admin refresh endpoint | Eng | 1h |
| 5 | If scheduler stopped: restart via Render deploy | Eng | 30min |
| 6 | If external API down: activate fallback data, notify client | Eng + AM | 1h |
| 7 | Verify fix: re-query endpoint, confirm data present | Eng | 15min |

**Manual refresh commands (admin required):**
```
POST /api/v2/data/worldbank/refresh  (20 cr)
POST /api/v2/data/imf/refresh       (10 cr)
POST /api/v2/data/commodities/refresh (5 cr)
POST /api/v2/data/acled/refresh      (5 cr)
```

**Recovery target:** Data restored within 2 hours
**Escalation:** If data gap affects client's primary use case, P2 — CTO + AM joint response

---

## R6 — Credit Exhaustion (balance < 10)

**Trigger:** Client's x402_balance drops below 10 credits before Day 7
**Root causes:** High call frequency, expensive endpoints (score-dossier = 10cr), polling loop

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Check client's current balance via `GET /api/auth/me` | Eng | 15min |
| 2 | Review QueryLog: which endpoints consumed most credits? | Eng | 30min |
| 3 | If polling loop: advise client to cache responses (5min TTL) | AM | 1h |
| 4 | If legitimate usage: top up 50 credits (pilot courtesy) | Eng | 30min |
| 5 | Send usage breakdown to client with optimization tips | AM | 2h |
| 6 | If burn rate > 30 cr/day: discuss paid tier early | AM | 4h |

**Optimization tips for client:**
- Cache `/api/indices/latest` — updates every 6h, no need to poll every minute
- Use `/api/composite/report` (3cr) instead of `/api/composite/calculate` (5cr)
- Batch country queries: fetch all via `/api/indices/latest` instead of per-country

**Recovery target:** Balance > 20 credits after top-up, burn rate sustainable
**Escalation:** If client exhausts 150+ credits in 3 days, likely conversion candidate — AM fast-track pricing discussion

---

## R7 — Client Silent (zero calls since Day 1)

**Trigger:** No API calls recorded after initial Day 0 verification
**Root causes:** Client lost interest, internal priorities shifted, forgot credentials, technical blocker

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | WhatsApp message: "Bonjour — avez-vous pu avancer sur l'integration?" | AM | 1h |
| 2 | If no response in 4h: email with subject "WASI Pilot — besoin d'aide?" | AM | 4h |
| 3 | If no response in 24h: phone call | AM | 24h |
| 4 | If reached — classify: lost interest / blocked / busy | AM | — |
| 5a | If blocked: schedule immediate support call | AM + Eng | 2h |
| 5b | If busy: offer to pause pilot timer, restart when ready | AM | 1h |
| 5c | If lost interest: ask why, log feedback, close gracefully | AM | 1h |
| 6 | If unreachable after 48h: send final "pilot expiring" email | AM | 48h |
| 7 | If no response by Day 5: close pilot, schedule 30-day follow-up | AM | Day 5 |

**Recovery target:** Client makes first real API call within 24h of re-engagement
**Escalation:** If client is a strategic account, CEO makes personal outreach at 48h mark

---

## R8 — Auth/Integration Failure (client gets 4xx errors)

**Trigger:** Client reports 401, 403, or 422 errors consistently
**Root causes:** Wrong credentials, expired token, missing headers, malformed requests

### Action Steps

| Step | Action | Owner | ETA |
|------|--------|-------|-----|
| 1 | Ask client: exact endpoint, HTTP method, error body | Eng | 15min |
| 2 | Verify credentials work: test login with client's username | Eng | 15min |
| 3 | If 401: token expired → guide client to re-login flow | Eng | 30min |
| 4 | If 403: check if endpoint requires admin → explain access | Eng | 30min |
| 5 | If 422: request body malformed → send correct example | Eng | 30min |
| 6 | If CORS: add client's origin to CORS_ORIGINS, redeploy | Eng | 1h |
| 7 | Provide working code snippet in client's language | Eng | 1h |

**Common fixes:**
```
401 → Token expired. Re-call POST /api/auth/login for new token.
403 → Endpoint requires admin role. Use standard endpoints instead.
402 → Credits exhausted. See R6.
422 → Request body format wrong. Check Content-Type: application/json.
429 → Rate limited. Reduce to < 60 calls/min.
```

**Recovery target:** Client can make successful calls within 1 hour
**Escalation:** If auth system itself is broken (affects all users), P1 incident

---

## Quick Reference Card

Print this and keep visible during Day 3 checkpoint:

```
DAY 3 RISK QUICK RESPONSE
==========================
R1  Low usage (<20 calls)  → Call client in 1h, ask what's blocking
R2  Narrow breadth (<3 ep)  → Send "did you know" email with examples
R3  Low satisfaction (<3/5)  → Debrief call in 1h, commit to fixes
R4  Latency drift (p95>2s)  → Check Render, add keep-alive ping
R5  Data gaps (empty/stale)  → Re-run scraper, check scheduler
R6  Credits low (<10)        → Top up 50cr, send optimization tips
R7  Client silent (0 calls)  → WhatsApp → Email → Phone → Close
R8  Auth errors (4xx)        → Verify creds, send working examples
```
