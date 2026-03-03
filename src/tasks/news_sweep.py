"""
News Sweep — Hourly Layer B signal update.

Layer A: Static index values from official stats (CSV ingestion + scrapers).
Layer B: Live adjustment from detected news events (this module).

Event types and lifetimes:
  PORT_DISRUPTION       — 72 hours  (magnitude -12)
  STRIKE                — 72 hours  (magnitude -8)
  POLITICAL_RISK        — 7 days    (magnitude -18)
  COMMODITY_SURGE       — 14 days   (magnitude -5)
  POLICY_CHANGE         — 14 days   (magnitude +5)
  DROUGHT_FOOD          — 21 days   (magnitude -10)
  CURRENCY_CRISIS       — 14 days   (magnitude -15)
  INFRASTRUCTURE_UPGRADE— 30 days   (magnitude +8)

Live adjustment capped at ±25 points.
adjusted_index clamped to [0, 100].

RSS feeds monitored:
  BBC Africa     — https://feeds.bbci.co.uk/news/world/africa/rss.xml
  Reuters Africa — https://feeds.reuters.com/Reuters/AfricaNews
  AllAfrica      — https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf
"""
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin

from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.models import Country, CountryIndex, NewsEvent, LiveSignal, GovernmentDocument

logger = logging.getLogger(__name__)

# ── Keyword tables ────────────────────────────────────────────────────────────
EVENT_KEYWORDS = {
    "PORT_DISRUPTION": [
        "port closed", "port closure", "port strike", "port disruption",
        "blocked cargo", "congestion port", "harbour shutdown", "dock workers strike",
        "shipping disruption", "vessel delays",
    ],
    "STRIKE": [
        "workers strike", "labour strike", "transport strike", "customs strike",
        "general strike", "dockworkers",
    ],
    "POLITICAL_RISK": [
        "coup", "coup d'état", "military takeover", "sanctions", "embargo",
        "political crisis", "unrest", "protest", "civil unrest", "martial law",
        "state of emergency",
    ],
    "COMMODITY_SURGE": [
        "price surge", "commodity surge", "fuel shortage", "oil price spike",
        "drought", "flood", "harvest failure", "food shortage", "commodity boom",
        "export ban",
    ],
    "POLICY_CHANGE": [
        "new tariff", "trade policy", "customs reform", "port privatization",
        "trade agreement", "investment law", "import tax", "export duty",
    ],
    "DROUGHT_FOOD": [
        "famine", "food crisis", "récolte", "sécheresse", "hunger crisis",
        "malnutrition", "crop failure", "locust", "food insecurity",
    ],
    "CURRENCY_CRISIS": [
        "devaluation", "dévaluation", "forex crisis", "currency collapse",
        "CFA franc", "taux de change", "foreign exchange shortage",
        "black market dollar", "currency peg",
    ],
    "INFRASTRUCTURE_UPGRADE": [
        "port expansion", "new terminal", "new wharf", "quay extension",
        "infrastructure investment", "port upgrade", "rail extension",
        "road construction", "bridge opening", "transport corridor",
    ],
    # New event types from WASI v3.0 spec Section 16.2
    "ROAD_CORRIDOR_BLOCKED": [
        "route coupée", "corridor bloqué", "road blocked", "attaque convoi",
        "convoy attack", "checkpoint extortion", "route fermée", "insécurité routière",
        "armed attack corridor", "corridor disruption",
    ],
    "TRADE_POSITIVE_SIGNAL": [
        "record exportation", "export record", "hausse trafic", "traffic increase",
        "nouveau contrat port", "investissement terminal", "port investment",
        "terminal expansion record",
    ],
    "RAIL_OPERATIONAL_CHANGE": [
        "SITARAIL", "reprise ferroviaire", "train marchandises", "freight train restored",
        "Simandou", "iron ore rail", "rail service restored", "rail corridor operational",
    ],
    "NEW_GOVERNMENT_DOCUMENT": [
        "bulletin statistique", "rapport mensuel", "quarterly data",
        "note de conjoncture", "statistical bulletin", "preliminary figures",
        "rapport trimestriel", "données préliminaires", "communiqué statistique",
    ],
    "LEGISLATIVE_CHANGE": [
        "new law", "parliament passes", "bill enacted", "law adopted",
        "national assembly approves", "gazette", "journal officiel",
        "loi adoptée", "assemblée nationale vote", "code adopté",
        "loi promulguée", "parliament approves", "bill signed into law",
        "finance act", "loi de finances", "investment code",
        "code des investissements", "customs act", "trade bill",
    ],
}

# Default magnitude per event type (negative = bad, positive = good)
EVENT_MAGNITUDE = {
    "PORT_DISRUPTION": -12.0,
    "STRIKE": -8.0,
    "POLITICAL_RISK": -18.0,
    "COMMODITY_SURGE": -5.0,
    "POLICY_CHANGE": 5.0,
    "DROUGHT_FOOD": -10.0,
    "CURRENCY_CRISIS": -15.0,
    "INFRASTRUCTURE_UPGRADE": 8.0,
    # New event types (v3.0 spec Section 16.2)
    "ROAD_CORRIDOR_BLOCKED": -20.0,
    "TRADE_POSITIVE_SIGNAL": 10.0,
    "RAIL_OPERATIONAL_CHANGE": 15.0,
    "NEW_GOVERNMENT_DOCUMENT": 0.0,     # neutral — triggers document download only
    "LEGISLATIVE_CHANGE": 6.0,           # positive default — refined by legislative engine
}

EVENT_LIFETIME = {
    "PORT_DISRUPTION": timedelta(hours=72),
    "STRIKE": timedelta(hours=72),
    "POLITICAL_RISK": timedelta(days=7),
    "COMMODITY_SURGE": timedelta(days=14),
    "POLICY_CHANGE": timedelta(days=14),
    "DROUGHT_FOOD": timedelta(days=21),
    "CURRENCY_CRISIS": timedelta(days=14),
    "INFRASTRUCTURE_UPGRADE": timedelta(days=30),
    # New event types (v3.0 spec Section 16.2)
    "ROAD_CORRIDOR_BLOCKED": timedelta(days=4),
    "TRADE_POSITIVE_SIGNAL": timedelta(days=14),
    "RAIL_OPERATIONAL_CHANGE": timedelta(days=14),
    "NEW_GOVERNMENT_DOCUMENT": timedelta(days=1),
    "LEGISLATIVE_CHANGE": timedelta(days=21),
}

# Country name → ISO-2 code mapping for headline matching
COUNTRY_NAME_TO_CODE = {
    "nigeria": "NG", "nigerian": "NG", "lagos": "NG", "abuja": "NG",
    "cote d'ivoire": "CI", "ivory coast": "CI", "abidjan": "CI", "ivorian": "CI",
    "ghana": "GH", "ghanaian": "GH", "accra": "GH", "tema": "GH",
    "senegal": "SN", "senegalese": "SN", "dakar": "SN",
    "burkina faso": "BF", "burkinabe": "BF", "ouagadougou": "BF",
    "mali": "ML", "malian": "ML", "bamako": "ML",
    "guinea": "GN", "guinean": "GN", "conakry": "GN",
    "benin": "BJ", "beninese": "BJ", "cotonou": "BJ",
    "togo": "TG", "togolese": "TG", "lome": "TG", "lomé": "TG",
    "niger": "NE", "nigerien": "NE", "niamey": "NE",
    "mauritania": "MR", "mauritanian": "MR", "nouakchott": "MR",
    "guinea-bissau": "GW", "bissau": "GW",
    "sierra leone": "SL", "freetown": "SL",
    "liberia": "LR", "liberian": "LR", "monrovia": "LR",
    "gambia": "GM", "gambian": "GM", "banjul": "GM",
    "cabo verde": "CV", "cape verde": "CV",
}

RSS_FEEDS = [
    # Continental Africa
    "https://feeds.bbci.co.uk/news/world/africa/rss.xml",
    "https://feeds.reuters.com/Reuters/AfricaNews",
    # Nigeria (NG)
    "https://businessday.ng/feed/",
    "https://punchng.com/feed/",
    # Côte d'Ivoire (CI)
    "https://www.fratmat.info/feed",
    # Ghana (GH)
    "https://www.ghanaweb.com/GhanaHomePage/rss/rss.xml",
    "https://businessghana.com/site/rss/news",
    # Senegal (SN)
    "https://www.seneweb.com/news/rss.php",
    # Burkina Faso (BF)
    "https://lefaso.net/spip.php?page=backend",
    # Mali (ML)
    "https://mali-web.org/feed",
    # Guinea (GN)
    "https://guineenews.org/feed/",
    # Benin / Togo (BJ/TG)
    "https://www.beninwebtv.com/feed/",
    # Niger (NE)
    "https://www.tamtaminfo.com/feed/",
    # Mauritania / Gambia / Sierra Leone / Liberia / Cape Verde
    "https://alakhbar.info/rss.xml",
]

# ── Government portal URLs — scanned for new document links ───────────────────
# Scanned hourly for new PDF/Excel/CSV documents (statistical bulletins, port reports).
# Scan is non-blocking: individual failures are logged and skipped.
GOVERNMENT_SOURCES: dict = {
    "NG": {
        "customs":   "https://www.customs.gov.ng/news",
        "ports":     "https://www.nimasa.gov.ng/news",
        "stats":     "https://nigerianstat.gov.ng/elibrary",
        "transport": "https://fmot.gov.ng/news",
        "assembly":  "https://nass.gov.ng/",
    },
    "CI": {
        "douanes":   "https://www.douanes.ci/actualites",
        "port":      "https://www.portabidjan.ci/actualites",
        "stats":     "https://www.ins.ci/actualites",
        "bceao":     "https://www.bceao.int/fr/publications",
        "assemblee": "https://www.assnat.ci/",
    },
    "GH": {
        "customs":   "https://www.gra.gov.gh/news",
        "ports":     "https://www.ghanaports.gov.gh/news",
        "stats":     "https://statsghana.gov.gh/news",
        "parliament": "https://www.parliament.gh/",
    },
    "SN": {
        "douanes":   "https://www.douanes.sn/actualites",
        "port":      "https://www.portdakar.sn/actualites",
        "ansd":      "https://www.ansd.sn/actualites",
        "assemblee": "https://www.assemblee-nationale.sn/",
    },
    "BF": {
        "dgd":       "https://www.douanes.bf/actualites",
        "sonabhy":   "https://www.sonabhy.bf/actualites",
        "finances":  "https://www.finances.gov.bf/actualites",
        "assemblee": "https://www.assembleenationale.bf/",
    },
    "ML": {
        "douanes":   "https://www.douanes.gov.ml/actualites",
        "bceao":     "https://www.bceao.int/fr/publications",
    },
    "GN": {
        "port":      "https://www.pag-guinee.com/actualites",
        "bcrg":      "https://www.bcrg-guinee.org/actualites",
    },
    "BJ": {
        "port":      "https://www.portdecotonou.com/actualites",
        "instadbe":  "https://www.insae-bj.org/actualites",
    },
    "TG": {
        "port":      "https://www.toglome.com/actualites",
        "otraf":     "https://www.otraf.tg/actualites",
    },
    "NE": {
        "finances":  "https://www.finances.gouv.ne/actualites",
        "bceao":     "https://www.bceao.int/fr/publications",
    },
    "MR": {
        "port":      "https://panpa.mr/actualites",
        "ons":       "https://www.ons.mr/actualites",
    },
    "SL": {"stats":  "https://www.statistics.sl/news"},
    "LR": {"stats":  "https://www.lisgis.net/news"},
    "GM": {"stats":  "https://www.gbos.gov.gm/news"},
    "GW": {"bceao":  "https://www.bceao.int/fr/publications"},
    "CV": {"stats":  "https://www.ine.cv/estatisticas"},
}


def _detect_country(text: str) -> Optional[str]:
    """Return ISO-2 code if any known country/city name is in the text."""
    text_lower = text.lower()
    for name, code in COUNTRY_NAME_TO_CODE.items():
        if name in text_lower:
            return code
    return None


def _detect_event_type(text: str) -> Optional[str]:
    """Return event type if any keyword matches in text."""
    text_lower = text.lower()
    for evt_type, keywords in EVENT_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return evt_type
    return None


def _expire_old_events(db: Session) -> int:
    """Mark expired events as inactive. Returns count deactivated."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    events = (
        db.query(NewsEvent)
        .filter(NewsEvent.is_active == True, NewsEvent.expires_at <= now)
        .all()
    )
    for e in events:
        e.is_active = False
    if events:
        db.commit()
    return len(events)


def _fetch_rss_headlines(feed_url: str) -> list:
    """
    Fetch RSS feed and return list of headline strings.
    Requires feedparser; falls back to empty list if not installed.
    """
    try:
        import feedparser
        feed = feedparser.parse(feed_url)
        return [
            entry.get("title", "") + " " + entry.get("summary", "")
            for entry in feed.entries[:50]   # cap at 50 entries per feed
        ]
    except ImportError:
        logger.warning("feedparser not installed — RSS sweep skipped. pip install feedparser")
        return []
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
        return []


_DOC_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".docx", ".csv", ".ods")
_SCAN_TIMEOUT = 15   # seconds per government page request


def scan_government_page(url: str, country_code: str, db: Session) -> list:
    """
    Scan a government webpage for new document links (PDF, Excel, etc.).
    Returns list of new doc dicts not already in government_documents table.
    Never raises — failures are logged and skipped.
    """
    new_docs = []
    try:
        import requests
        from bs4 import BeautifulSoup

        resp = requests.get(
            url, timeout=_SCAN_TIMEOUT,
            headers={"User-Agent": "WASI-DataBot/1.0 (+https://wasi.io)"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not any(href.lower().endswith(ext) for ext in _DOC_EXTENSIONS):
                continue
            # Resolve relative URL
            full_url = urljoin(url, href)
            if len(full_url) > 499:
                continue
            # Skip if already known
            existing = db.query(GovernmentDocument).filter(
                GovernmentDocument.url == full_url
            ).first()
            if existing:
                continue
            title = a_tag.get_text(strip=True) or full_url.split("/")[-1]
            new_docs.append({
                "country_code": country_code,
                "url": full_url,
                "title": title[:499],
            })
    except ImportError:
        logger.warning("requests/bs4 not installed — government page scan skipped")
    except Exception as exc:
        logger.debug("Gov page scan failed %s: %s", url, exc)
    return new_docs


def _save_government_doc(db: Session, doc: dict, country: "Country") -> bool:
    """
    Insert GovernmentDocument row. Returns True if inserted, False if duplicate.
    """
    try:
        db.add(GovernmentDocument(
            country_id=country.id,
            doc_type="GOVERNMENT_BULLETIN",
            title=doc["title"],
            url=doc["url"],
            relevance_score=0.5,
        ))
        db.flush()
        return True
    except Exception:
        db.rollback()
        return False


def sweep_news(db: Session) -> dict:
    """
    Main sweep: fetch RSS headlines, detect events, insert NewsEvent rows,
    then recompute LiveSignal for each country.

    Returns summary dict: {new_events, expired_events, signals_updated}.
    """
    expired = _expire_old_events(db)
    new_events = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Fetch headlines from all RSS feeds
    all_headlines = []
    for feed_url in RSS_FEEDS:
        all_headlines.extend(_fetch_rss_headlines(feed_url))

    # Detect and insert events
    for headline in all_headlines:
        country_code = _detect_country(headline)
        if not country_code:
            continue
        event_type = _detect_event_type(headline)
        if not event_type:
            continue

        country = db.query(Country).filter(Country.code == country_code).first()
        if not country:
            continue

        # De-duplicate: skip if same country + event_type + headline exists in last 24h
        cutoff = now - timedelta(hours=24)
        existing = (
            db.query(NewsEvent)
            .filter(
                NewsEvent.country_id == country.id,
                NewsEvent.event_type == event_type,
                NewsEvent.headline == headline[:499],
                NewsEvent.detected_at >= cutoff,
            )
            .first()
        )
        if existing:
            continue

        expires_at = now + EVENT_LIFETIME[event_type]
        db.add(NewsEvent(
            country_id=country.id,
            event_type=event_type,
            headline=headline[:499],
            source_url=None,
            source_name="rss_sweep",
            magnitude=EVENT_MAGNITUDE[event_type],
            detected_at=now,
            expires_at=expires_at,
            is_active=True,
        ))
        new_events += 1

    if new_events:
        db.commit()

    # ── Government page scanning — find new PDF/Excel documents ──────────────
    new_docs = 0
    for country_code, sources in GOVERNMENT_SOURCES.items():
        country = db.query(Country).filter(Country.code == country_code).first()
        if not country:
            continue
        for source_type, url in sources.items():
            docs = scan_government_page(url, country_code, db)
            for doc in docs:
                inserted = _save_government_doc(db, doc, country)
                if inserted:
                    new_docs += 1
                    # Emit a NEW_GOVERNMENT_DOCUMENT event (neutral magnitude)
                    evt_type = "NEW_GOVERNMENT_DOCUMENT"
                    cutoff = now - timedelta(hours=24)
                    already = (
                        db.query(NewsEvent)
                        .filter(
                            NewsEvent.country_id == country.id,
                            NewsEvent.event_type == evt_type,
                            NewsEvent.source_url == doc["url"],
                            NewsEvent.detected_at >= cutoff,
                        )
                        .first()
                    )
                    if not already:
                        db.add(NewsEvent(
                            country_id=country.id,
                            event_type=evt_type,
                            headline=f"New document: {doc['title'][:200]}",
                            source_url=doc["url"],
                            source_name=f"gov_{source_type}",
                            magnitude=EVENT_MAGNITUDE[evt_type],
                            detected_at=now,
                            expires_at=now + EVENT_LIFETIME[evt_type],
                            is_active=True,
                        ))

    if new_docs:
        db.commit()

    # Recompute LiveSignal for all active countries
    signals_updated = _update_live_signals(db)

    return {
        "new_events": new_events,
        "new_docs": new_docs,
        "expired_events": expired,
        "signals_updated": signals_updated,
        "swept_at": str(now),
    }


def _update_live_signals(db: Session) -> int:
    """
    For each country, sum active event magnitudes → compute adjusted_index.
    Upsert LiveSignal record.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    period_date = now.date().replace(day=1)
    updated = 0

    countries = db.query(Country).filter(Country.is_active == True).all()
    for country in countries:
        # Get latest base index
        latest_idx = (
            db.query(CountryIndex)
            .filter(CountryIndex.country_id == country.id)
            .order_by(CountryIndex.period_date.desc())
            .first()
        )
        base_index = latest_idx.index_value if latest_idx and latest_idx.index_value else 50.0

        # Sum active event magnitudes
        active_events = (
            db.query(NewsEvent)
            .filter(
                NewsEvent.country_id == country.id,
                NewsEvent.is_active == True,
                NewsEvent.expires_at > now,
            )
            .all()
        )
        raw_adjustment = sum(e.magnitude for e in active_events)
        adjustment = max(-25.0, min(25.0, raw_adjustment))   # cap ±25
        adjusted_index = max(0.0, min(100.0, base_index + adjustment))

        event_ids = json.dumps([e.id for e in active_events])

        existing = (
            db.query(LiveSignal)
            .filter(LiveSignal.country_id == country.id, LiveSignal.period_date == period_date)
            .first()
        )
        if existing:
            existing.base_index = base_index
            existing.live_adjustment = adjustment
            existing.adjusted_index = adjusted_index
            existing.active_event_ids = event_ids
            existing.computed_at = now
        else:
            db.add(LiveSignal(
                country_id=country.id,
                period_date=period_date,
                base_index=base_index,
                live_adjustment=adjustment,
                adjusted_index=adjusted_index,
                active_event_ids=event_ids,
                computed_at=now,
            ))
        updated += 1

    db.commit()
    return updated


def run_news_sweep():
    """Entry point called by APScheduler. Uses its own DB session."""
    db = SessionLocal()
    try:
        result = sweep_news(db)
        logger.info(
            "News sweep complete: new_events=%d expired=%d signals=%d",
            result["new_events"], result["expired_events"], result["signals_updated"],
        )
    except Exception as exc:
        logger.error("News sweep failed: %s", exc, exc_info=True)
    finally:
        db.close()
