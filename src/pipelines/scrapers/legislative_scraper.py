"""
Legislative Activity Scraper — src/pipelines/scrapers/legislative_scraper.py

Fetches legislative data from public APIs for all 16 ECOWAS countries:
  1. Laws.Africa Content API (v3) — structured legislation (acts, bills, amendments)
     Requires LAWS_AFRICA_API_TOKEN env var (free tier available).
     Endpoint: GET /v3/akn/{jurisdiction}/.json
  2. IPU Parline API — parliamentary session & structure data (free, no key)
     Endpoint: GET /api/data?country_iso={iso2}
  3. Fallback: known recent legislation seeded for primary countries.

Rate limit: 0.5s between requests (polite).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country
from src.database.legislative_models import LegislativeAct, ParliamentarySession

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = 20
REQUEST_DELAY = 0.5

# Laws.Africa jurisdiction codes (lowercase) → WASI ISO-2
LAWS_AFRICA_JURISDICTIONS: Dict[str, str] = {
    "ng": "NG",   # Nigeria
    "gh": "GH",   # Ghana
    "sl": "SL",   # Sierra Leone
    "gm": "GM",   # Gambia
    "lr": "LR",   # Liberia
}

# IPU country ISO-2 codes for all 16 ECOWAS
ECOWAS_ISO2 = [
    "NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ",
    "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV",
]

# Category detection keywords (bilingual EN/FR)
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "TRADE": [
        "trade", "export", "import", "commerce", "commercial",
        "échange", "exportation", "importation", "accord commercial",
    ],
    "TARIFF": [
        "tariff", "duty", "customs duty", "tarif", "droit de douane",
        "taxe douanière", "levy",
    ],
    "INVESTMENT": [
        "investment", "investissement", "code des investissements",
        "foreign investment", "investissement étranger", "incentive",
    ],
    "FISCAL": [
        "tax", "fiscal", "finance act", "budget", "loi de finances",
        "impôt", "taxe", "revenue", "recette",
    ],
    "CUSTOMS": [
        "customs", "douane", "port regulation", "règlement portuaire",
        "clearance", "dédouanement",
    ],
    "REGULATORY": [
        "regulation", "compliance", "règlement", "conformité",
        "licensing", "autorisation",
    ],
    "LABOR": [
        "labor", "labour", "employment", "travail", "emploi",
        "worker", "sécurité sociale",
    ],
    "INFRASTRUCTURE": [
        "infrastructure", "road", "rail", "port", "airport",
        "route", "chemin de fer", "aéroport", "modernization",
    ],
    "ENVIRONMENT": [
        "environment", "environnement", "climate", "climat",
        "pollution", "mining", "exploitation minière",
    ],
}


def _detect_category(title: str, description: str = "") -> str:
    """Detect legislative category from title + description keywords."""
    text = f"{title} {description}".lower()
    best_cat = "OTHER"
    best_count = 0
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_count = count
            best_cat = cat
    return best_cat


def _generate_external_id(source: str, jurisdiction: str, identifier: str) -> str:
    """Create a dedup-friendly external ID."""
    return f"{source}:{jurisdiction}:{identifier}"


# ── Laws.Africa API ───────────────────────────────────────────────────────────

def _fetch_laws_africa(api_token: str) -> List[dict]:
    """
    Fetch recent legislation from Laws.Africa Content API v3.
    Returns list of raw act dicts.
    """
    if not api_token:
        logger.info("LAWS_AFRICA_API_TOKEN not set — skipping Laws.Africa fetch")
        return []

    headers = {"Authorization": f"Token {api_token}"}
    results = []
    cutoff = (date.today() - timedelta(days=365)).isoformat()

    for jurisdiction, iso2 in LAWS_AFRICA_JURISDICTIONS.items():
        url = f"https://api.laws.africa/v3/akn/{jurisdiction}/.json"
        params = {"date_from": cutoff, "page_size": 20, "ordering": "-date"}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 401:
                logger.warning("Laws.Africa: invalid API token")
                return results
            if resp.status_code == 404:
                logger.debug("Laws.Africa: no data for jurisdiction %s", jurisdiction)
                time.sleep(REQUEST_DELAY)
                continue
            resp.raise_for_status()
            data = resp.json()
            works = data.get("results", [])
            for work in works:
                results.append({
                    "iso2": iso2,
                    "title": work.get("title", "Untitled"),
                    "description": work.get("description", ""),
                    "act_number": work.get("number", ""),
                    "act_date": work.get("date", ""),
                    "source_url": work.get("url", ""),
                    "external_id": _generate_external_id(
                        "laws_africa", jurisdiction,
                        work.get("frbr_uri", work.get("id", "")),
                    ),
                    "source": "laws_africa",
                    "confidence": 0.85,
                })
            logger.info(
                "Laws.Africa: %s (%s) — %d works fetched",
                jurisdiction.upper(), iso2, len(works),
            )
        except Exception as exc:
            logger.warning("Laws.Africa: error fetching %s: %s", jurisdiction, exc)
        time.sleep(REQUEST_DELAY)

    return results


# ── IPU Parline API ───────────────────────────────────────────────────────────

def _fetch_ipu_parline() -> List[dict]:
    """
    Fetch parliamentary data from IPU Parline for all ECOWAS countries.
    Free API, no key required.
    Returns list of session summary dicts.
    """
    results = []
    base_url = "https://data.ipu.org/api"

    for iso2 in ECOWAS_ISO2:
        url = f"{base_url}/data"
        params = {"country_iso": iso2, "format": "json"}
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.debug("IPU Parline: no data for %s (status %d)", iso2, resp.status_code)
                time.sleep(REQUEST_DELAY)
                continue
            data = resp.json()
            # IPU returns parliamentary structure/composition data
            if isinstance(data, dict):
                results.append({
                    "iso2": iso2,
                    "data": data,
                    "source": "ipu_parline",
                })
            logger.debug("IPU Parline: fetched data for %s", iso2)
        except Exception as exc:
            logger.debug("IPU Parline: error fetching %s: %s", iso2, exc)
        time.sleep(REQUEST_DELAY)

    return results


# ── Fallback seed data ────────────────────────────────────────────────────────
# Real recent legislation from ECOWAS primary countries (publicly known laws).
# Used when APIs are unreachable on first bootstrap.

FALLBACK_LEGISLATION = [
    # Nigeria
    {"iso2": "NG", "title": "Nigeria Finance Act 2025", "act_number": "FA-2025",
     "act_date": "2025-12-31", "category": "FISCAL",
     "description": "Annual finance act amending tax rates, customs duties, and fiscal incentives for 2025.",
     "source_name": "National Assembly of Nigeria", "confidence": 0.90},
    {"iso2": "NG", "title": "Nigeria Customs Service (Establishment) Act 2023", "act_number": "NCS-2023",
     "act_date": "2023-08-17", "category": "CUSTOMS",
     "description": "Restructures Nigeria Customs Service, modernizes customs administration and trade facilitation.",
     "source_name": "National Assembly of Nigeria", "confidence": 0.90},
    {"iso2": "NG", "title": "Nigeria Startup Act 2022", "act_number": "NSA-2022",
     "act_date": "2022-10-19", "category": "INVESTMENT",
     "description": "Provides tax relief, grants, and regulatory sandbox for technology startups in Nigeria.",
     "source_name": "National Assembly of Nigeria", "confidence": 0.90},
    {"iso2": "NG", "title": "Petroleum Industry Act 2021", "act_number": "PIA-2021",
     "act_date": "2021-08-16", "category": "TRADE",
     "description": "Overhauls governance of petroleum industry, creates new fiscal framework for oil and gas sector.",
     "source_name": "National Assembly of Nigeria", "confidence": 0.90},
    # Ghana
    {"iso2": "GH", "title": "Ghana Revenue Authority (Amendment) Act 2024", "act_number": "GRA-2024",
     "act_date": "2024-06-15", "category": "FISCAL",
     "description": "Strengthens revenue collection, introduces digital tax payment infrastructure.",
     "source_name": "Parliament of Ghana", "confidence": 0.90},
    {"iso2": "GH", "title": "Ghana Investment Promotion Centre Act 2013 (Amendment 2024)",
     "act_number": "GIPC-2024", "act_date": "2024-03-20", "category": "INVESTMENT",
     "description": "Updates foreign investment thresholds, expands sectors eligible for tax holidays.",
     "source_name": "Parliament of Ghana", "confidence": 0.90},
    {"iso2": "GH", "title": "Customs (Amendment) Act 2023", "act_number": "CA-2023",
     "act_date": "2023-12-10", "category": "CUSTOMS",
     "description": "Modernizes customs valuation, implements ECOWAS Common External Tariff compliance.",
     "source_name": "Parliament of Ghana", "confidence": 0.90},
    # Côte d'Ivoire
    {"iso2": "CI", "title": "Loi de Finances 2025 — Côte d'Ivoire", "act_number": "LF-2025-CI",
     "act_date": "2024-12-20", "category": "FISCAL",
     "description": "Loi de finances annuelle: ajustements TVA, droits de douane, incitations fiscales zones industrielles.",
     "source_name": "Assemblée Nationale de Côte d'Ivoire", "confidence": 0.90},
    {"iso2": "CI", "title": "Code des Investissements 2024 — Côte d'Ivoire", "act_number": "CI-INV-2024",
     "act_date": "2024-07-15", "category": "INVESTMENT",
     "description": "Nouveau code des investissements: exonérations fiscales, zones économiques spéciales, guichet unique.",
     "source_name": "Assemblée Nationale de Côte d'Ivoire", "confidence": 0.90},
    # Senegal
    {"iso2": "SN", "title": "Loi sur le Contenu Local — Pétrole et Gaz 2022", "act_number": "SN-CL-2022",
     "act_date": "2022-01-20", "category": "TRADE",
     "description": "Exige un contenu local minimum dans les contrats pétroliers et gaziers au Sénégal.",
     "source_name": "Assemblée Nationale du Sénégal", "confidence": 0.90},
    {"iso2": "SN", "title": "Loi de Finances 2025 — Sénégal", "act_number": "LF-2025-SN",
     "act_date": "2024-12-18", "category": "FISCAL",
     "description": "Budget annuel: droits de douane sur importations, recettes pétrolières, investissements portuaires.",
     "source_name": "Assemblée Nationale du Sénégal", "confidence": 0.90},
    # Burkina Faso
    {"iso2": "BF", "title": "Loi portant Code Minier du Burkina Faso 2024", "act_number": "BF-CM-2024",
     "act_date": "2024-06-25", "category": "TRADE",
     "description": "Révision du code minier: augmentation des royalties, obligation de transformation locale.",
     "source_name": "Assemblée Législative de Transition du Burkina Faso", "confidence": 0.85},
    # Mali
    {"iso2": "ML", "title": "Loi portant Code des Douanes du Mali 2023", "act_number": "ML-CD-2023",
     "act_date": "2023-09-10", "category": "CUSTOMS",
     "description": "Nouveau code des douanes: procédures simplifiées, contrôle électronique, tarif extérieur commun CEDEAO.",
     "source_name": "Conseil National de Transition du Mali", "confidence": 0.80},
    # Guinea
    {"iso2": "GN", "title": "Code Minier de la République de Guinée 2023", "act_number": "GN-CM-2023",
     "act_date": "2023-04-10", "category": "TRADE",
     "description": "Cadre fiscal minier révisé: bauxite, or, diamants. Obligations de transformation locale renforcées.",
     "source_name": "Conseil National de la Transition de Guinée", "confidence": 0.85},
    # Benin
    {"iso2": "BJ", "title": "Loi de Finances 2025 — Bénin", "act_number": "LF-2025-BJ",
     "act_date": "2024-12-22", "category": "FISCAL",
     "description": "Budget annuel: investissements portuaires Cotonou, zones franches, fiscalité numérique.",
     "source_name": "Assemblée Nationale du Bénin", "confidence": 0.85},
    # Togo
    {"iso2": "TG", "title": "Loi portant Code des Investissements du Togo 2024", "act_number": "TG-CI-2024",
     "act_date": "2024-05-15", "category": "INVESTMENT",
     "description": "Nouveau code des investissements: zone franche port de Lomé, exonérations industrielles.",
     "source_name": "Assemblée Nationale du Togo", "confidence": 0.85},
]


# ── Main entry ────────────────────────────────────────────────────────────────

def run_legislative_scraper(db: Session = None) -> Dict:
    """
    Fetch legislative data from all sources and upsert into DB.

    Returns: {acts_found, sessions_found, errors, countries_covered, sources_used}
    """
    import os
    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary = {
        "acts_found": 0, "sessions_found": 0, "errors": 0,
        "countries_covered": [], "sources_used": [],
    }

    # Build country lookup
    countries = db.query(Country).filter(Country.is_active == True).all()
    country_map: Dict[str, Country] = {c.code: c for c in countries}

    # Source 1: Laws.Africa
    api_token = os.environ.get("LAWS_AFRICA_API_TOKEN", "")
    laws_africa_data = _fetch_laws_africa(api_token)
    if laws_africa_data:
        summary["sources_used"].append("laws_africa")
        for item in laws_africa_data:
            try:
                _upsert_act(db, country_map, item, summary)
            except Exception as exc:
                logger.warning("Error upserting Laws.Africa act: %s", exc)
                summary["errors"] += 1

    # Source 2: IPU Parline (session data)
    ipu_data = _fetch_ipu_parline()
    if ipu_data:
        summary["sources_used"].append("ipu_parline")
        for item in ipu_data:
            try:
                _process_ipu_data(db, country_map, item, summary)
            except Exception as exc:
                logger.warning("Error processing IPU data: %s", exc)
                summary["errors"] += 1

    # Source 3: Fallback seed if no acts found at all
    if summary["acts_found"] == 0:
        logger.info("No live legislative data fetched — seeding fallback legislation")
        summary["sources_used"].append("fallback_seed")
        for item in FALLBACK_LEGISLATION:
            try:
                _upsert_act(db, country_map, {
                    **item,
                    "external_id": _generate_external_id("fallback", item["iso2"], item["act_number"]),
                    "source": "fallback_seed",
                    "source_url": "",
                }, summary)
            except Exception as exc:
                logger.warning("Error seeding fallback act: %s", exc)
                summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "Legislative scraper complete: acts=%d sessions=%d errors=%d countries=%s sources=%s",
        summary["acts_found"], summary["sessions_found"], summary["errors"],
        summary["countries_covered"], summary["sources_used"],
    )
    return summary


def _upsert_act(
    db: Session,
    country_map: Dict[str, Country],
    item: dict,
    summary: dict,
) -> None:
    """Upsert a single LegislativeAct from scraped data."""
    iso2 = item.get("iso2", "")
    country = country_map.get(iso2)
    if not country:
        return

    ext_id = item.get("external_id", "")
    if not ext_id:
        return

    # Check for existing
    existing = (
        db.query(LegislativeAct)
        .filter(
            LegislativeAct.country_id == country.id,
            LegislativeAct.external_id == ext_id,
        )
        .first()
    )
    if existing:
        return

    # Parse date
    act_date_str = item.get("act_date", "")
    try:
        act_date = date.fromisoformat(act_date_str)
    except (ValueError, TypeError):
        act_date = date.today()

    # Detect category if not provided
    category = item.get("category") or _detect_category(
        item.get("title", ""), item.get("description", "")
    )

    act = LegislativeAct(
        country_id=country.id,
        title=item.get("title", "Untitled"),
        description=item.get("description", ""),
        act_number=item.get("act_number", ""),
        act_date=act_date,
        category=category,
        status="ENACTED",
        impact_type="NEUTRAL",
        estimated_magnitude=0.0,
        source_url=item.get("source_url", ""),
        source_name=item.get("source_name", ""),
        external_id=ext_id,
        confidence=item.get("confidence", 0.70),
        data_quality="high" if item.get("confidence", 0.70) >= 0.80 else "medium",
        data_source=item.get("source", "unknown"),
        is_active=True,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(act)
    db.commit()

    summary["acts_found"] += 1
    if iso2 not in summary["countries_covered"]:
        summary["countries_covered"].append(iso2)


def _process_ipu_data(
    db: Session,
    country_map: Dict[str, Country],
    item: dict,
    summary: dict,
) -> None:
    """Process IPU Parline parliamentary data into session records."""
    iso2 = item.get("iso2", "")
    country = country_map.get(iso2)
    if not country:
        return

    data = item.get("data", {})
    if not data:
        return

    # IPU provides parliamentary metadata — create a session record for today
    today = date.today()
    existing = (
        db.query(ParliamentarySession)
        .filter(
            ParliamentarySession.country_id == country.id,
            ParliamentarySession.session_date == today,
        )
        .first()
    )
    if existing:
        return

    session_rec = ParliamentarySession(
        country_id=country.id,
        session_date=today,
        bills_introduced=0,
        bills_passed=0,
        bills_rejected=0,
        key_topics=json.dumps(["parliamentary_structure_update"]),
        summary=f"IPU Parline data refresh for {iso2}",
        source_url=f"https://data.ipu.org/parliament/{iso2}/",
        data_source="ipu_parline",
        confidence=0.80,
    )
    db.add(session_rec)
    db.commit()

    summary["sessions_found"] += 1
    if iso2 not in summary["countries_covered"]:
        summary["countries_covered"].append(iso2)
