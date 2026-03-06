import json
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import get_db
from src.database.models import User
from src.engines.credit_guardrails_engine import (
    CreditDecisionInput,
    DISCLAIMER,
    WASIExpertScoringEngine,
)
from src.schemas.v1_guardrails import (
    CreditDecisionRequest,
    CreditDecisionResponse,
    FXMarketResponse,
    FXRateRow,
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
)
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user
from src.utils.wacc_params import VALID_WASI_COUNTRIES

router = APIRouter(prefix="/v1", tags=["V1 Guardrails"])
limiter = Limiter(key_func=get_remote_address)

MISSING_REALTIME_DATA_MESSAGE = "Je n'ai pas cette donn\u00e9e en temps r\u00e9el"
SONNET_MODEL = "claude-sonnet-4-6"
OPEN_ER_API_BASE = "https://open.er-api.com/v6/latest"

_credit_engine = WASIExpertScoringEngine()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_symbols(raw: str | None) -> list[str]:
    if not raw:
        return ["EUR", "USD"]
    result: list[str] = []
    for token in raw.split(","):
        symbol = token.strip().upper()
        if not symbol:
            continue
        if len(symbol) != 3 or not symbol.isalpha():
            raise HTTPException(status_code=422, detail=f"Invalid currency symbol: {symbol}")
        if symbol not in result:
            result.append(symbol)
    if not result:
        return ["EUR", "USD"]
    return result


async def _fetch_open_er_api(base: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{OPEN_ER_API_BASE}/{base}")
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail=MISSING_REALTIME_DATA_MESSAGE)
    payload = resp.json()
    if payload.get("result") != "success":
        raise HTTPException(status_code=503, detail=MISSING_REALTIME_DATA_MESSAGE)
    return payload


def _extract_citations(context_data: Any) -> list[str]:
    citations: list[str] = []
    if isinstance(context_data, dict):
        explicit = context_data.get("citations") or context_data.get("sources")
        if isinstance(explicit, list):
            for item in explicit:
                if isinstance(item, str) and item.strip():
                    citations.append(item.strip())
        elif isinstance(explicit, str) and explicit.strip():
            citations.append(explicit.strip())
    if not citations:
        citations = [
            "WASI Data Engine v3.0",
            "open.er-api.com",
            "api.worldbank.org",
            "api.acleddata.com",
        ]
    return citations


def _build_local_analysis(question: str, context_data: Any, missing_flags: list[str]) -> str:
    context_hint = "Aucun contexte additionnel fourni."
    if isinstance(context_data, dict) and context_data:
        keys = ", ".join(sorted(context_data.keys())[:8])
        context_hint = f"Contexte detecte: {keys}."
    missing_block = (
        f"\nSignal donnees: {MISSING_REALTIME_DATA_MESSAGE}."
        if missing_flags
        else "\nSignal donnees: contexte partiel valide."
    )
    return (
        "Analyse locale WASI (mode confidentiel) basee sur regles expertes.\n"
        f"Question: {question}\n"
        f"{context_hint}{missing_block}\n"
        "Recommandation: validation humaine obligatoire avant toute decision bancaire."
    )


async def _call_sonnet_analysis(question: str, context_data: Any) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Chat service not available.")

    system_prompt = (
        "Tu es l'analyste financier WASI. Regles absolues: "
        "1) N'invente jamais prix spot, taux FX ou cours de bourse. "
        f"2) Si une donnee manque, dis exactement: '{MISSING_REALTIME_DATA_MESSAGE}'. "
        "3) Distingue toujours historique, estimation, et live. "
        "4) Reponds en francais."
    )
    payload = {
        "model": SONNET_MODEL,
        "max_tokens": 1200,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n"
                    f"Context data JSON: {json.dumps(context_data, ensure_ascii=False)}"
                ),
            }
        ],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Chat service returned an error")

    body = resp.json()
    try:
        return str(body["content"][0]["text"]).strip()
    except (KeyError, IndexError, TypeError):
        raise HTTPException(status_code=502, detail="Invalid chat response payload") from None


@router.get("/market/fx", response_model=FXMarketResponse)
@limiter.limit("30/minute")
async def get_fx_market(
    request: Request,
    base: str = Query(default="XOF", min_length=3, max_length=3),
    symbols: str = Query(default="EUR,USD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/v1/market/fx", method="GET", cost_multiplier=1.0)

    base_code = base.upper()
    wanted_symbols = _normalize_symbols(symbols)
    payload = await _fetch_open_er_api(base_code)
    rates = payload.get("rates", {})

    rows: list[FXRateRow] = []
    for code in wanted_symbols:
        value = rates.get(code)
        if isinstance(value, (int, float)):
            rows.append(FXRateRow(symbol=code, rate=float(value)))

    if not rows:
        raise HTTPException(status_code=503, detail=MISSING_REALTIME_DATA_MESSAGE)

    return FXMarketResponse(
        base=base_code,
        rates=rows,
        source="open.er-api.com",
        timestamp=_now_iso(),
        data_mode="live",
        confidence=0.95,
        as_of=payload.get("time_last_update_utc"),
        message=None,
    )


@router.post("/credit/decision", response_model=CreditDecisionResponse)
@limiter.limit("20/minute")
async def post_credit_decision(
    request: Request,
    body: CreditDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(current_user, db, "/v1/credit/decision", method="POST", cost_multiplier=5.0)

    country = body.country.upper()
    if country not in VALID_WASI_COUNTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"Country '{body.country}' is not in WASI ECOWAS set.",
        )

    try:
        result = _credit_engine.evaluate(
            CreditDecisionInput(
                country=country,
                loan_type=body.loan_type,
                components=body.components.model_dump(),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CreditDecisionResponse(**result)


@router.post("/ai/financial-analysis", response_model=FinancialAnalysisResponse)
@limiter.limit("15/minute")
async def post_financial_analysis(
    request: Request,
    body: FinancialAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deduct_credits(
        current_user,
        db,
        "/v1/ai/financial-analysis",
        method="POST",
        cost_multiplier=3.0,
    )

    mode = body.confidentiality_mode.lower().strip()
    if mode not in {"local", "cloud"}:
        raise HTTPException(
            status_code=422,
            detail="confidentiality_mode must be 'local' or 'cloud'",
        )

    missing_flags: list[str] = []
    context_data = body.context_data
    if context_data in (None, {}, []):
        missing_flags.append(MISSING_REALTIME_DATA_MESSAGE)
        context_data = {}

    if mode == "local":
        analysis = _build_local_analysis(body.question, context_data, missing_flags)
        model_used = "ollama/llama3.2"
    else:
        analysis = await _call_sonnet_analysis(body.question, context_data)
        model_used = SONNET_MODEL

    citations = _extract_citations(context_data)
    return FinancialAnalysisResponse(
        analysis=analysis,
        model_used=model_used,
        citations=citations,
        missing_data_flags=missing_flags,
        human_review_required=True,
        disclaimer=DISCLAIMER,
    )
