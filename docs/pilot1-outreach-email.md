# Pilot #1 — Outreach Email + Cover Note

**Status:** DRAFT — fill blanks before sending
**Language:** French (primary) + English summary

---

## Pre-Send Checklist

| # | Task | Done |
|---|------|------|
| 1 | Fill client name, contact, company in agreement | [ ] |
| 2 | Fill WASI legal entity name + signatory | [ ] |
| 3 | Set jurisdiction (Burkina Faso recommended) | [ ] |
| 4 | Set effective date | [ ] |
| 5 | Generate pilot credentials (username + password) | [ ] |
| 6 | Top up pilot account to 100 credits | [ ] |
| 7 | Verify all 4 Day 0 endpoints return 200 | [ ] |
| 8 | Name Day 7 GO/EXTEND/STOP approvers | [ ] |
| 9 | Convert agreement to PDF for signature | [ ] |
| 10 | Final review by legal/founder | [ ] |

---

## Email

**To:** [client_email]
**Cc:** [account_manager], [cto_email]
**Subject:** WASI — Accord Pilote API + SLA | Votre acces intelligence economique Afrique de l'Ouest

---

Bonjour [Prenom],

Suite a notre echange, j'ai le plaisir de vous transmettre le dossier
complet pour le demarrage de votre pilote WASI.

### Ce que vous recevez

WASI est une plateforme d'intelligence economique couvrant les 16 pays
de la CEDEAO. Pendant 14 jours, vous aurez acces a :

- **Indices economiques temps reel** pour 16 pays (Nigeria, Cote d'Ivoire, Ghana, Senegal...)
- **Taux de change live** (XOF/EUR, XOF/USD)
- **Prix des matieres premieres** (cacao, petrole, or, coton, cafe, minerai de fer)
- **Donnees macroeconomiques FMI** (PIB, inflation, dette, balance courante)
- **Scoring credit advisory** pour vos decisions d'investissement
- **Indice composite WASI** — score unique de sante economique regionale

### Conditions du pilote

| Element | Valeur |
|---------|--------|
| Duree | 14 jours |
| Credits API | 100 (suffisant pour ~80-100 requetes) |
| Cout | Gratuit (evaluation) |
| Support | Email + WhatsApp, Lun-Ven 09h-18h UTC |

### Documents joints

1. **Accord Pilote + SLA** (pilot-agreement-sla.pdf) — a signer
2. **Annexe A** — Guide d'integration (pilot-onboarding-runbook.pdf)
3. **Annexe B** — Grille tarifaire post-pilote (billing-activation-sop.pdf)
4. **Annexe C** — Tableau de bord hebdomadaire (weekly-executive-dashboard.pdf)
5. **Certificat de production** — Validation technique v4.0.0 (production-readiness-certificate.pdf)

### Prochaines etapes

1. **Signez** l'accord pilote et renvoyez-le par email
2. **Recevez** vos identifiants API sous 24h apres signature
3. **Participez** au kickoff technique (30 min, a planifier)
4. **Integrez** l'API dans votre environnement (jours 1-3)
5. **Evaluez** lors du checkpoint Day 7

### Vos identifiants (actives apres signature)

```
URL:      https://wasi-backend-api.onrender.com
Login:    POST /api/auth/login
Username: [____________]_pilot
Password: [sera communique separement par canal securise]
Credits:  100
```

### Points de controle

| Jour | Action |
|------|--------|
| J+0 | Kickoff : 4 appels API de verification |
| J+3 | Checkpoint : >= 20 appels, >= 3 endpoints utilises |
| J+7 | Revue intermediaire + enquete NPS |
| J+14 | Decision finale : GO / EXTENSION / FIN |

### Garanties de service (pilote)

| Metrique | Cible |
|----------|-------|
| Disponibilite | >= 99.0% |
| Temps de reponse (p50) | < 800ms |
| Temps de reponse (p95) | < 2 000ms |
| Fraicheur des indices | < 6h (composite), < 12 mois (pays) |

Je reste a votre disposition pour toute question. N'hesitez pas a
repondre directement a cet email ou a me contacter sur WhatsApp.

Cordialement,

[Votre Nom]
[Votre Titre]
WASI — West African Shipping Intelligence
[telephone]
[email]

---

## English Summary (for international clients)

**Subject:** WASI — Pilot API Agreement + SLA | West African Economic Intelligence Access

Dear [First Name],

Please find attached your WASI pilot package:

- 14-day free evaluation of our West African economic intelligence API
- 100 API credits covering indices, FX rates, commodities, IMF macro data, and credit advisory for 16 ECOWAS countries
- Signed agreement required before credential activation

Attachments: Pilot Agreement + SLA, Integration Guide, Pricing Grid, Weekly Dashboard Template, Production Readiness Certificate.

Next steps: sign and return the agreement, receive credentials within 24h, join a 30-minute kickoff call.

Best regards,
[Your Name]

---

## Decision Log — Pilot #1

**Client:** ________________________________
**Pilot start:** ___/___/2026
**Pilot end:** ___/___/2026

### Approvers for Day 14 Decision

| Role | Name | Signature |
|------|------|-----------|
| Account Manager | ____________ | ____________ |
| CTO / Tech Lead | ____________ | ____________ |
| CEO / Founder | ____________ | ____________ |

### Decision Record

| Checkpoint | Date | Status | Notes |
|------------|------|--------|-------|
| Day 0 kickoff | | | |
| Day 3 gate | | PASS / FAIL | |
| Day 7 NPS | | Score: ___ | |
| Day 14 decision | | GO / EXTEND / STOP | |

### If GO — Paid Conversion

| Item | Value |
|------|-------|
| Selected plan | Pro / Business / Enterprise |
| Monthly fee | EUR ___ |
| Payment method | Mobile Money / Card / Transfer |
| Start date | ___/___/2026 |
| Approved by | ____________ |

### If EXTEND — Pilot Extension

| Item | Value |
|------|-------|
| Extension duration | 14 days / 30 days |
| Additional credits | ___ |
| Blockers to resolve | |
| New checkpoint date | ___/___/2026 |

### If STOP — Closure

| Item | Value |
|------|-------|
| Reason | |
| Client feedback | |
| Re-engagement date | ___/___/2026 (30 days) |
| Lessons learned | |

---

## Frozen Commercial Terms (Source of Truth)

These terms are locked for Pilot #1. Any modification requires
approval from both Account Manager and CEO.

| Term | Value | Locked |
|------|-------|--------|
| Pilot duration | 14 days | YES |
| Pilot credits | 100 | YES |
| Pilot cost | EUR 0 | YES |
| Pro plan | EUR 150/mo, 1000 cr | YES |
| Business plan | EUR 500/mo, 5000 cr | YES |
| Enterprise plan | EUR 1500/mo, 20000 cr | YES |
| Overage (Pro) | EUR 0.20/cr | YES |
| Overage (Business) | EUR 0.15/cr | YES |
| Overage (Enterprise) | EUR 0.10/cr | YES |
| Uptime SLA (pilot) | 99.0% | YES |
| Uptime SLA (Pro) | 99.5% | YES |
| Uptime SLA (Business) | 99.7% | YES |
| Uptime SLA (Enterprise) | 99.9% | YES |
| Support (pilot) | Email+WhatsApp, 8h | YES |
| Confidentiality | 2 years post-termination | YES |
| Jurisdiction | [TBD — fill before send] | NO |
