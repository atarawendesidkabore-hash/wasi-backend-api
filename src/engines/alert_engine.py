"""
Alert Engine — Rule evaluation + webhook delivery.

Evaluation loop:
  1. For each active AlertRule, fetch latest relevant data.
  2. Compare against rule condition/threshold.
  3. If triggered and cooldown has elapsed, queue an AlertDelivery.

Delivery:
  POST JSON to webhook_url with HMAC-SHA256 signature in X-WASI-Signature header.
  Retry up to 3 times with exponential backoff (30s, 120s, 480s).
"""
import hashlib
import hmac as hmac_mod
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.alert_models import AlertDelivery, AlertRule
from src.database.models import (
    CommodityPrice, Country, CountryIndex, DivergenceSnapshot, NewsEvent,
)

logger = logging.getLogger(__name__)

RETRY_DELAYS = [30, 120, 480]  # seconds between retries


def generate_webhook_secret() -> str:
    """Generate a 64-char hex HMAC signing key."""
    return secrets.token_hex(32)


# ── Evaluation ────────────────────────────────────────────────────────


def evaluate_all_rules(db: Session) -> dict:
    """Evaluate all active alert rules and queue deliveries for triggered ones."""
    now = datetime.now(timezone.utc)
    rules = db.query(AlertRule).filter(AlertRule.is_active == True).all()

    evaluated = 0
    triggered = 0
    queued = 0

    for rule in rules:
        evaluated += 1

        # Respect cooldown
        if rule.last_triggered_at:
            cooldown_end = rule.last_triggered_at.replace(tzinfo=timezone.utc) + timedelta(
                seconds=rule.cooldown_seconds
            )
            if now < cooldown_end:
                rule.last_evaluated_at = now.replace(tzinfo=None)
                continue

        payload = _evaluate_rule(db, rule)
        if payload is not None:
            triggered += 1
            delivery = _queue_delivery(db, rule, payload, now)
            if delivery:
                queued += 1

        rule.last_evaluated_at = now.replace(tzinfo=None)

    db.commit()
    return {"rules_evaluated": evaluated, "alerts_triggered": triggered, "deliveries_queued": queued}


def _evaluate_rule(db: Session, rule: AlertRule) -> Optional[dict]:
    """Dispatch to the appropriate evaluator based on event_source."""
    evaluators = {
        "WASI_INDEX": _evaluate_wasi_index,
        "COMMODITY_PRICE": _evaluate_commodity_price,
        "NEWS_EVENT": _evaluate_news_event,
        "DIVERGENCE": _evaluate_divergence,
        "FORECAST_DEVIATION": _evaluate_forecast_deviation,
        "CONFIDENCE_DROP": _evaluate_confidence_drop,
    }
    fn = evaluators.get(rule.event_source)
    if fn is None:
        logger.warning("Unknown event_source '%s' on rule %d", rule.event_source, rule.id)
        return None
    return fn(db, rule)


def _evaluate_wasi_index(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check if WASI country index changed beyond threshold."""
    query = db.query(CountryIndex)
    if rule.country_code:
        country = db.query(Country).filter(Country.code == rule.country_code).first()
        if not country:
            return None
        query = query.filter(CountryIndex.country_id == country.id)

    rows = query.order_by(CountryIndex.period_date.desc()).limit(2).all()
    if len(rows) < 2:
        return None

    current, previous = rows[0], rows[1]
    change = current.index_value - previous.index_value

    if _check_condition(rule.condition, change, current.index_value, rule.threshold_value):
        cc = rule.country_code or "ALL"
        if rule.country_code and not hasattr(current, "_country_code_cache"):
            c = db.query(Country).filter(Country.id == current.country_id).first()
            cc = c.code if c else cc
        return {
            "country_code": cc,
            "current_value": round(current.index_value, 2),
            "previous_value": round(previous.index_value, 2),
            "change": round(change, 2),
            "period_date": str(current.period_date),
        }
    return None


def _evaluate_commodity_price(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check if commodity price changed beyond threshold (MoM %)."""
    if not rule.commodity_code:
        return None

    rows = (
        db.query(CommodityPrice)
        .filter(CommodityPrice.commodity_code == rule.commodity_code.upper())
        .order_by(CommodityPrice.period_date.desc())
        .limit(2)
        .all()
    )
    if len(rows) < 2:
        return None

    current, previous = rows[0], rows[1]
    if previous.price_usd and previous.price_usd > 0:
        pct_change = ((current.price_usd - previous.price_usd) / previous.price_usd) * 100
    else:
        return None

    if _check_condition(rule.condition, pct_change, current.price_usd, rule.threshold_value):
        return {
            "commodity_code": rule.commodity_code.upper(),
            "current_price_usd": round(current.price_usd, 2),
            "previous_price_usd": round(previous.price_usd, 2),
            "pct_change_mom": round(pct_change, 2),
            "period_date": str(current.period_date),
        }
    return None


def _evaluate_news_event(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check for new active news events since last evaluation."""
    query = db.query(NewsEvent).filter(NewsEvent.is_active == True)

    if rule.last_evaluated_at:
        query = query.filter(NewsEvent.detected_at > rule.last_evaluated_at)

    if rule.country_code:
        country = db.query(Country).filter(Country.code == rule.country_code).first()
        if country:
            query = query.filter(NewsEvent.country_id == country.id)

    if rule.event_type_filter:
        query = query.filter(NewsEvent.event_type == rule.event_type_filter.upper())

    event = query.order_by(NewsEvent.detected_at.desc()).first()
    if event is None:
        return None

    # For NEWS_EVENT, condition ANY always triggers; others check magnitude
    if rule.condition == "ANY" or _check_condition(
        rule.condition, event.magnitude, event.magnitude, rule.threshold_value
    ):
        cc = None
        if event.country_id:
            c = db.query(Country).filter(Country.id == event.country_id).first()
            cc = c.code if c else None
        return {
            "country_code": cc,
            "event_type": event.event_type,
            "headline": event.headline,
            "magnitude": event.magnitude,
            "source_name": event.source_name,
            "detected_at": str(event.detected_at),
        }
    return None


def _evaluate_divergence(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check for stock market divergence signals."""
    query = db.query(DivergenceSnapshot)
    if rule.last_evaluated_at:
        query = query.filter(DivergenceSnapshot.computed_at > rule.last_evaluated_at)

    snapshot = query.order_by(DivergenceSnapshot.computed_at.desc()).first()
    if snapshot is None:
        return None

    strong_signals = {"strong_overvalued", "strong_undervalued"}
    if snapshot.signal in strong_signals or (
        rule.threshold_value
        and snapshot.divergence_pct is not None
        and abs(snapshot.divergence_pct) > rule.threshold_value
    ):
        return {
            "exchange_code": snapshot.exchange_code,
            "signal": snapshot.signal,
            "divergence_pct": round(snapshot.divergence_pct, 2) if snapshot.divergence_pct else None,
            "stock_index_value": snapshot.stock_index_value,
            "snapshot_date": str(snapshot.snapshot_date),
        }
    return None


def _evaluate_forecast_deviation(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check if actual value deviates from forecast by more than threshold."""
    try:
        from src.database.forecast_models import ForecastResult
    except ImportError:
        return None

    if not rule.country_code:
        return None

    country = db.query(Country).filter(Country.code == rule.country_code).first()
    if not country:
        return None

    # Latest actual
    actual = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    if not actual:
        return None

    # Nearest forecast for this country
    forecast = (
        db.query(ForecastResult)
        .filter(
            ForecastResult.target_type == "country_index",
            ForecastResult.target_code == rule.country_code,
            ForecastResult.period_date == actual.period_date,
        )
        .first()
    )
    if not forecast:
        return None

    deviation = actual.index_value - forecast.forecast_value
    threshold = rule.threshold_value or 5.0

    if abs(deviation) > threshold:
        return {
            "country_code": rule.country_code,
            "actual_value": round(actual.index_value, 2),
            "forecast_value": round(forecast.forecast_value, 2),
            "deviation": round(deviation, 2),
            "period_date": str(actual.period_date),
        }
    return None


def _evaluate_confidence_drop(db: Session, rule: AlertRule) -> Optional[dict]:
    """Check if country index confidence dropped below threshold."""
    if not rule.country_code:
        return None

    country = db.query(Country).filter(Country.code == rule.country_code).first()
    if not country:
        return None

    latest = (
        db.query(CountryIndex)
        .filter(CountryIndex.country_id == country.id)
        .order_by(CountryIndex.period_date.desc())
        .first()
    )
    if not latest or latest.confidence is None:
        return None

    threshold = rule.threshold_value or 0.50
    if latest.confidence < threshold:
        return {
            "country_code": rule.country_code,
            "current_confidence": round(latest.confidence, 3),
            "threshold": threshold,
            "index_value": round(latest.index_value, 2),
            "period_date": str(latest.period_date),
        }
    return None


def _check_condition(condition: str, change: float, current_value: float, threshold: Optional[float]) -> bool:
    """Evaluate a condition against a value."""
    if condition == "ANY":
        return True
    if threshold is None:
        return False
    if condition == "DROP_GT":
        return change < -threshold
    if condition == "RISE_GT":
        return change > threshold
    if condition == "CHANGE_GT":
        return abs(change) > threshold
    if condition == "BELOW":
        return current_value < threshold
    if condition == "ABOVE":
        return current_value > threshold
    return False


# ── Delivery Queueing ────────────────────────────────────────────────


def _queue_delivery(db: Session, rule: AlertRule, payload_data: dict, now: datetime) -> Optional[AlertDelivery]:
    """Create a pending delivery, deducting credits first."""
    # Check user balance
    cost = rule.credit_cost_per_delivery
    if cost > 0:
        result = db.execute(
            text("UPDATE users SET x402_balance = x402_balance - :cost WHERE id = :uid AND x402_balance >= :cost"),
            {"cost": cost, "uid": rule.user_id},
        )
        if result.rowcount == 0:
            delivery = AlertDelivery(
                rule_id=rule.id,
                user_id=rule.user_id,
                event_source=rule.event_source,
                payload_json=json.dumps(_build_payload(rule, payload_data, now)),
                status="skipped_insufficient_credits",
                credits_charged=0.0,
            )
            db.add(delivery)
            return None

    payload = _build_payload(rule, payload_data, now)
    delivery = AlertDelivery(
        rule_id=rule.id,
        user_id=rule.user_id,
        event_source=rule.event_source,
        payload_json=json.dumps(payload),
        status="pending",
        credits_charged=cost,
    )
    db.add(delivery)
    rule.last_triggered_at = now.replace(tzinfo=None)
    return delivery


def _build_payload(rule: AlertRule, data: dict, now: datetime) -> dict:
    """Build the standard webhook payload."""
    return {
        "event_source": rule.event_source,
        "rule_id": rule.id,
        "rule_name": rule.name or f"Rule #{rule.id}",
        "triggered_at": now.isoformat(),
        "data": data,
    }


# ── Webhook Delivery ─────────────────────────────────────────────────


def deliver_pending_webhooks(db: Session) -> dict:
    """Send all pending webhook deliveries, handling retries."""
    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)

    pending = (
        db.query(AlertDelivery)
        .filter(
            AlertDelivery.status == "pending",
        )
        .all()
    )

    # Filter: only those with no next_retry_at or past it
    ready = [d for d in pending if d.next_retry_at is None or d.next_retry_at <= now_naive]

    delivered = 0
    failed = 0
    retrying = 0

    for delivery in ready:
        rule = db.query(AlertRule).filter(AlertRule.id == delivery.rule_id).first()
        if not rule:
            delivery.status = "failed"
            delivery.error_message = "Rule not found"
            failed += 1
            continue

        success = _send_webhook(delivery, rule)
        if success:
            delivery.status = "delivered"
            delivery.delivered_at = now_naive
            delivered += 1
        else:
            delivery.attempt_count += 1
            if delivery.attempt_count >= delivery.max_attempts:
                delivery.status = "failed"
                failed += 1
            else:
                delay = RETRY_DELAYS[min(delivery.attempt_count - 1, len(RETRY_DELAYS) - 1)]
                delivery.next_retry_at = now_naive + timedelta(seconds=delay)
                retrying += 1

    db.commit()
    return {"delivered": delivered, "failed": failed, "retrying": retrying}


def _send_webhook(delivery: AlertDelivery, rule: AlertRule) -> bool:
    """POST the payload to the webhook URL with HMAC signature. Returns True on success."""
    payload_bytes = delivery.payload_json.encode("utf-8")

    # HMAC-SHA256 signature
    signature = hmac_mod.new(
        rule.webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-WASI-Signature": f"sha256={signature}",
        "X-WASI-Delivery-Id": str(delivery.id),
        "X-WASI-Event": delivery.event_source,
        "User-Agent": "WASI-Webhook/1.0",
    }

    try:
        response = httpx.post(
            rule.webhook_url,
            content=payload_bytes,
            headers=headers,
            timeout=10.0,
        )
        delivery.http_status_code = response.status_code
        if 200 <= response.status_code < 300:
            return True
        delivery.error_message = f"HTTP {response.status_code}"
        return False
    except httpx.TimeoutException:
        delivery.error_message = "Timeout (10s)"
        return False
    except Exception as exc:
        delivery.error_message = str(exc)[:500]
        return False


def send_test_webhook(rule: AlertRule) -> dict:
    """Send a synthetic test payload immediately. Returns delivery result."""
    now = datetime.now(timezone.utc)
    payload = {
        "test": True,
        "event_source": rule.event_source,
        "rule_id": rule.id,
        "rule_name": rule.name or f"Rule #{rule.id}",
        "message": "Test webhook from WASI Alert System",
        "triggered_at": now.isoformat(),
        "data": {},
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = hmac_mod.new(
        rule.webhook_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-WASI-Signature": f"sha256={signature}",
        "X-WASI-Delivery-Id": "test",
        "X-WASI-Event": rule.event_source,
        "User-Agent": "WASI-Webhook/1.0",
    }

    try:
        response = httpx.post(
            rule.webhook_url,
            content=payload_bytes,
            headers=headers,
            timeout=10.0,
        )
        return {
            "status": "delivered" if 200 <= response.status_code < 300 else "failed",
            "http_status_code": response.status_code,
        }
    except httpx.TimeoutException:
        return {"status": "failed", "error": "Timeout (10s)"}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)[:500]}
