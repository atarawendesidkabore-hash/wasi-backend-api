import os
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./wasi.db"
    SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BLACKLIST_CLEANUP_INTERVAL_MINUTES: int = 30
    DEFAULT_QUERY_COST: float = 1.0
    FREE_TIER_BALANCE: float = 10.0
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8000",
    ]
    SCHEDULER_ENABLED: bool = True
    COMPOSITE_UPDATE_INTERVAL_HOURS: int = 6
    ANTHROPIC_API_KEY: str = ""
    ACLED_API_KEY: str = ""          # Register free at acleddata.com
    ACLED_EMAIL: str = ""            # Email used for ACLED registration
    COMTRADE_API_KEY: str = ""       # UN Comtrade subscription key (optional)
    SKIP_SCRAPERS: bool = False      # Skip external API scrapers on startup (fast local dev)
    LIGHT_STARTUP: bool = False      # Skip all seeding/bootstrap — just init_db (for free-tier hosting)
    FORECAST_ENGINE_VERSION: int = 2  # 1 = v1 only (/api/v3/), 2 = v1+v2 (/api/v3/ + /api/v4/)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Render provides postgres:// but SQLAlchemy needs postgresql://
_raw_url = os.environ.get("DATABASE_URL", "")
if _raw_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = _raw_url.replace("postgres://", "postgresql://", 1)

settings = Settings()

# Guard: refuse to start without an explicit SECRET_KEY
if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "FATAL: SECRET_KEY is missing or too short (min 32 chars). "
        "Set a cryptographically random SECRET_KEY in your .env file:\n"
        "  python -c \"import secrets; print(secrets.token_urlsafe(64))\" "
    )

# Production guard: refuse wildcard CORS with credentials (credential theft risk)
if not settings.DEBUG and "*" in settings.CORS_ORIGINS:
    raise RuntimeError(
        "FATAL: CORS_ORIGINS contains '*' in production. "
        "Wildcard CORS with allow_credentials=True allows any website to "
        "make authenticated API calls. Set explicit origins in CORS_ORIGINS."
    )
