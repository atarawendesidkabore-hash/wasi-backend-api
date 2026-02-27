from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from src.database.connection import get_db

router = APIRouter(tags=["Health"])


@router.get("/api/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint. Returns database connectivity status."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {exc}"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }
