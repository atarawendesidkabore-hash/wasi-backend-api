"""
ACLED Conflict Data Scraper — src/pipelines/scrapers/acled_scraper.py

Fetches armed conflict event data from ACLED (Armed Conflict Location & Event Data Project)
for WASI countries and creates/updates NewsEvent records with real security signals.

API:        https://api.acleddata.com/acled/read  (free tier, requires registration)
Key:        Register at https://acleddata.com/register/ — set ACLED_API_KEY + ACLED_EMAIL in .env
Rate limit: 10,000 rows/month on free tier. This scraper fetches ~30 days of events.

Fallback:   If no API key is configured, uses hardcoded known-conflict regions
            (BF, ML, NE Sahel corridor) to create conservative warning signals.

Event mapping (ACLED → WASI event types):
  Battles, Explosions/Remote violence    → POLITICAL_RISK    (magnitude -18)
  Violence against civilians             → POLITICAL_RISK    (magnitude -12)
  Riots, Protests (at ports/borders)     → STRIKE            (magnitude -8)
  Strategic developments (convoy)        → ROAD_CORRIDOR_BLOCKED (magnitude -20)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import SessionLocal
from src.database.models import Country, NewsEvent

logger = logging.getLogger(__name__)

# ── API config ────────────────────────────────────────────────────────────────
ACLED_API_URL   = "https://api.acleddata.com/acled/read"
REQUEST_TIMEOUT = 20
LOOKBACK_DAYS   = 30    # fetch events from last 30 days

# ACLED country names (how ACLED names them, not ISO codes)
ACLED_COUNTRY_NAMES: Dict[str, str] = {
    "CI": "Ivory Coast",
    "NG": "Nigeria",
    "GH": "Ghana",
    "SN": "Senegal",
    "BF": "Burkina Faso",
    "ML": "Mali",
    "GN": "Guinea",
    "BJ": "Benin",
    "TG": "Togo",
    "NE": "Niger",
    "MR": "Mauritania",
    "GW": "Guinea-Bissau",
    "SL": "Sierra Leone",
    "LR": "Liberia",
    "GM": "Gambia",
    "CV": "Cabo Verde",
}

# ACLED event types → WASI event types
EVENT_TYPE_MAP: Dict[str, str] = {
    "Battles":                        "POLITICAL_RISK",
    "Explosions/Remote violence":     "POLITICAL_RISK",
    "Violence against civilians":     "POLITICAL_RISK",
    "Riots":                          "STRIKE",
    "Protests":                       "STRIKE",
    "Strategic developments":         "ROAD_CORRIDOR_BLOCKED",
}

EVENT_MAGNITUDE: Dict[str, float] = {
    "POLITICAL_RISK":        -18.0,
    "STRIKE":                -8.0,
    "ROAD_CORRIDOR_BLOCKED": -20.0,
}

EVENT_LIFETIME: Dict[str, timedelta] = {
    "POLITICAL_RISK":        timedelta(days=7),
    "STRIKE":                timedelta(days=3),
    "ROAD_CORRIDOR_BLOCKED": timedelta(days=4),
}

# Conflict intensity thresholds — only create signals above these counts
MIN_EVENTS_FOR_SIGNAL: Dict[str, int] = {
    "POLITICAL_RISK":        3,    # 3+ battle/explosion events in 30d
    "STRIKE":                5,    # 5+ riot/protest events in 30d
    "ROAD_CORRIDOR_BLOCKED": 2,    # 2+ strategic developments (convoy attacks)
}

# Known high-risk corridor countries — used when no API key is configured
_FALLBACK_RISK: Dict[str, Dict] = {
    "BF": {"event_type": "POLITICAL_RISK", "fatalities": 15,
           "headline": "Burkina Faso: ongoing armed group activity — ECOWAS security alert (fallback estimate)"},
    "ML": {"event_type": "POLITICAL_RISK", "fatalities": 12,
           "headline": "Mali: armed group activity on Bamako-Abidjan corridor (fallback estimate)"},
    "NE": {"event_type": "ROAD_CORRIDOR_BLOCKED", "fatalities": 8,
           "headline": "Niger: corridor restrictions following security incidents (fallback estimate)"},
}


# ── API helpers ───────────────────────────────────────────────────────────────

def _fetch_acled_events(country_name: str, start_date: str) -> List[Dict]:
    """
    Fetch ACLED events for one country since start_date (YYYY-MM-DD).
    Returns list of event dicts. Raises on network error.
    """
    params = {
        "key":              settings.ACLED_API_KEY,
        "email":            settings.ACLED_EMAIL,
        "country":          country_name,
        "event_date":       start_date,
        "event_date_where": ">=",
        "limit":            200,
        "fields":           "event_id_cnty,event_date,event_type,sub_event_type,country,location,fatalities,notes",
    }
    resp = requests.get(ACLED_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != 200:
        raise ValueError(f"ACLED API error: {payload.get('error', 'unknown')}")
    return payload.get("data", [])


def _aggregate_by_event_type(events: List[Dict]) -> Dict[str, Dict]:
    """
    Group ACLED events by mapped WASI event type.
    Returns {wasi_event_type: {count, total_fatalities, locations, latest_notes}}
    """
    buckets: Dict[str, Dict] = {}
    for ev in events:
        acled_type = ev.get("event_type", "")
        wasi_type = EVENT_TYPE_MAP.get(acled_type)
        if not wasi_type:
            continue
        if wasi_type not in buckets:
            buckets[wasi_type] = {
                "count": 0, "total_fatalities": 0,
                "locations": set(), "notes": [],
            }
        b = buckets[wasi_type]
        b["count"] += 1
        b["total_fatalities"] += int(ev.get("fatalities") or 0)
        loc = ev.get("location", "")
        if loc:
            b["locations"].add(loc)
        note = ev.get("notes", "")
        if note and len(b["notes"]) < 3:
            b["notes"].append(note[:200])

    return buckets


def _save_event_if_significant(
    db: Session,
    country: Country,
    wasi_type: str,
    bucket: Dict,
    source_url: str = "https://acleddata.com",
) -> bool:
    """
    Create a NewsEvent if the bucket exceeds the minimum event threshold
    and no active event of the same type already exists for this country.
    Returns True if a new event was created.
    """
    threshold = MIN_EVENTS_FOR_SIGNAL.get(wasi_type, 3)
    if bucket["count"] < threshold:
        return False

    # Check for active existing event of same type
    now = datetime.now(timezone.utc)
    existing = (
        db.query(NewsEvent)
        .filter(
            NewsEvent.country_id == country.id,
            NewsEvent.event_type == wasi_type,
            NewsEvent.is_active == True,
            NewsEvent.expires_at > now,
        )
        .first()
    )
    if existing:
        # Update expiry to extend
        existing.expires_at = now + EVENT_LIFETIME[wasi_type]
        return False

    locations_str = ", ".join(list(bucket["locations"])[:4]) or "multiple locations"
    notes_str = "; ".join(bucket["notes"]) if bucket["notes"] else ""
    headline = (
        f"ACLED: {bucket['count']} {wasi_type.replace('_', ' ').lower()} events in {country.name} "
        f"({bucket['total_fatalities']} fatalities) — {locations_str}. {notes_str}"
    )[:490]

    expires = now + EVENT_LIFETIME[wasi_type]
    db.add(NewsEvent(
        country_id  = country.id,
        event_type  = wasi_type,
        headline    = headline,
        source_url  = source_url,
        source_name = "ACLED",
        magnitude   = EVENT_MAGNITUDE[wasi_type],
        detected_at = now,
        expires_at  = expires,
        is_active   = True,
    ))
    return True


def _apply_fallback_signals(db: Session, countries: List[Country]) -> int:
    """
    When no ACLED key is configured, apply conservative known-conflict signals
    for Sahel countries (BF, ML, NE). Creates events only if none are active.
    """
    created = 0
    country_map = {c.code: c for c in countries}
    now = datetime.now(timezone.utc)

    for code, info in _FALLBACK_RISK.items():
        country = country_map.get(code)
        if not country:
            continue
        wasi_type = info["event_type"]
        existing = (
            db.query(NewsEvent)
            .filter(
                NewsEvent.country_id == country.id,
                NewsEvent.event_type == wasi_type,
                NewsEvent.is_active == True,
                NewsEvent.expires_at > now,
            )
            .first()
        )
        if existing:
            continue
        expires = now + EVENT_LIFETIME.get(wasi_type, timedelta(days=7))
        db.add(NewsEvent(
            country_id  = country.id,
            event_type  = wasi_type,
            headline    = info["headline"],
            source_url  = "https://acleddata.com",
            source_name = "ACLED (fallback — add ACLED_API_KEY for real data)",
            magnitude   = EVENT_MAGNITUDE[wasi_type],
            detected_at = now,
            expires_at  = expires,
            is_active   = True,
        ))
        created += 1
        logger.info("ACLED fallback: created %s event for %s", wasi_type, code)

    db.commit()
    return created


# ── Main entry ────────────────────────────────────────────────────────────────

def run_acled_scraper(db: Session = None) -> Dict:
    """
    Fetch ACLED conflict data for all WASI countries and create NewsEvent records.

    - If ACLED_API_KEY is set in .env, uses live ACLED API.
    - If not, applies conservative fallback signals for known Sahel conflict zones.

    Returns: {events_created, events_skipped, errors, countries_scanned, api_used}
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    summary = {
        "events_created": 0, "events_skipped": 0, "errors": 0,
        "countries_scanned": 0, "api_used": False,
    }

    countries = db.query(Country).filter(Country.is_active == True).all()

    if not settings.ACLED_API_KEY or not settings.ACLED_EMAIL:
        logger.info("ACLED: no API key configured — applying fallback conflict signals")
        created = _apply_fallback_signals(db, countries)
        summary["events_created"] = created
        summary["api_used"] = False
        if own_session:
            db.close()
        return summary

    # Live API path
    summary["api_used"] = True
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    for country in countries:
        country_name = ACLED_COUNTRY_NAMES.get(country.code)
        if not country_name:
            continue
        try:
            events = _fetch_acled_events(country_name, start_date)
            if not events:
                summary["events_skipped"] += 1
                continue

            buckets = _aggregate_by_event_type(events)
            created_for_country = 0

            for wasi_type, bucket in buckets.items():
                created = _save_event_if_significant(db, country, wasi_type, bucket)
                if created:
                    created_for_country += 1
                    summary["events_created"] += 1
                else:
                    summary["events_skipped"] += 1

            db.commit()
            summary["countries_scanned"] += 1

            if created_for_country > 0:
                logger.info(
                    "ACLED: %s — %d raw events → %d signals created",
                    country.code, len(events), created_for_country,
                )
            else:
                logger.debug("ACLED: %s — %d events, below thresholds", country.code, len(events))

        except Exception as exc:
            logger.error("ACLED error for %s: %s", country.code, exc)
            db.rollback()
            summary["errors"] += 1

    if own_session:
        db.close()

    logger.info(
        "ACLED scraper complete — created=%d skipped=%d errors=%d",
        summary["events_created"], summary["events_skipped"], summary["errors"],
    )
    return summary
