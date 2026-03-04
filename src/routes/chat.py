"""
Chat routes.

POST /api/chat             — raw proxy to Anthropic (API key never exposed to browser)
POST /api/chat/intelligence — RAG-enhanced: queries live WASI DB then calls Claude

The intelligence endpoint answers questions like:
  - "How many WASI countries trade with Switzerland?"
  - "What is the WASI composite index?"
  - "What are Nigeria top trading partners?"
  - "Is the market bullish or bearish?"
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import settings
from src.database.connection import get_db
from src.database.models import BilateralTrade, Country, CountryIndex, WASIComposite, User, StockMarketData
from src.utils.credits import deduct_credits
from src.utils.security import get_current_user

router = APIRouter(prefix="/api/chat", tags=["Chat"])
limiter = Limiter(key_func=get_remote_address)
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# ── Security: model whitelist and token cap ───────────────────────────────────
ALLOWED_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250514",
}
MAX_TOKENS_CAP = 2000
MAX_MESSAGES = 50  # prevent context-stuffing abuse

# ── Security: prompt injection detection ──────────────────────────────────────
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instruction", re.IGNORECASE),
    re.compile(r"forget\s+(your|all|the)\s+(system|previous)", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now|no\s+longer)\b", re.IGNORECASE),
    re.compile(r"(print|reveal|show|output|repeat)\s+(your\s+)?(full\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"disregard\s+(all|any|the)\s+(above|previous)", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]

# ── Financial disclaimer appended to all AI responses ─────────────────────────
_DISCLAIMER = (
    "\n\n---\n*WASI provides data intelligence only. This is NOT investment, "
    "legal, or financial advice. Consult a licensed professional before making "
    "financial decisions. WASI accepts no liability for losses.*"
)


def _check_injection(text: str) -> None:
    """Reject messages containing prompt injection patterns."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            raise HTTPException(
                status_code=400,
                detail="Message contains disallowed instructions.",
            )


def _validate_model(model: str) -> str:
    """Enforce model whitelist — prevent expensive model abuse."""
    if model not in ALLOWED_MODELS:
        return "claude-haiku-4-5-20251001"  # fall back to cheapest
    return model


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str = Field(..., max_length=10000)


class ChatRequest(BaseModel):
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = Field(default=1000, le=MAX_TOKENS_CAP)
    system: Optional[str] = None
    messages: list[ChatMessage]


class IntelligenceRequest(BaseModel):
    question: str
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1200
    language: str = "en"   # W5: "en" | "fr" — response language


# ── Raw proxy ─────────────────────────────────────────────────────────────────

@router.post("")
async def proxy_chat(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Proxy to Anthropic. Keeps API key server-side. Costs 1 credit."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Chat service not available.")

    # Security: validate model, cap tokens, limit message count
    safe_model = _validate_model(payload.model)
    safe_max_tokens = min(payload.max_tokens, MAX_TOKENS_CAP)

    if len(payload.messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail="Too many messages in conversation.")

    # Security: check all user messages AND system prompt for prompt injection
    for msg in payload.messages:
        if msg.role == "user":
            _check_injection(msg.content)
    if payload.system:
        _check_injection(payload.system)

    deduct_credits(current_user, db, "/api/chat", cost_multiplier=1.0)

    body = {
        "model": safe_model,
        "max_tokens": safe_max_tokens,
        "messages": [{"role": m.role, "content": m.content} for m in payload.messages],
    }
    if payload.system:
        body["system"] = payload.system

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=body,
            )
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail="Chat service temporarily unavailable")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Chat service returned an error")

    # Append financial disclaimer to AI response
    result = resp.json()
    try:
        result["content"][0]["text"] += _DISCLAIMER
    except (KeyError, IndexError):
        logger.warning("Chat response missing expected content structure; disclaimer not appended")
    return result


# ── RAG helpers ───────────────────────────────────────────────────────────────

_WASI_CODES = {"NG", "CI", "GH", "SN", "BF", "ML", "GN", "BJ",
               "TG", "NE", "MR", "GW", "SL", "LR", "GM", "CV"}

# Maps common country names (and alternate spellings) to ISO-2 codes
_NAME_TO_CODE: dict[str, str] = {
    "switzerland": "CH", "swiss": "CH", "suisse": "CH",
    "france": "FR", "french": "FR",
    "china": "CN", "chinese": "CN",
    "united states": "US", "usa": "US", "america": "US",
    "india": "IN", "indian": "IN",
    "germany": "DE", "german": "DE", "allemagne": "DE",
    "netherlands": "NL", "dutch": "NL", "holland": "NL",
    "united kingdom": "GB", "uk": "GB", "britain": "GB",
    "belgium": "BE", "spain": "ES", "italy": "IT",
    "uae": "AE", "emirates": "AE", "portugal": "PT",
    "japan": "JP", "south africa": "ZA", "saudi arabia": "SA",
    "nigeria": "NG", "ivory coast": "CI", "cote d'ivoire": "CI",
    "ghana": "GH", "senegal": "SN", "burkina faso": "BF", "burkina": "BF",
    "mali": "ML", "guinea": "GN", "guinee": "GN", "benin": "BJ", "togo": "TG",
    "niger": "NE", "mauritania": "MR", "mauritanie": "MR",
    "guinea-bissau": "GW", "guinee-bissau": "GW",
    "sierra leone": "SL", "liberia": "LR", "gambia": "GM", "cape verde": "CV",
}


def _extract_codes(question: str) -> tuple[list[str], list[str]]:
    q = question.lower()
    wasi: list[str] = []
    partners: list[str] = []
    for name, code in _NAME_TO_CODE.items():
        if name in q:
            lst = wasi if code in _WASI_CODES else partners
            if code not in lst:
                lst.append(code)
    return wasi, partners


def _is_trade_q(q: str) -> bool:
    kws = ["trade", "partner", "export", "import", "commercial", "partenaire",
           "commerce", "bilateral", "suisse", "switzerland", "china", "france",
           "volume", "surplus", "deficit", "balance", "pays", "countries", "country"]
    return any(k in q.lower() for k in kws)


def _is_index_q(q: str) -> bool:
    return any(k in q.lower() for k in [
        "index", "composite", "wasi", "score", "value",
        "shipping", "infrastructure", "economic", "indice",
    ])


def _is_signal_q(q: str) -> bool:
    return any(k in q.lower() for k in ["signal", "bullish", "bearish", "trend", "momentum"])


def _is_market_q(q: str) -> bool:
    return any(k in q.lower() for k in [
        "stock", "exchange", "ngx", "gse", "brvm", "bourse", "equity", "equities",
        "market cap", "share", "listed", "valeur", "action", "divergence",
        "overvalued", "undervalued", "investor", "investisseur",
    ])


def _fmt(v: float) -> str:
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.0f}M"
    return f"${v:,.0f}"


def _build_context(question: str, db: Session) -> str:
    sections: list[str] = []
    wasi_codes, partner_codes = _extract_codes(question)

    # ── Bilateral trade ───────────────────────────────────────────────────────
    if _is_trade_q(question) or partner_codes:
        if partner_codes:
            for pc in partner_codes[:2]:
                rows = (
                    db.query(BilateralTrade, Country)
                    .join(Country, Country.id == BilateralTrade.country_id)
                    .filter(
                        BilateralTrade.partner_code == pc,
                        BilateralTrade.year == 2022,
                    )
                    .order_by(BilateralTrade.total_trade_usd.desc())
                    .all()
                )
                if rows:
                    pname = rows[0].BilateralTrade.partner_name
                    total_vol = sum(r.BilateralTrade.total_trade_usd for r in rows)
                    lines = [
                        f"## WASI Countries Trading with {pname} ({pc}) in 2022",
                        f"Number of WASI countries with {pname} as trade partner: "
                        f"{len(rows)} | Combined volume: {_fmt(total_vol)}",
                        "",
                    ]
                    for r in rows:
                        bt = r.BilateralTrade
                        lines.append(
                            f"- **{r.Country.name} ({r.Country.code})**: "
                            f"Total {_fmt(bt.total_trade_usd)} | "
                            f"Exports to {pc}: {_fmt(bt.export_value_usd)} | "
                            f"Imports from {pc}: {_fmt(bt.import_value_usd)} | "
                            f"Balance: {_fmt(bt.trade_balance_usd)} | "
                            f"Main exports: {bt.top_exports}"
                        )
                    sections.append("\n".join(lines))

        if wasi_codes:
            for wc in wasi_codes[:2]:
                country = db.query(Country).filter(Country.code == wc).first()
                if not country:
                    continue
                rows = (
                    db.query(BilateralTrade)
                    .filter(
                        BilateralTrade.country_id == country.id,
                        BilateralTrade.year == 2022,
                    )
                    .order_by(BilateralTrade.total_trade_usd.desc())
                    .limit(8)
                    .all()
                )
                if rows:
                    lines = [f"## {country.name} ({wc}) Top Trade Partners 2022"]
                    for r in rows:
                        lines.append(
                            f"- **{r.partner_name} ({r.partner_code})**: "
                            f"Total {_fmt(r.total_trade_usd)} | "
                            f"Balance: {_fmt(r.trade_balance_usd)} | "
                            f"Exports: {r.top_exports}"
                        )
                    sections.append("\n".join(lines))

        if not partner_codes and not wasi_codes:
            top = (
                db.query(BilateralTrade, Country)
                .join(Country, Country.id == BilateralTrade.country_id)
                .filter(BilateralTrade.year == 2022)
                .order_by(BilateralTrade.total_trade_usd.desc())
                .limit(10)
                .all()
            )
            if top:
                lines = ["## Top 10 WASI Bilateral Trade Relationships 2022"]
                for i, r in enumerate(top, 1):
                    lines.append(
                        f"{i}. {r.Country.name} with "
                        f"{r.BilateralTrade.partner_name}: "
                        f"{_fmt(r.BilateralTrade.total_trade_usd)}"
                    )
                sections.append("\n".join(lines))

    # ── Composite / signals ───────────────────────────────────────────────────
    if _is_index_q(question) or _is_signal_q(question):
        latest = (
            db.query(WASIComposite)
            .order_by(WASIComposite.period_date.desc())
            .first()
        )
        if latest:
            mom_str = f"MoM: {latest.mom_change:.2f}% | " if latest.mom_change else ""
            vol_str = (
                f"Annualized vol: {latest.annualized_volatility:.4f}"
                if latest.annualized_volatility else ""
            )
            sections.append(
                f"## WASI Composite Index ({latest.period_date})\n"
                f"- Value: {latest.composite_value:.2f}/100\n"
                f"- Trend: {latest.trend_direction or 'N/A'} | {mom_str}{vol_str}\n"
                f"- Countries included: {latest.countries_included}"
            )

        latest_date = db.query(func.max(CountryIndex.period_date)).scalar()
        if latest_date:
            crows = (
                db.query(CountryIndex, Country)
                .join(Country, Country.id == CountryIndex.country_id)
                .filter(CountryIndex.period_date == latest_date)
                .order_by(CountryIndex.index_value.desc())
                .all()
            )
            if crows:
                lines = [f"## Country Index Scores ({latest_date})"]
                for r in crows:
                    ci = r.CountryIndex
                    s = r.CountryIndex.shipping_score or 0
                    t = r.CountryIndex.trade_score or 0
                    infra = r.CountryIndex.infrastructure_score or 0
                    econ = r.CountryIndex.economic_score or 0
                    lines.append(
                        f"- {r.Country.name} ({r.Country.code}): {ci.index_value:.2f} "
                        f"[Ship:{s:.1f} Trade:{t:.1f} Infra:{infra:.1f} Econ:{econ:.1f}]"
                    )
                sections.append("\n".join(lines))

    # ── Stock market data ─────────────────────────────────────────────────────
    if _is_market_q(question) or _is_signal_q(question):
        subq = (
            db.query(
                StockMarketData.exchange_code,
                StockMarketData.index_name,
                func.max(StockMarketData.trade_date).label("max_date"),
            )
            .group_by(StockMarketData.exchange_code, StockMarketData.index_name)
            .subquery()
        )
        stock_rows = (
            db.query(StockMarketData)
            .join(
                subq,
                (StockMarketData.exchange_code == subq.c.exchange_code)
                & (StockMarketData.index_name == subq.c.index_name)
                & (StockMarketData.trade_date == subq.c.max_date),
            )
            .order_by(StockMarketData.exchange_code)
            .all()
        )
        if stock_rows:
            from src.engines.divergence_engine import EXCHANGE_WASI_WEIGHT
            lines = ["## West African Stock Markets (latest data)"]
            lines.append("Exchange | Index | Value | Change % | Market Cap | WASI Weight")
            for s in stock_rows:
                chg = f"{s.change_pct:+.2f}%" if s.change_pct is not None else "N/A"
                mcap = _fmt(s.market_cap_usd) if s.market_cap_usd else "N/A"
                w = EXCHANGE_WASI_WEIGHT.get(s.exchange_code, 0)
                lines.append(
                    f"- **{s.exchange_code}** {s.index_name}: {s.index_value:.2f} pts | "
                    f"Change: {chg} | Market Cap: {mcap} | "
                    f"WASI weight: {w*100:.0f}% | Date: {s.trade_date}"
                )
            sections.append("\n".join(lines))

    # ── Fallback: WASI country list ───────────────────────────────────────────
    if not sections:
        countries = (
            db.query(Country)
            .filter(Country.is_active.is_(True))
            .order_by(Country.weight.desc())
            .all()
        )
        lines = ["## WASI Countries (16 nations, index weights)"]
        for c in countries:
            lines.append(f"- {c.name} ({c.code}): {c.tier} tier, weight {c.weight * 100:.1f}%")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


_SYSTEM_PROMPT_EN = (
    "You are the WASI Intelligence Assistant for the West African Shipping & "
    "Economic Intelligence platform.\n\n"
    "WASI tracks 16 ECOWAS countries: NG(28%), CI(22%), GH(15%), SN(10%), "
    "BF(4%), ML(4%), GN(4%), BJ(3%), TG(3%), "
    "NE(1%), MR(1%), GW(1%), SL(1%), LR(1%), GM(1%), CV(1%).\n\n"
    "WASI Index formula: Shipping 40% + Trade 30% + Infrastructure 20% + Economic 10%.\n\n"
    "Stock exchanges covered: NGX (Nigeria, 28%), GSE (Ghana, 15%), "
    "BRVM (Côte d'Ivoire/Senegal/Benin/Togo, 34%) — combined 77% of WASI weight.\n\n"
    "Divergence signals: positive divergence = market outrunning fundamentals (overvaluation); "
    "negative = market lagging fundamentals (undervaluation opportunity).\n\n"
    "STRICT RULES:\n"
    "- Use ONLY the data in the <wasi_data> block. Never invent or hallucinate values.\n"
    "- Answer directly and confidently when data is present.\n"
    "- T5: After your answer, add a '**Sources cited:**' section listing every specific "
    "figure you used, e.g. '- Nigeria exports to CH: $320M (UN Comtrade estimate, 2022)'.\n"
    "- Format responses as a WASI Intelligence Briefing with clear markdown headers.\n"
    "- All trade figures are 2022 annual estimates (UN Comtrade / World Bank WITS).\n"
    "- If requested data is absent, say so clearly and direct the user to the REST API.\n"
)

# W5: French system prompt — same rules, Francophone framing
_SYSTEM_PROMPT_FR = (
    "Vous êtes l'Assistant Intelligence WASI pour la plateforme d'Intelligence "
    "du Transport Maritime et Économique Ouest-Africain.\n\n"
    "WASI suit 16 pays CEDEAO : NG(28%), CI(22%), GH(15%), SN(10%), "
    "BF(4%), ML(4%), GN(4%), BJ(3%), TG(3%), "
    "NE(1%), MR(1%), GW(1%), SL(1%), LR(1%), GM(1%), CV(1%).\n\n"
    "Formule de l'indice WASI : Transport maritime 40% + Commerce 30% + Infrastructure 20% + Économie 10%.\n\n"
    "Bourses couvertes : NGX (Nigeria, 28%), GSE (Ghana, 15%), "
    "BRVM (Côte d'Ivoire/Sénégal/Bénin/Togo, 34%) — 77% du poids WASI combiné.\n\n"
    "Signaux de divergence : divergence positive = marché devançant les fondamentaux (surévaluation) ; "
    "négative = marché en retard sur les fondamentaux (opportunité de sous-évaluation).\n\n"
    "RÈGLES STRICTES :\n"
    "- Utilisez UNIQUEMENT les données dans le bloc <wasi_data>. Ne jamais inventer de valeurs.\n"
    "- Répondez directement et avec confiance lorsque les données sont présentes.\n"
    "- T5: Après votre réponse, ajoutez une section '**Sources citées :**' listant chaque "
    "chiffre utilisé, ex. '- Exportations Nigeria vers CH : 320M$ (estimation UN Comtrade, 2022)'.\n"
    "- Formatez les réponses comme un Briefing Intelligence WASI avec des titres markdown clairs.\n"
    "- Toutes les données commerciales sont des estimations annuelles 2022 (UN Comtrade / WITS).\n"
    "- Si les données demandées sont absentes, dites-le clairement et orientez vers l'API REST.\n"
    "- Répondez en français.\n"
)


def _get_system_prompt(language: str) -> str:
    return _SYSTEM_PROMPT_FR if language.lower().startswith("fr") else _SYSTEM_PROMPT_EN


def _grounding_score(context: str, answer: str) -> float:
    """
    T5: Estimate how much of the answer is grounded in retrieved data.
    Heuristic: count numeric values in answer that also appear in the context.
    Returns 0.0 – 1.0.
    """
    import re
    # Extract numbers from both context and answer
    ctx_nums  = set(re.findall(r"\d[\d,\.]+", context))
    ans_nums  = re.findall(r"\d[\d,\.]+", answer)
    if not ans_nums:
        # No numbers in answer — check for key noun overlap instead
        ctx_words = set(context.lower().split())
        ans_words = answer.lower().split()
        overlap = sum(1 for w in ans_words if len(w) > 5 and w in ctx_words)
        return min(1.0, round(overlap / max(len(ans_words), 1) * 3, 2))
    matched = sum(1 for n in ans_nums if n in ctx_nums)
    return min(1.0, round(matched / len(ans_nums), 2))


# ── Intelligence endpoint (RAG) ───────────────────────────────────────────────

@router.post("/intelligence")
async def intelligence_chat(
    request: Request,
    payload: IntelligenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    RAG-enhanced: retrieves live WASI data, then asks Claude for a grounded answer.
    Costs 2 credits.
    """
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Chat service not available.")

    # Security: prompt injection check on user question
    _check_injection(payload.question)

    # Security: enforce model whitelist
    safe_model = _validate_model(payload.model)

    deduct_credits(current_user, db, "/api/chat/intelligence", cost_multiplier=2.0)

    context = _build_context(payload.question, db)
    system_with_data = (
        _get_system_prompt(payload.language)
        + "\n\n<wasi_data>\n"
        + context
        + "\n</wasi_data>"
    )

    body = {
        "model": safe_model,
        "max_tokens": min(payload.max_tokens, MAX_TOKENS_CAP),
        "system": system_with_data,
        "messages": [{"role": "user", "content": payload.question}],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json=body,
            )
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail="Chat service temporarily unavailable")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Chat service returned an error")

    # T5: compute grounding score and inject into response metadata
    result = resp.json()
    answer_text = ""
    try:
        answer_text = result["content"][0]["text"]
        # Append financial disclaimer
        result["content"][0]["text"] += _DISCLAIMER
    except (KeyError, IndexError):
        logger.warning("Intelligence response missing expected content structure; disclaimer not appended")

    result["wasi_metadata"] = {
        "grounding_score": _grounding_score(context, answer_text),
        "language": payload.language,
        "context_sections": len(context.split("\n\n## ")),
        "data_retrieved": bool(context),
    }
    return result
