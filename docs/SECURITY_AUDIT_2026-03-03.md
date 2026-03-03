# WASI Backend API — Full Security & Psychological Risk Audit

**Date:** 2026-03-03
**Scope:** Complete codebase scan — auth, API, eCFA CBDC, tokenization, USSD, social engineering
**Classification:** CONFIDENTIAL — Internal Use Only
**Auditor:** Automated static analysis + architecture review

---

## Executive Summary

**72 total findings** across 4 audit domains:

| Severity | Count | Domains |
|----------|-------|---------|
| CRITICAL | 12 | eCFA ledger, auth, USSD, data privacy |
| HIGH | 22 | Race conditions, privilege escalation, phishing, Sybil |
| MEDIUM | 23 | AML gaps, CORS, password policy, cognitive exploitation |
| LOW | 15 | Info leakage, CSP headers, audit logging |

**Top 5 risks requiring immediate action before production:**

1. **Any user can mint unlimited eCFA** — no admin role check on mint/burn/policy endpoints
2. **Any user can transfer from any wallet** — no wallet ownership verification + optional auth
3. **Free money via topup endpoint** — no payment gateway verification
4. **Unsalted phone hashing** — all 16 countries' phone numbers reversible via rainbow table
5. **Any user can register as MNO provider** — full USSD impersonation capability

---

## SECTION 1: Authentication & Authorization

### [C1] CRITICAL — Topup Endpoint Gives Free Credits (No Payment Verification)
- **File:** `src/routes/payment.py:11-46`
- **Issue:** `POST /api/payment/topup` lets any authenticated user add up to 10,000 credits by providing an amount + reference_id. No payment gateway, no admin check.
- **Attack:** Register → topup 10,000 credits → access all premium endpoints for free.
- **Fix:** Restrict to admin-only OR integrate a real payment gateway (Flutterwave/Stripe).

### [C2] CRITICAL — No Admin Role Enforcement on eCFA Admin Endpoints
- **Files:** `src/routes/cbdc_admin.py`, `cbdc_monetary_policy.py`, `cbdc_transaction.py:141-183`
- **Issue:** All 35+ admin/policy endpoints use only `get_current_user` — any JWT holder can mint eCFA, change BCEAO rates, run settlements, resolve AML alerts.
- **Attack:** Register → call `POST /api/v3/ecfa/tx/mint` with any CENTRAL_BANK wallet_id → unlimited eCFA.
- **Fix:** Add `Depends(require_cbdc_role(["CENTRAL_BANK"]))` to all admin mutation endpoints.

### [C3] CRITICAL — No Wallet Ownership Check on Transfers
- **File:** `src/engines/cbdc_ledger_engine.py:192-329`, `src/routes/cbdc_transaction.py:37-62`
- **Issue:** `sender_wallet_id` is accepted from request body. Never verified that `current_user` owns the sender wallet.
- **Attack:** User A sends from User B's wallet by specifying B's wallet_id.
- **Fix:** Verify `wallet.user_id == current_user.id` before transfer.

### [C4] CRITICAL — Transfer Authentication is Entirely Optional
- **File:** `src/engines/cbdc_ledger_engine.py:232-244`
- **Issue:** PIN check only if `channel=="USSD" and pin`. Signature check only if `channel=="API" and signature`. No `else` clause → `channel="BATCH"` bypasses everything.
- **Fix:** Require mandatory auth for all channels. Add `else: raise 401`.

### [H1] HIGH — No Token Revocation / No Logout
- **File:** `src/utils/security.py` (entire file)
- **Issue:** No logout endpoint, no token blacklist. Compromised tokens valid for 60 minutes.
- **Fix:** Add JWT ID (`jti`), token blacklist table, `POST /api/auth/logout`.

### [H2] HIGH — No JWT ID (`jti`) — Token Replay
- **File:** `src/utils/security.py:22-28`
- **Issue:** No unique identifier per token. Can't revoke individual tokens.
- **Fix:** Add `"jti": uuid4().hex` to payload.

### [H3] HIGH — Credit Deduction Race Condition (TOCTOU)
- **File:** `src/utils/credits.py:35-56`
- **Issue:** Read balance → check → subtract → commit. Two concurrent requests can double-spend.
- **Fix:** Atomic SQL: `UPDATE users SET balance = balance - :cost WHERE id = :id AND balance >= :cost`.

### [H4] HIGH — Wallet Type Self-Assignment (Privilege Escalation)
- **File:** `src/routes/cbdc_wallet.py:40-113`
- **Issue:** Any user can create a `CENTRAL_BANK` wallet (costs 2 credits). This wallet passes `wallet_type` checks in mint/burn.
- **Fix:** Restrict institutional wallet types to admin creation only.

### [H5] HIGH — No Ownership Check on Freeze/Unfreeze
- **File:** `src/routes/cbdc_wallet.py:190-225`
- **Issue:** Combined with H4, any user can freeze any other user's wallet (DoS).
- **Fix:** Verify `admin_wallet.user_id == current_user.id` + restrict CENTRAL_BANK creation.

### [H6] HIGH — Monetary Policy Changeable by Any User
- **File:** `src/routes/cbdc_monetary_policy.py:76-99`
- **Issue:** Any user with 20 credits can change BCEAO interest rates.
- **Fix:** Add role check + multi-signature approval workflow.

### [H7] HIGH — Broken Signature Verification (Server-Side Nonce)
- **File:** `src/engines/cbdc_ledger_engine.py:236-244`
- **Issue:** Server generates a new random nonce, but client signed with a different nonce. Verification always fails → users learn to skip signatures → unauthenticated path.
- **Fix:** Client-provided nonce validated for uniqueness, or server-issued nonce via separate endpoint.

### [M1] MEDIUM — 60-Minute Token Expiry (Too Long for Financial API)
- **File:** `src/config.py:13`
- **Fix:** Reduce to 15 min + add refresh token rotation.

### [M2] MEDIUM — No Account Lockout After Failed Logins
- **File:** `src/routes/auth.py:38-61`
- **Issue:** Rate limit is per-IP, not per-username. Botnet can brute-force.
- **Fix:** Track failed attempts per username + progressive lockout.

### [M3] MEDIUM — No Password Complexity Beyond Length
- **File:** `src/schemas/auth.py:9`
- **Fix:** Require uppercase + lowercase + digit + special char.

### [M4] MEDIUM — User Enumeration via Registration Errors
- **File:** `src/routes/auth.py:20-23`
- **Fix:** Return generic "Registration failed" for both username/email collisions.

### [M5] MEDIUM — CORS Credentials + Expandable Origins
- **File:** `src/main.py:384-390`
- **Fix:** Validate that `CORS_ORIGINS` never contains `"*"` when `allow_credentials=True`.

### [M6] MEDIUM — No HSTS Header
- **File:** `src/main.py:370-378`
- **Fix:** Add `Strict-Transport-Security: max-age=63072000; includeSubDomains`.

### [M7] MEDIUM — Float Arithmetic for Financial Balances
- **Files:** All `Float` columns in `cbdc_models.py`, `models.py`, `tokenization_models.py`
- **Issue:** IEEE 754 float can't represent 0.1 exactly. Accumulated rounding errors in financial ops.
- **Fix:** Use `Numeric(18,2)` in DB + Python `Decimal` for all money math.

### [L1] LOW — Swagger UI Exposed in Production
- **Fix:** Set `docs_url=None, redoc_url=None` when `DEBUG=False`.

### [L2] LOW — No `aud`/`iss` Claims in JWT
- **Fix:** Add `"iss": "wasi-backend-api"`, `"aud": "wasi-api"` to token payload.

### [L3] LOW — CBDC Role Error Leaks Allowed Wallet Types
- **File:** `src/utils/security.py:96`
- **Fix:** Return generic "Insufficient permissions."

### [L4] LOW — Sequential User ID in JWT `sub`
- **Fix:** Use UUID `public_id` instead of auto-increment integer.

---

## SECTION 2: Injection & Input Validation

### [M8] MEDIUM — No IDOR Protection on eCFA Wallet Queries
- **Files:** `src/routes/cbdc_wallet.py:116-163`, `cbdc_transaction.py:186-256`
- **Issue:** Any user can query any wallet's balance, info, and full transaction history.
- **Fix:** Add `wallet.user_id == current_user.id` to all queries.

### [M9] MEDIUM — Stored XSS Risk via USSD Text Fields
- **File:** `src/engines/ussd_engine.py:161`
- **Issue:** USSD text input stored directly in DB. If rendered in admin dashboard: XSS.
- **Fix:** Sanitize inputs, strip HTML tags, enforce character whitelist.

### [M10] MEDIUM — Registration Race Condition (Unhandled IntegrityError)
- **File:** `src/routes/auth.py:20-34`
- **Fix:** Wrap in try/except for `IntegrityError` → return 409.

### [L5] LOW — No Content-Security-Policy Header
- **Fix:** Add CSP for Swagger UI page.

**SQL Injection:** Not found. SQLAlchemy ORM with parameterized queries throughout.
**Command Injection:** Not found. No subprocess/os.system calls with user input.
**Path Traversal:** Not found. No file operations with user-controlled paths.
**Deserialization:** Not found. No pickle/yaml loads.

---

## SECTION 3: Financial System (eCFA CBDC + Tokenization)

### [C5] CRITICAL — Double-Spend via Balance Check Race Condition
- **File:** `src/engines/cbdc_ledger_engine.py:248`
- **Issue:** Balance check and debit are not atomic. Two concurrent transfers can both pass the check.
- **Fix:** Move balance check inside `_execute_double_entry()` under `FOR UPDATE` lock. Add `CHECK (balance_ecfa >= 0)`.

### [H8] HIGH — Tax Credit Cap Bypass via Concurrent Submissions
- **File:** `src/engines/tokenization_engine.py:228-244`
- **Issue:** Cumulative cap read-check-write is not atomic. Two simultaneous submissions can exceed 5M CFA.
- **Fix:** `SELECT ... FOR UPDATE` on cumulative query.

### [H9] HIGH — Cross-Validation Gameable with Fake Phone Hashes
- **File:** `src/engines/tokenization_engine.py:527-566`
- **Issue:** Only 3 unique phone_hashes needed. Attacker generates fake SHA-256 hashes.
- **Fix:** OTP phone verification, velocity checks, geographic proof.

### [H10] HIGH — Inspector Role Self-Declared (Milestone Fraud)
- **File:** `src/routes/tokenization.py:291-329`
- **Issue:** `verifier_type` comes from request body. Anyone claims INSPECTOR (3x weight).
- **Fix:** Derive `verifier_type` from user profile, not request parameter.

### [M11] MEDIUM — AML Pre-Screen Never Called
- **File:** `src/engines/cbdc_compliance_engine.py:61-106`
- **Issue:** `pre_screen()` exists but is never invoked from `transfer()`. Large transactions never blocked.
- **Fix:** Call `compliance_engine.pre_screen()` before executing double entry.

### [M12] MEDIUM — Citizen Payments Auto-Approved at Low Confidence
- **File:** `src/engines/tokenization_engine.py:106-200`
- **Issue:** `payment_status="approved"` set at creation with confidence=0.30.
- **Fix:** Set initial status to `"pending"`, approve only after cross-validation.

### [M13] MEDIUM — Settlement Double-Counting (Transactions Not Marked Settled)
- **File:** `src/engines/cbdc_settlement_engine.py:35-125`
- **Fix:** Add `settled_at` column, filter out settled transactions.

### [M14] MEDIUM — PIN Change Without Current PIN
- **File:** `src/routes/cbdc_wallet.py:166-187`
- **Fix:** Require current PIN to set new PIN.

### [M15] MEDIUM — Batch Payments Bypass Transfer Auth
- **File:** `src/engines/tokenization_engine.py:812-852`
- **Issue:** `channel="BATCH"` with no PIN/signature → unauthenticated central bank transfer.
- **Fix:** Require system-level service auth for batch channel.

### [M16] MEDIUM — Collateral Registration Has No Auth
- **File:** `src/routes/cbdc_monetary_policy.py:319-361`
- **Issue:** Any user can register fake collateral with arbitrary value → borrow against it.
- **Fix:** Restrict to CENTRAL_BANK role + verification workflow.

### [M17] MEDIUM — Daily Spent Reset Exploitable
- **File:** `src/engines/cbdc_ledger_engine.py:536-567`
- **Fix:** Atomic daily reset + tracking under DB lock.

### [L6] LOW — Balance Verification Tolerance (0.01 XOF)
- **Fix:** After switching to Decimal, reduce to exact match.

---

## SECTION 4: USSD Technical Security

### [C6] CRITICAL — Session Hijacking (No Session-Phone Binding)
- **File:** `src/engines/ussd_engine.py:146-241`
- **Issue:** `sessionId` from MNO gateway is trusted blindly. Attacker can inject into victim's session.
- **Fix:** Bind `(sessionId, phoneNumber)` on first interaction, reject mismatches.

### [C7] CRITICAL — No PIN Brute-Force Protection
- **File:** `src/engines/cbdc_ussd_engine.py:523-530`
- **Issue:** 4-digit PIN = 10,000 combinations. Zero rate limiting on attempts.
- **Fix:** Lock wallet after 3-5 failures, exponential backoff, SMS alert.

### [H11] HIGH — Phone Number Enumeration via Wallet Lookup
- **File:** `src/engines/cbdc_ussd_engine.py:168-172`
- **Fix:** Return same response regardless of wallet existence.

### [H12] HIGH — No Server-Side Session Timeout
- **File:** `src/engines/ussd_engine.py`
- **Fix:** Reject callbacks for sessions older than 120 seconds.

### [H13] HIGH — USSD Replay Attacks (No Nonce/Timestamp)
- **File:** `src/routes/ussd.py:75-106`
- **Fix:** Add request-level nonce + completed-session rejection.

### [H14] HIGH — Unsalted SHA-256 Phone Hashing (Rainbow Table)
- **File:** `src/engines/ussd_engine.py:121-123`
- **Issue:** SHA-256 of phone number. ~2 billion hashes for all West African numbers = ~1 hour on GPU.
- **Fix:** Use `HMAC-SHA256(SECRET, phone)` with server-side secret key.

### [H15] HIGH — No Request Signing on USSD Gateway
- **File:** `src/routes/ussd.py:75-106`
- **Issue:** Only `X-Provider-Key` header. No request signatures, no IP whitelist.
- **Fix:** HMAC request signing per provider + IP whitelist.

### [H16] HIGH — Any User Can Register as MNO Provider
- **File:** `src/routes/ussd.py:521-561`
- **Issue:** Only costs 10 credits. Gives full USSD impersonation capability.
- **Fix:** Admin-only provider registration + approval workflow.

### [M18] MEDIUM — No Rate Limiting on USSD Callback
- **Fix:** Per-provider + global rate limiting.

---

## SECTION 5: Psychological & Social Engineering Risks

### [C8] CRITICAL — BCEAO/Government Trust Exploitation
- **Risk:** Platform uses official BCEAO branding. Scammers create clone USSD menus on different shortcodes to steal PINs.
- **Mitigation:** Official MNO shortcode registration + per-session verification codes + "never share PIN" warnings.

### [C9] CRITICAL — Fake USSD Menu + SMS Phishing
- **Risk:** Menu structure is public. Bulk SMS ($0.01/msg) directs victims to fake shortcode.
- **Mitigation:** Transaction SMS confirmations + user-chosen security phrases + OTP for high-value ops.

### [C10] CRITICAL — Data Weaponization / Surveillance Risk
- **Risk:** Platform collects location, financial, trade, labor, and social graph data across 16 countries. Combined with reversible phone hashes, enables complete individual profiling.
- **Mitigation:** Data minimization, 90-day individual data expiry, differential privacy, DPIA under ECOWAS data protection laws, independent data governance board.

### [H17] HIGH — SIM Farm Data Fraud for Payments
- **Risk:** 3 SIMs → 3 fake phone_hashes → pass cross-validation → earn payments for false data.
- **Mitigation:** OTP verification, velocity checks, geographic proof, trust scores.

### [H18] HIGH — Cognitive Exploitation of Low-Literacy Users
- **Risk:** 9 menu options, French-only, no undo, deep sub-menus confuse illiterate users.
- **Mitigation:** Language selection, reduce to 4-5 options, "0 = Cancel" at every step, IVR for illiterate users.

### [H19] HIGH — Authority Impersonation (Self-Declared Inspectors)
- **Risk:** Anyone claims INSPECTOR role. Fake WASI agents visit rural villages to collect PINs.
- **Mitigation:** Verified inspector registry, digital credentials, public verification hotline.

### [H20] HIGH — Coordinated Milestone Verification Fraud
- **Risk:** 3 colluding "inspectors" auto-verify milestones → release large payments for unfinished work.
- **Mitigation:** Pre-registered inspector pool, geographic proximity checks, multi-day verification window.

### [M19] MEDIUM — Fear/Urgency Exploitation via Fake Compliance Alerts
- **Mitigation:** Never include PIN requests in push notifications + message authenticity codes.

### [M20] MEDIUM — Information Asymmetry (API vs USSD Users)
- **Risk:** API traders exploit forecasts from data generated by USSD farmers.
- **Mitigation:** USSD trend alerts, data dividends for contributors, free API tier for USSD users.

### [M21] MEDIUM — Platform Dependency for Income/Wages
- **Mitigation:** Offline fallback mechanisms, paper receipts, data portability, SLA commitments.

---

## SECTION 6: Remediation Priority Matrix

### Immediate (Block Production Deployment)

| # | Finding | Effort | Impact |
|---|---------|--------|--------|
| C1 | Topup without payment verification | 1h | Free money for all users |
| C2 | No admin role on eCFA endpoints | 2h | Anyone can mint unlimited eCFA |
| C3 | No wallet ownership on transfers | 1h | Drain any wallet |
| C4 | Optional transfer authentication | 30m | Bypass all wallet security |
| C5 | Balance check race condition | 2h | Double-spend attacks |
| C6 | USSD session hijacking | 1h | Hijack financial operations |
| C7 | No PIN brute-force protection | 1h | Crack any 4-digit PIN |
| H4 | Wallet type self-assignment | 30m | Escalate to CENTRAL_BANK |
| H14 | Unsalted phone hashing | 2h | Reverse all user identities |
| H16 | Any user registers as MNO provider | 30m | Full USSD impersonation |

### Before Public Launch

| # | Finding | Effort |
|---|---------|--------|
| H1-H2 | Token revocation + JWT IDs | 4h |
| H3 | Credit deduction race condition | 1h |
| H6 | Monetary policy role check | 1h |
| H8-H10 | Tax credit/cross-validation/inspector fixes | 6h |
| M7 | Float → Decimal for money columns | 8h (migration) |
| M11 | Integrate AML pre-screen into transfers | 2h |
| M12 | Pending (not approved) initial payment status | 30m |

### Ongoing / Hardening

| # | Finding | Effort |
|---|---------|--------|
| M1-M6 | Token expiry, lockout, password, CORS, HSTS | 4h |
| M8 | IDOR protection on wallet queries | 2h |
| M14-M17 | PIN change, batch auth, collateral, daily reset | 4h |
| S-01 to S-10 | Social engineering mitigations | Ongoing program |

---

## Appendix: Positive Security Controls Already In Place

Credit where due — these are correctly implemented:

1. **Production secret key guard** — `config.py:41-46` raises RuntimeError if default key used in prod
2. **Bcrypt password hashing** — `passlib` with auto-deprecation
3. **Rate limiting on auth** — login 10/min, register 5/min via `slowapi`
4. **JWT algorithm pinned** — prevents algorithm confusion attacks
5. **Security headers middleware** — X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
6. **Input validation** — Username regex, EmailStr, min-length password
7. **Topup idempotency** — Duplicate reference_id rejected with 409
8. **Username sanitization** — Blocks `<>&"'/;` characters
9. **SQLAlchemy ORM** — No raw SQL anywhere = no SQL injection
10. **Phone number hashing** — Privacy by design (needs salt upgrade)
11. **Double-entry ledger** — Correct accounting structure for CBDC
12. **Compliance engine** — AML/CFT framework built (needs integration)
13. **ML guardrails** — Data quality gates, Platt scaling, human-in-the-loop flags

---

*End of audit. This report should be reviewed by a qualified security professional before acting on the findings.*
