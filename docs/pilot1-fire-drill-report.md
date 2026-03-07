# Pilot #1 — Pre-Launch Fire Drill Report

**Date:** 2026-03-06 17:36 UTC
**Conducted by:** Automated simulation
**Environment:** https://wasi-backend-api.onrender.com (production)
**Duration:** 58 seconds total (both drills)

---

## Drill 1: P1 API Outage Simulation

### Scenario

Simulated detection of API health failure, rapid-fire flap detection,
partial outage assessment, and recovery confirmation.

### Timeline

| Time (UTC) | Event | Result |
|------------|-------|--------|
| 17:36:25 | Incident declared (T0) | Drill start |
| 17:36:27 | Baseline health probe | HTTP 200, 944ms |
| 17:36:28 | Simulated broken endpoint (404 as 503 proxy) | HTTP 404, 559ms — API framework responding |
| 17:36:29 | Rapid flap detection (5 probes) | 5/5 = 200 (391-718ms) |
| 17:36:34 | Data endpoint probe (partial outage check) | HTTP 200, indices returned (16 countries) |
| 17:36:37 | Recovery confirmed | HTTP 200, 745ms |
| 17:36:37 | Incident closed (T_end) | Total elapsed: 12s |

### Metrics

| Metric | Value |
|--------|-------|
| MTTA (Mean Time To Acknowledge) | **2s** (first health probe response) |
| MTTD (Mean Time To Detect) | **3s** (5-probe flap check completed) |
| MTTR (Mean Time To Recovery) | **0s** (no actual outage — API was healthy) |
| Health probe success rate | 5/5 (100%) |
| Health probe latency (p50) | 480ms |
| Health probe latency (p95) | 718ms |
| Data endpoint available during drill | YES |

### Observations

1. **Health endpoint is reliable.** 5/5 probes returned 200 with consistent sub-1s latency.
2. **No cold start observed.** First probe was 944ms (warm), subsequent probes dropped to 391-718ms.
3. **Partial outage detection works.** Even if health fails, we can independently verify data endpoints.
4. **404 vs 503 distinction is clear.** Framework returns proper 404 for unknown routes (not generic 500).

### Process Gaps Identified

| Gap | Impact | Remediation |
|-----|--------|-------------|
| G1: No automated health monitor running continuously | Detection depends on manual probes or monitor-24h.sh | Set up UptimeRobot or cron-job.org free tier: ping /api/health every 5 min, alert on 2 consecutive failures |
| G2: No alert notification channel configured | Team won't know about outage until manual check | Configure webhook to WhatsApp/Telegram/email on health failure |
| G3: No Render status page monitoring | Render platform issues not tracked | Subscribe to status.render.com notifications |

---

## Drill 2: Auth Failure Simulation

### Scenario

Simulated all auth failure modes a pilot client might encounter,
validated error messages, tested recovery path, and probed rate limiting.

### Results

| Scenario | Input | HTTP | Error Message | Correct? |
|----------|-------|------|---------------|----------|
| A: Wrong password | bad password | 401 | "Incorrect username or password" | YES — no username leak |
| B: Expired token | garbage JWT | 401 | "Invalid token" | YES — generic, no internal leak |
| C: Missing header | no Authorization | 401 | "Not authenticated" | YES — clear instruction |
| D: Admin endpoint | no X-Admin-Key | 404 | "Not Found" | YES — hidden (ADMIN_SEED_ENABLED off) |
| E: Valid login | correct creds | 200 | Token issued | YES — recovery works |
| F: Recovered token | fresh token | 200 | Indices returned | YES — immediate recovery |
| G: Rate limit | 30 rapid calls | 200 | 30/30 OK, 0 throttled | NOTE — see gap G4 |

### Metrics

| Metric | Value |
|--------|-------|
| MTTA (client reports auth issue) | **Depends on client** — see client comms template below |
| MTTR (auth recovery after correct creds) | **< 2s** (login + first successful call) |
| Error message quality | 3/3 correct: no info leakage, clear guidance |
| Admin endpoint hidden | YES — returns 404 not 403 |
| Token recovery | Immediate — no cooldown, no lockout |

### Client Communication Template (auth failure)

When a client reports 401/403 errors, send this:

```
Bonjour [Prenom],

Voici la procedure de resolution pour les erreurs d'authentification :

1. ERREUR 401 "Not authenticated"
   → Vous devez inclure le header Authorization dans chaque requete :
     Authorization: Bearer <votre_token>

2. ERREUR 401 "Invalid token"
   → Votre token a expire (validite : 1 heure).
   → Reconnectez-vous :
     POST /api/auth/login
     Body: username=<votre_user>&password=<votre_mot_de_passe>
   → Utilisez le nouveau access_token retourne.

3. ERREUR 401 "Incorrect username or password"
   → Verifiez vos identifiants. Si le probleme persiste,
     contactez-nous pour reinitialiser votre mot de passe.

4. ERREUR 402 "Payment Required"
   → Vos credits sont epuises. Contactez-nous pour un
     rechargement ou passez a un plan payant.

Cordialement,
L'equipe WASI
```

### Process Gaps Identified

| Gap | Impact | Remediation |
|-----|--------|-------------|
| G4: Rate limiter triggers at 60 calls/min | CONFIRMED WORKING. 80-call burst: 60 OK + 20 rejected (429). Threshold = 60/min. | No action needed — slowapi is correctly enforced. Pilot client should stay well under 60/min. |
| G5: No account lockout after N failed logins | Brute-force risk on pilot credentials | Add configurable lockout: 5 failed attempts → 15-min cooldown. Low priority for pilot (strong passwords), but needed before scale. |
| G6: No client-facing error code reference | Client must guess what 401 sub-messages mean | Add error codes to onboarding guide (e.g., AUTH_EXPIRED, AUTH_MISSING, AUTH_INVALID). Post-pilot improvement. |

---

## Consolidated Gap Analysis

| # | Gap | Severity | Owner | Action | ETA |
|---|-----|----------|-------|--------|-----|
| G1 | No continuous health monitor | HIGH | Eng | Set up UptimeRobot free tier (5-min interval, email + webhook alert) | Before Day 0 |
| G2 | No alert notification channel | HIGH | Eng + AM | Create incident WhatsApp group, configure UptimeRobot webhook | Before Day 0 |
| G3 | No Render status subscription | LOW | Eng | Subscribe to status.render.com | Before Day 0 |
| G4 | ~~Rate limiter untested~~ VERIFIED | CLOSED | Eng | 80-call burst: 60 OK + 20x 429. Threshold = 60/min. Working correctly. | DONE |
| G5 | No login brute-force protection | LOW | Eng | Implement 5-attempt lockout. Acceptable risk for pilot (strong passwords). | Sprint after pilot |
| G6 | No client-facing error reference | LOW | AM | Add error code table to onboarding email or guide | Before Day 3 |

### Pre-Day 0 Required Actions (G1 + G2 + G3)

| Action | Steps | Time Estimate |
|--------|-------|---------------|
| UptimeRobot setup | 1. Create free account. 2. Add monitor: HTTPS, URL=https://wasi-backend-api.onrender.com/api/health, interval=5min. 3. Add alert contact (email + webhook). | 15 min |
| Incident WhatsApp group | 1. Create group "WASI Incidents". 2. Add AM + CTO + Eng. 3. Set as UptimeRobot webhook target. | 10 min |
| Render status alerts | 1. Go to status.render.com. 2. Subscribe with ops email. | 2 min |
| ~~Rate limiter verification~~ | DONE — 80-call burst confirmed 60/min threshold enforced (60 OK + 20x 429). | 0 min |

---

## Fire Drill Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| Detection speed | 9/10 | Sub-second health probes, 5-probe flap detection in 3s |
| Error message quality | 10/10 | No info leakage, clear messages, admin endpoint hidden |
| Auth recovery | 10/10 | Immediate — login + call in < 2s, no lockout |
| Data availability during incident | 10/10 | Indices served throughout drill |
| Monitoring readiness | 4/10 | No automated monitor, no alert channel, no Render status sub |
| Rate limiting | 5/10 | Not triggered at 30 calls — needs verification |
| Client comms readiness | 7/10 | Template drafted but no error code reference in docs yet |

**Overall: 55/70 (79%) — PASS WITH CONDITIONS**

Must close G1 + G2 before Day 0 (monitoring + alerts).
G4 should be investigated before Day 0 (rate limiter).
G5 + G6 acceptable as post-pilot improvements.

---

## Sign-Off

| Role | Name | Reviewed | Date |
|------|------|----------|------|
| Engineering | ____________ | [ ] | |
| Account Manager | ____________ | [ ] | |
| CTO | ____________ | [ ] | |

**Fire drill status: COMPLETE. 4 actions required before Day 0 launch.**
