# WASI Weekly Executive Dashboard

**Template version:** 1.0 | **Created:** 2026-03-06
**Frequency:** Every Monday, covering prior 7 days
**Audience:** CEO, CTO, Head of Sales

---

## Week of: ____/____/2026

### Traffic Light Summary

| Domain | Status | Notes |
|--------|--------|-------|
| Revenue (MRR) | ___ | |
| Activation | ___ | |
| Reliability | ___ | |
| Data Quality | ___ | |
| Security | ___ | |

Legend: GREEN = on track | YELLOW = needs attention | RED = action required

---

## 1. Revenue & Commercial

| Metric | This Week | Last Week | Delta | Target |
|--------|-----------|-----------|-------|--------|
| MRR (EUR) | | | | |
| Total paying clients | | | | |
| New registrations | | | | |
| Pilot → Paid conversions | | | | |
| Credits purchased | | | | |
| Credits consumed | | | | |
| Revenue per client (avg) | | | | |
| ARPU (EUR/mo) | | | | |

### Pipeline

| Stage | Count | Expected Revenue |
|-------|-------|-----------------|
| Lead (contacted) | | |
| Pilot (active) | | |
| Negotiation | | |
| Closed-Won | | |
| Closed-Lost | | |

### Churn Risk

| Client | Plan | Last API Call | Days Silent | Risk | Action |
|--------|------|---------------|-------------|------|--------|
| | | | | | |

Churn definition: No API call in 7+ days for paid client.

---

## 2. Activation & Engagement

| Metric | This Week | Last Week | Delta |
|--------|-----------|-----------|-------|
| Registered users (total) | | | |
| Active users (>=1 call/week) | | | |
| Activation rate (%) | | | |
| Avg calls per active user | | | |
| Median session duration | | | |

### Top Endpoints by Volume

| # | Endpoint | Calls | % of Total |
|---|----------|-------|------------|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

### Feature Adoption

| Feature | Users | % Adoption | Trend |
|---------|-------|------------|-------|
| Indices (basic) | | | |
| Composite report | | | |
| FX rates | | | |
| Bank credit scoring | | | |
| Commodities | | | |
| IMF macro | | | |
| Forecast | | | |
| USSD | | | |
| eCFA CBDC | | | |
| Chat/AI | | | |

---

## 3. Reliability & Performance

| Metric | This Week | SLA Target | Status |
|--------|-----------|------------|--------|
| Uptime (%) | | >= 99.0% | |
| p50 latency (ms) | | < 800 | |
| p95 latency (ms) | | < 2000 | |
| 5xx errors (total) | | < 10/week | |
| 4xx errors (total) | | monitor | |
| Cold start events | | monitor | |
| Scheduled tasks completed | | 100% | |

### Incidents

| Date | Severity | Duration | Root Cause | Resolution |
|------|----------|----------|------------|------------|
| | | | | |

### Scheduler Health

| Task | Frequency | Last Run | Status |
|------|-----------|----------|--------|
| Composite update | 6h | | |
| News sweep | 1h | | |
| USSD aggregation | 4h | | |
| Forecast recalc | Daily 04:00 | | |
| Token payments | Daily 20:00 | | |

---

## 4. Data Quality

| Data Layer | Records | Freshness | Confidence | Status |
|------------|---------|-----------|------------|--------|
| Country Indices | /16 | | | |
| Composite | | | | |
| Stock Markets | /4 | | | |
| Commodities | /6 | | | |
| IMF Macro | /16 | | | |
| FX Rates | | | | |
| News Events | | | | |
| USSD Aggregates | | | | |

### Data Gaps

| Gap | Impact | ETA to Fix |
|-----|--------|------------|
| | | |

---

## 5. Security & Compliance

| Check | Status | Last Verified |
|-------|--------|---------------|
| Auth enforcement (401 on unauth) | | |
| Security headers (7/7) | | |
| Admin seed locked | | |
| No exposed credentials | | |
| Rate limiting active | | |
| CORS properly scoped | | |

### Access Audit

| Event | Count |
|-------|-------|
| Successful logins | |
| Failed logins | |
| 403 Forbidden | |
| Rate limit hits (429) | |

---

## 6. Engineering Velocity

| Metric | This Week |
|--------|-----------|
| Commits to main | |
| Deploys to production | |
| Open issues | |
| Issues closed | |
| Test pass rate | |

### Next Sprint Priorities

| Priority | Task | Owner | ETA |
|----------|------|-------|-----|
| P1 | | | |
| P2 | | | |
| P3 | | | |

---

## 7. Key Decisions Needed

| Decision | Context | Options | Deadline |
|----------|---------|---------|----------|
| | | | |

---

## 8. How to Populate This Dashboard

### Automated (run weekly)

```bash
# KPI snapshot (availability, latency, data freshness, security)
bash scripts/pilot-kpi-snapshot.sh <username> <password>

# 24h monitoring summary (if monitor-24h.sh is running)
bash scripts/extract-24h-report.sh
```

### Manual (requires DB access or admin API)

- Revenue/credits: Query X402Transaction table
- User counts: Query User table
- Endpoint volume: Query QueryLog table
- Error rates: Render dashboard logs or structured logging

### Data Sources

| Metric | Source |
|--------|--------|
| Revenue, credits | X402Transaction + payment provider dashboard |
| Users, activation | User table + QueryLog |
| Latency, errors | pilot-kpi-snapshot.sh + Render metrics |
| Data quality | /api/indices/latest + /api/v2/data/status |
| Security | pilot-kpi-snapshot.sh security posture section |
| Engineering | GitHub (commits, issues) |
| Pipeline | CRM (manual entry) |

---

*Fill every Monday. Archive completed dashboards in `docs/dashboards/YYYY-MM-DD.md`.*
