"""
World News Intelligence Engine.

Three-layer relevance scoring for global news events:
  Layer 1 (0.30): Keyword match — direct West Africa references
  Layer 2 (0.30): Supply chain proximity — trade partner mentions
  Layer 3 (0.40): Transmission channel — causal economic pathways

Thresholds:
  0.4000 — Cascade to country-specific NewsEvent (feeds LiveSignal)
  0.6000 — High relevance (daily briefing top events)
  0.8000 — Critical (watchlist)
"""
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import Country, NewsEvent
from src.database.world_news_models import (
    WorldNewsEvent, NewsImpactAssessment, DailyNewsBriefing,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# ECOWAS v3.0 country weights (must match composite_engine.py)
# ─────────────────────────────────────────────────────────────────────
WASI_COUNTRY_WEIGHTS = {
    "NG": 0.28, "CI": 0.22, "GH": 0.15, "SN": 0.10,
    "BF": 0.04, "ML": 0.04, "GN": 0.04, "BJ": 0.03, "TG": 0.03,
    "NE": 0.01, "MR": 0.01, "GW": 0.01, "SL": 0.01,
    "LR": 0.01, "GM": 0.01, "CV": 0.01,
}

# ─────────────────────────────────────────────────────────────────────
# Global RSS Feeds (free, public)
# ─────────────────────────────────────────────────────────────────────
GLOBAL_RSS_FEEDS = [
    # Wire services
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml", "region": "GLOBAL", "name": "BBC Business"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "region": "GLOBAL", "name": "BBC World"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "region": "AMERICAS", "name": "NYT Business"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "region": "AMERICAS", "name": "NYT World"},

    # Commodity / Energy
    {"url": "https://www.mining.com/feed/", "region": "GLOBAL", "name": "Mining.com"},
    {"url": "https://oilprice.com/rss/main", "region": "GLOBAL", "name": "OilPrice"},

    # Shipping / Logistics
    {"url": "https://www.seatrade-maritime.com/rss.xml", "region": "GLOBAL", "name": "Seatrade Maritime"},
    {"url": "https://gcaptain.com/feed/", "region": "GLOBAL", "name": "gCaptain"},
    {"url": "https://www.hellenicshippingnews.com/feed/", "region": "GLOBAL", "name": "Hellenic Shipping"},
    {"url": "https://theloadstar.com/feed/", "region": "GLOBAL", "name": "The Loadstar"},
    {"url": "https://splash247.com/feed/", "region": "GLOBAL", "name": "Splash247"},

    # Central Bank / Financial
    {"url": "https://www.imf.org/en/News/Rss?Language=ENG", "region": "GLOBAL", "name": "IMF News"},

    # Trade Policy
    {"url": "https://www.wto.org/english/news_e/news_e.rss", "region": "GLOBAL", "name": "WTO News"},

    # Climate / Disaster
    {"url": "https://reliefweb.int/updates/rss.xml", "region": "GLOBAL", "name": "ReliefWeb"},
    {"url": "https://www.fao.org/newsroom/en/rss/latest.xml", "region": "GLOBAL", "name": "FAO News"},

    # China (ECOWAS's largest bilateral partner)
    {"url": "https://www.scmp.com/rss/5/feed", "region": "ASIA", "name": "SCMP Business"},

    # Middle East (oil, Suez, Red Sea)
    {"url": "https://www.middleeasteye.net/rss", "region": "MIDDLE_EAST", "name": "Middle East Eye"},
]

# ─────────────────────────────────────────────────────────────────────
# 7 Global Event Types
# ─────────────────────────────────────────────────────────────────────
GLOBAL_EVENT_TYPES = {
    "GLOBAL_COMMODITY_SHOCK": {
        "keywords": [
            "oil price crash", "oil price surge", "opec cut", "opec+ cut",
            "commodity crash", "commodity boom", "cocoa price", "gold price",
            "iron ore price", "cotton price", "coffee price", "brent crude",
            "oil supply disruption", "grain shortage", "wheat crisis",
            "fertilizer shortage", "rare earth", "lithium shortage",
        ],
        "default_magnitude": -10.0,
        "lifetime_days": 14,
    },
    "GLOBAL_TRADE_POLICY": {
        "keywords": [
            "trade war", "tariff increase", "import ban", "export restriction",
            "trade sanctions", "wto ruling", "trade dispute", "customs duty",
            "protectionism", "trade agreement", "free trade", "trade deal",
            "anti-dumping", "countervailing duty", "trade barrier",
            "afcfta", "african continental free trade",
        ],
        "default_magnitude": -8.0,
        "lifetime_days": 21,
    },
    "GLOBAL_SHIPPING_DISRUPTION": {
        "keywords": [
            "suez canal", "panama canal", "shipping lane blocked",
            "container shortage", "freight rate spike", "port congestion",
            "houthi attack", "red sea", "piracy", "strait of hormuz",
            "strait of malacca", "shipping crisis", "vessel grounding",
            "maritime security", "container ship", "bulk carrier",
            "cape of good hope", "bab el-mandeb",
        ],
        "default_magnitude": -12.0,
        "lifetime_days": 10,
    },
    "GLOBAL_CLIMATE_EVENT": {
        "keywords": [
            "hurricane", "typhoon", "cyclone", "severe flooding",
            "drought emergency", "crop failure", "el nino", "la nina",
            "climate disaster", "wildfire", "monsoon failure",
            "locust outbreak", "desertification", "sahel drought",
        ],
        "default_magnitude": -8.0,
        "lifetime_days": 21,
    },
    "GLOBAL_FINANCIAL_CRISIS": {
        "keywords": [
            "financial crisis", "bank collapse", "credit crunch",
            "sovereign default", "debt crisis", "stock market crash",
            "recession", "gdp contraction", "interest rate hike",
            "fed rate", "dollar strengthening", "emerging market crisis",
            "capital flight", "currency crisis",
        ],
        "default_magnitude": -15.0,
        "lifetime_days": 30,
    },
    "GLOBAL_HEALTH_EMERGENCY": {
        "keywords": [
            "pandemic", "epidemic", "who emergency", "disease outbreak",
            "quarantine", "lockdown", "vaccination campaign",
            "health crisis", "ebola", "mpox", "cholera outbreak",
            "avian flu", "supply chain health",
        ],
        "default_magnitude": -10.0,
        "lifetime_days": 30,
    },
    "GLOBAL_SUPPLY_CHAIN": {
        "keywords": [
            "supply chain disruption", "chip shortage", "semiconductor",
            "factory shutdown", "port strike", "logistics crisis",
            "backlog", "inventory shortage", "just-in-time failure",
            "supply bottleneck", "warehouse shortage",
        ],
        "default_magnitude": -8.0,
        "lifetime_days": 14,
    },
}

# ─────────────────────────────────────────────────────────────────────
# Layer 1: West Africa keyword list
# ─────────────────────────────────────────────────────────────────────
WEST_AFRICA_KEYWORDS = [
    # Country names (all 16 ECOWAS)
    "nigeria", "ivory coast", "cote d'ivoire", "ghana", "senegal",
    "burkina faso", "mali", "guinea", "benin", "togo", "niger",
    "mauritania", "guinea-bissau", "sierra leone", "liberia",
    "gambia", "cabo verde", "cape verde",
    # Major cities / ports
    "lagos", "abidjan", "accra", "tema", "dakar", "conakry",
    "cotonou", "lome", "ouagadougou", "bamako", "freetown", "monrovia",
    # Institutions
    "ecowas", "bceao", "waemu", "uemoa", "cedeao",
    # Key commodity exports
    "cocoa", "crude oil", "gold", "cotton", "coffee", "cashew",
    "rubber", "iron ore", "bauxite", "phosphate", "uranium",
    "shea butter", "palm oil",
    # Shipping corridors
    "gulf of guinea", "west african", "sahel",
    "abidjan-lagos corridor", "dakar-bamako",
    # Currency terms
    "cfa franc", "naira", "cedi", "african trade",
]

# ─────────────────────────────────────────────────────────────────────
# Layer 2: Trade partner proximity weights
# ─────────────────────────────────────────────────────────────────────
TRADE_PARTNER_WEIGHTS = {
    "china": 0.95,
    "india": 0.80,
    "netherlands": 0.75,
    "france": 0.75,
    "united states": 0.70,
    "switzerland": 0.65,
    "germany": 0.60,
    "united kingdom": 0.60,
    "uae": 0.55,
    "spain": 0.50,
    "japan": 0.45,
    "brazil": 0.40,
    "south africa": 0.40,
    "turkey": 0.35,
    "saudi arabia": 0.30,
    "russia": 0.25,
    "ukraine": 0.25,
    # Regional terms
    "europe": 0.70,
    "european union": 0.70,
    "asia": 0.60,
    "middle east": 0.50,
    "suez": 0.85,
    "red sea": 0.85,
    "mediterranean": 0.50,
}

# ─────────────────────────────────────────────────────────────────────
# Layer 3: Transmission channels with per-country impact weights
# ─────────────────────────────────────────────────────────────────────
TRANSMISSION_CHANNELS = {
    "oil_price": {
        "keywords": [
            "oil price", "crude oil", "brent", "opec", "fuel cost",
            "petroleum", "gasoline", "diesel",
        ],
        "score": 0.90,
        "affected_countries": {
            "NG": 0.95, "GH": 0.70, "CI": 0.60, "SN": 0.60,
            "BF": 0.50, "ML": 0.50, "NE": 0.45, "BJ": 0.40,
            "TG": 0.40, "GN": 0.40, "MR": 0.35, "SL": 0.35,
            "LR": 0.35, "GM": 0.30, "GW": 0.30, "CV": 0.25,
        },
    },
    "cocoa_market": {
        "keywords": [
            "cocoa price", "cocoa market", "chocolate", "cocoa bean",
            "cocoa butter", "cocoa shortage",
        ],
        "score": 0.95,
        "affected_countries": {
            "CI": 0.95, "GH": 0.90, "NG": 0.40, "TG": 0.20,
        },
    },
    "gold_market": {
        "keywords": ["gold price", "gold market", "gold mining", "bullion"],
        "score": 0.85,
        "affected_countries": {
            "GH": 0.90, "ML": 0.80, "BF": 0.75, "GN": 0.60,
            "SN": 0.40, "NG": 0.30,
        },
    },
    "cotton_market": {
        "keywords": ["cotton price", "cotton market", "textile"],
        "score": 0.80,
        "affected_countries": {
            "BF": 0.90, "ML": 0.85, "BJ": 0.80, "CI": 0.50, "TG": 0.40,
        },
    },
    "shipping_freight": {
        "keywords": [
            "freight rate", "container rate", "shipping cost",
            "baltic dry index", "charter rate", "vessel rate",
        ],
        "score": 0.85,
        "affected_countries": {
            "NG": 0.90, "CI": 0.85, "GH": 0.80, "SN": 0.75,
            "BJ": 0.70, "TG": 0.70, "GN": 0.60, "MR": 0.50,
            "SL": 0.45, "LR": 0.45, "GM": 0.40, "GW": 0.35, "CV": 0.30,
            "BF": 0.40, "ML": 0.35, "NE": 0.30,
        },
    },
    "shipping_lane_disruption": {
        "keywords": [
            "suez canal", "panama canal", "red sea", "strait of hormuz",
            "bab el-mandeb", "cape of good hope", "piracy gulf",
        ],
        "score": 0.90,
        "affected_countries": {
            "NG": 0.90, "CI": 0.85, "GH": 0.80, "SN": 0.75,
            "BJ": 0.65, "TG": 0.65, "GN": 0.60, "MR": 0.50,
            "SL": 0.45, "LR": 0.45, "GM": 0.40, "GW": 0.35, "CV": 0.30,
            "BF": 0.50, "ML": 0.45, "NE": 0.40,
        },
    },
    "food_security": {
        "keywords": [
            "wheat price", "rice price", "food crisis", "grain",
            "fertilizer", "food security", "famine",
        ],
        "score": 0.85,
        "affected_countries": {
            "NG": 0.80, "NE": 0.85, "BF": 0.85, "ML": 0.80,
            "SN": 0.70, "GN": 0.65, "SL": 0.70, "LR": 0.65,
            "GM": 0.60, "MR": 0.70, "GW": 0.65,
            "CI": 0.50, "GH": 0.50, "BJ": 0.55, "TG": 0.55, "CV": 0.60,
        },
    },
    "global_recession": {
        "keywords": [
            "global recession", "world economy", "global gdp",
            "world trade slowdown", "demand contraction",
        ],
        "score": 0.75,
        "affected_countries": {
            "NG": 0.80, "CI": 0.75, "GH": 0.70, "SN": 0.65,
            "BF": 0.50, "ML": 0.50, "GN": 0.55, "BJ": 0.50,
            "TG": 0.50, "NE": 0.45, "MR": 0.45, "GW": 0.40,
            "SL": 0.45, "LR": 0.40, "GM": 0.35, "CV": 0.35,
        },
    },
    "dollar_fx": {
        "keywords": [
            "dollar strength", "fed rate", "interest rate hike",
            "dollar index", "emerging market", "capital outflow",
        ],
        "score": 0.70,
        "affected_countries": {
            "NG": 0.85, "GH": 0.80, "GN": 0.70, "SL": 0.65,
            "LR": 0.60, "GM": 0.55,
            # XOF-pegged countries — protected by EUR peg
            "CI": 0.30, "SN": 0.30, "BF": 0.30, "ML": 0.30,
            "BJ": 0.30, "TG": 0.30, "NE": 0.25, "GW": 0.25,
            "MR": 0.40, "CV": 0.25,
        },
    },
    "bauxite_iron_mining": {
        "keywords": ["bauxite", "iron ore", "mining", "aluminium", "simandou"],
        "score": 0.80,
        "affected_countries": {
            "GN": 0.95, "SL": 0.60, "LR": 0.50, "NG": 0.30,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────
# Scoring weights & thresholds
# ─────────────────────────────────────────────────────────────────────
LAYER_WEIGHTS = {"keyword": 0.30, "supply_chain": 0.30, "transmission": 0.40}

RELEVANCE_THRESHOLD_CASCADE = 0.4000
RELEVANCE_THRESHOLD_HIGH = 0.6000
RELEVANCE_THRESHOLD_CRITICAL = 0.8000

# ─────────────────────────────────────────────────────────────────────
# Sentiment indicators for magnitude sign refinement
# ─────────────────────────────────────────────────────────────────────
POSITIVE_INDICATORS = [
    "agreement", "deal", "boost", "growth", "recovery", "rise",
    "surplus", "investment", "expansion", "improvement", "trade deal",
    "free trade", "afcfta", "record high", "rally",
]
NEGATIVE_INDICATORS = [
    "crisis", "crash", "collapse", "shortage", "disruption", "war",
    "sanctions", "ban", "restriction", "decline", "drought",
    "pandemic", "strike", "block", "attack", "shutdown", "slump",
]


# ═════════════════════════════════════════════════════════════════════
# LAYER 1: Keyword Match Score
# ═════════════════════════════════════════════════════════════════════
def score_layer1_keyword(text: str) -> tuple:
    """
    Layer 1: Direct keyword relevance to West African trade/shipping.

    Returns (score, matched_keywords).
    Score: 0 matches→0.0, 1→0.25, 2→0.50, 3→0.75, 4+→1.0.
    """
    text_lower = text.lower()
    matched = [kw for kw in WEST_AFRICA_KEYWORDS if kw in text_lower]
    count = len(matched)
    if count == 0:
        score = 0.0
    elif count == 1:
        score = 0.25
    elif count == 2:
        score = 0.50
    elif count == 3:
        score = 0.75
    else:
        score = 1.0
    return score, matched


# ═════════════════════════════════════════════════════════════════════
# LAYER 2: Supply Chain Proximity Score
# ═════════════════════════════════════════════════════════════════════
def score_layer2_supply_chain(text: str) -> float:
    """
    Layer 2: Supply chain proximity.
    Returns max weight of any matched trade partner/region. 0.0 if none.
    """
    text_lower = text.lower()
    max_weight = 0.0
    for partner, weight in TRADE_PARTNER_WEIGHTS.items():
        if partner in text_lower:
            max_weight = max(max_weight, weight)
    return max_weight


# ═════════════════════════════════════════════════════════════════════
# LAYER 3: Transmission Channel Score
# ═════════════════════════════════════════════════════════════════════
def score_layer3_transmission(text: str) -> tuple:
    """
    Layer 3: Economic transmission channels.

    Returns (channel_score, channel_name, country_impacts).
    - channel_score: highest matching channel score (0.0-1.0)
    - channel_name: name of the primary channel ("" if none)
    - country_impacts: {country_code: impact_weight} for affected countries
    """
    text_lower = text.lower()
    best_score = 0.0
    best_channel = ""
    best_impacts = {}

    for channel_name, config in TRANSMISSION_CHANNELS.items():
        for kw in config["keywords"]:
            if kw in text_lower:
                if config["score"] > best_score:
                    best_score = config["score"]
                    best_channel = channel_name
                    best_impacts = config["affected_countries"]
                break  # found match for this channel
    return best_score, best_channel, best_impacts


# ═════════════════════════════════════════════════════════════════════
# Composite Relevance Score
# ═════════════════════════════════════════════════════════════════════
def compute_relevance_score(layer1: float, layer2: float, layer3: float) -> float:
    """
    Weighted sum of 3 layers, clamped to [0.0, 1.0], 4 decimal precision.
    """
    raw = (
        LAYER_WEIGHTS["keyword"] * layer1
        + LAYER_WEIGHTS["supply_chain"] * layer2
        + LAYER_WEIGHTS["transmission"] * layer3
    )
    return round(max(0.0, min(1.0, raw)), 4)


# ═════════════════════════════════════════════════════════════════════
# Magnitude Sign Determination
# ═════════════════════════════════════════════════════════════════════
def determine_magnitude_sign(headline: str, default_magnitude: float) -> float:
    """
    Refine magnitude sign based on headline sentiment keywords.
    Positive indicators flip negative defaults to positive (for exporters).
    """
    text_lower = headline.lower()
    pos_count = sum(1 for kw in POSITIVE_INDICATORS if kw in text_lower)
    neg_count = sum(1 for kw in NEGATIVE_INDICATORS if kw in text_lower)

    if pos_count > neg_count:
        return abs(default_magnitude)
    elif neg_count > pos_count:
        return -abs(default_magnitude)
    return default_magnitude


# ═════════════════════════════════════════════════════════════════════
# Country Magnitude Computation
# ═════════════════════════════════════════════════════════════════════
def compute_country_magnitude(
    global_magnitude: float,
    relevance_score: float,
    country_impact_weight: float,
    country_wasi_weight: float,
) -> float:
    """
    Country-specific magnitude from global event.

    Formula: global_mag * relevance * country_weight * tier_multiplier
    Tier: primary (>=0.10) → 1.0, secondary (>=0.03) → 0.8, tertiary → 0.6
    Clamped to [-25.0, +25.0], 4 decimal precision.
    """
    if country_wasi_weight >= 0.10:
        tier_multiplier = 1.0
    elif country_wasi_weight >= 0.03:
        tier_multiplier = 0.8
    else:
        tier_multiplier = 0.6

    raw = global_magnitude * relevance_score * country_impact_weight * tier_multiplier
    return round(max(-25.0, min(25.0, raw)), 4)


# ═════════════════════════════════════════════════════════════════════
# Event Type Detection
# ═════════════════════════════════════════════════════════════════════
def detect_global_event_type(text: str) -> Optional[str]:
    """
    Detect the global event type from headline + summary text.
    Returns the first matching type or None.
    """
    text_lower = text.lower()
    for event_type, config in GLOBAL_EVENT_TYPES.items():
        for kw in config["keywords"]:
            if kw in text_lower:
                return event_type
    return None


# ═════════════════════════════════════════════════════════════════════
# Full Scoring Pipeline
# ═════════════════════════════════════════════════════════════════════
def score_headline(headline: str, summary: str = "") -> dict:
    """
    Run full 3-layer scoring on a headline + summary.

    Returns dict with all scoring components:
      event_type, global_magnitude,
      layer1, layer2, layer3, relevance_score,
      channel_name, country_impacts, keywords_matched
    """
    text = f"{headline} {summary}"
    event_type = detect_global_event_type(text)
    if not event_type:
        return {"event_type": None}

    config = GLOBAL_EVENT_TYPES[event_type]
    magnitude = determine_magnitude_sign(headline, config["default_magnitude"])

    l1_score, keywords = score_layer1_keyword(text)
    l2_score = score_layer2_supply_chain(text)
    l3_score, channel_name, country_impacts = score_layer3_transmission(text)
    relevance = compute_relevance_score(l1_score, l2_score, l3_score)

    return {
        "event_type": event_type,
        "global_magnitude": magnitude,
        "lifetime_days": config["lifetime_days"],
        "layer1": l1_score,
        "layer2": l2_score,
        "layer3": l3_score,
        "relevance_score": relevance,
        "channel_name": channel_name,
        "country_impacts": country_impacts,
        "keywords_matched": keywords,
    }


# ═════════════════════════════════════════════════════════════════════
# Impact Assessment Generation
# ═════════════════════════════════════════════════════════════════════
def assess_country_impacts(
    world_event: WorldNewsEvent,
    channel_name: str,
    channel_impacts: dict,
) -> list:
    """
    Generate per-country impact assessments.
    Only includes countries where |country_magnitude| >= 1.0.

    Returns list of dicts for NewsImpactAssessment creation.
    """
    assessments = []
    for cc, impact_weight in channel_impacts.items():
        wasi_weight = WASI_COUNTRY_WEIGHTS.get(cc, 0.01)
        magnitude = compute_country_magnitude(
            world_event.global_magnitude,
            world_event.relevance_score,
            impact_weight,
            wasi_weight,
        )
        if abs(magnitude) < 1.0:
            continue

        direct = round(impact_weight * world_event.relevance_score, 4)
        indirect = round(world_event.relevance_layer2_supply_chain * 0.5, 4)
        systemic = round(world_event.relevance_layer3_transmission * 0.3, 4)

        assessments.append({
            "country_code": cc,
            "direct_impact": direct,
            "indirect_impact": indirect,
            "systemic_impact": systemic,
            "country_magnitude": magnitude,
            "transmission_channel": channel_name,
            "explanation": (
                f"{channel_name}: global_mag={world_event.global_magnitude}, "
                f"relevance={world_event.relevance_score}, "
                f"country_weight={impact_weight}, wasi_weight={wasi_weight}"
            ),
        })
    return assessments


# ═════════════════════════════════════════════════════════════════════
# Cascade to Existing NewsEvent Pipeline
# ═════════════════════════════════════════════════════════════════════
def cascade_to_news_events(
    db: Session,
    world_event: WorldNewsEvent,
    assessments_data: list,
) -> int:
    """
    For each assessment, create a country-specific NewsEvent that feeds
    into the existing LiveSignal recomputation.

    Returns count of NewsEvent rows created.
    """
    created = 0
    config = GLOBAL_EVENT_TYPES.get(world_event.event_type, {})
    lifetime_days = config.get("lifetime_days", 14)
    now = datetime.now(timezone.utc)

    for assessment in assessments_data:
        cc = assessment["country_code"]

        # Look up country
        country = db.query(Country).filter(Country.code == cc).first()
        if not country:
            continue

        # De-duplicate: skip if same world event already cascaded for this country
        existing = (
            db.query(NewsImpactAssessment)
            .filter(
                NewsImpactAssessment.world_news_event_id == world_event.id,
                NewsImpactAssessment.country_code == cc,
                NewsImpactAssessment.news_event_created.is_(True),
            )
            .first()
        )
        if existing:
            continue

        # Create country-specific NewsEvent
        news_event = NewsEvent(
            country_id=country.id,
            event_type=world_event.event_type,
            headline=f"[GLOBAL] {world_event.headline[:480]}",
            source_url=world_event.source_url,
            source_name="world_news_cascade",
            magnitude=assessment["country_magnitude"],
            detected_at=now,
            expires_at=now + timedelta(days=lifetime_days),
            is_active=True,
        )
        db.add(news_event)
        db.flush()  # get news_event.id

        # Create impact assessment
        impact = NewsImpactAssessment(
            world_news_event_id=world_event.id,
            country_code=cc,
            direct_impact=assessment["direct_impact"],
            indirect_impact=assessment["indirect_impact"],
            systemic_impact=assessment["systemic_impact"],
            country_magnitude=assessment["country_magnitude"],
            transmission_channel=assessment["transmission_channel"],
            explanation=assessment["explanation"],
            news_event_created=True,
            news_event_id=news_event.id,
        )
        db.add(impact)
        created += 1

    # Mark world event as cascaded
    if created > 0:
        world_event.cascaded = True

    return created


# ═════════════════════════════════════════════════════════════════════
# Non-cascade Impact Assessments (below threshold)
# ═════════════════════════════════════════════════════════════════════
def store_assessments_only(
    db: Session,
    world_event: WorldNewsEvent,
    assessments_data: list,
) -> int:
    """
    Store impact assessments without creating NewsEvent rows.
    Used when relevance < CASCADE threshold but we still want to track impact.
    """
    created = 0
    for assessment in assessments_data:
        existing = (
            db.query(NewsImpactAssessment)
            .filter(
                NewsImpactAssessment.world_news_event_id == world_event.id,
                NewsImpactAssessment.country_code == assessment["country_code"],
            )
            .first()
        )
        if existing:
            continue

        impact = NewsImpactAssessment(
            world_news_event_id=world_event.id,
            country_code=assessment["country_code"],
            direct_impact=assessment["direct_impact"],
            indirect_impact=assessment["indirect_impact"],
            systemic_impact=assessment["systemic_impact"],
            country_magnitude=assessment["country_magnitude"],
            transmission_channel=assessment["transmission_channel"],
            explanation=assessment["explanation"],
            news_event_created=False,
        )
        db.add(impact)
        created += 1
    return created


# ═════════════════════════════════════════════════════════════════════
# Daily Briefing Generation
# ═════════════════════════════════════════════════════════════════════
def generate_daily_briefing(db: Session, briefing_date: date) -> dict:
    """
    Generate a daily intelligence briefing from active WorldNewsEvents.
    Returns dict suitable for DailyNewsBriefing creation.
    """
    now = datetime.now(timezone.utc)
    start_of_day = datetime.combine(briefing_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = start_of_day + timedelta(days=1)

    # Get all active world events
    events = (
        db.query(WorldNewsEvent)
        .filter(
            WorldNewsEvent.is_active.is_(True),
            WorldNewsEvent.detected_at >= start_of_day,
            WorldNewsEvent.detected_at < end_of_day,
        )
        .order_by(WorldNewsEvent.relevance_score.desc())
        .all()
    )

    if not events:
        # Fall back to all active events (not just today's)
        events = (
            db.query(WorldNewsEvent)
            .filter(
                WorldNewsEvent.is_active.is_(True),
                WorldNewsEvent.expires_at > now,
            )
            .order_by(WorldNewsEvent.relevance_score.desc())
            .all()
        )

    high_rel = [e for e in events if e.relevance_score >= RELEVANCE_THRESHOLD_HIGH]

    # Top events (up to 10)
    top_events = []
    for e in events[:10]:
        assessment_count = (
            db.query(NewsImpactAssessment)
            .filter(NewsImpactAssessment.world_news_event_id == e.id)
            .count()
        )
        most_affected = (
            db.query(NewsImpactAssessment)
            .filter(NewsImpactAssessment.world_news_event_id == e.id)
            .order_by(NewsImpactAssessment.country_magnitude.asc())
            .first()
        )
        top_events.append({
            "event_id": e.id,
            "event_type": e.event_type,
            "headline": e.headline,
            "relevance_score": e.relevance_score,
            "global_magnitude": e.global_magnitude,
            "countries_affected": assessment_count,
            "most_affected": most_affected.country_code if most_affected else None,
        })

    # Country exposure summary
    country_exposure = {}
    assessments = (
        db.query(NewsImpactAssessment)
        .join(WorldNewsEvent, WorldNewsEvent.id == NewsImpactAssessment.world_news_event_id)
        .filter(
            WorldNewsEvent.is_active.is_(True),
            WorldNewsEvent.expires_at > now,
        )
        .all()
    )
    for a in assessments:
        if a.country_code not in country_exposure:
            country_exposure[a.country_code] = {
                "net_impact": 0.0,
                "event_count": 0,
            }
        country_exposure[a.country_code]["net_impact"] += a.country_magnitude
        country_exposure[a.country_code]["event_count"] += 1

    # Trend: compare today vs yesterday
    yesterday = briefing_date - timedelta(days=1)
    prev_briefing = (
        db.query(DailyNewsBriefing)
        .filter(DailyNewsBriefing.briefing_date == yesterday)
        .first()
    )
    trends = {}
    if prev_briefing:
        prev_exposure = json.loads(prev_briefing.country_exposure_json)
        for cc, data in country_exposure.items():
            prev_impact = prev_exposure.get(cc, {}).get("net_impact", 0.0)
            diff = data["net_impact"] - prev_impact
            if diff < -2.0:
                trends[cc] = "worsening"
            elif diff > 2.0:
                trends[cc] = "improving"
            else:
                trends[cc] = "stable"
    else:
        for cc in country_exposure:
            trends[cc] = "stable"

    # Watchlist: critical events
    watchlist = []
    for e in events:
        if e.relevance_score >= RELEVANCE_THRESHOLD_CRITICAL:
            watchlist.append(f"[CRITICAL] {e.event_type}: {e.headline[:200]}")

    return {
        "briefing_date": briefing_date,
        "total_global_events": len(events),
        "high_relevance_events": len(high_rel),
        "countries_affected": len(country_exposure),
        "top_events_json": json.dumps(top_events),
        "country_exposure_json": json.dumps(country_exposure),
        "trend_indicators_json": json.dumps(trends),
        "watchlist_json": json.dumps(watchlist),
        "generated_at": now,
    }
