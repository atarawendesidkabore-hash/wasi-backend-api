import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./wasi.db"
    SECRET_KEY: str = "wasi-dev-secret-key-change-in-production"
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
