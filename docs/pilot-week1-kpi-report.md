# WASI Pilot — Week-1 KPI Report

**Pilot start:** 2026-03-06T15:14Z
**Report generated:** 2026-03-06 (T+0 baseline)
**Next snapshot due:** 2026-03-13 (T+7)
**Environment:** https://wasi-backend-api.onrender.com

---

## Executive Summary

WASI Backend API v4.0.0 entered production on 2026-03-06 with all data
layers live and verified. This report establishes the T+0 baseline and
defines the KPIs to be measured at T+7 for pilot evaluation.

---

## 1. Availability & Latency (T+0 Baseline)

All 10 critical endpoints returned HTTP 200 on first probe.

| Endpoint | HTTP | Latency | SLA Target |
|----------|------|---------|------------|
| GET /api/health | 200 | 604ms | < 1s |
| GET /api/indices/latest | 200 | 848ms | < 2s |
| GET /api/composite/report | 200 | 526ms | < 2s |
| GET /api/markets/latest | 200 | 812ms | < 2s |
| GET /v1/market/fx | 200 | 659ms | < 2s |
| GET /api/v2/data/commodities/latest | 200 | 491ms | < 2s |
| GET /api/v2/data/macro/CI | 200 | 543ms | < 2s |
| GET /api/v2/bank/credit-context/NG | 200 | 478ms | < 2s |
| GET /api/v2/signals/live | 200 | 470ms | < 2s |
| GET /api/country/NG/index | 200 | 796ms | < 2s |

**Baseline p50:** 570ms | **p95:** 848ms | **All within SLA**

> Note: Render free tier adds ~300-500ms cold start overhead. Paid tier
> would reduce p50 to ~100-200ms.

---

## 2. Data Freshness (T+0)

| Data Layer | Records | Period | Source | Freshness |
|------------|---------|--------|--------|-----------|
| Country Indices | 16 countries | 2024-01-01 | World Bank | Annual |
| WASI Composite | 75.93 | Q1-2024 | Calculated | 6h refresh |
| Stock Markets | 4 exchanges | 2023-12-28 | Seed historical | Static |
| Commodities | 6 prices | 2025-01-01 | WB Pink Sheet | Monthly |
| IMF Macro | 16 countries | 2025 | IMF WEO | Annual |
| FX Rates | XOF/EUR, XOF/USD | Real-time | open.er-api.com | Live |

**Confidence distribution:** 15 green, 1 yellow, 0 red

### T+7 Target
- Composite history depth: > 1 data point (scheduler should add entries)
- No regression in country count (must remain >= 16)
- Commodities: still 6 tracked, period unchanged or newer

---

## 3. Reliability (T+0)

| Metric | Baseline | Week-1 Target |
|--------|----------|---------------|
| Uptime | 100% (probe) | >= 99.0% |
| 5xx errors | 0 | < 5 total |
| Failed probes | 0/10 | < 2/10 per snapshot |
| Cold start wake | ~600ms | < 2s |
| Unhandled exceptions | 0 | 0 |

**Measurement method:** `scripts/monitor-24h.sh` runs every 10 minutes,
logs HTTP status codes. `scripts/extract-24h-report.sh` produces daily
summaries. `scripts/pilot-kpi-snapshot.sh` captures full state.

---

## 4. Credit Economy (T+0)

| Metric | Baseline | Week-1 Target |
|--------|----------|---------------|
| Registered users | 6 | Track growth |
| Free tier balance | 10.0 credits | — |
| Credits consumed (total) | 0 | Track total |
| Top endpoint by cost | — | Identify |
| Credit exhaustion events | 0 | Track |

### Credit Cost Table (reference)

| Endpoint | Cost | Category |
|----------|------|----------|
| GET /indices, /commodities, /macro | 1 cr | Read |
| GET /country/{cc}/history | 2 cr | Read |
| GET /composite/report | 3 cr | Read |
| POST /composite/calculate | 5 cr | Compute |
| POST /bank/score-dossier | 10 cr | Premium |
| POST /data/worldbank/refresh | 20 cr | Admin |

**Week-1 analysis needed:** Average credits consumed per session,
ratio of read vs. compute endpoints, credit exhaustion rate.

---

## 5. Security Posture (T+0)

| Check | Result | Status |
|-------|--------|--------|
| Unauthenticated /indices | 401 | PASS |
| Unauthenticated /composite | 401 | PASS |
| Admin seed endpoint | 403 (locked) | PASS |
| X-Content-Type-Options | nosniff | PASS |
| X-Frame-Options | DENY | PASS |
| Strict-Transport-Security | max-age=31536000 | PASS |
| X-XSS-Protection | 1; mode=block | PASS |
| Content-Security-Policy | default-src 'self' | PASS |
| Referrer-Policy | strict-origin-when-cross-origin | PASS |
| Permissions-Policy | geo=(), cam=(), mic=() | PASS |

**7/7 security headers present. 0 unauthenticated data leaks.**

---

## 6. Week-1 KPI Targets (to verify at T+7)

| KPI | Target | How to Measure |
|-----|--------|----------------|
| Uptime | >= 99.0% | monitor-24h.sh logs |
| p50 latency | < 800ms | pilot-kpi-snapshot.sh probes |
| p95 latency | < 2000ms | pilot-kpi-snapshot.sh probes |
| 5xx errors | < 5 total | monitor-24h.sh logs |
| Data layer coverage | 16 countries, 6 commodities | indices/latest + commodities/latest |
| Composite freshness | >= 2 data points | composite/report history_12m |
| Security headers | 7/7 present | pilot-kpi-snapshot.sh |
| Auth enforcement | 100% (401 on unauth) | pilot-kpi-snapshot.sh |
| Registered pilot users | >= 1 real pilot | auth/me check |
| Credit consumption | tracked | Payment/query logs |

---

## 7. How to Run

### T+7 Snapshot (run on 2026-03-13)
```bash
cd wasi-backend-api
bash scripts/pilot-kpi-snapshot.sh seed_check SeedCheck2026x
```

### Continuous Monitoring (already running)
```bash
bash scripts/monitor-24h.sh    # 10-min health probes
bash scripts/extract-24h-report.sh  # daily KPI summary
```

### Compare T+0 vs T+7
Fill in the T+7 column in sections 1-5 above. Any metric outside
its target triggers investigation before pilot expansion.

---

## 8. Client Trust Pack Contents

For pilot client delivery, package:

1. `docs/v4.0.0-production-readiness-certificate.md` — system certification
2. `docs/pilot-week1-kpi-report.md` — this report (with T+7 data filled)
3. `docs/client-onboarding-checklist.md` — integration guide
4. `docs/SECURITY_AUDIT_2026-03-03.md` — security audit
5. API access credentials (username + initial credits)

---

*Baseline captured: 2026-03-06T15:14Z | Commit: 28f40cf (main)*
