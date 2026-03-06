# WASI — Pilot Agreement & Service Level Agreement

**Document ref:** WASI-PILOT-SLA-001
**Effective date:** ___/___/2026
**Duration:** 14 calendar days from effective date
**Parties:**

| Role | Entity |
|------|--------|
| Provider | WASI (West African Shipping Intelligence) |
| Client | __________________________________ |
| Client contact | __________________________________ |
| Client email | __________________________________ |

---

## 1. Scope of Service

During the pilot period, Client receives access to the WASI API platform
for evaluation purposes, including:

- **WASI Composite Index** — weighted economic health score across 16 ECOWAS countries
- **Country-level indices** — per-country shipping & economic indicators
- **Market data** — stock exchanges (NGX, GSE, BRVM), commodity prices, FX rates
- **Macroeconomic data** — IMF WEO indicators (GDP, inflation, debt, current account)
- **Credit advisory** — bank credit context and scoring (advisory only, non-binding)
- **Live signals** — news-driven index adjustments
- **AI analysis** — natural language financial analysis (when available)

### Excluded from Pilot

- Custom endpoint development
- Dedicated infrastructure or SLA guarantees beyond this document
- Historical data exports exceeding 12 months
- White-label or embedded redistribution rights

---

## 2. Pilot Terms

| Term | Value |
|------|-------|
| Duration | 14 days |
| Credit allocation | 100 credits (non-rollover) |
| Cost | EUR 0 (evaluation grant) |
| Users | 1 API account |
| Rate limit | 60 requests/minute |
| Support window | Mon-Fri 09:00-18:00 UTC |
| Support channel | Email + WhatsApp |
| Response time | See Section 5 |

### Credit Consumption

| Operation | Cost | Example |
|-----------|------|---------|
| Basic read | 1 credit | Indices, FX, commodities, macro |
| Extended read | 2 credits | Country history (12 months) |
| Report | 3-5 credits | Composite report, forecast |
| Premium | 10 credits | Bank credit dossier |

100 credits allow approximately 80-100 basic queries or 10 full credit
assessments during the pilot period.

---

## 3. Service Level Targets

These are targets, not contractual guarantees, during the pilot period.
Contractual SLAs apply upon paid conversion (Section 7).

### Availability

| Metric | Target |
|--------|--------|
| Monthly uptime | >= 99.0% |
| Planned maintenance window | Sundays 02:00-04:00 UTC |
| Maintenance notice | 24 hours in advance |

Uptime = (total minutes - downtime minutes) / total minutes x 100.
Downtime excludes: planned maintenance, force majeure, client-side issues.

### Performance

| Metric | Target |
|--------|--------|
| API response time (p50) | < 800ms |
| API response time (p95) | < 2,000ms |
| API response time (p99) | < 5,000ms |

Measured from Render edge to response. Does not include client network latency.

### Data Freshness

| Data Layer | Update Frequency | Target Staleness |
|------------|-----------------|-----------------|
| Country indices | Annual (World Bank) | < 12 months |
| Composite index | Every 6 hours | < 6 hours |
| FX rates | Real-time (per request) | < 1 minute |
| Commodity prices | Monthly (WB Pink Sheet) | < 45 days |
| IMF macro | Annual (WEO release) | < 12 months |
| News signals | Hourly (RSS sweep) | < 2 hours |

---

## 4. Data Use & Restrictions

### Client May

- Query the API for internal business evaluation
- Integrate API responses into internal dashboards or tools
- Share aggregated insights derived from WASI data internally
- Provide feedback to improve the service

### Client May Not

- Redistribute raw API data to third parties
- Resell, sublicense, or white-label WASI data
- Use automated tools to bulk-download historical data
- Attempt to reverse-engineer index calculation methodology
- Share API credentials with unauthorized personnel
- Use the service for any unlawful purpose

### Data Disclaimer

WASI data is provided for **informational and advisory purposes only**.

- Index values, credit scores, and signals are **not financial advice**
- All credit decisions carry `human_review_required: true`
- WASI is not a licensed credit bureau, rating agency, or financial advisor
- Client bears sole responsibility for decisions made using WASI data

---

## 5. Support & Escalation

### Support Tiers

| Severity | Definition | Response Target | Resolution Target |
|----------|-----------|-----------------|-------------------|
| P1 Critical | API completely unavailable | 1 hour | 4 hours |
| P2 High | Data stale > 24h or key endpoint broken | 4 hours | 24 hours |
| P3 Medium | Non-critical endpoint error, degraded performance | 8 hours (business) | 48 hours |
| P4 Low | Feature request, documentation question | 24 hours (business) | Best effort |

### Contact

| Channel | Address | Hours |
|---------|---------|-------|
| Email | [________________] | Mon-Fri 09:00-18:00 UTC |
| WhatsApp | [________________] | Mon-Fri 09:00-18:00 UTC |
| Emergency | [________________] | P1 only, 24/7 |

### Escalation Path

```
Client contact → Support email/WhatsApp
     └─ No response in SLA → Emergency contact
          └─ No response in 2x SLA → Account Manager direct
               └─ No resolution in 24h → CTO escalation
```

---

## 6. Pilot Evaluation

### Checkpoints

| Day | Activity | Gate |
|-----|----------|------|
| 0 | Kickoff call, credential delivery, first 4 API calls | All 4 calls succeed |
| 3 | First checkpoint: adoption review | >= 20 calls, >= 3 endpoints |
| 7 | Mid-pilot survey (NPS + feature feedback) | NPS >= 6 |
| 14 | Final review: GO / EXTEND / STOP decision | See criteria below |

### Conversion Criteria (Day 14)

| Signal | Decision |
|--------|----------|
| >= 100 API calls + NPS >= 8 + conversion intent | **GO** — proceed to paid |
| 50-99 calls or NPS 6-7 | **EXTEND** — 14-day extension |
| < 50 calls or NPS < 6 | **STOP** — close pilot |

---

## 7. Post-Pilot: Paid Service Terms

Upon conversion, the following contractual SLAs replace the pilot targets:

### Paid SLA Guarantees

| Plan | Uptime SLA | p95 Latency | Support | Credits/mo |
|------|-----------|-------------|---------|------------|
| Pro | 99.5% | < 1,500ms | Email, 8h response | 1,000 |
| Business | 99.7% | < 1,000ms | Email + WhatsApp, 4h response | 5,000 |
| Enterprise | 99.9% | < 800ms | Dedicated, 1h response | 20,000 |

### SLA Credits (paid plans only)

| Uptime Achieved | Service Credit |
|----------------|---------------|
| 99.0% - SLA target | 10% of monthly fee |
| 95.0% - 98.9% | 25% of monthly fee |
| < 95.0% | 50% of monthly fee |

Service credits are applied to the next billing cycle. Maximum credit:
50% of monthly fee. Credits do not apply during pilot period.

### Pricing

| Plan | EUR/month | XOF/month | Included Credits | Overage |
|------|-----------|-----------|-----------------|---------|
| Pro | 150 | 98,400 | 1,000 | 0.20 EUR/cr |
| Business | 500 | 328,000 | 5,000 | 0.15 EUR/cr |
| Enterprise | 1,500 | 984,000 | 20,000 | 0.10 EUR/cr |

Payment methods: Mobile Money (Orange/MTN/Wave via PayDunya),
bank card (Visa/MC via Stripe), bank transfer (Enterprise only).

---

## 8. Confidentiality

Both parties agree to treat as confidential:
- API credentials and authentication tokens
- Pricing terms and commercial negotiations
- Proprietary index methodology details
- Client's usage patterns and business context

Confidentiality survives termination for 2 years.

---

## 9. Termination

Either party may terminate this pilot agreement:
- With 24 hours written notice, for any reason
- Immediately, if the other party breaches Section 4 (Data Use)
- Automatically, at the end of the 14-day pilot period (unless extended)

Upon termination:
- Client's API credentials are deactivated within 24 hours
- Unused credits expire and are non-refundable
- Client must cease use of any cached WASI data within 30 days

---

## 10. Signatures

| | Provider (WASI) | Client |
|---|----------------|--------|
| Name | ________________ | ________________ |
| Title | ________________ | ________________ |
| Date | ___/___/2026 | ___/___/2026 |
| Signature | ________________ | ________________ |

---

*This agreement is governed by the laws of [Burkina Faso / jurisdiction TBD].
Disputes shall be resolved by [arbitration / mediation] in [Ouagadougou / TBD].*

---

**Document history:**
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-03-06 | Initial draft |
