"""
WASI-Pay Cross-Border Payments — /api/v3/ecfa/payments/

Endpoints for cross-border payment operations across 15 ECOWAS countries.

Credit costs:
  POST /cross-border    — 5 credits  (execute payment)
  POST /quote           — 1 credit   (get fee/rate quote)
  GET  /{id}/status     — 1 credit   (track payment)
  GET  /{id}/trace      — 2 credits  (full hop trace)
  GET  /corridors       — 1 credit   (list corridors)
  GET  /fx/rates        — 1 credit   (all FX rates)
  GET  /fx/rates/{pair} — 1 credit   (specific rate)
  POST /fx/rates/update — 10 credits (admin rate update)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.database.connection import get_db
from src.database.models import User
from src.utils.security import get_current_user
from src.utils.credits import deduct_credits
from src.engines.cbdc_payment_router import CbdcPaymentRouter
from src.engines.cbdc_fx_engine import CbdcFxEngine
from src.schemas.cbdc_payments import (
    CrossBorderQuoteRequest, CrossBorderQuoteResponse,
    CrossBorderPaymentRequest, CrossBorderPaymentResponse,
    PaymentStatusResponse, PaymentTraceResponse, PaymentTraceHop,
    FxRateResponse, FxRateUpdateRequest,
    CorridorResponse,
)

router = APIRouter(prefix="/api/v3/ecfa/payments", tags=["WASI-Pay Cross-Border"])
limiter = Limiter(key_func=get_remote_address)


# ── Payment Operations ────────────────────────────────────────────────


@router.post("/cross-border", response_model=CrossBorderPaymentResponse)
@limiter.limit("10/minute")
async def execute_cross_border_payment(
    request: Request,
    body: CrossBorderPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a cross-border payment across ECOWAS.

    Handles all routing automatically:
    - WAEMU→WAEMU: instant eCFA transfer (no FX)
    - WAEMU→WAMZ: eCFA debit → FX conversion → external bridge
    - WAMZ→WAEMU: external bridge → FX conversion → eCFA credit
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/cross-border", "POST", 5.0)

    router_engine = CbdcPaymentRouter(db)
    result = router_engine.execute_payment(
        sender_wallet_id=body.sender_wallet_id,
        receiver_wallet_id=body.receiver_wallet_id,
        receiver_country=body.receiver_country,
        amount=body.amount,
        source_currency=body.source_currency,
        target_currency=body.target_currency,
        purpose=body.purpose,
        pin=body.pin,
        quote_id=body.quote_id,
    )
    return CrossBorderPaymentResponse(**result)


@router.post("/quote", response_model=CrossBorderQuoteResponse)
@limiter.limit("30/minute")
async def get_payment_quote(
    request: Request,
    body: CrossBorderQuoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a fee/rate quote for a cross-border payment.

    Optionally locks the FX rate for 30 seconds (lock_rate=true).
    Use the returned quote_id when executing the payment to guarantee the rate.
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/quote", "POST", 1.0)

    router_engine = CbdcPaymentRouter(db)
    result = router_engine.get_quote(
        sender_wallet_id=body.sender_wallet_id,
        receiver_wallet_id=body.receiver_wallet_id,
        receiver_country=body.receiver_country,
        amount=body.amount,
        source_currency=body.source_currency,
        target_currency=body.target_currency,
        lock_rate=body.lock_rate,
    )
    return CrossBorderQuoteResponse(**result)


# ── Payment Tracking ──────────────────────────────────────────────────


@router.get("/{payment_id}/status", response_model=PaymentStatusResponse)
@limiter.limit("30/minute")
async def get_payment_status(
    request: Request,
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current status of a cross-border payment."""
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/status", "GET", 1.0)

    router_engine = CbdcPaymentRouter(db)
    result = router_engine.get_payment_status(payment_id)
    return PaymentStatusResponse(**result)


@router.get("/{payment_id}/trace", response_model=PaymentTraceResponse)
@limiter.limit("20/minute")
async def get_payment_trace(
    request: Request,
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the detailed hop-by-hop trace of a cross-border payment.

    Shows each step: compliance → FX lock → source debit → FX conversion
    → destination credit → settlement.
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/trace", "GET", 2.0)

    router_engine = CbdcPaymentRouter(db)
    result = router_engine.get_payment_trace(payment_id)
    hops = [PaymentTraceHop(**h) for h in result["hops"]]
    return PaymentTraceResponse(
        payment_id=result["payment_id"],
        status=result["status"],
        rail_type=result["rail_type"],
        hops=hops,
    )


# ── Corridors ─────────────────────────────────────────────────────────


@router.get("/corridors", response_model=list[CorridorResponse])
@limiter.limit("20/minute")
async def list_corridors(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available ECOWAS payment corridors with fees.

    Returns 240 corridors (16×15) with fee breakdown, rail type,
    and availability status.
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/corridors", "GET", 1.0)

    router_engine = CbdcPaymentRouter(db)
    corridors = router_engine.list_corridors()
    return [CorridorResponse(**c) for c in corridors]


# ── FX Rates ──────────────────────────────────────────────────────────


@router.get("/fx/rates", response_model=list[FxRateResponse])
@limiter.limit("30/minute")
async def get_all_fx_rates(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get FX rates for all 8 non-XOF ECOWAS currencies.

    Rates are quoted as XOF per 1 unit of target currency.
    Includes staleness indicator (stale if >24 hours old).
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/fx/rates", "GET", 1.0)

    fx_engine = CbdcFxEngine(db)
    rates = fx_engine.get_all_rates()
    return [FxRateResponse(**r) for r in rates]


@router.get("/fx/rates/{currency_pair}", response_model=FxRateResponse)
@limiter.limit("30/minute")
async def get_fx_rate(
    request: Request,
    currency_pair: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get FX rate for a specific currency pair (e.g., XOF-NGN).

    Accepts formats: 'XOF-NGN', 'XOF_NGN', or just 'NGN'.
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/fx/rates", "GET", 1.0)

    # Parse currency pair
    pair = currency_pair.upper().replace("-", "_")
    if "_" in pair:
        parts = pair.split("_")
        target_currency = parts[1] if parts[0] == "XOF" else parts[0]
    else:
        target_currency = pair

    fx_engine = CbdcFxEngine(db)
    result = fx_engine.get_rate(target_currency)
    return FxRateResponse(**result)


@router.post("/fx/rates/update", response_model=FxRateResponse)
@limiter.limit("5/minute")
async def update_fx_rate(
    request: Request,
    body: FxRateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an FX rate (admin/BCEAO only).

    Inserts or updates today's rate for the specified currency.
    """
    deduct_credits(current_user, db, "/api/v3/ecfa/payments/fx/rates/update", "POST", 10.0)

    fx_engine = CbdcFxEngine(db)
    result = fx_engine.update_rate(
        target_currency=body.target_currency,
        new_rate=body.new_rate,
        source=body.source,
    )
    db.commit()
    return FxRateResponse(**result)
