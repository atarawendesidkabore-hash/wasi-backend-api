"""
World News Sweep — Daily global news intelligence update.

Runs daily at 05:00 UTC (after forecast update at 04:00).
Also supports manual triggering via POST /api/v3/news/refresh.

Steps:
  1. Expire old WorldNewsEvent rows (expires_at < now → is_active=False)
  2. Fetch all GLOBAL_RSS_FEEDS (cap 50 entries per feed)
  3. For each headline+summary: detect global event type, compute 3-layer relevance
  4. Dedup within 48h window (headline + source_name)
  5. Insert WorldNewsEvent if new
  6. For events with relevance >= 0.4000: assess country impacts, cascade to NewsEvent
  7. Generate/update daily briefing
  8. Return summary
"""
import json
import logging
import threading
from datetime import datetime, timedelta, timezone, date

from sqlalchemy.orm import Session

from src.database.connection import SessionLocal
from src.database.world_news_models import WorldNewsEvent, DailyNewsBriefing
from src.engines.world_news_engine import (
    GLOBAL_RSS_FEEDS,
    GLOBAL_EVENT_TYPES,
    RELEVANCE_THRESHOLD_CASCADE,
    RELEVANCE_THRESHOLD_HIGH,
    score_headline,
    assess_country_impacts,
    cascade_to_news_events,
    store_assessments_only,
    generate_daily_briefing,
)

logger = logging.getLogger(__name__)
_world_news_lock = threading.Lock()


def _fetch_rss_entries(feed_url: str) -> list:
    """
    Fetch RSS feed and return list of dicts with title, summary, link.
    Cap at 50 entries per feed. Never raises.
    """
    try:
        import feedparser
        feed = feedparser.parse(feed_url)
        entries = []
        for entry in feed.entries[:50]:
            entries.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
                "link": entry.get("link", ""),
            })
        return entries
    except ImportError:
        logger.warning("feedparser not installed — world news sweep skipped")
        return []
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
        return []


def _expire_old_events(db: Session) -> int:
    """Mark expired WorldNewsEvent rows as inactive."""
    now = datetime.now(timezone.utc)
    events = (
        db.query(WorldNewsEvent)
        .filter(WorldNewsEvent.is_active.is_(True), WorldNewsEvent.expires_at <= now)
        .all()
    )
    for e in events:
        e.is_active = False
    if events:
        db.commit()
    return len(events)


def _is_duplicate(db: Session, headline: str, source_name: str) -> bool:
    """Check if same headline + source exists within last 48h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    existing = (
        db.query(WorldNewsEvent)
        .filter(
            WorldNewsEvent.headline == headline[:500],
            WorldNewsEvent.source_name == source_name,
            WorldNewsEvent.detected_at >= cutoff,
        )
        .first()
    )
    return existing is not None


def sweep_world_news(db: Session) -> dict:
    """
    Main worldwide news sweep. Returns summary dict.
    """
    now = datetime.now(timezone.utc)
    logger.info("World news sweep starting at %s", now.isoformat())

    # Step 1: Expire old events
    expired = _expire_old_events(db)
    logger.info("Expired %d old world news events", expired)

    # Step 2-6: Fetch feeds and process
    events_detected = 0
    high_relevance = 0
    cascaded_total = 0
    assessments_total = 0

    for feed_config in GLOBAL_RSS_FEEDS:
        entries = _fetch_rss_entries(feed_config["url"])
        logger.debug(
            "Fetched %d entries from %s", len(entries), feed_config["name"]
        )

        for entry in entries:
            headline = entry["title"].strip()
            summary = entry["summary"].strip()
            link = entry["link"].strip()

            if not headline:
                continue

            # Score the headline
            scoring = score_headline(headline, summary)
            if not scoring.get("event_type"):
                continue

            # Truncate headline
            headline = headline[:500]

            # De-duplicate
            if _is_duplicate(db, headline, feed_config["name"]):
                continue

            # Create WorldNewsEvent
            lifetime_days = scoring["lifetime_days"]
            world_event = WorldNewsEvent(
                event_type=scoring["event_type"],
                headline=headline,
                summary=summary[:2000] if summary else "",
                source_url=link[:500] if link else None,
                source_name=feed_config["name"],
                source_region=feed_config["region"],
                relevance_score=scoring["relevance_score"],
                relevance_layer1_keyword=scoring["layer1"],
                relevance_layer2_supply_chain=scoring["layer2"],
                relevance_layer3_transmission=scoring["layer3"],
                keywords_matched=json.dumps(scoring["keywords_matched"]),
                global_magnitude=scoring["global_magnitude"],
                detected_at=now,
                expires_at=now + timedelta(days=lifetime_days),
                is_active=True,
                cascaded=False,
            )
            db.add(world_event)
            db.flush()  # get world_event.id

            events_detected += 1
            if scoring["relevance_score"] >= RELEVANCE_THRESHOLD_HIGH:
                high_relevance += 1

            # Assess country impacts
            channel_impacts = scoring.get("country_impacts", {})
            channel_name = scoring.get("channel_name", "")

            if channel_impacts:
                assessments_data = assess_country_impacts(
                    world_event, channel_name, channel_impacts
                )

                if scoring["relevance_score"] >= RELEVANCE_THRESHOLD_CASCADE:
                    # Cascade to country-specific NewsEvent
                    count = cascade_to_news_events(db, world_event, assessments_data)
                    cascaded_total += count
                    assessments_total += count
                else:
                    # Store assessments only (no NewsEvent cascade)
                    count = store_assessments_only(db, world_event, assessments_data)
                    assessments_total += count

    db.commit()
    logger.info(
        "World news sweep: detected=%d high_rel=%d cascaded=%d assessments=%d",
        events_detected, high_relevance, cascaded_total, assessments_total,
    )

    # Step 7: Generate daily briefing
    briefing_generated = False
    today = date.today()
    existing_briefing = (
        db.query(DailyNewsBriefing)
        .filter(DailyNewsBriefing.briefing_date == today)
        .first()
    )
    if existing_briefing:
        # Update existing briefing
        data = generate_daily_briefing(db, today)
        for key, value in data.items():
            if key != "briefing_date":
                setattr(existing_briefing, key, value)
        db.commit()
        briefing_generated = True
    else:
        # Create new briefing
        data = generate_daily_briefing(db, today)
        briefing = DailyNewsBriefing(**data)
        db.add(briefing)
        db.commit()
        briefing_generated = True

    return {
        "status": "completed",
        "global_events_detected": events_detected,
        "high_relevance_events": high_relevance,
        "country_events_cascaded": cascaded_total,
        "assessments_created": assessments_total,
        "briefing_generated": briefing_generated,
        "swept_at": now.isoformat(),
    }


def run_world_news_sweep():
    """APScheduler entry point. Creates its own DB session."""
    if not _world_news_lock.acquire(blocking=False):
        logger.info("World news sweep: previous run still in progress, skipping")
        return
    db = SessionLocal()
    try:
        result = sweep_world_news(db)
        logger.info(
            "World news sweep complete: detected=%d cascaded=%d",
            result["global_events_detected"],
            result["country_events_cascaded"],
        )
    except Exception as exc:
        logger.error("World news sweep failed: %s", exc, exc_info=True)
    finally:
        db.close()
        _world_news_lock.release()
