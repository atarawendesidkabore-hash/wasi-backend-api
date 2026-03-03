"""
Legislative Impact Engine — scores laws by trade/economic impact and emits
NewsEvent records for high-impact legislation.

Category → base magnitude mapping:
  TRADE ±10, TARIFF ±12, INVESTMENT +8, FISCAL ±6, REGULATORY -4,
  CUSTOMS ±8, LABOR ±3, INFRASTRUCTURE +7, ENVIRONMENT ±4, OTHER ±2

Keyword analysis refines direction (positive/negative) and scales magnitude.
Acts with |magnitude| > 5 automatically create NewsEvent records that feed
into the existing LiveSignal pipeline (±25 cap preserved).
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from src.database.models import Country, NewsEvent
from src.database.legislative_models import LegislativeAct, ParliamentarySession

logger = logging.getLogger(__name__)

# ── Category base magnitudes ──────────────────────────────────────────────────
CATEGORY_BASE_MAGNITUDE: Dict[str, float] = {
    "TRADE": 10.0,
    "TARIFF": 12.0,
    "INVESTMENT": 8.0,
    "FISCAL": 6.0,
    "REGULATORY": 4.0,
    "CUSTOMS": 8.0,
    "LABOR": 3.0,
    "INFRASTRUCTURE": 7.0,
    "ENVIRONMENT": 4.0,
    "OTHER": 2.0,
}

CATEGORY_LIFETIME: Dict[str, timedelta] = {
    "TRADE": timedelta(days=21),
    "TARIFF": timedelta(days=30),
    "INVESTMENT": timedelta(days=30),
    "FISCAL": timedelta(days=14),
    "REGULATORY": timedelta(days=14),
    "CUSTOMS": timedelta(days=21),
    "LABOR": timedelta(days=7),
    "INFRASTRUCTURE": timedelta(days=30),
    "ENVIRONMENT": timedelta(days=14),
    "OTHER": timedelta(days=7),
}

# ── Bilingual keyword lists for direction detection ───────────────────────────
POSITIVE_KEYWORDS = [
    # English
    "trade agreement", "free trade", "investment code", "tax incentive",
    "tax relief", "port modernization", "infrastructure upgrade",
    "export promotion", "duty reduction", "tariff reduction", "customs reform",
    "trade facilitation", "special economic zone", "incentive", "stimulus",
    "liberalization", "deregulation", "startup act",
    # French
    "accord commercial", "libre-échange", "code des investissements",
    "incitation fiscale", "exonération", "modernisation portuaire",
    "zone économique spéciale", "promotion des exportations",
    "réduction tarifaire", "facilitation des échanges", "stimulus",
    "zone franche", "guichet unique",
]

NEGATIVE_KEYWORDS = [
    # English
    "import ban", "export restriction", "new tariff", "tariff increase",
    "tax increase", "price control", "nationalization", "embargo",
    "sanction", "capital control", "foreign exchange restriction",
    "regulatory burden", "compliance requirement", "mining royalty increase",
    # French
    "interdiction d'importation", "restriction d'exportation",
    "hausse tarifaire", "hausse taxe", "augmentation des impôts",
    "contrôle des prix", "nationalisation", "embargo", "sanction",
    "contrôle des capitaux", "charge réglementaire",
    "augmentation des royalties",
]

MAGNITUDE_CAP = 25.0


class LegislativeImpactEngine:
    """Scores legislative acts and emits NewsEvent records for high-impact laws."""

    def __init__(self, db: Session):
        self.db = db

    def score_act(self, title: str, description: str = "", category: str = "OTHER") -> dict:
        """
        Analyze a legislative act and return impact scoring.

        Returns: {
            impact_type: POSITIVE|NEGATIVE|NEUTRAL,
            estimated_magnitude: float (-25 to +25),
            confidence: float (0-1),
            keywords_matched: list[str],
        }
        """
        text = f"{title} {description}".lower()

        pos_matches = [kw for kw in POSITIVE_KEYWORDS if kw in text]
        neg_matches = [kw for kw in NEGATIVE_KEYWORDS if kw in text]

        base = CATEGORY_BASE_MAGNITUDE.get(category, 2.0)

        # Determine direction
        pos_score = len(pos_matches)
        neg_score = len(neg_matches)

        if pos_score > neg_score:
            impact_type = "POSITIVE"
            direction = 1.0
        elif neg_score > pos_score:
            impact_type = "NEGATIVE"
            direction = -1.0
        else:
            impact_type = "NEUTRAL"
            direction = 0.0

        # Scale magnitude by keyword density
        keyword_count = pos_score + neg_score
        if keyword_count == 0:
            scale = 0.3  # minimal impact when no keywords match
        elif keyword_count <= 2:
            scale = 0.6
        else:
            scale = min(1.0, 0.5 + keyword_count * 0.15)

        magnitude = round(min(MAGNITUDE_CAP, base * scale * direction), 2)

        # Confidence based on keyword clarity
        if keyword_count >= 3:
            confidence = 0.85
        elif keyword_count >= 1:
            confidence = 0.70
        else:
            confidence = 0.50

        return {
            "impact_type": impact_type,
            "estimated_magnitude": magnitude,
            "confidence": confidence,
            "keywords_matched": pos_matches + neg_matches,
        }

    def score_and_update_act(self, act: LegislativeAct) -> dict:
        """Score a LegislativeAct record in-place and commit."""
        result = self.score_act(act.title, act.description or "", act.category)
        act.impact_type = result["impact_type"]
        act.estimated_magnitude = result["estimated_magnitude"]
        act.confidence = result["confidence"]

        lifetime = CATEGORY_LIFETIME.get(act.category, timedelta(days=14))
        act.expires_at = datetime.now(timezone.utc) + lifetime

        self.db.commit()
        return result

    def emit_news_event(self, act: LegislativeAct) -> Optional[NewsEvent]:
        """
        Create a NewsEvent if |magnitude| > 5.
        This integrates with the existing LiveSignal pipeline.
        """
        if abs(act.estimated_magnitude) <= 5.0:
            return None

        # Check for existing event for this act
        existing = (
            self.db.query(NewsEvent)
            .filter(
                NewsEvent.country_id == act.country_id,
                NewsEvent.headline == f"[LEGISLATIVE] {act.title}",
            )
            .first()
        )
        if existing:
            return existing

        lifetime = CATEGORY_LIFETIME.get(act.category, timedelta(days=14))
        now = datetime.now(timezone.utc)

        event = NewsEvent(
            country_id=act.country_id,
            event_type="LEGISLATIVE_CHANGE",
            headline=f"[LEGISLATIVE] {act.title}",
            magnitude=act.estimated_magnitude,
            detected_at=now,
            expires_at=now + lifetime,
            is_active=True,
            source_url=act.source_url or "",
            source_name=act.source_name or "legislative_engine",
        )
        self.db.add(event)
        self.db.commit()

        logger.info(
            "NewsEvent emitted: %s (magnitude=%.1f, country_id=%d)",
            act.title[:60], act.estimated_magnitude, act.country_id,
        )
        return event

    def get_legislative_impact(self, country_code: str) -> dict:
        """Get active legislative impact summary for a country."""
        country = self.db.query(Country).filter(Country.code == country_code).first()
        if not country:
            return {"error": f"Country {country_code} not found"}

        now = datetime.now(timezone.utc)
        active_acts = (
            self.db.query(LegislativeAct)
            .filter(
                LegislativeAct.country_id == country.id,
                LegislativeAct.is_active == True,
            )
            .order_by(LegislativeAct.act_date.desc())
            .all()
        )

        positive_acts = [a for a in active_acts if a.impact_type == "POSITIVE"]
        negative_acts = [a for a in active_acts if a.impact_type == "NEGATIVE"]
        neutral_acts = [a for a in active_acts if a.impact_type == "NEUTRAL"]

        net_magnitude = sum(a.estimated_magnitude for a in active_acts)

        # Category breakdown
        categories: Dict[str, int] = {}
        for act in active_acts:
            categories[act.category] = categories.get(act.category, 0) + 1

        return {
            "country_code": country_code,
            "country_name": country.name,
            "total_active_acts": len(active_acts),
            "positive_count": len(positive_acts),
            "negative_count": len(negative_acts),
            "neutral_count": len(neutral_acts),
            "net_magnitude": round(net_magnitude, 2),
            "categories": categories,
            "recent_acts": [
                {
                    "title": a.title,
                    "category": a.category,
                    "impact_type": a.impact_type,
                    "magnitude": a.estimated_magnitude,
                    "act_date": a.act_date.isoformat() if a.act_date else None,
                    "confidence": a.confidence,
                }
                for a in active_acts[:10]
            ],
            "assessment": (
                "NET_POSITIVE" if net_magnitude > 3
                else "NET_NEGATIVE" if net_magnitude < -3
                else "NEUTRAL"
            ),
            "timestamp": now.isoformat(),
        }

    def get_ecowas_summary(self) -> dict:
        """Get legislative impact dashboard for all 16 ECOWAS countries."""
        from src.engines.composite_engine import CompositeEngine
        COUNTRY_WEIGHTS = CompositeEngine.COUNTRY_WEIGHTS

        countries = (
            self.db.query(Country)
            .filter(Country.is_active == True)
            .all()
        )

        country_summaries = []
        total_acts = 0
        total_positive = 0
        total_negative = 0

        for country in countries:
            acts = (
                self.db.query(LegislativeAct)
                .filter(
                    LegislativeAct.country_id == country.id,
                    LegislativeAct.is_active == True,
                )
                .all()
            )

            pos = sum(1 for a in acts if a.impact_type == "POSITIVE")
            neg = sum(1 for a in acts if a.impact_type == "NEGATIVE")
            net = sum(a.estimated_magnitude for a in acts)
            weight = COUNTRY_WEIGHTS.get(country.code, 0.0)

            total_acts += len(acts)
            total_positive += pos
            total_negative += neg

            country_summaries.append({
                "country_code": country.code,
                "country_name": country.name,
                "wasi_weight": weight,
                "total_acts": len(acts),
                "positive": pos,
                "negative": neg,
                "net_magnitude": round(net, 2),
                "weighted_impact": round(net * weight, 4),
            })

        # Sort by weighted impact
        country_summaries.sort(key=lambda x: abs(x["weighted_impact"]), reverse=True)

        weighted_total = sum(c["weighted_impact"] for c in country_summaries)

        return {
            "total_acts_tracked": total_acts,
            "total_positive": total_positive,
            "total_negative": total_negative,
            "ecowas_weighted_impact": round(weighted_total, 4),
            "ecowas_assessment": (
                "NET_POSITIVE" if weighted_total > 1
                else "NET_NEGATIVE" if weighted_total < -1
                else "NEUTRAL"
            ),
            "countries": country_summaries,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
