# WASI ECOWAS PAYMENT INTEROPERABILITY BLUEPRINT

## West African Stack for Interoperability — Technical & Financial Analysis

---

**Classification:** Confidential — For Executive Decision-Making

**Version:** 1.0

**Date:** March 2026

**Prepared by:** WASI — West African Shipping & Economic Intelligence

**Reference:** WASI/ECOWAS/INTEROP/2026-001

---

# TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [ECOWAS Payment Landscape Analysis](#2-ecowas-payment-landscape-analysis)
3. [Technical Architecture Blueprint](#3-technical-architecture-blueprint)
4. [Country-by-Country Integration Analysis](#4-country-by-country-integration-analysis)
5. [Transaction Economics](#5-transaction-economics)
6. [Financial Model — 10-Year Projections](#6-financial-model--10-year-projections)
7. [Risk Matrix](#7-risk-matrix)
8. [Regulatory Framework & Compliance](#8-regulatory-framework--compliance)
9. [Implementation Roadmap](#9-implementation-roadmap)
10. [Resource Requirements](#10-resource-requirements)
11. [Success Metrics & KPIs](#11-success-metrics--kpis)
12. [Sensitivity Analysis](#12-sensitivity-analysis)
13. [Appendices](#13-appendices)
14. [Remittance Corridor Analysis](#14-remittance-corridor-analysis)
15. [Comparable System Benchmarks](#15-comparable-system-benchmarks)
16. [PAPSS Coexistence & Integration Strategy](#16-papss-coexistence--integration-strategy)
17. [Governance & Institutional Structure](#17-governance--institutional-structure)
18. [Investment Thesis — Executive Decision Framework](#18-investment-thesis--executive-decision-framework)
19. [Conclusion](#19-conclusion)

---

# 1. EXECUTIVE SUMMARY

## The Problem

West Africa's 440 million people across 15 ECOWAS countries conduct an estimated **$120 billion** in cross-border trade annually, yet over 80% of these transactions move through informal channels — cash, hawala networks, and unregulated mobile money agents. Formal cross-border payment infrastructure is fragmented across 3 monetary zones, 9 currencies, 15 central banks, 40+ mobile money operators, and incompatible national payment switches.

A merchant in Ouagadougou selling to a buyer in Accra faces:
- 3-5 day settlement delays via correspondent banking
- 5-12% total cost (FX spread + transfer fees + intermediary charges)
- No direct mobile-to-mobile path between XOF and GHS
- Regulatory friction across WAEMU and Ghanaian jurisdictions

This friction costs ECOWAS economies an estimated **$4.8 billion annually** in dead-weight loss — funds trapped in correspondent accounts, forex premiums, informal channel fees, and lost trade that never happens because the payment cost exceeds the margin.

## The Solution

WASI proposes building the **West African Stack for Interoperability (WASI-Pay)** — a unified payment routing, clearing, and settlement layer that connects:

- **8 WAEMU countries** via the eCFA CBDC platform (built and operational)
- **Nigeria** via eNaira + NIP/NIBSS integration
- **Ghana** via eCedi + GhIPSS integration
- **5 remaining countries** via mobile money aggregation APIs (Orange, MTN, Wave, Africell)
- **Cross-border FX** via real-time multi-currency conversion engine

WASI-Pay is not a competing payment system. It is the **routing and settlement middleware** that sits between existing national systems and enables them to talk to each other — the same role that SWIFT plays globally, but purpose-built for Africa's mobile-first, CBDC-emerging reality.

## Key Figures

| Metric | Value |
|--------|-------|
| Total addressable market (ECOWAS cross-border payments) | $32.7B remittances + $20-25B formal trade + $15-25B informal |
| WASI-Pay transaction fee (average) | 0.35% of transaction value |
| Year 1 projected transaction volume | $2.4B (conservative) |
| Year 1 projected revenue | $8.4M |
| Year 5 projected transaction volume | $28.6B |
| Year 5 projected revenue | $85.7M |
| Year 10 projected transaction volume | $94.2B |
| Year 10 projected revenue | $245.0M |
| Total 10-year cumulative revenue | $1.12B |
| Initial capital investment required | $18.5M |
| Breakeven | Month 22 |
| 10-year NPV (12% discount rate) | $387M |
| 10-year IRR | 68.4% |

## Strategic Position

WASI-Pay combines three unique advantages no competitor possesses:

1. **eCFA CBDC platform** — the only operational CBDC infrastructure for WAEMU, giving us the monetary policy layer that BCEAO needs
2. **USSD data collection network** — 200,000+ citizen data reporters across ECOWAS providing the transaction origination layer for the unbanked
3. **Sovereign data contracts** — government relationships (starting with Burkina Faso) that provide regulatory cover and first-mover access to national payment infrastructure

PAPSS (Pan-African Payment and Settlement System) exists but focuses on bank-to-bank settlement. WASI-Pay extends this to **mobile money, CBDC wallets, USSD-based payments, and data income disbursements** — the layers where 80% of West African transactions actually happen.

---

# 2. ECOWAS PAYMENT LANDSCAPE ANALYSIS

## 2.1 Monetary Zones and Currencies

ECOWAS operates across three monetary zones with fundamentally different characteristics:

### Zone 1: WAEMU (West African Economic and Monetary Union)
- **Countries:** Benin, Burkina Faso, Cote d'Ivoire, Guinea-Bissau, Mali, Niger, Senegal, Togo
- **Currency:** CFA Franc (XOF) — pegged to EUR at 655.957 XOF/EUR
- **Central Bank:** BCEAO (Banque Centrale des Etats de l'Afrique de l'Ouest)
- **RTGS:** STAR-UEMOA (3,000-5,000 tx/day, CFA 800B-1.5T daily = ~$1.3-2.4B)
- **Card Switch:** GIM-UEMOA (20M+ cards, ~10,000 ATMs, ~50,000 POS, 150-200M tx/year)
- **Population:** ~140 million
- **Combined GDP:** ~$210 billion
- **Key advantage:** Single currency = zero FX friction within zone
- **Current BCEAO rates (June 2025):** Taux directeur 3.25%, marginal lending 5.25%, inflation 3.5%
- **Key constraint:** EUR peg limits monetary policy flexibility

### Zone 2: WAMZ (West African Monetary Zone)
- **Countries:** Nigeria, Ghana, Guinea, Sierra Leone, Liberia, The Gambia
- **Currencies:** NGN, GHS, GNF, SLL, LRD, GMD (6 separate currencies)
- **Central Banks:** 6 independent central banks
- **Population:** ~280 million (Nigeria alone: 230M)
- **Combined GDP:** ~$580 billion (Nigeria alone: $477B)
- **Key advantage:** Nigeria's massive market drives volume
- **Key constraint:** Currency volatility (NGN lost 70% vs USD 2022-2024)

### Zone 3: Cape Verde (Standalone)
- **Currency:** CVE — pegged to EUR at 110.265 CVE/EUR
- **Population:** ~600,000
- **GDP:** ~$2.4 billion
- **Key note:** Small market but EUR peg alignment with WAEMU

## 2.2 Current Payment Infrastructure by Country

### Tier 1: Mature Payment Ecosystems

#### Nigeria (NG) — The Giant
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 230 million | UN 2025 |
| GDP | $477 billion | IMF WEO 2024 |
| Bank accounts | 130 million | CBN 2024 |
| Mobile money accounts | 45 million | GSMA 2024 |
| NIP annual transactions (2024) | ~11 billion (30M+ daily avg) | CBN Fintech Report Feb 2026 |
| NIP growth | 120% increase in 2 years (5B in 2022 → 11B in 2024) | CBN/NIBSS |
| eNaira wallets | 13-16 million (but <2% active) | CBN 2024 |
| eNaira status | Deprioritized; CBN pivoting to NIP/AfriGO | CBN 2025 |
| AfriGO domestic card scheme | 1M+ cards, ₦70B+ value (launched Jan 2023) | NIBSS Feb 2026 |
| Connected institutions | 26 commercial banks + 100+ fintechs/PSBs | CBN |
| Agent network points | 1.5 million+ (OPay, PalmPay, MTN, Moniepoint) | Industry estimates |
| Active fintechs | 200+ | Techcabal |
| Remittance inflows | $19.5B/year (61% of ECOWAS total) | KNOMAD 2024 |
| Internet penetration | 55% | DataReportal 2025 |
| Smartphone penetration | 45% | GSMA 2025 |
| Electricity access | 62% | World Bank |

**Key systems:** NIBSS Instant Payment (NIP — 11B tx/year), AfriGO domestic card, eNaira (deprioritized), Remita, Interswitch, Flutterwave, Paystack, OPay, PalmPay, Moniepoint

**NIP fee structure (CBN-regulated):** Up to ₦5,000: ₦10 | ₦5,001-₦50,000: ₦25 | Above ₦50,000: ₦50

**Integration approach:** API integration with NIBSS NIP + AfriGO. Nigeria alone represents ~65% of ECOWAS GDP. eNaira bridge deprioritized given low adoption — direct NIP integration is the higher-value path.

#### Ghana (GH) — The Mobile Money Leader
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 34 million | UN 2025 |
| GDP | $76 billion | IMF WEO 2024 |
| Mobile money registered accounts | 60+ million (multi-SIM) | BoG 2024 |
| Mobile money active accounts (90-day) | ~20 million | BoG 2024 |
| Mobile money annual volume (2024) | GH₵1.2-1.4 trillion (~$90-100B) | BoG |
| Mobile money agents | 500,000+ | GSMA |
| GhIPSS Instant Pay (GIP) monthly | ~15-20 million tx/month | BoG Payment Systems Report |
| MMI monthly transactions | ~80-100 million/month | BoG |
| MTN MoMo active users | ~15-18 million (est. 2025, up from 10.6M Q3 2021) | MTN Group |
| eCedi pilot | Extended pilot with G+D (Giesecke+Devrient); no public launch date | BoG 2025 |
| Remittance inflows | $4.6B/year (5.8% of GDP) | KNOMAD 2024 |
| Internet penetration | 68% | DataReportal 2025 |
| Smartphone penetration | 55% | GSMA 2025 |
| Electricity access | 85% | World Bank |

**Key systems:** GhIPSS (Instant Pay + MMI), MTN MoMo (~70% market share, 15-18M active), AirtelTigo Money, Vodafone Cash, eCedi (extended pilot)

**Integration approach:** GhIPSS GIP API + Mobile Money Interoperability (MMI) switch. eCedi bridge when production-ready but not a dependency — MMI alone provides comprehensive mobile money coverage.

#### Cote d'Ivoire (CI) — WAEMU Anchor
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 29 million | UN 2025 |
| GDP | $74 billion | IMF WEO 2024 |
| Mobile money accounts | 35+ million | GSMA 2024 |
| Mobile money annual volume | $42 billion | GSMA 2024 |
| Mobile money agents | 280,000+ | GSMA |
| Orange Money users | 20+ million | Orange |
| MTN MoMo users | 10+ million | MTN |
| Wave users | 8+ million | Wave |
| Internet penetration | 52% | DataReportal 2025 |
| Smartphone penetration | 40% | GSMA 2025 |
| Electricity access | 70% | World Bank |

**Key systems:** STAR-UEMOA (BCEAO RTGS), GIM-UEMOA, Orange Money, MTN MoMo, Wave, Moov Money

**Integration approach:** Direct via eCFA CBDC platform (our own infrastructure) + BCEAO STAR-UEMOA settlement

#### Senegal (SN) — Fintech Hub
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 18 million | UN 2025 |
| GDP | $30 billion | IMF WEO 2024 |
| Mobile money accounts | 18+ million | GSMA 2024 |
| Mobile money annual volume | $18 billion | GSMA 2024 |
| Wave market share | ~55% | Wave |
| Orange Money users | 8 million | Orange |
| Internet penetration | 58% | DataReportal 2025 |
| Smartphone penetration | 45% | GSMA 2025 |
| Electricity access | 75% | World Bank |

**Key systems:** STAR-UEMOA, GIM-UEMOA, Wave (dominant), Orange Money, Free Money

**Integration approach:** Direct via eCFA CBDC platform + Wave/Orange APIs

### Tier 2: Growing Payment Ecosystems

#### Burkina Faso (BF) — WASI Home Base
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 23 million | UN 2025 |
| GDP | $21 billion | IMF WEO 2024 |
| Mobile money accounts | 14+ million | GSMA 2024 |
| Mobile money annual volume | $12 billion | GSMA 2024 |
| Orange Money users | 9 million | Orange |
| Moov Money users | 3 million | Moov |
| Internet penetration | 25% | DataReportal 2025 |
| Smartphone penetration | 25% | GSMA 2025 |
| Electricity access | 22% (rural: <5%) | World Bank |

**Key systems:** STAR-UEMOA, GIM-UEMOA, Orange Money, Moov Money

**Integration approach:** Direct via eCFA CBDC platform (sovereign data program provides user base)

#### Mali (ML)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 23 million | UN 2025 |
| GDP | $20 billion | IMF WEO 2024 |
| Mobile money accounts | 12+ million | GSMA 2024 |
| Mobile money annual volume | $10 billion | GSMA 2024 |
| Internet penetration | 30% | DataReportal 2025 |
| Smartphone penetration | 25% | GSMA 2025 |
| Electricity access | 50% | World Bank |

**Key systems:** STAR-UEMOA, Orange Money, Moov Money

**Integration approach:** eCFA CBDC platform

#### Benin (BJ)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 13.5 million | UN 2025 |
| GDP | $19 billion | IMF WEO 2024 |
| Mobile money accounts | 8+ million | GSMA 2024 |
| Mobile money annual volume | $6 billion | GSMA 2024 |
| Internet penetration | 35% | DataReportal 2025 |
| Electricity access | 43% | World Bank |

**Key systems:** STAR-UEMOA, MTN MoMo, Moov Money

**Integration approach:** eCFA CBDC platform

#### Guinea (GN)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 14 million | UN 2025 |
| GDP | $21 billion | IMF WEO 2024 |
| Mobile money accounts | 9+ million | GSMA 2024 |
| Mobile money annual volume | $4 billion | GSMA 2024 |
| Internet penetration | 28% | DataReportal 2025 |
| Electricity access | 44% | World Bank |

**Key systems:** Orange Money, MTN MoMo

**Integration approach:** Mobile money aggregation API (no CBDC, no national switch)

#### Togo (TG)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 9 million | UN 2025 |
| GDP | $9 billion | IMF WEO 2024 |
| Mobile money accounts | 6+ million | GSMA 2024 |
| Mobile money annual volume | $4 billion | GSMA 2024 |
| Internet penetration | 25% | DataReportal 2025 |
| Electricity access | 55% | World Bank |

**Key systems:** STAR-UEMOA, T-Money (Togocel), Flooz (Moov)

**Integration approach:** eCFA CBDC platform

#### Niger (NE)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 27 million | UN 2025 |
| GDP | $16 billion | IMF WEO 2024 |
| Mobile money accounts | 7+ million | GSMA 2024 |
| Mobile money annual volume | $2 billion | GSMA 2024 |
| Internet penetration | 15% | DataReportal 2025 |
| Electricity access | 19% | World Bank |

**Key systems:** STAR-UEMOA, Airtel Money, Orange Money (limited)

**Integration approach:** eCFA CBDC platform + USSD-first (lowest smartphone penetration in ECOWAS)

### Tier 3: Emerging Payment Ecosystems

#### Sierra Leone (SL)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 8.6 million | UN 2025 |
| GDP | $4.3 billion | IMF WEO 2024 |
| Mobile money accounts | 3+ million | GSMA 2024 |
| Internet penetration | 20% | DataReportal 2025 |
| Electricity access | 26% | World Bank |

**Key systems:** Orange Money, Africell Money

**Integration approach:** Mobile money aggregation

#### Liberia (LR)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 5.4 million | UN 2025 |
| GDP | $4.0 billion | IMF WEO 2024 |
| Mobile money accounts | 2.5+ million | GSMA 2024 |
| Internet penetration | 18% | DataReportal 2025 |
| Electricity access | 30% | World Bank |

**Key systems:** Orange Money, MTN MoMo, Lonestar Cell Money

**Integration approach:** Mobile money aggregation (dual currency: LRD + USD)

#### The Gambia (GM)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 2.7 million | UN 2025 |
| GDP | $2.2 billion | IMF WEO 2024 |
| Mobile money accounts | 1.5+ million | GSMA 2024 |
| Internet penetration | 35% | DataReportal 2025 |
| Electricity access | 65% | World Bank |

**Key systems:** Africell Money, QMoney, QCELL

**Integration approach:** Mobile money aggregation

#### Guinea-Bissau (GW)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 2.1 million | UN 2025 |
| GDP | $1.9 billion | IMF WEO 2024 |
| Mobile money accounts | 0.5+ million | GSMA 2024 |
| Internet penetration | 15% | DataReportal 2025 |
| Electricity access | 35% | World Bank |

**Key systems:** STAR-UEMOA, Orange Money (limited)

**Integration approach:** eCFA CBDC platform (smallest WAEMU economy)

#### Cape Verde (CV)
| Indicator | Value | Source |
|-----------|-------|--------|
| Population | 0.6 million | UN 2025 |
| GDP | $2.4 billion | IMF WEO 2024 |
| Bank account penetration | 75% (highest in ECOWAS) | World Bank |
| Internet penetration | 70% | DataReportal 2025 |
| Electricity access | 95% | World Bank |

**Key systems:** SISP (national payment switch), Vinti4 (card network)

**Integration approach:** SISP API integration (Cape Verde is the most banked ECOWAS country but smallest by population)

## 2.3 Cross-Border Payment Flows

### Major Corridors (estimated annual flows, formal + informal)

| Corridor | Annual Flow (est.) | Primary Mechanism | Pain Point |
|----------|-------------------|-------------------|------------|
| Nigeria → Ghana | $3.2B | Informal hawala, cash | No direct digital path |
| CI → Burkina Faso | $1.8B | Orange Money (same zone) | Limited cross-MNO |
| Senegal → Mali | $1.5B | Wave/Orange Money | Same WAEMU zone, works |
| Nigeria → Senegal | $1.1B | SWIFT, informal | 3-5 day settlement |
| Nigeria → CI | $0.9B | Informal, some banks | High FX cost |
| Ghana → Nigeria | $0.8B | Informal, fintech | Naira volatility |
| CI → Mali | $0.7B | Orange Money | Works within WAEMU |
| Guinea → Senegal | $0.6B | Cash, informal | No digital infrastructure |
| Benin → Nigeria | $0.9B | Cash (border trade) | Almost entirely informal |
| BF → CI | $0.6B | Orange Money | Works within WAEMU |
| All other corridors | $6.9B | Mixed | Fragmented |
| **Total estimated** | **$19.0B** | | |

### Major Trade Corridors (formal + informal goods movement)

| Corridor | Key Products | Est. Annual Volume | Primary Challenge |
|----------|-------------|-------------------|-------------------|
| Abidjan → Lagos (Coastal) | Manufactured goods, petroleum, cocoa | $5-8B | Multiple border stops, informal fees |
| Dakar → Bamako | Imported goods (transit), livestock | $2-3B | Road quality, checkpoints (7-10 per 100km) |
| Tema/Accra → Ouagadougou | Transit goods, gold, agriculture | $1.5-2.5B | Customs delays, FX conversion |
| Lagos → Niamey | Petroleum, manufactured goods | $1-2B | Almost entirely informal |
| Abidjan → Ouagadougou | Petroleum, transit goods | $1-2B | Road corridor congestion |
| Cotonou → Lagos | Re-exports, consumer goods | $3-5B (informal) | Nigeria-Benin border closures |

Source: ECOWAS Trade Facilitation reports, Borderless Alliance corridor monitoring, UNCTAD

### Current Cost of Cross-Border Payments

| Payment Method | Avg. Cost | Settlement Time | Coverage |
|----------------|-----------|-----------------|----------|
| SWIFT (bank transfer) | 5-12% | 2-5 days | Banks only |
| Western Union/MoneyGram | 8-15% | Minutes-hours | Agent network |
| Informal hawala | 2-5% | Same day | Cash only, no trail |
| Mobile money (same operator, same zone) | 0.5-2% | Instant | Within operator footprint |
| Mobile money (cross-operator) | 2-5% | Minutes-hours | Limited corridors |
| Mobile money (cross-border) | 3-8% | Hours-days | Very limited |
| **WASI-Pay target** | **0.25-0.50%** | **< 30 seconds** | **All 15 ECOWAS** |

## 2.4 Mobile Money Operator Landscape

Understanding the MNO landscape is critical for WASI-Pay's integration planning:

| Operator | ECOWAS Countries | Active Users (est.) | Key Markets | Integration Priority |
|----------|-----------------|--------------------|-----------|--------------------|
| Orange Money | CI, SN, BF, ML, GN, NE, GW, SL, LR (9) | 25-30M | CI (10M), SN (7M), BF (9M) | Phase 1 |
| MTN MoMo | GH, NG, BJ, CI, LR, GN (6) | 20-25M | GH (15-18M), NG (3-5M) | Phase 1 |
| Wave | SN, CI, BF, ML, GM (5) | 10-12M | SN (70%+ market share) | Phase 1 |
| Moov Africa | BJ, BF, CI, ML, NE, TG (6) | 8-12M | BJ, BF | Phase 2 |
| T-Money (Togocel) | TG (1) | ~2M | TG (dominant) | Phase 2 |
| Africell | GM, SL (2) | ~2M | GM, SL | Phase 3 |
| Airtel Money | NE, various (2+) | ~3M | NE | Phase 2 |
| **Total ECOWAS** | | **~80-95M active** | | |
| **Total ECOWAS agents** | | **2.5-3 million points** | | |

Sources: Orange Group FY2024, MTN Group FY2024, Wave company reports, GSMA State of Industry 2024

## 2.5 Aggregate ECOWAS Payment Market

| Metric | Value | Source |
|--------|-------|--------|
| ECOWAS combined GDP | $790 billion | IMF WEO 2024 |
| ECOWAS population | 440 million | UN 2025 |
| WAEMU GDP | ~$220 billion (CFA 135,730B) | BCEAO Feb 2026 |
| WAEMU GDP growth | 6.2% | BCEAO 2024 |
| Total mobile money accounts (ECOWAS) | 250+ million registered | GSMA 2024 |
| Active mobile money accounts (90-day) | 80-95 million | GSMA/operator data |
| Total mobile money agents | 2.5-3 million | GSMA/operator data |
| Annual mobile money volume (ECOWAS) | $180+ billion | GSMA 2024 |
| Annual mobile money volume (WAEMU only) | $75-90 billion (CFA 45-55T) | BCEAO |
| Annual mobile money volume (Ghana only) | $90-100 billion (GH₵1.2-1.4T) | BoG 2024 |
| Nigeria NIP annual transactions | 11 billion (2024) | CBN/NIBSS Feb 2026 |
| Annual formal cross-border payments | $18.7 billion | World Bank |
| Annual informal cross-border payments (est.) | $15-25 billion | WB/UNCTAD |
| Annual remittance inflows (diaspora) | $32.7 billion | KNOMAD 2024 |
| Intra-ECOWAS trade (formal) | $20-25 billion | ECOWAS Commission |
| Intra-ECOWAS trade as % of total | 10-15% | WTO Trade Policy Review |
| STAR-UEMOA daily RTGS value | $1.3-2.4 billion | BCEAO |
| GIM-UEMOA annual card transactions | 150-200 million | GIM-UEMOA |

---

# 3. TECHNICAL ARCHITECTURE BLUEPRINT

## 3.1 System Overview

```
╔══════════════════════════════════════════════════════════════════════╗
║                    WASI-PAY ARCHITECTURE                            ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  ┌──────────────────────────────────────────────────────────────┐    ║
║  │                    CLIENT LAYER                               │    ║
║  │  USSD (*384*WASI#)  │  REST API  │  Mobile SDK  │  Web Portal│    ║
║  └──────────────┬───────────────────────────────────────────────┘    ║
║                 │                                                     ║
║  ┌──────────────▼───────────────────────────────────────────────┐    ║
║  │                 API GATEWAY & AUTHENTICATION                  │    ║
║  │  Rate limiting │ JWT/OAuth2 │ API keys │ IP whitelisting     │    ║
║  │  TLS 1.3 │ mTLS for bank connections │ Request signing       │    ║
║  └──────────────┬───────────────────────────────────────────────┘    ║
║                 │                                                     ║
║  ┌──────────────▼───────────────────────────────────────────────┐    ║
║  │              WASI-PAY CORE ENGINE                             │    ║
║  │                                                               │    ║
║  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐     │    ║
║  │  │  PAYMENT     │  │  FX ENGINE   │  │  COMPLIANCE      │     │    ║
║  │  │  ROUTER      │  │              │  │  ENGINE          │     │    ║
║  │  │              │  │  Multi-rate  │  │                  │     │    ║
║  │  │  Route to    │  │  source      │  │  AML/CFT screen │     │    ║
║  │  │  optimal     │  │  aggregation │  │  KYC validation  │     │    ║
║  │  │  payment     │  │  Real-time   │  │  Sanctions check │     │    ║
║  │  │  rail per    │  │  bid/ask     │  │  GIABA reporting │     │    ║
║  │  │  corridor    │  │  Spread      │  │  Per-country     │     │    ║
║  │  │              │  │  management  │  │  thresholds      │     │    ║
║  │  └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘     │    ║
║  │         │                │                   │                │    ║
║  │  ┌──────▼────────────────▼───────────────────▼───────────┐   │    ║
║  │  │            CLEARING & SETTLEMENT ENGINE                │   │    ║
║  │  │                                                        │   │    ║
║  │  │  ISO 20022 message formatting                          │   │    ║
║  │  │  Bilateral netting (15-minute cycles)                  │   │    ║
║  │  │  Multi-currency position management                    │   │    ║
║  │  │  Prefunded nostro/vostro pool management               │   │    ║
║  │  │  Deferred net settlement (DNS) for batch               │   │    ║
║  │  │  Real-time gross settlement (RTGS) for large value     │   │    ║
║  │  └──────┬─────────────────────────────────────────────┘   │    ║
║  │         │                                                  │    ║
║  └─────────┼──────────────────────────────────────────────────┘    ║
║            │                                                        ║
║  ┌─────────▼──────────────────────────────────────────────────┐    ║
║  │              PAYMENT RAIL ADAPTERS                          │    ║
║  │                                                             │    ║
║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │    ║
║  │  │ eCFA     │ │ eNaira   │ │ eCedi    │ │ Mobile Money │  │    ║
║  │  │ CBDC     │ │ Bridge   │ │ Bridge   │ │ Aggregator   │  │    ║
║  │  │ (WAEMU)  │ │ (Nigeria)│ │ (Ghana)  │ │ (Others)     │  │    ║
║  │  │          │ │          │ │          │ │              │  │    ║
║  │  │ 8 ctries │ │ NIBSS+   │ │ GhIPSS+ │ │ Orange Money │  │    ║
║  │  │ Direct   │ │ eNaira   │ │ MMI+    │ │ MTN MoMo     │  │    ║
║  │  │ ledger   │ │ Hyper-   │ │ eCedi   │ │ Wave         │  │    ║
║  │  │ access   │ │ ledger   │ │ Emtech  │ │ Airtel Money │  │    ║
║  │  │          │ │          │ │         │ │ Africell     │  │    ║
║  │  └──────────┘ └──────────┘ └─────────┘ └──────────────┘  │    ║
║  │                                                             │    ║
║  │  ┌──────────┐ ┌────────────────────────────────────────┐   │    ║
║  │  │ SISP     │ │ Bank/RTGS Adapters                     │   │    ║
║  │  │ (Cape    │ │ STAR-UEMOA │ CBN RTGS │ BoG RTGS     │   │    ║
║  │  │ Verde)   │ │ PAPSS (fallback)                       │   │    ║
║  │  └──────────┘ └────────────────────────────────────────┘   │    ║
║  └─────────────────────────────────────────────────────────────┘    ║
║                                                                      ║
║  ┌─────────────────────────────────────────────────────────────┐    ║
║  │              OBSERVABILITY & OPERATIONS                      │    ║
║  │  Prometheus │ Grafana │ ELK │ PagerDuty │ Audit Trail       │    ║
║  └─────────────────────────────────────────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════════════╝
```

## 3.2 Payment Router — Optimal Rail Selection

The Payment Router is the brain of WASI-Pay. For each transaction, it determines the optimal path:

### Routing Decision Matrix

| Source Country | Dest Country | Rail Selected | FX Required | Settlement |
|---------------|-------------|---------------|-------------|------------|
| WAEMU → WAEMU | Same zone | eCFA ledger (internal) | No | Instant |
| WAEMU → Nigeria | Cross-zone | eCFA → FX → eNaira/NIP | XOF→NGN | < 30s |
| WAEMU → Ghana | Cross-zone | eCFA → FX → GhIPSS/MMI | XOF→GHS | < 30s |
| WAEMU → Guinea | Cross-zone | eCFA → FX → Orange MM | XOF→GNF | < 60s |
| Nigeria → Ghana | Cross-zone | NIP → FX → GhIPSS | NGN→GHS | < 30s |
| Nigeria → WAEMU | Cross-zone | NIP → FX → eCFA | NGN→XOF | < 30s |
| Ghana → Nigeria | Cross-zone | GhIPSS → FX → NIP | GHS→NGN | < 30s |
| Ghana → WAEMU | Cross-zone | GhIPSS → FX → eCFA | GHS→XOF | < 30s |
| Any → SL/LR/GM | MM corridor | Source rail → FX → MM API | Various | < 120s |
| Any → Cape Verde | Bank/SISP | Source rail → FX → SISP | Various→CVE | < 60s |

### Routing Algorithm

```
FUNCTION route_payment(sender, receiver, amount, currency):

  1. IDENTIFY source_country, dest_country from wallet metadata
  2. DETERMINE source_rail = best_rail(source_country)
  3. DETERMINE dest_rail = best_rail(dest_country)
  4. CHECK compliance(sender, receiver, amount)  // AML/CFT pre-screen
     IF blocked → REJECT with reason code

  5. IF source_country.zone == dest_country.zone:
       IF zone == "WAEMU":
         USE eCFA internal ledger transfer (zero FX cost)
         SETTLEMENT: instant, on-ledger
       ELSE:
         USE national switch (NIP, GhIPSS, etc.)
         SETTLEMENT: instant via national infrastructure

  6. ELSE:  // Cross-zone
     a. LOCK source funds (debit source wallet/account)
     b. CONVERT via FX engine:
        - Get best rate from rate sources (BCEAO, CBN, BoG, Reuters)
        - Apply WASI spread (0.15-0.30%)
        - Lock rate for 30 seconds
     c. CREDIT destination via dest_rail adapter
     d. CONFIRM to source
     e. QUEUE for batch settlement (net positions every 15 min)

  7. LOG to audit trail (immutable)
  8. RETURN transaction_id, status, FX rate applied, fees
```

## 3.3 FX Engine — Multi-Currency Conversion

### Supported Currency Pairs (36 pairs from 9 currencies)

| # | Currency | Code | Rate Source | Volatility Class |
|---|----------|------|-------------|------------------|
| 1 | CFA Franc (WAEMU) | XOF | BCEAO (EUR peg) | Stable (EUR-linked) |
| 2 | Nigerian Naira | NGN | CBN + parallel market | High volatility |
| 3 | Ghanaian Cedi | GHS | BoG | Medium volatility |
| 4 | Guinean Franc | GNF | BCRG | High volatility |
| 5 | Sierra Leonean Leone | SLL | BSL | High volatility |
| 6 | Liberian Dollar | LRD | CBL (USD co-circulation) | Medium volatility |
| 7 | Gambian Dalasi | GMD | CBG | Medium volatility |
| 8 | Cape Verdean Escudo | CVE | BCV (EUR peg) | Stable (EUR-linked) |
| 9 | US Dollar | USD | Reference currency | Benchmark |

### FX Rate Management

```
Rate Refresh Frequency:
  - XOF, CVE: Daily (EUR-pegged, rarely changes)
  - GHS, GMD, LRD: Every 15 minutes (market hours)
  - NGN: Every 5 minutes (high volatility)
  - GNF, SLL: Every 30 minutes (thin markets)

Rate Sources (priority order):
  1. Central bank official rates (BCEAO, CBN, BoG, etc.)
  2. Reuters/Refinitiv feed
  3. Commercial bank dealer quotes (aggregated)
  4. PAPSS reference rates

Spread Model:
  - Stable pairs (XOF↔CVE): 0.15%
  - Medium pairs (XOF↔GHS, GHS↔GMD): 0.25%
  - Volatile pairs (anything↔NGN, GNF, SLL): 0.35%
  - Emergency spread (>5% daily move): 0.50% + manual review

Position Limits:
  - Max net position per currency: $2M equivalent
  - Max single transaction: $500K equivalent
  - Daily aggregate limit: $50M equivalent
  - Excess position auto-hedge via correspondent banks
```

## 3.4 Clearing & Settlement Engine

### Settlement Architecture

WASI-Pay uses a **prefunded model** to eliminate counterparty risk:

```
┌────────────────────────────────────────────────────────────┐
│                 WASI-PAY SETTLEMENT ACCOUNTS               │
│                                                            │
│  ┌─────────────┐  Prefunded pools held at:                │
│  │ XOF Pool    │  BCEAO (Dakar) — $10M equivalent         │
│  │ NGN Pool    │  CBN (Lagos) — $15M equivalent            │
│  │ GHS Pool    │  BoG (Accra) — $5M equivalent             │
│  │ GNF Pool    │  BCRG (Conakry) — $1M equivalent          │
│  │ SLL Pool    │  BSL (Freetown) — $0.5M equivalent        │
│  │ LRD Pool    │  CBL (Monrovia) — $0.5M equivalent        │
│  │ GMD Pool    │  CBG (Banjul) — $0.5M equivalent          │
│  │ CVE Pool    │  BCV (Praia) — $0.5M equivalent           │
│  │ USD Pool    │  Correspondent (NY) — $5M equivalent      │
│  └─────────────┘                                           │
│                                                            │
│  Total prefunding requirement: ~$38.5M                     │
│  (Funded from capital raise + revolving credit facility)   │
└────────────────────────────────────────────────────────────┘
```

### Settlement Cycles

| Settlement Type | Frequency | Threshold | Mechanism |
|----------------|-----------|-----------|-----------|
| Instant (on-ledger) | Real-time | eCFA within WAEMU | Internal ledger transfer |
| Near-instant | < 30 seconds | Cross-zone < $10K | Prefunded pool debit/credit |
| Batch netting | Every 15 minutes | All cross-zone | Bilateral net calculation |
| RTGS settlement | As needed | Single tx > $100K | Direct RTGS instruction |
| End-of-day | Daily 23:00 UTC | Net positions | Pool rebalancing |
| Weekly reconciliation | Friday 18:00 UTC | All positions | Full audit |

### Bilateral Netting Example

```
15-minute window: 14:00 - 14:15 UTC

Transactions:
  CI → NG: 45 payments totaling $125,000
  NG → CI: 38 payments totaling $92,000

Gross volume: $217,000 (83 transactions)
Net position: CI owes NG $33,000 (1 settlement)

Netting ratio: 84.8% reduction in settlement volume
Settlement: Single $33,000 transfer XOF→NGN via pool accounts

Benefit: 83 individual cross-border settlements → 1 net transfer
```

## 3.5 ISO 20022 Message Standards

All WASI-Pay messages conform to ISO 20022 for interoperability with SWIFT, PAPSS, and national RTGS systems:

| Message Type | ISO 20022 Code | Usage |
|-------------|---------------|-------|
| Credit Transfer | pacs.008 | P2P, P2B payments |
| Payment Return | pacs.004 | Refunds, reversals |
| Payment Status | pacs.002 | Transaction status inquiry |
| Settlement | pacs.009 | Inter-institution settlement |
| FX Quote | fxtr.014 | Rate inquiry |
| FX Confirmation | fxtr.017 | Rate lock confirmation |
| Account Statement | camt.053 | Daily position reports |
| Compliance Report | auth.024 | AML/CFT reporting |

## 3.6 Security Architecture

| Layer | Standard | Implementation |
|-------|----------|----------------|
| Transport | TLS 1.3 | All API endpoints |
| Bank connections | mTLS | Mutual certificate authentication |
| API authentication | OAuth 2.0 + API keys | Per-institution credentials |
| Message signing | ECDSA (secp256k1) | Every transaction signed |
| Encryption at rest | AES-256-GCM | All PII and financial data |
| Key management | HSM (Thales Luna) | Master keys never in software |
| Tokenization | UUID + hash | Wallet IDs, account references |
| Audit trail | SHA-256 hash chain | Immutable, append-only |
| DDoS protection | Cloudflare Enterprise | Edge protection |
| WAF | ModSecurity + custom rules | OWASP Top 10 |
| PCI DSS | Level 1 (target) | Annual QSA audit |
| SOC 2 Type II | Trust services criteria | Annual audit |

## 3.7 Infrastructure Requirements

### Primary Data Center: Abidjan, Cote d'Ivoire
- **Justification:** WAEMU financial capital, BCEAO headquarters, submarine cable landing (MainOne, ACE, SAT-3)
- **Specification:** Tier III+ colocation (99.982% uptime)
- **Capacity:** 4 racks, 40kW power, 10Gbps uplink
- **Cost:** $18,000/month

### Secondary Data Center: Lagos, Nigeria
- **Justification:** Nigeria = 65% of ECOWAS GDP, low-latency NIBSS connection
- **Specification:** Tier III colocation (Rack Centre or MDXi)
- **Capacity:** 2 racks, 20kW power, 10Gbps uplink
- **Cost:** $12,000/month

### Disaster Recovery: Accra, Ghana
- **Justification:** Third major economy, geographic diversity
- **Specification:** Tier III colocation (cold standby)
- **Capacity:** 1 rack, 10kW power
- **Cost:** $6,000/month

### Cloud Supplement: AWS Africa (Cape Town)
- **Usage:** Non-financial workloads (analytics, reporting, dev/test)
- **Cost:** ~$8,000/month

### Total Monthly Infrastructure: $44,000 ($528,000/year)

---

# 4. COUNTRY-BY-COUNTRY INTEGRATION ANALYSIS

## 4.1 Integration Readiness Scoring

Each country is scored on 10 dimensions (1-5 scale, max 50 points):

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Digital payment penetration | 15% | % of adults using digital payments |
| Regulatory readiness | 15% | Licensing framework, open banking rules |
| Technical infrastructure | 10% | Internet, electricity, national switch |
| Mobile money ecosystem | 15% | MNO presence, agent networks |
| CBDC status | 10% | Active CBDC program or roadmap |
| Central bank engagement | 10% | Willingness to engage private operators |
| Cross-border trade volume | 10% | Existing demand for cross-border payments |
| FX market maturity | 5% | Liquid FX market, convertibility |
| Political stability | 5% | Governance, coup risk, sanctions |
| WASI existing presence | 5% | Existing WASI data/USSD operations |

## 4.2 Country Readiness Matrix

| Country | Code | Score /50 | Tier | Integration Cost | Timeline | Priority |
|---------|------|-----------|------|-----------------|----------|----------|
| Cote d'Ivoire | CI | 42 | 1 | $280K | 3 months | Phase 1 |
| Senegal | SN | 41 | 1 | $250K | 3 months | Phase 1 |
| Burkina Faso | BF | 38 | 1 | $180K | 2 months | Phase 1 |
| Nigeria | NG | 44 | 1 | $1,200K | 6 months | Phase 1 |
| Ghana | GH | 43 | 1 | $800K | 5 months | Phase 1 |
| Mali | ML | 34 | 2 | $220K | 4 months | Phase 2 |
| Benin | BJ | 35 | 2 | $200K | 4 months | Phase 2 |
| Togo | TG | 33 | 2 | $200K | 4 months | Phase 2 |
| Niger | NE | 28 | 2 | $250K | 5 months | Phase 2 |
| Guinea | GN | 30 | 3 | $350K | 6 months | Phase 3 |
| The Gambia | GM | 27 | 3 | $300K | 6 months | Phase 3 |
| Sierra Leone | SL | 25 | 3 | $350K | 7 months | Phase 3 |
| Liberia | LR | 24 | 3 | $350K | 7 months | Phase 3 |
| Guinea-Bissau | GW | 22 | 3 | $200K | 5 months | Phase 3 |
| Cape Verde | CV | 36 | 2 | $300K | 5 months | Phase 2 |
| **Total** | | | | **$5,430K** | **36 months** | |

## 4.3 Detailed Country Integration Plans

### Nigeria — The Critical Integration ($1.2M, 6 months)

| Component | Cost | Duration | Dependency |
|-----------|------|----------|------------|
| CBN PSP License application | $150K | 3-6 months | Legal entity in Nigeria |
| NIBSS NIP integration | $200K | 3 months | PSP license |
| eNaira API bridge (Hyperledger) | $180K | 2 months | CBN partnership |
| OPay/PalmPay fallback APIs | $80K | 1 month | Commercial agreements |
| FX engine (NGN module) | $120K | 2 months | CBN FX license |
| Compliance module (CBN regs) | $100K | 2 months | NFIU registration |
| Testing & certification | $150K | 2 months | NIBSS sandbox |
| Local team (3 engineers, 1 compliance) | $220K/yr | Ongoing | Lagos office |

**Revenue potential:** $4.2M/year (Year 1) — Nigeria alone could fund WASI-Pay operations

### Ghana — The Mobile Money Bridge ($800K, 5 months)

| Component | Cost | Duration | Dependency |
|-----------|------|----------|------------|
| BoG PSP license | $80K | 2-4 months | Legal entity |
| GhIPSS GIP integration | $120K | 2 months | BoG license |
| Mobile Money Interoperability (MMI) | $100K | 2 months | GhIPSS |
| MTN MoMo API integration | $60K | 1 month | Commercial |
| eCedi bridge (Emtech) | $100K | 3 months | BoG pilot access |
| FX engine (GHS module) | $80K | 1 month | BoG FX desk |
| Compliance module (BoG regs) | $60K | 1 month | FIC registration |
| Testing & certification | $100K | 2 months | GhIPSS sandbox |
| Local team (2 engineers, 1 compliance) | $100K/yr | Ongoing | Accra office |

### WAEMU Countries (CI, SN, BF, ML, BJ, TG, NE, GW) — eCFA Advantage

The 8 WAEMU countries integrate through our **existing eCFA CBDC platform**, dramatically reducing costs:

| Component | Cost (per country avg) | Duration | Dependency |
|-----------|----------------------|----------|------------|
| eCFA wallet system activation | $50K | Already built | - |
| BCEAO STAR-UEMOA settlement | $80K (one-time) | 2 months | BCEAO agreement |
| Orange Money API (per country) | $30K | 1 month | Orange partnership |
| MTN MoMo API (where present) | $25K | 1 month | MTN partnership |
| Wave API (SN, CI, BF, ML) | $20K | 1 month | Wave partnership |
| Moov API (BJ, TG, CI, NE) | $20K | 1 month | Moov partnership |
| Country-specific compliance | $25K | 1 month | BCEAO unified |
| Testing | $30K | 1 month | - |

**Total WAEMU integration: $1,780K** (8 countries, average $222K each)
**Key advantage:** Single BCEAO regulatory relationship covers all 8 countries

---

# 5. TRANSACTION ECONOMICS

## 5.1 Per-Transaction Cost Structure

### Domestic Transactions (within same country)

| Cost Component | Per Transaction | Notes |
|---------------|----------------|-------|
| WASI platform processing | $0.005 | Server, compute, storage |
| National switch fee | $0.02-0.05 | NIBSS, GhIPSS, STAR-UEMOA |
| Mobile money API fee | $0.01-0.03 | MNO interchange |
| Compliance screening | $0.003 | AML/CFT check |
| **Total cost to WASI** | **$0.038-0.083** | |
| **WASI fee charged** | **$0.05-0.15** | |
| **Margin** | **$0.012-0.067** | **24-45%** |

### Cross-Border Transactions (different countries/currencies)

| Cost Component | Per Transaction | Notes |
|---------------|----------------|-------|
| WASI platform processing | $0.008 | Higher complexity |
| Source-side rail fee | $0.02-0.05 | Debit from sender |
| FX conversion cost | 0.08-0.15% of amount | Spread to rate source |
| Destination-side rail fee | $0.02-0.05 | Credit to receiver |
| Settlement cost (netting) | $0.005 | Amortized RTGS fees |
| Compliance screening (2x) | $0.006 | Both jurisdictions |
| **Total cost to WASI** | **$0.059-0.119 + FX** | |
| **WASI fee charged** | **0.25-0.50% of amount** | |

### Revenue per Transaction (by corridor type and average size)

| Corridor Type | Avg Tx Size | WASI Fee Rate | WASI Revenue | WASI Cost | Margin |
|--------------|-------------|---------------|-------------|-----------|--------|
| WAEMU ↔ WAEMU (eCFA) | $25 | 0.15% | $0.038 | $0.018 | 53% |
| WAEMU ↔ Nigeria | $80 | 0.35% | $0.280 | $0.110 | 61% |
| WAEMU ↔ Ghana | $65 | 0.30% | $0.195 | $0.090 | 54% |
| Nigeria ↔ Ghana | $120 | 0.35% | $0.420 | $0.150 | 64% |
| Any ↔ Tier 3 country | $40 | 0.40% | $0.160 | $0.095 | 41% |
| Merchant payment (cross-border) | $15 | 0.50% | $0.075 | $0.045 | 40% |
| Data income disbursement | $0.50 | Fixed $0.01 | $0.010 | $0.005 | 50% |
| **Weighted average** | **$45** | **0.35%** | **$0.158** | **$0.072** | **54%** |

## 5.2 Pricing Model

### Tiered Pricing by Volume (Monthly)

| Tier | Monthly Volume | Fee Rate | Target Segment |
|------|---------------|----------|----------------|
| Starter | < $100K | 0.50% | Small merchants, individuals |
| Growth | $100K - $1M | 0.40% | SMEs, cooperatives |
| Enterprise | $1M - $10M | 0.30% | Banks, large merchants |
| Institutional | $10M+ | 0.20% | Central banks, governments, MNOs |
| Sovereign Data | Any | 0.10% + subsidy | Government data income payments |

### Additional Revenue Streams

| Revenue Stream | Pricing | Year 1 Revenue | Year 5 Revenue |
|---------------|---------|----------------|----------------|
| Transaction fees | 0.20-0.50% | $5,600K | $64,300K |
| FX spread revenue | 0.10-0.25% | $1,800K | $14,300K |
| API access fees (data buyers) | $500-5,000/month | $360K | $2,400K |
| Settlement services (banks) | $2,000-10,000/month | $240K | $1,800K |
| CBDC platform license (BCEAO) | $2M-5M/year | $2,000K | $4,000K |
| Integration services | Per project | $400K | $1,200K |
| Training & support | Annual contracts | $0 | $600K |
| White-label licensing | Per country | $0 | $2,100K |
| **Total revenue** | | **$10,400K** | **$90,700K** |

## 5.3 Unit Economics at Scale

### Year 5 Unit Economics

```
Total transactions processed:      580 million/year
  Domestic (same country):         420 million (72%)
  Cross-border (diff country):     160 million (28%)

Total payment volume:              $28.6 billion
  Domestic volume:                 $12.8 billion
  Cross-border volume:             $15.8 billion

Revenue:
  Transaction fees:                $64.3M (avg 0.26% blended)
  FX spread:                       $14.3M (avg 0.09% on total volume)
  Platform/licensing:              $12.1M
  Total:                           $90.7M

Costs:
  Rail fees (switches, MNOs):      $18.6M
  FX hedging costs:                $4.8M
  Infrastructure:                  $3.2M
  Personnel (180 staff):           $12.6M
  Compliance & licensing:          $4.2M
  Marketing & BD:                  $3.5M
  G&A:                             $5.1M
  Total:                           $52.0M

EBITDA:                            $38.7M (42.7% margin)
```

---

# 6. FINANCIAL MODEL — 10-YEAR PROJECTIONS

## 6.0 Key Assumptions & Data Sources

The financial model below is built on the following validated assumptions:

| Assumption | Value | Validation Source |
|------------|-------|-------------------|
| ECOWAS combined GDP | $790B | IMF WEO 2024 |
| ECOWAS population | 440M | UN Population 2025 |
| Annual remittance inflows | $32.7B | KNOMAD 2024 (validated by research) |
| Annual formal intra-ECOWAS trade | $20-25B | ECOWAS Commission, WTO |
| Annual informal cross-border trade | $15-25B | World Bank/UNCTAD estimates |
| ECOWAS mobile money volume | $180B+ | GSMA 2024, BCEAO, BoG data |
| Nigeria NIP annual transactions | 11B (2024) | CBN Fintech Report Feb 2026 |
| Average cost of cross-border remittance (intra-Africa) | 8-12% | World Bank RPW Q4 2024 |
| Average cost of diaspora remittance to ECOWAS | 5-8% | World Bank RPW Q4 2024 |
| WASI-Pay average fee rate | 0.35% | Below all competitors |
| WASI-Pay market capture Year 1 | ~1.3% of addressable market | Conservative for new entrant |
| WASI-Pay market capture Year 5 | ~5.8% of addressable market | Realistic for established player |
| UPI central infrastructure cost benchmark | $50-100M | NPCI annual reports (validated) |
| PIX central infrastructure cost benchmark | $40-60M | BCB (validated) |
| PAPSS investment benchmark | $50M+ | Afreximbank (validated) |
| WASI-Pay development + initial deployment | $18.5M | Bottom-up engineering estimate |

**Cross-validation:** WASI-Pay's Year 1 target of $2.4B in transaction volume represents ~1.3% of the total addressable market ($180B+ mobile money + $32.7B remittances). For context, PIX captured ~5% of Brazil's total payment volume within its first year. Our 1.3% capture rate is 4x more conservative.

## 6.1 Revenue Projections

### Base Case Scenario

| Year | Countries Live | Tx Volume ($B) | Transactions (M) | Revenue ($M) | Growth |
|------|---------------|----------------|-------------------|-------------|--------|
| 1 | 5 (CI,SN,BF,NG,GH) | 2.4 | 48 | 10.4 | — |
| 2 | 9 (+ML,BJ,TG,NE) | 7.8 | 142 | 28.6 | 175% |
| 3 | 12 (+GN,CV,GM) | 15.2 | 290 | 52.8 | 85% |
| 4 | 15 (all ECOWAS) | 22.4 | 440 | 73.5 | 39% |
| 5 | 15 (matured) | 28.6 | 580 | 90.7 | 23% |
| 6 | 15 + 2 non-ECOWAS | 36.8 | 720 | 112.4 | 24% |
| 7 | 15 + 5 non-ECOWAS | 48.2 | 900 | 142.6 | 27% |
| 8 | Pan-West Africa | 62.5 | 1,100 | 178.0 | 25% |
| 9 | Pan-West Africa | 78.4 | 1,350 | 215.8 | 21% |
| 10 | Pan-West Africa | 94.2 | 1,600 | 245.0 | 14% |

### Revenue Breakdown by Stream (Year 5)

```
Transaction Fees          ████████████████████████████████  $64.3M  (70.9%)
FX Spread Revenue         ████████                          $14.3M  (15.8%)
CBDC License (BCEAO)      ██                                $4.0M   (4.4%)
API Access Fees            █                                $2.4M   (2.6%)
Settlement Services        █                                $1.8M   (2.0%)
White-Label Licensing     █                                 $2.1M   (2.3%)
Integration Services       █                                $1.2M   (1.3%)
Training & Support                                          $0.6M   (0.7%)
                          ─────────────────────────────────────────────────
Total                                                       $90.7M  (100%)
```

## 6.2 Cost Projections

| Cost Category | Year 1 | Year 2 | Year 3 | Year 5 | Year 10 |
|--------------|--------|--------|--------|--------|---------|
| **Rail & network fees** | $1.2M | $3.8M | $7.6M | $18.6M | $38.2M |
| Switch fees (NIBSS, GhIPSS) | $0.4M | $1.2M | $2.4M | $5.8M | $12.0M |
| MNO interchange | $0.5M | $1.6M | $3.2M | $8.0M | $16.4M |
| RTGS settlement fees | $0.1M | $0.4M | $0.8M | $2.0M | $4.0M |
| Correspondent banking | $0.2M | $0.6M | $1.2M | $2.8M | $5.8M |
| **FX costs** | $0.4M | $1.4M | $2.6M | $4.8M | $9.6M |
| Rate source fees | $0.1M | $0.2M | $0.3M | $0.5M | $0.8M |
| Hedging costs | $0.2M | $0.8M | $1.5M | $2.8M | $5.6M |
| FX losses (slippage) | $0.1M | $0.4M | $0.8M | $1.5M | $3.2M |
| **Infrastructure** | $1.8M | $2.2M | $2.6M | $3.2M | $5.4M |
| Data centers (3 sites) | $0.5M | $0.5M | $0.6M | $0.6M | $0.8M |
| Cloud (AWS, analytics) | $0.1M | $0.2M | $0.3M | $0.5M | $0.8M |
| HSMs & security hardware | $0.3M | $0.1M | $0.1M | $0.2M | $0.4M |
| Telecom (USSD gateways) | $0.4M | $0.6M | $0.8M | $1.0M | $1.6M |
| Software licenses | $0.3M | $0.4M | $0.5M | $0.6M | $1.0M |
| Maintenance & upgrades | $0.2M | $0.4M | $0.3M | $0.3M | $0.8M |
| **Personnel** | $3.6M | $5.8M | $8.4M | $12.6M | $22.4M |
| Engineering (25→80) | $1.8M | $3.0M | $4.2M | $6.2M | $10.8M |
| Operations (10→40) | $0.6M | $1.0M | $1.6M | $2.4M | $4.2M |
| Compliance (5→20) | $0.4M | $0.6M | $1.0M | $1.6M | $2.8M |
| Business development (5→15) | $0.4M | $0.6M | $0.8M | $1.2M | $2.0M |
| Management (5→10) | $0.4M | $0.6M | $0.8M | $1.2M | $2.6M |
| **Compliance & licensing** | $1.4M | $2.2M | $3.0M | $4.2M | $7.2M |
| Country licenses (15 total) | $0.6M | $0.8M | $1.0M | $1.2M | $2.0M |
| PCI DSS / SOC 2 audits | $0.2M | $0.2M | $0.3M | $0.3M | $0.5M |
| AML/CFT systems | $0.3M | $0.5M | $0.7M | $1.0M | $1.8M |
| Legal (multi-jurisdiction) | $0.3M | $0.7M | $1.0M | $1.7M | $2.9M |
| **Marketing & BD** | $0.8M | $1.4M | $2.2M | $3.5M | $5.8M |
| **G&A** | $1.2M | $2.0M | $3.2M | $5.1M | $8.8M |
| **Total operating costs** | **$10.4M** | **$18.8M** | **$29.6M** | **$52.0M** | **$97.4M** |

## 6.3 Profitability Analysis

| Metric | Year 1 | Year 2 | Year 3 | Year 5 | Year 10 |
|--------|--------|--------|--------|--------|---------|
| Revenue | $10.4M | $28.6M | $52.8M | $90.7M | $245.0M |
| Operating costs | $10.4M | $18.8M | $29.6M | $52.0M | $97.4M |
| **EBITDA** | **$0.0M** | **$9.8M** | **$23.2M** | **$38.7M** | **$147.6M** |
| **EBITDA margin** | **0.0%** | **34.3%** | **43.9%** | **42.7%** | **60.2%** |
| Depreciation & amortization | $1.2M | $1.4M | $1.6M | $2.0M | $3.2M |
| **EBIT** | **-$1.2M** | **$8.4M** | **$21.6M** | **$36.7M** | **$144.4M** |
| Interest expense | $0.8M | $0.6M | $0.4M | $0.0M | $0.0M |
| Taxes (avg 25%) | $0.0M | $1.9M | $5.3M | $9.2M | $36.1M |
| **Net income** | **-$2.0M** | **$5.9M** | **$15.9M** | **$27.5M** | **$108.3M** |
| **Net margin** | **-19.2%** | **20.6%** | **30.1%** | **30.3%** | **44.2%** |

## 6.4 Cash Flow Analysis

| Metric | Year 1 | Year 2 | Year 3 | Year 5 | Year 10 |
|--------|--------|--------|--------|--------|---------|
| Cash from operations | -$0.8M | $10.2M | $24.8M | $40.7M | $150.8M |
| Capital expenditure | -$12.5M | -$3.2M | -$2.8M | -$2.5M | -$4.0M |
| Prefunding deployment | -$18.5M | -$8.0M | -$6.0M | -$4.0M | -$2.0M |
| **Free cash flow** | **-$31.8M** | **-$1.0M** | **$16.0M** | **$34.2M** | **$144.8M** |
| Cumulative FCF | -$31.8M | -$32.8M | -$16.8M | $38.8M | $561.4M |

**Breakeven month:** Month 22 (cumulative cash flow turns positive in Year 3)

## 6.5 Return on Investment

| Metric | Value |
|--------|-------|
| Total 10-year revenue | $1,124M |
| Total 10-year net income | $420M |
| Total initial investment required | $18.5M |
| NPV (12% discount rate) | $387M |
| NPV (15% discount rate) | $298M |
| NPV (20% discount rate) | $196M |
| IRR | 68.4% |
| Payback period | 2.8 years |
| MOIC (Multiple on Invested Capital) | 22.7x |

## 6.6 Capital Requirements

### Initial Capital Raise: $18.5M

| Use | Amount | % | Timeline |
|-----|--------|---|----------|
| Technology development | $4.5M | 24% | Months 1-12 |
| Country integrations (Phase 1: 5 countries) | $2.7M | 15% | Months 3-12 |
| Prefunding pools (initial) | $5.0M | 27% | Month 6 |
| Regulatory & licensing | $1.5M | 8% | Months 1-9 |
| Personnel (Year 1 team) | $3.6M | 19% | Months 1-12 |
| Working capital | $1.2M | 7% | Month 1 |

### Subsequent Funding Requirements

| Phase | Amount | Source | Purpose |
|-------|--------|--------|---------|
| Phase 2 (Year 2) | $12M | Series A or debt | 4 more countries + pool expansion |
| Phase 3 (Year 3) | $8M | Revenue + debt facility | Final 6 countries |
| Growth (Year 4-5) | $15M | Revolving credit facility | Pool scaling + non-ECOWAS |
| **Total through Year 5** | **$53.5M** | | |

---

# 7. RISK MATRIX

## 7.1 Quantified Risk Assessment

| # | Risk | Category | Probability | Impact | Risk Score | Mitigation | Residual Risk |
|---|------|----------|------------|--------|------------|------------|---------------|
| 1 | Nigeria CBN denies PSP license | Regulatory | 25% | Critical ($4.2M revenue loss) | High | Apply through local subsidiary; engage fintech association | Medium |
| 2 | NGN currency crisis (>30% devaluation) | Financial | 35% | High ($2.1M FX loss) | High | Cap NGN position at $2M; auto-hedge daily; widen spread during vol | Medium |
| 3 | BCEAO rejects eCFA partnership | Strategic | 15% | Critical (8-country gap) | High | Pitch alongside BF government contract; BCEAO benefits from visibility | Low |
| 4 | Major security breach / hack | Technical | 10% | Critical (reputation, $5M+ loss) | Medium | HSM, mTLS, SOC 2, bug bounty, $5M cyber insurance | Low |
| 5 | PAPSS achieves mobile money interop | Competitive | 20% | High (market share loss) | Medium | PAPSS is bank-focused; WASI has USSD+CBDC+data moat | Low |
| 6 | MNO refuses API access | Operational | 30% | Medium ($1.5M corridor loss) | Medium | Multi-MNO strategy; regulatory push for open access | Low |
| 7 | Political instability (coup, sanctions) | Political | 20% | Medium (1-2 country disruption) | Medium | Multi-country diversification; no single-country >40% revenue | Low |
| 8 | FX pool liquidity crunch | Financial | 15% | High (settlement delays) | Medium | $5M standby facility; automated pool rebalancing; position limits | Low |
| 9 | Data center outage (Abidjan) | Technical | 10% | Medium (4-8 hour disruption) | Low | Active-passive failover to Lagos; RPO < 1 min, RTO < 15 min | Low |
| 10 | Key personnel departure | Operational | 30% | Medium (3-month setback) | Medium | Competitive comp; vesting; knowledge documentation; 2-deep coverage | Low |
| 11 | Regulatory change (new fees, restrictions) | Regulatory | 25% | Medium (margin compression) | Medium | Multi-country diversification; regulatory affairs team | Low |
| 12 | Settlement fraud / double-spend | Financial | 5% | High ($1M+ loss) | Low | Prefunded model eliminates credit risk; hash chains; reconciliation | Very Low |

## 7.2 Concentration Risk

| Risk Factor | Current Exposure | Limit | Mitigation |
|-------------|-----------------|-------|------------|
| Nigeria revenue dependency | 40% (Year 1) | < 35% (Year 3) | Accelerate WAEMU volume |
| Single currency (NGN) exposure | $2M max position | $2M | Auto-hedge, position limits |
| Top customer dependency | < 15% | < 10% (Year 3) | Diversified customer base |
| Single data center | Abidjan primary | N/A | Lagos secondary, Accra DR |
| MNO dependency (Orange) | 35% of MoMo volume | < 30% | Multi-MNO, Wave, MTN |

---

# 8. REGULATORY FRAMEWORK & COMPLIANCE

## 8.1 Licensing Requirements by Country

| Country | License Type | Authority | Est. Cost | Processing Time | Status |
|---------|-------------|-----------|-----------|-----------------|--------|
| Cote d'Ivoire | Etablissement de Monnaie Electronique | BCEAO | $120K | 6-12 months | Priority |
| Senegal | Same (BCEAO unified) | BCEAO | Covered above | Covered | With CI |
| Burkina Faso | Same (BCEAO unified) | BCEAO | Covered above | Covered | With CI |
| All WAEMU | Single BCEAO license covers all 8 | BCEAO | $120K total | 6-12 months | Priority |
| Nigeria | PSP License | CBN | $150K | 6-12 months | Priority |
| Nigeria | PSSP License (switching) | CBN | $200K | 6-12 months | Priority |
| Ghana | Enhanced PSP License | BoG | $80K | 3-6 months | Priority |
| Guinea | E-money License | BCRG | $50K | 4-8 months | Phase 3 |
| Sierra Leone | Mobile Money License | BSL | $40K | 3-6 months | Phase 3 |
| Liberia | E-money License | CBL | $30K | 3-6 months | Phase 3 |
| The Gambia | PSP License | CBG | $25K | 3-6 months | Phase 3 |
| Cape Verde | Payment Institution License | BCV | $60K | 4-8 months | Phase 2 |
| **Total licensing costs** | | | **$875K** | | |

## 8.2 AML/CFT Framework

| Requirement | Standard | Implementation |
|-------------|----------|----------------|
| Customer identification | FATF Rec. 10 | KYC tiers aligned with BCEAO/CBN standards |
| Transaction monitoring | FATF Rec. 20 | Real-time screening (7 alert types from eCFA engine) |
| Suspicious activity reporting | GIABA standards | Automated SAR filing to each country's FIU |
| Cross-border threshold | GIABA directive | $5,000 equivalent auto-report |
| Sanctions screening | OFAC, EU, UN lists | Real-time screening on every transaction |
| Record keeping | 5 years minimum | Immutable audit trail (hash chain) |
| Travel rule | FATF Rec. 16 | Originator/beneficiary info on all transfers > $1,000 |

## 8.3 Data Protection Compliance

| Country/Zone | Law | Key Requirement | WASI Compliance |
|-------------|-----|-----------------|-----------------|
| WAEMU | BCEAO Regulation 2020 | Data localization in WAEMU | Abidjan data center |
| Nigeria | NDPA 2023 | Consent, breach notification | In-app consent, 72h breach notice |
| Ghana | Data Protection Act 2012 | Registration with DPA | Registration planned |
| ECOWAS | Supplementary Act 2010 | Harmonized principles | Aligned with strictest standard |

---

# 9. IMPLEMENTATION ROADMAP

## 9.1 Phased Rollout

```
YEAR 1                          YEAR 2                    YEAR 3
Q1    Q2    Q3    Q4           Q1    Q2    Q3    Q4      Q1    Q2    Q3    Q4
|     |     |     |            |     |     |     |       |     |     |     |

PHASE 1: CORE + ANCHOR COUNTRIES
├─ Platform build ─────┤
├─ BCEAO license ──────────┤
├─ CI integration ─────┤
├─ SN integration ─────┤
├─ BF integration ──┤
      ├─ NG (CBN license) ──────────┤
      ├─ NG (NIBSS + eNaira) ──────────┤
         ├─ GH (BoG license) ──────┤
         ├─ GH (GhIPSS + MMI) ────────┤
                  ├─ GO LIVE: 5 COUNTRIES ──►

PHASE 2: WAEMU EXPANSION + CAPE VERDE
                           ├─ ML integration ──┤
                           ├─ BJ integration ──┤
                           ├─ TG integration ──┤
                              ├─ NE integration ────┤
                              ├─ CV integration ────┤
                                       ├─ GO LIVE: 10 COUNTRIES ──►

PHASE 3: REMAINING ECOWAS
                                          ├─ GN integration ──────┤
                                          ├─ GM integration ──────┤
                                             ├─ SL integration ──────┤
                                             ├─ LR integration ──────┤
                                             ├─ GW integration ──┤
                                                         ├─ ALL 15 LIVE ──►
```

## 9.2 Key Milestones

| Milestone | Target Date | Success Criteria |
|-----------|------------|------------------|
| M1: Platform MVP | Month 4 | eCFA ↔ eCFA transfers working |
| M2: BCEAO agreement signed | Month 6 | Formal partnership |
| M3: First cross-border tx (CI→SN) | Month 6 | End-to-end eCFA intra-WAEMU |
| M4: Nigeria live | Month 12 | NIP + eNaira operational |
| M5: Ghana live | Month 12 | GhIPSS + MMI operational |
| M6: First cross-zone tx (CI→NG) | Month 13 | XOF→NGN with FX conversion |
| M7: 1 million transactions | Month 14 | Volume milestone |
| M8: 10 ECOWAS countries live | Month 20 | Phase 2 complete |
| M9: EBITDA positive | Month 18 | Monthly profitability |
| M10: All 15 countries live | Month 30 | Full ECOWAS coverage |
| M11: 100 million transactions | Month 36 | Scale milestone |
| M12: $1B monthly volume | Month 42 | Critical mass |

---

# 10. RESOURCE REQUIREMENTS

## 10.1 Team Structure

### Year 1: 50 people

| Function | Headcount | Avg Salary | Total Cost |
|----------|-----------|-----------|------------|
| Engineering (platform) | 15 | $72K | $1,080K |
| Engineering (integrations) | 10 | $65K | $650K |
| DevOps / SRE | 5 | $70K | $350K |
| Product management | 3 | $80K | $240K |
| Compliance & legal | 5 | $65K | $325K |
| Business development | 5 | $60K | $300K |
| Operations / support | 4 | $45K | $180K |
| Finance | 2 | $55K | $110K |
| Executive team | 4 | $120K | $480K |
| **Total Year 1** | **53** | | **$3,715K** |

### Year 5: 180 people across 8 offices

| Office | Location | Headcount | Purpose |
|--------|----------|-----------|---------|
| HQ | Abidjan, CI | 50 | Platform, BCEAO liaison, WAEMU ops |
| Nigeria | Lagos, NG | 35 | NIBSS/CBN integration, NG market |
| Ghana | Accra, GH | 15 | GhIPSS integration, GH market |
| Senegal | Dakar, SN | 15 | WAEMU market, fintech partnerships |
| Burkina Faso | Ouagadougou, BF | 20 | USSD/data ops, government contract |
| Nigeria (eng) | Lagos, NG | 20 | Engineering hub #2 |
| Remote | Various | 15 | Compliance, specialized roles |
| Roaming | Travel | 10 | Integration teams for Phase 3 countries |
| **Total** | | **180** | |

---

# 11. SUCCESS METRICS & KPIs

## 11.1 Phase 1 KPIs (Months 1-12)

| KPI | Target | Measurement |
|-----|--------|-------------|
| Countries live | 5 | CI, SN, BF, NG, GH |
| Monthly transactions | 4M | Platform analytics |
| Monthly volume | $200M | Settlement reports |
| System uptime | 99.9% | Monitoring (Prometheus) |
| Avg transaction time (domestic) | < 5 seconds | P95 latency |
| Avg transaction time (cross-border) | < 30 seconds | P95 latency |
| Failed transaction rate | < 0.5% | Error logs |
| AML alert false positive rate | < 20% | Compliance review |
| Customer satisfaction (CSAT) | > 80% | Surveys |
| Revenue | $10.4M | Financial statements |

## 11.2 Phase 2 KPIs (Months 13-24)

| KPI | Target | Measurement |
|-----|--------|-------------|
| Countries live | 10 | +ML, BJ, TG, NE, CV |
| Monthly transactions | 12M | Platform analytics |
| Monthly volume | $650M | Settlement reports |
| EBITDA margin | > 30% | Financial statements |
| Unique active users (monthly) | 2M | User analytics |
| Cross-border tx share | > 25% | Platform analytics |

## 11.3 Phase 3 KPIs (Months 25-36)

| KPI | Target | Measurement |
|-----|--------|-------------|
| Countries live | 15 | Full ECOWAS |
| Monthly transactions | 25M+ | Platform analytics |
| Monthly volume | $1.5B+ | Settlement reports |
| Revenue run rate | $52M+/year | Financial statements |
| Unique active users (monthly) | 5M+ | User analytics |
| Market share (ECOWAS cross-border digital) | 15%+ | Industry reports |

---

# 12. SENSITIVITY ANALYSIS

## 12.1 Three Scenarios

### Base Case (presented above)
- 5 countries Year 1, 15 by Year 3
- Average fee rate: 0.35%
- Cross-border volume capture: 8% Year 1 → 22% Year 5
- All major integrations succeed
- **10-year NPV: $387M | IRR: 68.4%**

### Bull Case (favorable conditions)
- Faster rollout (10 countries Year 1)
- PAPSS partnership (routing via WASI)
- BCEAO mandates eCFA for WAEMU interoperability
- Higher fee tolerance (0.45% average)
- Mobile money operators partner rather than compete
- **10-year NPV: $612M | IRR: 89.2%**

| Year | Revenue (Bull) | EBITDA (Bull) |
|------|---------------|---------------|
| 1 | $16.8M | $4.2M |
| 3 | $78.4M | $38.2M |
| 5 | $142.0M | $72.8M |
| 10 | $385.0M | $235.0M |

### Bear Case (adverse conditions)
- Nigeria delays PSP license by 12 months
- NGN devaluation causes 6-month pause
- BCEAO requires 2 years for eCFA approval
- Only mobile money integration (no CBDC)
- Price competition drives fees to 0.25%
- 2 countries face political disruption
- **10-year NPV: $142M | IRR: 38.6%**

| Year | Revenue (Bear) | EBITDA (Bear) |
|------|---------------|---------------|
| 1 | $4.2M | -$4.8M |
| 3 | $24.6M | $6.4M |
| 5 | $48.2M | $16.8M |
| 10 | $128.0M | $62.4M |

## 12.2 Key Variable Sensitivity

| Variable | -30% Change | Base | +30% Change | Impact on Y5 Revenue |
|----------|-------------|------|-------------|---------------------|
| Transaction volume | $63.5M | $90.7M | $117.9M | $27.2M swing |
| Fee rate | $63.5M | $90.7M | $117.9M | $27.2M swing |
| FX spread revenue | $86.4M | $90.7M | $95.0M | $4.3M swing |
| Operating costs | N/A | N/A | -$15.6M to EBITDA | $15.6M swing |
| Prefunding costs | N/A | N/A | -$3.0M to FCF | $3.0M swing |

## 12.3 Breakeven Sensitivity

| Scenario | Breakeven Month | Capital Required to Breakeven |
|----------|----------------|------------------------------|
| Bull case | Month 14 | $12M |
| Base case | Month 22 | $18.5M |
| Bear case | Month 38 | $28M |

---

# 13. APPENDICES

## Appendix A: WASI Existing Technology Stack

The following components are **already built and operational**, giving WASI a 12-18 month head start:

| Component | Status | Relevance to WASI-Pay |
|-----------|--------|----------------------|
| eCFA CBDC Ledger Engine | Production-ready, 77 tests passing | Core of WAEMU payment processing |
| 17 CBDC database models | Production-ready | Wallet, transaction, compliance, settlement models |
| Monetary Policy Engine (15 endpoints, 17 live tests) | Production-ready | BCEAO rate management (validated: taux directeur 3.50% → updated to 3.25% per BCEAO June 2025), reserves, corridor rates, standing facilities, money supply M0/M1/M2, policy decisions, collateral framework |
| AML/CFT Compliance Engine (7 alert types) | Production-ready | Transaction screening |
| Settlement Engine (bilateral netting) | Production-ready | Cross-border settlement |
| USSD Engine (*384*WASI#) | Production-ready | Unbanked access layer |
| COBOL-compatible output | Production-ready | Legacy bank integration |
| FX Rate Engine (16 currencies) | Production-ready | Multi-currency conversion |
| Credit Scoring Module | Production-ready | Merchant/bank risk assessment |
| 77 automated tests (100% pass) | Verified | Quality assurance |

## Appendix B: Competitive Landscape

| Competitor | Scope | Strength | Weakness vs WASI |
|-----------|-------|----------|-----------------|
| PAPSS (Afreximbank) | Pan-African, bank-to-bank | Political backing, 9 central banks | No mobile money, no CBDC, no USSD |
| Flutterwave | Africa-wide fintech | Developer ecosystem, brand | No CBDC, no regulatory infrastructure |
| MFS Africa | Mobile money hub | 320M wallets connected | Aggregator only, no ledger, no CBDC |
| Thunes | Global cross-border | Network scale | Not Africa-focused, no sovereign data |
| SWIFT gpi | Global, bank-to-bank | Universal adoption | Expensive, slow, no mobile money |
| Terrapay | Mobile money cross-border | Growing network | No CBDC, no government contracts |
| Wave | West Africa mobile money | Free transfers, UX | Single operator, not interop layer |

**WASI's unique position:** Only player with CBDC infrastructure + USSD data network + government sovereign data contracts + multi-currency settlement engine.

## Appendix C: ECOWAS Currency Exchange Rates (Reference)

| Currency | Code | Per USD | Per EUR | Per XOF (1000) | Volatility (12mo) |
|----------|------|---------|---------|----------------|-------------------|
| CFA Franc | XOF | 607.2 | 655.957 | — | Low (EUR peg) |
| Nigerian Naira | NGN | 1,590 | 1,718 | 2,618 | Very High |
| Ghanaian Cedi | GHS | 15.5 | 16.7 | 25.5 | High |
| Guinean Franc | GNF | 8,610 | 9,302 | 14,180 | High |
| Sierra Leonean Leone | SLL | 22,800 | 24,630 | 37,550 | High |
| Liberian Dollar | LRD | 192 | 207.5 | 316 | Medium |
| Gambian Dalasi | GMD | 72 | 77.8 | 118.6 | Medium |
| Cape Verdean Escudo | CVE | 102 | 110.265 | 168 | Low (EUR peg) |

## Appendix D: Glossary

| Term | Definition |
|------|-----------|
| BCEAO | Banque Centrale des Etats de l'Afrique de l'Ouest (WAEMU central bank) |
| CBN | Central Bank of Nigeria |
| BoG | Bank of Ghana |
| CBDC | Central Bank Digital Currency |
| DNS | Deferred Net Settlement |
| eCFA | Electronic CFA Franc (WASI's CBDC platform for WAEMU) |
| ECOWAS | Economic Community of West African States (15 countries) |
| FIU | Financial Intelligence Unit |
| GIABA | Inter-Governmental Action Group against Money Laundering in West Africa |
| GhIPSS | Ghana Interbank Payment and Settlement Systems |
| GIM-UEMOA | Groupement Interbancaire Monétique de l'UEMOA |
| HSM | Hardware Security Module |
| ISO 20022 | International standard for financial messaging |
| MMI | Mobile Money Interoperability (Ghana) |
| MNO | Mobile Network Operator |
| NIBSS | Nigeria Inter-Bank Settlement System |
| NIP | NIBSS Instant Payment |
| PAPSS | Pan-African Payment and Settlement System |
| RTGS | Real-Time Gross Settlement |
| STAR-UEMOA | BCEAO's RTGS system |
| WAEMU | West African Economic and Monetary Union (8 XOF countries) |
| WAMZ | West African Monetary Zone (6 non-XOF countries) |
| WASI-Pay | WASI Payment Interoperability Platform |

---

# 14. REMITTANCE CORRIDOR ANALYSIS

Remittances represent the largest financial inflow to most ECOWAS countries — larger than FDI and ODA combined. Capturing even a fraction of remittance settlement is a game-changer.

## 14.1 Remittance Inflows by Country

| Country | Code | Remittance Inflow (2024 est.) | % of GDP | Primary Source Corridors |
|---------|------|------------------------------|----------|--------------------------|
| Nigeria | NG | $19.5B | 4.1% | US, UK, UAE, South Africa |
| Ghana | GH | $4.6B | 6.1% | US, UK, Germany, Netherlands |
| Senegal | SN | $2.9B | 9.7% | France, Italy, Spain, US |
| Mali | ML | $1.2B | 6.0% | France, CI, Spain, Gabon |
| Cote d'Ivoire | CI | $0.5B | 0.7% | France, Burkina Faso, Mali |
| Burkina Faso | BF | $0.5B | 2.4% | CI, Italy, France, Gabon |
| Guinea | GN | $0.3B | 1.4% | France, US, Sierra Leone |
| Togo | TG | $0.7B | 7.8% | Nigeria, Benin, France, Ghana |
| Benin | BJ | $0.4B | 2.1% | Nigeria, France, CI |
| Niger | NE | $0.3B | 1.9% | Nigeria, France, CI |
| The Gambia | GM | $0.7B | 31.8% | UK, US, Spain, Sweden |
| Sierra Leone | SL | $0.2B | 4.7% | US, UK, Guinea |
| Liberia | LR | $0.5B | 12.5% | US, Ghana, Sierra Leone |
| Cape Verde | CV | $0.3B | 12.5% | Portugal, US, France |
| Guinea-Bissau | GW | $0.08B | 4.2% | Portugal, France, Senegal |
| **ECOWAS Total** | | **$32.7B** | **4.1% avg** | |

Source: World Bank Migration and Remittances Data, IMF Balance of Payments (2024 estimates)

## 14.2 Cost of Sending Remittances to ECOWAS

The World Bank Remittance Prices Worldwide (RPW) database shows West Africa remains one of the most expensive corridors globally. The global average cost fell to ~6.2% in 2024, but Sub-Saharan Africa averages 7.9% and some West African corridors exceed 12%.

### Diaspora Corridors (sending $200)

| Corridor | Average Cost | Cheapest Provider | Cheapest Cost | WASI-Pay Target |
|----------|-------------|-------------------|---------------|-----------------|
| France → Senegal | 5.8% ($11.60) | Wave | 1.5% | 0.50% ($1.00) |
| France → CI | 6.2% ($12.40) | WorldRemit | 2.8% | 0.50% ($1.00) |
| France → Mali | 7.1% ($14.20) | Orange Money | 3.2% | 0.50% ($1.00) |
| France → BF | 8.2% ($16.40) | WorldRemit | 4.1% | 0.50% ($1.00) |
| UK → Nigeria | 4.8% ($9.60) | Lemfi | 1.2% | 0.50% ($1.00) |
| UK → Ghana | 5.2% ($10.40) | Lemfi | 1.5% | 0.50% ($1.00) |
| US → Nigeria | 5.4% ($10.80) | Remitly | 1.8% | 0.50% ($1.00) |
| US → Ghana | 5.8% ($11.60) | Remitly | 2.2% | 0.50% ($1.00) |
| Italy → Senegal | 6.8% ($13.60) | Wave | 2.0% | 0.50% ($1.00) |
| Spain → Gambia | 8.5% ($17.00) | WorldRemit | 4.5% | 0.50% ($1.00) |

### Intra-ECOWAS Corridors (the most expensive, least served)

| Corridor | Average Cost | Primary Method | Volume Est. | WASI-Pay Target |
|----------|-------------|----------------|-------------|-----------------|
| Nigeria → Ghana | 12-15% | Cash (hawala) | $3.2B | 0.35% |
| Nigeria → Benin | 8-12% | Cash (border) | $0.9B | 0.35% |
| CI → BF | 2-4% | Orange Money | $0.6B | 0.15% (eCFA) |
| SN → Mali | 1.5-3% | Wave/Orange | $0.4B | 0.15% (eCFA) |
| Nigeria → CI | 10-14% | Informal | $0.9B | 0.35% |
| Ghana → Nigeria | 10-14% | Informal | $0.8B | 0.35% |
| Nigeria → Niger | 6-10% | Cash | $0.3B | 0.35% |
| Guinea → SN | 5-8% | Cash/MoMo | $0.2B | 0.40% |
| Togo → Ghana | 4-8% | Cash/MoMo | $0.2B | 0.30% |
| **Intra-ECOWAS Total** | **8-12% avg** | | **$7.5B+** | **0.25-0.35% avg** |

**Key insight:** Intra-ECOWAS remittances cost 2-3x the global average, and most move through cash. WASI-Pay can offer a 95%+ cost reduction on intra-ECOWAS corridors. At $7.5B annual volume and 0.35% fee rate, this represents **$26.3M annual revenue** from intra-ECOWAS remittances alone.

## 14.3 WASI-Pay Remittance Revenue Model

### Conservative Capture Rates

| Corridor Type | Total Market | Y1 Capture | Y3 Capture | Y5 Capture | Y5 Revenue |
|--------------|-------------|-----------|-----------|-----------|-----------|
| Intra-ECOWAS remittances | $7.5B | 2% ($150M) | 8% ($600M) | 18% ($1.35B) | $4.7M |
| Diaspora → WAEMU | $6.0B | 1% ($60M) | 5% ($300M) | 12% ($720M) | $3.6M |
| Diaspora → NG/GH | $24.1B | 0.5% ($120M) | 2% ($482M) | 5% ($1.21B) | $4.8M |
| Diaspora → Others | $2.6B | 0% | 1% ($26M) | 3% ($78M) | $0.3M |
| **Total remittance** | **$32.7B** | **$330M** | **$1.41B** | **$3.36B** | **$13.4M** |

### Why WASI-Pay Wins in Remittances

1. **Last-mile delivery via eCFA/USSD**: Recipient in rural BF/NE/ML can receive directly on USSD wallet — no bank, no smartphone, no agent visit needed
2. **Zero FX cost within WAEMU**: France → Senegal uses EUR → XOF (fixed peg, no spread risk), then eCFA delivery at near-zero marginal cost
3. **Instant settlement**: vs 2-5 days for traditional remittances
4. **Regulatory umbrella**: Single BCEAO license covers 8 WAEMU destination countries
5. **Data income integration**: Remittance + data income disbursement on same rail = lower marginal cost per user

---

# 15. COMPARABLE SYSTEM BENCHMARKS

## 15.1 Global Instant Payment System Comparisons

Understanding what comparable systems cost to build and what they achieved validates WASI-Pay's financial projections.

### India UPI (Unified Payments Interface)

| Metric | Value | Source |
|--------|-------|--------|
| Launch date | April 11, 2016 (pilot), August 25, 2016 (public) | NPCI |
| Development time | ~2-2.5 years (conception 2014 → launch 2016) | NPCI |
| Development cost (central infra) | $50-100M (NPCI central switch) | NPCI annual reports (estimated) |
| Bank-side integration costs | $200M+ aggregate (300+ banks) | Industry estimates |
| Ongoing annual cost | $200-300M/year (NPCI operations across all products) | NPCI annual reports |
| Government MDR subsidy | ~$180M/year (INR 1,500 crore) | Union Budget |
| Year 1 transactions | 30 million/month (end of Year 1) | NPCI |
| Year 3 transactions | 800M-1B/month (2019) | NPCI |
| Year 5 transactions | 3.5-4B/month (2021) | NPCI |
| Current (2024) | 14-16B/month, ~$230B/month value | NPCI |
| Cumulative value processed | $2.6 trillion/year (2024) | NPCI |
| Fee model | Free P2P and P2M (zero-MDR since Jan 2020) | RBI mandate |
| Revenue model | Government subsidy; 1.1% interchange on prepaid instruments >$24 | RBI |
| Banks connected | 500+ | NPCI |
| Apps (third-party) | 60+ (PhonePe, Google Pay, Paytm, etc.) | NPCI |
| Key success factor | Government mandate (demonetization Nov 2016), zero-cost model | — |

**Relevance to WASI-Pay:** UPI proves that a centralized payment switch can achieve massive scale in a developing market. The central infrastructure cost ($50-100M) is comparable to WASI-Pay's $18.5M — but UPI serves a single 1.4B population with one currency, while WASI-Pay serves 440M across 9 currencies. UPI is government-subsidized ($180M/year in MDR subsidies); WASI-Pay must be commercially self-sustaining. WASI-Pay leverages existing infrastructure (MNO APIs, NIBSS, GhIPSS) rather than building from scratch. **Critical lesson:** UPI's "free for users" model required government subsidy and is not replicable without sovereign backing. WASI-Pay's 0.25-0.50% fee rate is sustainable and still represents a 90%+ discount vs current ECOWAS cross-border costs (8-12%).

### Brazil PIX

| Metric | Value | Source |
|--------|-------|--------|
| Announcement date | May 2018 | BCB |
| Launch date | November 16, 2020 | BCB |
| Development time | ~30 months (announcement → launch) | BCB |
| Development cost (central infra) | R$200-300M (~$40-60M USD) | BCB (estimated) |
| Bank-side integration costs | R$2-5B aggregate (800+ institutions) | Industry estimates |
| Ongoing cost | BCB absorbs as public good; minimal per-tx cost | BCB |
| Month 1 transactions | 130 million | BCB PIX statistics |
| Year 1 transactions | 1.4 billion/month | BCB |
| Year 2 transactions | 2.5 billion/month | BCB |
| Year 3 transactions | 3.5-4.0 billion/month | BCB |
| Year 4 (2024) | 5.5 billion/month, ~$450B/month value | BCB |
| Cumulative (through 2024) | ~45 billion transactions, $4+ trillion value | BCB |
| Fee model | Free P2P (BCB mandate); merchants: 0.5-1.0% (institution-set) | BCB |
| BCB infrastructure fee | R$0.01 per 10 transactions (negligible) | BCB |
| Registered PIX keys | 770+ million (3.6 per person for 215M population) | BCB |
| Financial institutions offering PIX | 800+ (banks, fintechs, credit unions) | BCB |
| Merchants accepting PIX | 12+ million (including micro/informal) | BCB |
| Previously unbanked gaining digital access | 40-50 million | BCB/World Bank |
| Cash usage at POS decline | 40% (2019) → 18-20% (2024) | BCB |
| Economy-wide cost savings | R$20-30B/year ($4-6B) in reduced cash handling | BCB estimates |

**Relevance to WASI-Pay:** PIX's central build cost ($40-60M) puts WASI-Pay's $18.5M in perspective — a third of PIX's cost for a system covering 15 countries. PIX's financial inclusion impact (40-50M unbanked gaining digital access) mirrors WASI-Pay's opportunity with West Africa's 250M+ unbanked adults. PIX's merchant adoption (12M+ including street vendors) demonstrates that even informal merchants adopt digital payments when the system is simple enough (QR codes). WASI-Pay's USSD interface serves the same simplicity function for West Africa's feature-phone-dominant market.

### Tanzania — National Payment Switch

| Metric | Value |
|--------|-------|
| Launch date | 2014 (mobile money interoperability) |
| Development cost | $3-5M (Selcom/Maxcom, much smaller scope) |
| Scope | Mobile money interoperability only (4 MNOs) |
| Transaction growth | From 0 to 2M+ transactions/month within 2 years |
| Fee model | MNO-set interchange (0.5-1.5%) |
| Current status | Fully operational, expanded to banks |
| Key lesson | Even basic interoperability unlocks massive latent demand |

**Relevance to WASI-Pay:** Tanzania proves the model works in East Africa at low cost. WASI-Pay's WAEMU integration (via eCFA ledger) is functionally equivalent but adds CBDC capabilities and cross-border settlement — a 10x upgrade at comparable or lower cost per country.

### PAPSS (Pan-African Payment and Settlement System)

| Metric | Value | Source |
|--------|-------|--------|
| Launch date | January 13, 2022 (pilot); October 2022 (commercial) | Afreximbank |
| Development cost | $50M+ (Afreximbank funded) | Afreximbank |
| Development time | ~3 years (pilot to commercial) | Afreximbank |
| Connected central banks | 12-14 (incl. BCEAO covering 8 WAEMU, BEAC covering 6 CEMAC) | Afreximbank Q2 2024 |
| Commercial banks connected | ~120+ (many in pilot/integration phase) | Afreximbank |
| Countries with live access | ~18-22 (many via BCEAO/BEAC umbrella) | Afreximbank |
| Cumulative transaction value | ~$2.5-3.0 billion (since launch through mid-2024) | Afreximbank press releases |
| Cumulative transaction count | ~1.5-2 million | Estimated from press releases |
| Peak monthly volume | ~$400-500 million (late 2024) | Afreximbank |
| Average transaction size | ~$1,500-2,000 (skews toward commercial/trade) | Derived |
| Fee model | $3-5 flat per transaction (or ~0.5% for larger) | Afreximbank |
| Transaction cap | $10,000 initially (being raised) | Afreximbank |
| Currencies supported | 42 African currencies (pairwise) | Afreximbank |
| Settlement | Real-time net settlement, pre-funded via Afreximbank guarantee | Afreximbank |
| Mobile money integration | Limited (MTN, Orange in early stages) | PAPSS |
| Key limitation | Bank-to-bank only; no retail, no CBDC, no USSD, no offline | — |

**Relevance to WASI-Pay:** PAPSS is complementary, not competitive. PAPSS handles bank-to-bank settlement for large-value commercial transfers (avg $1,500-2,000). WASI-Pay handles the retail layer (mobile money, USSD, CBDC wallets) where avg transaction is $15-80. PAPSS has explicitly acknowledged its mobile money gap. Strategy: integrate with PAPSS as a settlement rail for bank-backed corridors, while using eCFA + mobile money for retail corridors. PAPSS's $3-5 per-transaction fee makes it unsuitable for the micro-payments that dominate West African commerce — a $5 fee on a $15 merchant payment is 33%.

## 15.2 Cost Benchmarking — WASI-Pay vs Comparable Systems

| System | Central Infra Cost | Total Ecosystem Cost | Scope | Population | Central Cost/Person |
|--------|-------------------|---------------------|-------|------------|-------------------|
| UPI (India) | $50-100M | $300M+ (incl. bank integration) | 1 country, 1 currency | 1,400M | $0.04-0.07 |
| PIX (Brazil) | $40-60M | $500M+ (incl. 800 institution integration) | 1 country, 1 currency | 215M | $0.19-0.28 |
| Tanzania Switch | $3-5M | $8-10M | 1 country, MoMo interop | 65M | $0.05-0.08 |
| PAPSS | $50M+ | $80M+ | Pan-African, bank-to-bank | 1,400M (target) | $0.036 |
| **WASI-Pay** | **$18.5M** | **$53.5M (through Year 5)** | **15 countries, 9 currencies, multi-rail** | **440M** | **$0.042** |

**WASI-Pay's cost efficiency** matches PAPSS ($0.04/person) while delivering a far broader scope (retail, mobile money, CBDC, USSD — not just bank-to-bank). The key insight is that UPI and PIX's central infrastructure costs ($50-100M and $40-60M respectively) are only 2-3x WASI-Pay's $18.5M, yet those systems serve single countries with single currencies. WASI-Pay achieves this efficiency by **integrating** with existing rails (NIBSS, GhIPSS, MNO APIs) rather than building from scratch.

## 15.3 Revenue Model Benchmarking

| System | Fee Model | Revenue/Tx | Y5 Annual Revenue | Status |
|--------|----------|-----------|-------------------|--------|
| UPI | Government subsidized | ~$0.002 (interchange subsidy) | ~$800M (subsidies) | Operating loss |
| PIX | Free P2P, capped P2M | ~$0.001 | ~$400M (central bank absorbs) | Operating loss |
| PAPSS | $1-2/tx | $1.50 avg | ~$100M projected | Near breakeven |
| Flutterwave | 1.4% local, 3.8% international | $0.50-2.00 | ~$300M (est.) | Profitable |
| WASI-Pay | 0.25-0.50% | $0.16 avg | $90.7M | Projected profitable Y2 |

**Key insight:** UPI and PIX are government-funded public goods with unsustainable economics. PAPSS is bank-focused with high per-transaction fees. WASI-Pay's model (low percentage fee on high volume) is closest to Flutterwave's commercial model but with lower fees enabled by the eCFA ledger's near-zero internal cost.

---

# 16. PAPSS COEXISTENCE & INTEGRATION STRATEGY

## 16.1 PAPSS Architecture and Gaps

PAPSS was developed by Afreximbank as Africa's answer to SWIFT for intra-continental payments. It is designed to reduce Africa's dependency on correspondent banking (most intra-African payments currently route through New York, London, or Paris).

**What PAPSS does well:**
- Bank-to-bank settlement in local currencies
- ISO 20022 messaging standard
- Multilateral net settlement (reduces nostro/vostro needs)
- Political backing from African Union and Afreximbank
- 42 currency pairs supported

**What PAPSS does NOT do:**
- Mobile money integration (no MNO connectivity)
- CBDC settlement (no digital currency support)
- Retail/USSD payments (bank accounts required)
- Merchant payments (no QR code, no POS integration)
- Government-to-person disbursements
- Data income/micro-transaction payments
- Offline/voucher payments for unbanked

## 16.2 WASI-Pay + PAPSS Integration Model

Rather than competing with PAPSS, WASI-Pay should integrate as a **retail-layer participant**:

```
End User (USSD/App) → WASI-Pay (routing + FX + compliance)
                         ↓
                    ┌─────────────────────────────┐
                    │     SETTLEMENT OPTIONS       │
                    │                               │
                    │  Option A: eCFA Ledger         │ ← WAEMU internal (instant)
                    │  Option B: PAPSS               │ ← Bank-backed cross-border
                    │  Option C: Direct MNO           │ ← Mobile money corridors
                    │  Option D: NIBSS/GhIPSS         │ ← Domestic switches
                    │  Option E: Correspondent        │ ← Fallback (legacy)
                    └─────────────────────────────┘
```

### Integration Benefits

| Benefit | For WASI-Pay | For PAPSS |
|---------|------------|----------|
| Volume | Access to bank-backed settlement rail | +200M retail users feeding volume |
| Cost | PAPSS settlement cheaper than correspondent for large value | Revenue from retail-originated bank settlements |
| Coverage | PAPSS covers countries where WASI-Pay lacks direct rails | WASI-Pay extends reach to mobile/USSD users PAPSS can't reach |
| Regulatory | PAPSS political legitimacy strengthens WASI-Pay's position | Retail volume improves PAPSS utilization metrics |
| Revenue | Estimated $2-4M/year in PAPSS-routed settlements | Estimated $5-8M/year from WASI-Pay originated flows |

### Technical Integration

WASI-Pay would connect to PAPSS as a **Participant Financial Institution (PFI)** through a sponsored settlement bank in each currency zone:

| Zone | Sponsoring Bank (target) | PAPSS Participant ID |
|------|------------------------|---------------------|
| WAEMU (XOF) | BCEAO or BOAD | WASI-XOF-001 |
| Nigeria (NGN) | Access Bank or GTBank | WASI-NGN-001 |
| Ghana (GHS) | GCB Bank or Ecobank GH | WASI-GHS-001 |
| Gambia (GMD) | Trust Bank | WASI-GMD-001 |

### Revenue Attribution (PAPSS-routed transactions)

```
Transaction: $5,000 remittance, US → Nigeria (via UK bank)

Without PAPSS:
  WASI receives on eCFA/mobile rail → correspondent bank settlement → $15 cost → 3 days

With PAPSS:
  WASI receives on eCFA/mobile rail → PAPSS settlement → $2 cost → same day

WASI-Pay fee:     0.35% × $5,000 = $17.50
PAPSS fee:        $1.50
WASI net margin:  $17.50 - $1.50 - $3.00 (FX + processing) = $13.00
```

---

# 17. GOVERNANCE & INSTITUTIONAL STRUCTURE

## 17.1 Recommended Corporate Structure

For multi-country payment operations across ECOWAS, the optimal structure separates the technology holding company from the operating entities:

```
WASI Holdings Ltd (Mauritius or Rwanda — tax treaty advantages)
├── WASI Technology SAS (CI) — Platform development, IP ownership
├── WASI-Pay UEMOA SA (CI) — BCEAO-licensed e-money institution
├── WASI-Pay Nigeria Ltd (NG) — CBN PSP/PSSP licensed entity
├── WASI-Pay Ghana Ltd (GH) — BoG PSP licensed entity
├── WASI Data Burkina SARL (BF) — Sovereign data contract entity
└── WASI Labs (Remote) — R&D, future product development
```

## 17.2 Board Composition (Target)

| Seat | Profile | Rationale |
|------|---------|-----------|
| Founder/CEO | WASI founder | Vision, technology, West Africa expertise |
| CTO | Senior engineer, payment systems background | Technical leadership |
| Independent Director | Former BCEAO/CBN executive | Regulatory credibility, central bank relationships |
| Independent Director | African fintech executive (ex-Flutterwave, Paystack, MFS Africa) | Industry expertise, partnerships |
| Investor Director | Lead investor representative | Governance, financial oversight |
| Independent Director | Compliance/legal expert (GIABA, FATF background) | AML/CFT credibility |

## 17.3 Advisory Board (Target)

| Advisor | Background | Value |
|---------|-----------|-------|
| Former BCEAO Governor | Monetary policy, WAEMU regulation | BCEAO access, credibility |
| ECOWAS Commission Member | Regional integration, ETLS | Political cover, regulatory access |
| Global CBDC Expert | BIS, IMF, or existing CBDC project | Technical credibility |
| African VC Partner | Partech Africa, TLcom, or similar | Fundraising, market intelligence |

---

# 18. INVESTMENT THESIS — EXECUTIVE DECISION FRAMEWORK

## 18.1 Why Invest in WASI-Pay Now

### The Window Is Open

1. **PAPSS hasn't solved retail:** PAPSS launched in 2022 and has connected 12 central banks for bank-to-bank settlement, but retail payment interoperability remains unsolved. The first mover in retail ECOWAS interoperability wins.

2. **CBDCs are moving from pilot to production:** Nigeria's eNaira (2021), Ghana's eCedi (pilot), BCEAO exploring digital franc — the central banks are investing in CBDC infrastructure but lack retail distribution. WASI-Pay is the distribution layer.

3. **Mobile money regulation is opening:** BCEAO's 2024 e-money directives, Nigeria's PSB framework, Ghana's open banking push — regulators are creating space for interoperability players.

4. **Remittance costs are under political pressure:** G20 commitment to reduce remittance costs to 3% by 2030, AU Agenda 2063 targets — political will is aligned.

5. **Existing infrastructure reduces build cost:** NIBSS, GhIPSS, STAR-UEMOA, MNO APIs — the building blocks exist. WASI-Pay connects them, not replaces them.

### The Moat

| Competitive Advantage | Durability | Replication Difficulty |
|----------------------|------------|----------------------|
| eCFA CBDC platform (operational) | High | 18+ months to replicate, needs BCEAO relationship |
| USSD data collection network | High | Takes years to build agent/reporter network |
| BF sovereign data contract | High | First-mover government relationship |
| Multi-currency settlement engine | Medium | Technically replicable but regulatory approvals take 1-2 years |
| 77-test verified codebase | Medium | Code quality is a moat vs competitors with technical debt |
| BCEAO monetary policy integration | Very High | No competitor has this — it's the reason BCEAO would partner |

## 18.2 Return Summary

| Metric | Bear | Base | Bull |
|--------|------|------|------|
| 10-year NPV (12%) | $142M | $387M | $612M |
| 10-year IRR | 38.6% | 68.4% | 89.2% |
| Year 5 EBITDA | $16.8M | $38.7M | $72.8M |
| Year 5 EBITDA margin | 34.9% | 42.7% | 51.3% |
| Year 10 revenue | $128.0M | $245.0M | $385.0M |
| Payback period | 3.2 years | 2.3 years | 1.2 years |
| MOIC (10-year) | 7.7x | 22.7x | 33.1x |

### Comparable Valuations

| Company | Valuation | Revenue Multiple | Status |
|---------|-----------|-----------------|--------|
| Flutterwave | $3.0B (2022) | 10-15x revenue | Private, profitable |
| Chipper Cash | $2.0B (2022, down) | 15-20x revenue | Private, pre-profit |
| MFS Africa | $100M+ | 8-12x revenue | Private, growing |
| OPay | $2.0B (2024) | 5-8x revenue | Private, Nigeria-focused |
| WASI-Pay (Year 5 implied) | $545M-$1.4B | 6-15x on $90.7M revenue | Projected |

At a conservative 6x Year 5 revenue multiple, WASI-Pay would be valued at **$544M** — a **29.4x return** on the initial $18.5M investment. At 10x (median for African fintech), the valuation reaches **$907M**.

## 18.3 Use of Funds — $18.5M Allocation

```
Technology Development          ████████████  $4.5M  (24%)
  Platform core + FX engine     $2.0M
  Country adapters              $1.5M
  Security + compliance systems $1.0M

Prefunding (Settlement Pools)   ██████████████  $5.0M  (27%)
  XOF pool (BCEAO)              $2.0M
  NGN pool (CBN)                $1.5M
  GHS pool (BoG)                $0.8M
  Other currencies              $0.7M

Personnel (Year 1 Team)         ████████████  $3.6M  (19%)
  53 staff across 4 offices

Country Integrations            ██████████  $2.7M  (15%)
  Nigeria (NIBSS + eNaira)      $1.2M
  Ghana (GhIPSS + MMI)          $0.8M
  WAEMU (3 priority countries)  $0.7M

Regulatory & Licensing          ████  $1.5M  (8%)
  BCEAO e-money license         $0.12M
  CBN PSP + PSSP licenses       $0.35M
  BoG PSP license               $0.08M
  Legal (multi-jurisdiction)    $0.95M

Working Capital                 ███  $1.2M  (7%)
  Office setup (4 locations)    $0.4M
  Travel & BD                   $0.3M
  Insurance                     $0.2M
  Contingency                   $0.3M
```

---

# 19. CONCLUSION

West Africa's 440 million people need a payment system that works for how they actually transact — mobile money, USSD, small amounts, multiple currencies, cross-border. The existing infrastructure (NIBSS, GhIPSS, STAR-UEMOA, mobile money operators) provides the building blocks but no one has connected them into a coherent whole.

WASI-Pay is uniquely positioned to be that connective layer because:

1. **We already built the hard part** — the eCFA CBDC platform with double-entry ledger, monetary policy integration, AML/CFT compliance, and settlement engine
2. **We have the unbanked access layer** — USSD data collection network across ECOWAS
3. **We have the government relationship** — Burkina Faso sovereign data contract provides the first user base and regulatory cover
4. **The market is ready** — regulators are opening, CBDCs are moving to production, and political will for lower remittance costs is at an all-time high
5. **The economics work** — 0.35% average fee on growing transaction volume delivers 42.7% EBITDA margins by Year 5

The $18.5M investment required is modest relative to the opportunity ($32.7B in remittances, $120B+ in intra-ECOWAS trade, $180B in mobile money volume). At our base case projections, investors can expect a 68.4% IRR and 22.7x MOIC over 10 years.

The window is open. The building blocks exist. The question is not whether ECOWAS payment interoperability will happen — it is whether WASI builds it or waits for someone else to.

---

*This document is the property of WASI. Reproduction without authorization is prohibited.*

*Reference: WASI/ECOWAS/INTEROP/2026-001 — Version 1.1 — March 2026*
