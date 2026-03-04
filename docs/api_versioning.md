# API Versioning Policy

## Version Inventory

### Unversioned — `/api/`
Core platform endpoints. Stable, never breaking.

| Prefix | Module | Endpoints |
|--------|--------|-----------|
| /api/health | health.py | GET /api/health, GET /api/health/detailed |
| /api/auth | auth.py | POST /register, POST /login, GET /me, POST /logout, POST /refresh |
| /api/indices | indices.py | GET /latest, /history, /all |
| /api/country | country.py | GET /{code}/index, /{code}/history |
| /api/composite | composite.py | POST /calculate, GET /report |
| /api/payment | payment.py | POST /topup, GET /status |

### v2 — `/api/v2/`
Stable operational layer. Production-ready.

| Prefix | Module | Description |
|--------|--------|-------------|
| /api/v2/ussd | ussd.py | USSD callback, mobile money, commodity reports |
| /api/v2/transport | transport.py | Air/rail/road transport composites |
| /api/v2/bank | bank.py | Credit context, loan advisory, dossier |
| /api/v2/data | data_admin.py | Data refresh, commodity prices, macro indicators |
| /api/v2/signals | live_signals.py | Live signals, news events |

### v3 — `/api/v3/` (Current)
Active development version. New features land here.

| Prefix | Module | Description |
|--------|--------|-------------|
| /api/v3/ecfa/wallet | cbdc_wallet.py | eCFA wallet CRUD |
| /api/v3/ecfa/tx | cbdc_transaction.py | eCFA transactions (send, mint, burn) |
| /api/v3/ecfa/admin | cbdc_admin.py | CBDC admin (policy, settlement, AML) |
| /api/v3/ecfa/payments | cbdc_payments.py | Cross-border WASI-Pay |
| /api/v3/ecfa/monetary-policy | cbdc_monetary_policy.py | BCEAO rates, reserves, facilities |
| /api/v3/forecast | forecast.py | Time-series forecasting |
| /api/v3/tokenization | tokenization.py | Data tokenization (3 pillars) |
| /api/v3/risk | risk.py | Country risk scoring |
| /api/v3/alerts | alerts.py | Alert rules and delivery |
| /api/v3/corridors | corridors.py | Trade corridor assessment |
| /api/v3/fx | fx.py | FX analytics |
| /api/v3/legislative | legislative.py | Legislative monitoring |
| /api/v3/signals | signals.py | Signal aggregation |
| /api/v3/valuation | valuation.py | Economic valuation |
| /api/v3/news | world_news.py | World news intelligence |
| /api/v3/reconciliation | reconciliation.py | Data integrity checks |

### v4 — `/api/v4/` (Experimental)
Cutting-edge features. May change without notice.

| Prefix | Module | Description |
|--------|--------|-------------|
| /api/v4/forecast | forecast_v4.py | Adaptive ensemble, Monte Carlo, scenarios |

## Policy Rules

### 1. New Features
New endpoints are added to the **current major version** (v3). Only bump to v4+ when introducing fundamentally different API contracts.

### 2. Breaking Changes
A "breaking change" is:
- Removing or renaming an endpoint
- Changing required request fields
- Changing response field names or types
- Changing authentication requirements
- Changing HTTP status codes for existing scenarios

Breaking changes **require a version bump**. The old version continues to work during the sunset window.

### 3. Non-Breaking Changes
These do NOT require a version bump:
- Adding new optional request fields
- Adding new response fields
- Adding new endpoints
- Improving error messages
- Performance improvements

### 4. Deprecation & Sunset
- Deprecated versions get a **6-month sunset window**
- Deprecated endpoints return `Sunset` and `Deprecation` headers
- After sunset, endpoints return 410 Gone

### 5. Experimental (v4)
- Endpoints may change or be removed at any time
- Not covered by the deprecation policy
- Response includes `X-API-Status: experimental` header

## Future: Content Negotiation

When needed, the API will support version negotiation via:
```
X-API-Version: 3
```
If omitted, the latest stable version is used. This header is reserved for future use.

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-02-24 | v2 | Initial v2 routes (USSD, transport, bank, data, signals) |
| 2026-02-25 | v3 | eCFA CBDC platform, tokenization, forecasting |
| 2026-03-03 | v4 | Adaptive ensemble forecast engine |
| 2026-03-04 | v3 | Risk scoring engine added |
