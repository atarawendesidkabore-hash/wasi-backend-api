from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User
from src.utils.security import create_access_token, decode_access_token, get_current_user, hash_password

router = APIRouter(tags=["WASI Core"])

DEMO_IDENTITIES = [
    {
        "accessCode": "CORE-ADMIN",
        "username": "wasi-admin",
        "email": "wasi-admin@wasi.local",
        "password": "WasiCore!2026",
        "displayName": "WASI Admin",
        "roleLabel": "Administration",
        "organization": "WASI Core",
        "tier": "admin",
        "isAdmin": True,
    },
    {
        "accessCode": "CORE-ANALYST",
        "username": "wasi-analyst",
        "email": "wasi-analyst@wasi.local",
        "password": "WasiCore!2026",
        "displayName": "Analyste WASI",
        "roleLabel": "Analyse",
        "organization": "WASI Intelligence",
        "tier": "analyst",
        "isAdmin": False,
    },
    {
        "accessCode": "CORE-INVESTOR",
        "username": "wasi-investor",
        "email": "wasi-investor@wasi.local",
        "password": "WasiCore!2026",
        "displayName": "Investisseur WASI",
        "roleLabel": "Investisseur",
        "organization": "WASI DEX",
        "tier": "investor",
        "isAdmin": False,
    },
    {
        "accessCode": "CORE-MFI",
        "username": "wasi-microfinance",
        "email": "wasi-microfinance@wasi.local",
        "password": "WasiCore!2026",
        "displayName": "Operateur Microfinance",
        "roleLabel": "Operation",
        "organization": "CIREX",
        "tier": "microfinance",
        "isAdmin": False,
    },
    {
        "accessCode": "CORE-ISSUER",
        "username": "wasi-issuer",
        "email": "wasi-issuer@wasi.local",
        "password": "WasiCore!2026",
        "displayName": "Emetteur WASI",
        "roleLabel": "Emetteur",
        "organization": "WASI Private Market",
        "tier": "issuer",
        "isAdmin": False,
    },
]

DEMO_BY_CODE = {entry["accessCode"]: entry for entry in DEMO_IDENTITIES}
DEMO_BY_USERNAME = {entry["username"]: entry for entry in DEMO_IDENTITIES}

MARKET_SUMMARY = {
    "familyName": "AFEX Africa",
    "packageName": "WASI Market Intelligence Pack",
    "countryCount": 55,
    "subfamilyCount": 14,
    "generatedOn": "2026-03-30T09:00:00Z",
    "regions": [
        {"code": "NORD", "name": "Afrique du Nord", "countryCount": 6},
        {"code": "OUEST", "name": "Afrique de l'Ouest", "countryCount": 16},
        {"code": "CENTRE", "name": "Afrique centrale", "countryCount": 9},
        {"code": "EST", "name": "Afrique de l'Est", "countryCount": 14},
        {"code": "SUD", "name": "Afrique australe", "countryCount": 10},
    ],
}

CORE_MODULES = [
    {
        "title": "Intelligence",
        "status": "ACTIF",
        "summary": "Scoring pays, veille sectorielle et contexte reglementaire.",
        "audience": "Analystes",
        "sourceMode": "Hybride",
        "route": "/wasi-platform/index.html",
    },
    {
        "title": "DEX",
        "status": "ACTIF",
        "summary": "Marche prive, listings, fonds et suivi portefeuille.",
        "audience": "Investisseurs",
        "sourceMode": "Versionne",
        "route": "/wasidex/",
    },
    {
        "title": "Banking",
        "status": "ACTIF",
        "summary": "Operations, guardrails, export et supervision.",
        "audience": "Institutions",
        "sourceMode": "Transactionnel",
        "route": "/api/v1/banking/transactions/export",
    },
    {
        "title": "CIREX",
        "status": "ACTIF",
        "summary": "Controle credit, relation client et portes d'entree investissement.",
        "audience": "Microfinance",
        "sourceMode": "Local + IA",
        "route": "/wasidex/microfinance-app/",
    },
]

FUNDS = [
    {
        "ticker": "WASI-INDEX",
        "name": "Fonds Indiciel WASI Horizon",
        "category": "Fonds indiciel",
        "currency": "XOF",
        "nav": 10000,
        "changePct": 1.8,
        "focus": "Multi-pays Afrique",
    },
    {
        "ticker": "WASI-UEMOA",
        "name": "Champions UEMOA WASI",
        "category": "Fonds thematique",
        "currency": "XOF",
        "nav": 8500,
        "changePct": 1.1,
        "focus": "Consommation et logistique UEMOA",
    },
    {
        "ticker": "WASI-GROWTH",
        "name": "Panier Croissance PME WASI",
        "category": "Panier prive",
        "currency": "XOF",
        "nav": 12000,
        "changePct": 2.4,
        "focus": "Croissance PME",
    },
]

LISTINGS = [
    {
        "ticker": "CIREX-PS",
        "name": "Action Privee CIREX",
        "exchange": "WASI Private Market",
        "price": 12500,
        "currency": "XOF",
        "changePct": 2.3,
        "stage": "Cotation privee",
    },
    {
        "ticker": "AGRLINK",
        "name": "AgroLink Croissance",
        "exchange": "WASI Private Market",
        "price": 3200,
        "currency": "XOF",
        "changePct": 1.4,
        "stage": "Constitution du livre",
    },
    {
        "ticker": "SOLBRIDGE",
        "name": "SolarBridge PME",
        "exchange": "WASI Private Market",
        "price": 4750,
        "currency": "XOF",
        "changePct": 0.9,
        "stage": "Admission",
    },
    {
        "ticker": "KORALOG",
        "name": "Kora Logistics Hub",
        "exchange": "WASI Private Market",
        "price": 5400,
        "currency": "XOF",
        "changePct": -0.4,
        "stage": "Pre-admission",
    },
]

PORTFOLIOS = {
    "wasi-admin": [
        {"ticker": "CIREX-PS", "name": "Action Privee CIREX", "qty": 120, "pru": 11800, "current": 12500},
        {"ticker": "WASI-INDEX", "name": "Fonds Indiciel WASI Horizon", "qty": 90, "pru": 9600, "current": 10000},
    ],
    "wasi-analyst": [
        {"ticker": "WASI-UEMOA", "name": "Champions UEMOA WASI", "qty": 55, "pru": 8200, "current": 8500},
    ],
    "wasi-investor": [
        {"ticker": "CIREX-PS", "name": "Action Privee CIREX", "qty": 40, "pru": 12150, "current": 12500},
        {"ticker": "WASI-GROWTH", "name": "Panier Croissance PME WASI", "qty": 25, "pru": 11600, "current": 12000},
    ],
}

ALERTS = [
    {
        "id": "alt-001",
        "severity": "WARNING",
        "message": "Revue manuelle requise sur les regles d'acces au marche prive.",
        "alert_type": "COMPLIANCE",
        "created_at_utc": "2026-03-30T07:30:00Z",
        "acknowledged": False,
    },
    {
        "id": "alt-002",
        "severity": "INFO",
        "message": "Le snapshot AFEX a ete regenere pour la session du jour.",
        "alert_type": "DATA",
        "created_at_utc": "2026-03-30T08:05:00Z",
        "acknowledged": False,
    },
]

AUDIT_LOG = [
    {
        "created_at_utc": "2026-03-30T07:15:00Z",
        "action": "CORE_BOOTSTRAP",
        "status": "SUCCESS",
        "actor_username": "system",
        "detail_json": json.dumps({"module": "wasi_core", "message": "bootstrap charge"}),
    },
    {
        "created_at_utc": "2026-03-30T07:45:00Z",
        "action": "SOURCE_REFRESH",
        "status": "SUCCESS",
        "actor_username": "system",
        "detail_json": json.dumps({"source": "afex", "mode": "scheduled"}),
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _find_demo_identity(value: str) -> dict | None:
    return DEMO_BY_CODE.get(value) or DEMO_BY_USERNAME.get(value)


def _display_name_for_user(user: User) -> str:
    demo = DEMO_BY_USERNAME.get(user.username)
    if demo:
        return demo["displayName"]
    return user.username.replace("-", " ").title()


def _organization_for_user(user: User) -> str:
    demo = DEMO_BY_USERNAME.get(user.username)
    if demo:
        return demo["organization"]
    return "WASI"


def _role_label_for_user(user: User) -> str:
    demo = DEMO_BY_USERNAME.get(user.username)
    if demo:
        return demo["roleLabel"]
    if user.is_admin:
        return "Administration"
    if user.tier == "microfinance":
        return "Operation"
    if user.tier == "analyst":
        return "Analyse"
    if user.tier == "issuer":
        return "Emetteur"
    return "Investisseur"


def _admin_role_for_user(user: User) -> str:
    if user.is_admin or user.tier in {"admin", "issuer", "institution"}:
        return "MANAGER"
    if user.tier in {"microfinance", "operator", "teller"}:
        return "TELLER"
    return "CLIENT"


def _optional_current_user(request: Request, db: Session) -> User | None:
    raw = request.headers.get("authorization", "")
    match = re.match(r"^Bearer\\s+(.+)$", raw, re.IGNORECASE)
    if not match:
        return None
    token = match.group(1)
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id), User.is_active == True).first()


def _session_payload(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "displayName": _display_name_for_user(user),
            "roleLabel": _role_label_for_user(user),
            "organization": _organization_for_user(user),
        },
        "tokenExpiresAt": (_utcnow() + timedelta(minutes=60)).isoformat(),
    }


def _bootstrap_payload(user: User | None, db: Session) -> dict:
    return {
        "database": {
            "path": "Render PostgreSQL",
            "engine": "postgresql",
        },
        "session": _session_payload(user),
        "source": {
            "refreshRequired": False,
            "lastRefreshAt": "2026-03-30T08:05:00Z",
            "sourceError": None,
        },
        "audit": {
            "total": len(AUDIT_LOG),
        },
        "market": MARKET_SUMMARY,
        "modules": CORE_MODULES,
        "demoUsers": [
            {
                "accessCode": identity["accessCode"],
                "displayName": identity["displayName"],
                "roleLabel": identity["roleLabel"],
                "organization": identity["organization"],
            }
            for identity in DEMO_IDENTITIES
        ],
        "counts": {
            "users": db.query(User).count(),
            "alerts": sum(1 for alert in ALERTS if not alert["acknowledged"]),
            "funds": len(FUNDS),
            "listings": len(LISTINGS),
        },
    }


def _ensure_demo_user(identity: dict, db: Session) -> User:
    user = db.query(User).filter(User.username == identity["username"]).first()
    if not user:
        user = User(
            username=identity["username"],
            email=identity["email"],
            hashed_password=hash_password(identity["password"]),
            x402_balance=2500,
            tier=identity["tier"],
            is_active=True,
            is_admin=identity["isAdmin"],
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    updated = False
    if user.email != identity["email"]:
        user.email = identity["email"]
        updated = True
    if user.tier != identity["tier"]:
        user.tier = identity["tier"]
        updated = True
    if user.is_admin != identity["isAdmin"]:
        user.is_admin = identity["isAdmin"]
        updated = True
    if not user.is_active:
        user.is_active = True
        updated = True
    if updated:
        db.commit()
        db.refresh(user)
    return user


def _record_audit(action: str, status: str, actor_username: str, detail: dict) -> None:
    AUDIT_LOG.insert(
        0,
        {
            "created_at_utc": _utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "action": action,
            "status": status,
            "actor_username": actor_username,
            "detail_json": json.dumps(detail),
        },
    )
    del AUDIT_LOG[100:]


def _serialized_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": _admin_role_for_user(user),
        "tier": user.tier,
        "display_name": _display_name_for_user(user),
        "organization": _organization_for_user(user),
        "is_active": bool(user.is_active),
        "is_admin": bool(user.is_admin),
    }


def _portfolio_for_user(user: User | None) -> dict:
    holdings = PORTFOLIOS.get(user.username if user else "wasi-investor") or PORTFOLIOS["wasi-investor"]
    total_value = sum(item["qty"] * item["current"] for item in holdings)
    total_cost = sum(item["qty"] * item["pru"] for item in holdings)
    return {
        "owner": _display_name_for_user(user) if user else "Investisseur demo",
        "holdings": holdings,
        "totals": {
            "value": total_value,
            "cost": total_cost,
            "pnl": total_value - total_cost,
        },
    }


@router.get("/api/core/bootstrap")
async def core_bootstrap(request: Request, db: Session = Depends(get_db)):
    user = _optional_current_user(request, db)
    return _bootstrap_payload(user, db)


@router.post("/api/core/auth/demo-login")
async def core_demo_login(request: Request, db: Session = Depends(get_db)):
    payload = request.json if hasattr(request, "json") else None
    body = await request.json()
    access_code = str(body.get("accessCode", "")).strip()
    identity = _find_demo_identity(access_code)
    if not identity:
        raise HTTPException(status_code=401, detail="Code d'acces demo invalide.")
    user = _ensure_demo_user(identity, db)
    token = create_access_token({"sub": str(user.id)})
    _record_audit("DEMO_LOGIN", "SUCCESS", user.username, {"access_code": access_code})
    return {
        "token": token,
        "bootstrap": _bootstrap_payload(user, db),
    }


@router.get("/api/core/audit")
async def core_audit(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    del current_user
    entries = []
    for entry in AUDIT_LOG[:limit]:
        entries.append(
            {
                "action": entry["action"],
                "createdAt": entry["created_at_utc"],
                "actorName": entry["actor_username"],
                "actorRole": None,
                "entityType": "system",
                "entityId": None,
            }
        )
    return {"audit": entries}


@router.get("/api/v1/market/funds")
async def list_funds():
    return {"funds": FUNDS}


@router.get("/api/v1/stock-market/listings")
async def list_stock_market_listings():
    return {"listings": LISTINGS}


@router.get("/api/v1/stock-market/portfolio")
async def get_stock_market_portfolio(request: Request, db: Session = Depends(get_db)):
    user = _optional_current_user(request, db)
    return {"portfolio": _portfolio_for_user(user)}


@router.get("/api/v1/admin/audit/summary")
async def admin_audit_summary(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    last_24h_cutoff = _utcnow() - timedelta(hours=24)
    last_24h = 0
    failure_entries = []
    for entry in AUDIT_LOG:
        created = datetime.fromisoformat(entry["created_at_utc"].replace("Z", "+00:00"))
        if created >= last_24h_cutoff:
            last_24h += 1
        if entry["status"] != "SUCCESS":
            failure_entries.append(entry)
    return {
        "status": "healthy",
        "database": "healthy",
        "version": "3.1.0-core",
        "uptime": 3600,
        "counts": {"users": len(DEMO_IDENTITIES), "accounts": len(PORTFOLIOS), "transactions": 18},
        "unacknowledgedAlerts": sum(1 for alert in ALERTS if not alert["acknowledged"]),
        "totalEntries": len(AUDIT_LOG),
        "last24h": last_24h,
        "failureCount": len(failure_entries),
        "recentFailures": failure_entries[:8],
    }


@router.get("/api/v1/admin/audit/search")
async def admin_audit_search(
    action: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    filtered = AUDIT_LOG
    if action:
        filtered = [entry for entry in filtered if entry["action"] == action]
    if status:
        filtered = [entry for entry in filtered if entry["status"] == status]
    return {"entries": filtered[:limit]}


@router.get("/api/v1/admin/users")
async def admin_users(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    for identity in DEMO_IDENTITIES:
        _ensure_demo_user(identity, db)
    users = db.query(User).order_by(User.id.asc()).limit(limit).all()
    return {"users": [_serialized_user(user) for user in users]}


@router.post("/api/v1/admin/users/{user_id}/role")
async def admin_change_role(
    user_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    role = str(payload.get("role", "")).upper()
    if role not in {"CLIENT", "TELLER", "MANAGER"}:
        raise HTTPException(status_code=400, detail="Role invalide.")
    if role == "MANAGER":
        user.tier = "admin"
        user.is_admin = True
    elif role == "TELLER":
        user.tier = "microfinance"
        user.is_admin = False
    else:
        user.tier = "investor"
        user.is_admin = False
    db.commit()
    db.refresh(user)
    _record_audit("USER_ROLE_UPDATE", "SUCCESS", current_user.username, {"target_user_id": user_id, "role": role})
    return {"user": _serialized_user(user)}


@router.post("/api/v1/admin/users/{user_id}/status")
async def admin_change_status(
    user_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    user.is_active = bool(payload.get("is_active", True))
    db.commit()
    db.refresh(user)
    _record_audit("USER_STATUS_UPDATE", "SUCCESS", current_user.username, {"target_user_id": user_id, "is_active": user.is_active})
    return {"user": _serialized_user(user)}


@router.get("/api/v1/admin/alerts")
async def admin_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    return {"alerts": ALERTS[:limit]}


@router.post("/api/v1/admin/alerts/{alert_id}/acknowledge")
async def admin_acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    alert = next((entry for entry in ALERTS if entry["id"] == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    alert["acknowledged"] = True
    _record_audit("ALERT_ACKNOWLEDGE", "SUCCESS", current_user.username, {"alert_id": alert_id})
    return {"ok": True}


@router.get("/api/v1/banking/transactions/export")
async def export_transactions_csv(
    format: str = Query(default="csv"),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Privileges administrateur requis.")
    if format.lower() != "csv":
        raise HTTPException(status_code=400, detail="Seul le format csv est supporte.")
    rows = [
        ["date_utc", "module", "reference", "amount_xof", "status"],
        ["2026-03-30T08:00:00Z", "DEX", "ORD-9001", "750000", "SETTLED"],
        ["2026-03-30T08:25:00Z", "CIREX", "ORD-9002", "320000", "PENDING"],
        ["2026-03-30T08:40:00Z", "WASI FUND", "ORD-9003", "540000", "SETTLED"],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    _record_audit("TRANSACTION_EXPORT", "SUCCESS", current_user.username, {"format": "csv"})
    return PlainTextResponse(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="wasi_transactions.csv"'},
    )
