import os
import warnings
from pydantic_settings import BaseSettings
from typing import List

_DEFAULT_SECRET_KEY = "wasi-dev-secret-key-change-in-production"


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./wasi.db"
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DEFAULT_QUERY_COST: float = 1.0
    FREE_TIER_BALANCE: float = 10.0
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    SCHEDULER_ENABLED: bool = True
    COMPOSITE_UPDATE_INTERVAL_HOURS: int = 6
    ANTHROPIC_API_KEY: str = ""
    ACLED_API_KEY: str = ""          # Register free at acleddata.com
    ACLED_EMAIL: str = ""            # Email used for ACLED registration
    COMTRADE_API_KEY: str = ""       # UN Comtrade subscription key (optional)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Render provides postgres:// but SQLAlchemy needs postgresql://
_raw_url = os.environ.get("DATABASE_URL", "")
if _raw_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = _raw_url.replace("postgres://", "postgresql://", 1)

settings = Settings()

# Production guard: refuse to start with the default placeholder secret key
if not settings.DEBUG and settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
    raise RuntimeError(
        "FATAL: SECRET_KEY is still the default placeholder. "
        "Set a cryptographically random SECRET_KEY in your .env or environment "
        "before running in production (DEBUG=False)."
    )
if settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
    warnings.warn(
        "Using default SECRET_KEY — acceptable for local development only. "
        "Set a strong SECRET_KEY before deploying.",
        stacklevel=1,
    )
