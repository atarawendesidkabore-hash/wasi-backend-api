from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import User
from src.engines.demo_seed_engine import DemoSeedEngine
from src.utils.security import get_current_user

router = APIRouter(tags=["Demo"])

_DEMO_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "connected_demo.html"


@router.get("/app", response_class=HTMLResponse)
async def connected_app() -> str:
    return _DEMO_HTML_PATH.read_text(encoding="utf-8")


@router.post("/api/demo/bootstrap")
async def bootstrap_demo_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DemoSeedEngine.bootstrap(db, current_user)
