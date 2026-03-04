"""
Alert/Webhook routes — /api/v3/alerts/

User-configurable rules that trigger signed webhook deliveries when
economic events occur (index changes, price spikes, news, divergence, etc.).

Endpoint credit costs:
  POST /rules                — 2 credits
  GET  /rules                — 0 credits
  GET  /rules/{id}           — 0 credits
  PUT  /rules/{id}           — 0 credits
  DELETE /rules/{id}         — 0 credits (soft-deactivate)
  POST /rules/{id}/test      — 1 credit
  GET  /deliveries           — 0 credits
  GET  /deliveries/{id}      — 0 credits
  GET  /status               — 0 credits
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import settings
from src.database.alert_models import AlertDelivery, AlertRule
from src.database.connection import get_db
from src.database.models import User
from src.engines.alert_engine import generate_webhook_secret, send_test_webhook
from src.schemas.alert import (
    AlertDeliveryDetailResponse,
    AlertDeliveryResponse,
    AlertRuleCreateRequest,
    AlertRuleCreateResponse,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    AlertStatusResponse,
)
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user

MAX_RULES_PER_USER = 20

router = APIRouter(prefix="/api/v3/alerts", tags=["Alerts & Webhooks"])


# ── Rules CRUD ──────────────────────────────────────────────────────


@router.post("/rules", response_model=AlertRuleCreateResponse)
async def create_alert_rule(
    body: AlertRuleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new alert rule. Returns webhook_secret once. 2 credits."""
    deduct_credits(current_user, db, "/api/v3/alerts/rules", method="POST", cost_multiplier=2.0)

    # Enforce max rules per user
    active_count = (
        db.query(func.count(AlertRule.id))
        .filter(AlertRule.user_id == current_user.id, AlertRule.is_active == True)
        .scalar()
    )
    if active_count >= MAX_RULES_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_RULES_PER_USER} active rules per user.",
        )

    # Webhook URL must be HTTPS in production
    if not settings.DEBUG and not body.webhook_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS.")

    secret = body.webhook_secret or generate_webhook_secret()

    rule = AlertRule(
        user_id=current_user.id,
        name=body.name,
        event_source=body.event_source,
        country_code=body.country_code.upper() if body.country_code else None,
        commodity_code=body.commodity_code.upper() if body.commodity_code else None,
        event_type_filter=body.event_type_filter.upper() if body.event_type_filter else None,
        condition=body.condition,
        threshold_value=body.threshold_value,
        webhook_url=body.webhook_url,
        webhook_secret=secret,
        cooldown_seconds=body.cooldown_seconds,
        credit_cost_per_delivery=body.credit_cost_per_delivery,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    return AlertRuleCreateResponse.model_validate(rule)


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all alert rules for the current user. 0 credits."""
    rules = (
        db.query(AlertRule)
        .filter(AlertRule.user_id == current_user.id)
        .order_by(AlertRule.created_at.desc())
        .all()
    )
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single alert rule. 0 credits."""
    rule = (
        db.query(AlertRule)
        .filter(AlertRule.id == rule_id, AlertRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found.")
    return AlertRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    body: AlertRuleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an alert rule (partial). 0 credits."""
    rule = (
        db.query(AlertRule)
        .filter(AlertRule.id == rule_id, AlertRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found.")

    updates = body.model_dump(exclude_unset=True)

    # Validate webhook URL if being changed
    if "webhook_url" in updates and not settings.DEBUG:
        if not updates["webhook_url"].startswith("https://"):
            raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS.")

    # Validate condition if being changed
    if "condition" in updates and updates["condition"]:
        from src.schemas.alert import VALID_CONDITIONS
        cond = updates["condition"].upper()
        if cond not in VALID_CONDITIONS:
            raise HTTPException(status_code=400, detail=f"condition must be one of {sorted(VALID_CONDITIONS)}")
        updates["condition"] = cond

    for field, value in updates.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    return AlertRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-deactivate an alert rule. 0 credits."""
    rule = (
        db.query(AlertRule)
        .filter(AlertRule.id == rule_id, AlertRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found.")

    rule.is_active = False
    db.commit()
    return {"detail": "Alert rule deactivated.", "rule_id": rule_id}


@router.post("/rules/{rule_id}/test")
async def test_alert_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a test webhook to verify the endpoint. 1 credit."""
    deduct_credits(current_user, db, f"/api/v3/alerts/rules/{rule_id}/test", method="POST", cost_multiplier=1.0)

    rule = (
        db.query(AlertRule)
        .filter(AlertRule.id == rule_id, AlertRule.user_id == current_user.id)
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Alert rule not found.")

    result = send_test_webhook(rule)
    return result


# ── Delivery History ────────────────────────────────────────────────


@router.get("/deliveries", response_model=list[AlertDeliveryResponse])
async def list_deliveries(
    rule_id: int | None = Query(None, description="Filter by rule ID"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List delivery history for the current user. 0 credits."""
    query = db.query(AlertDelivery).filter(AlertDelivery.user_id == current_user.id)

    if rule_id is not None:
        query = query.filter(AlertDelivery.rule_id == rule_id)
    if status:
        query = query.filter(AlertDelivery.status == status)

    deliveries = query.order_by(AlertDelivery.created_at.desc()).offset(offset).limit(limit).all()
    return [AlertDeliveryResponse.model_validate(d) for d in deliveries]


@router.get("/deliveries/{delivery_id}", response_model=AlertDeliveryDetailResponse)
async def get_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single delivery with full payload. 0 credits."""
    delivery = (
        db.query(AlertDelivery)
        .filter(AlertDelivery.id == delivery_id, AlertDelivery.user_id == current_user.id)
        .first()
    )
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found.")
    return AlertDeliveryDetailResponse.model_validate(delivery)


# ── Dashboard ───────────────────────────────────────────────────────


@router.get("/status", response_model=AlertStatusResponse)
async def get_alert_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard: rule counts, delivery stats, credits spent (24h). 0 credits."""
    total_rules = db.query(func.count(AlertRule.id)).filter(AlertRule.user_id == current_user.id).scalar()
    active_rules = (
        db.query(func.count(AlertRule.id))
        .filter(AlertRule.user_id == current_user.id, AlertRule.is_active == True)
        .scalar()
    )

    total_deliveries = (
        db.query(func.count(AlertDelivery.id))
        .filter(AlertDelivery.user_id == current_user.id)
        .scalar()
    )

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_naive = cutoff.replace(tzinfo=None)

    deliveries_24h = (
        db.query(func.count(AlertDelivery.id))
        .filter(AlertDelivery.user_id == current_user.id, AlertDelivery.created_at >= cutoff_naive)
        .scalar()
    )

    credits_24h = (
        db.query(func.coalesce(func.sum(AlertDelivery.credits_charged), 0.0))
        .filter(AlertDelivery.user_id == current_user.id, AlertDelivery.created_at >= cutoff_naive)
        .scalar()
    )

    failed_24h = (
        db.query(func.count(AlertDelivery.id))
        .filter(
            AlertDelivery.user_id == current_user.id,
            AlertDelivery.created_at >= cutoff_naive,
            AlertDelivery.status == "failed",
        )
        .scalar()
    )

    return AlertStatusResponse(
        total_rules=total_rules,
        active_rules=active_rules,
        total_deliveries=total_deliveries,
        deliveries_last_24h=deliveries_24h,
        credits_spent_last_24h=float(credits_24h),
        failed_deliveries_last_24h=failed_24h,
    )
