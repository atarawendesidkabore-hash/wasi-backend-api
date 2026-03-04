from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timezone, datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
from src.database.connection import get_db

router = APIRouter(tags=["Health"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/api/health")
@limiter.limit("60/minute")
async def health_check(request: Request, db: Session = Depends(get_db)):
    """Health check endpoint. Returns database connectivity status."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
