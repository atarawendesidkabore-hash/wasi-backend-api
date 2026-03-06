# WASI Billing Activation SOP

**Version:** 1.0 | **Effective:** 2026-03-06
**Audience:** Operations team, finance

---

## 1. Pricing Grid

### Credit Packs (one-time purchase)

| Pack | Credits | Price (EUR) | Price (XOF) | Per-Credit |
|------|---------|-------------|-------------|------------|
| Starter | 100 | 25 | 16,400 | 0.25 EUR |
| Growth | 500 | 100 | 65,600 | 0.20 EUR |
| Enterprise | 2,000 | 300 | 196,800 | 0.15 EUR |
| Custom | 5,000+ | Negotiated | Negotiated | < 0.15 EUR |

### Monthly Subscriptions

| Plan | Included Credits | Overage Rate | Price (EUR/mo) | Price (XOF/mo) |
|------|-----------------|--------------|----------------|-----------------|
| Free | 10 | N/A (blocked) | 0 | 0 |
| Pilot | 100 | 0.30 EUR/cr | 0 (trial) | 0 |
| Pro | 1,000 | 0.20 EUR/cr | 150 | 98,400 |
| Business | 5,000 | 0.15 EUR/cr | 500 | 328,000 |
| Enterprise | 20,000 | 0.10 EUR/cr | 1,500 | 984,000 |

### Endpoint Cost Reference

| Category | Endpoints | Cost |
|----------|-----------|------|
| Read (basic) | indices, commodities, macro, FX, signals | 1 credit |
| Read (extended) | country history, divergence | 2 credits |
| Report | composite report, forecast summary | 3-5 credits |
| Compute | composite calculate, forecast refresh | 5-20 credits |
| Premium | bank score-dossier, credit decision | 10 credits |
| Admin | data refresh (WB, IMF, etc.) | 5-20 credits |

---

## 2. Payment Providers

### Primary: PayDunya (West Africa)

Best for XOF/CFA zone clients. Supports Mobile Money + cards.

**Integration flow:**
1. Client initiates top-up via `POST /api/payment/topup`
2. Backend creates PayDunya invoice
3. Client pays via Orange Money, MTN MoMo, Wave, or card
4. PayDunya webhook confirms payment
5. Backend credits user's x402_balance

**Setup requirements:**
- PayDunya merchant account (paydunya.com)
- API keys in Render env: `PAYDUNYA_MASTER_KEY`, `PAYDUNYA_PRIVATE_KEY`, `PAYDUNYA_TOKEN`
- Webhook URL: `https://wasi-backend-api.onrender.com/api/payment/webhook/paydunya`

### Secondary: Stripe (International)

Best for EUR/USD clients outside CFA zone.

**Integration flow:**
1. Client initiates top-up
2. Backend creates Stripe Checkout session
3. Client completes payment on Stripe-hosted page
4. Stripe webhook confirms payment
5. Backend credits user's x402_balance

**Setup requirements:**
- Stripe account (stripe.com)
- API keys in Render env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- Webhook URL: `https://wasi-backend-api.onrender.com/api/payment/webhook/stripe`

---

## 3. Trial-to-Paid Conversion Flow

### Trigger Conditions

| Trigger | Action |
|---------|--------|
| Pilot Day 7 + GO decision | Send pricing proposal |
| Credits < 10% of allocation | Send low-balance warning |
| Credits = 0 | Send conversion CTA + temporary 50cr extension |
| Client requests paid access | Immediate billing setup |

### Conversion Steps

```
Step 1: Client selects plan (Pro/Business/Enterprise or credit pack)
        └─ AM sends pricing proposal via email

Step 2: Payment method setup
        ├─ CFA zone → PayDunya (Mobile Money preferred)
        └─ International → Stripe (card or bank transfer)

Step 3: First payment processed
        └─ Backend webhook credits account automatically

Step 4: Account upgrade
        ├─ Tier changes: free → pro/business/enterprise
        ├─ Rate limits adjusted (if applicable)
        └─ AM confirms via email + support channel

Step 5: Ongoing billing
        ├─ Subscription: auto-renewal monthly
        └─ Credit packs: manual top-up on demand
```

### Failure Handling

| Failure | Detection | Response |
|---------|-----------|----------|
| Payment declined | Webhook status != success | Notify client, retry in 24h |
| Webhook missed | Credit not applied after 5 min | Manual reconciliation via dashboard |
| Double charge | Duplicate webhook events | Idempotency key check (built into API) |
| Subscription lapse | No renewal after 30 days | Grace period 7 days, then downgrade to free |
| Refund request | Client email | Process within 48h, deduct equivalent credits |
| Disputed charge | Stripe/PayDunya alert | Freeze account, investigate, resolve in 5 days |

---

## 4. Credit Management Operations

### Manual Top-Up (admin)

For pilot clients or special arrangements:

```bash
# Via API (requires admin user)
curl -X POST https://wasi-backend-api.onrender.com/api/payment/topup \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "method": "admin_grant", "note": "Pilot allocation"}'
```

### Balance Alerts

| Threshold | Action |
|-----------|--------|
| < 20% of plan credits | Email: "Low balance" warning |
| < 5 credits | Email: "Critical — top up now" |
| 0 credits | API returns 402, email: conversion CTA |
| Negative balance (bug) | P1 alert to engineering |

### Credit Audit

Monthly reconciliation:
1. Sum all X402Transaction records for the period
2. Compare against payment provider totals
3. Variance > 1% triggers investigation
4. Archive report in `docs/billing/` directory

---

## 5. Subscription Lifecycle

```
FREE (10 cr)
  │
  ├─ Top-up ──→ FREE + credits (no tier change)
  │
  └─ Subscribe ──→ PRO (1000 cr/mo)
                    │
                    ├─ Upgrade ──→ BUSINESS (5000 cr/mo)
                    │               │
                    │               └─ Upgrade ──→ ENTERPRISE (20000 cr/mo)
                    │
                    ├─ Downgrade ──→ FREE (at period end)
                    │
                    └─ Lapse ──→ 7-day grace ──→ FREE
```

### Cancellation Policy

- Client can cancel anytime
- Access continues until end of billing period
- Unused credits expire at period end (no rollover on free/pilot)
- Pro+ plans: unused credits roll over for 1 month
- Refund: pro-rata for annual plans, no refund for monthly

---

## 6. Tax & Compliance

| Region | Tax | Rate | Notes |
|--------|-----|------|-------|
| WAEMU (CFA zone) | TVA | 18% | Required for B2B in CI, SN, BF, ML, BJ, TG, NE, GW |
| Nigeria | VAT | 7.5% | Required for NG-registered entities |
| Ghana | VAT + NHIL + GETFund | 15.5% | Combined levy |
| EU | VAT | 20% (varies) | Reverse charge for B2B |
| Other | None | 0% | Until local nexus established |

**Invoice requirements:**
- Company name, address, tax ID
- Service description: "WASI API access — economic intelligence data services"
- Credit quantity and unit price
- Tax amount (if applicable)
- Payment reference number

---

## 7. Implementation Checklist

| Phase | Task | Status |
|-------|------|--------|
| 1 | Choose primary payment provider (PayDunya or Stripe) | [ ] |
| 2 | Create merchant account + obtain API keys | [ ] |
| 3 | Set env vars on Render dashboard | [ ] |
| 4 | Implement payment webhook endpoint | [ ] |
| 5 | Test end-to-end payment flow (sandbox) | [ ] |
| 6 | Configure balance alert emails | [ ] |
| 7 | Set up monthly credit audit process | [ ] |
| 8 | Publish pricing page (frontend or static) | [ ] |
| 9 | First paid transaction processed | [ ] |

**Current state:** Credit system (x402) is live. Payment provider integration
is the next engineering task to enable self-service billing.
