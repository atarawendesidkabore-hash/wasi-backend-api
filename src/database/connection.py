from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from typing import Generator
from src.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from src.database.models import Base  # deferred to avoid circular import
    import src.database.ussd_models  # noqa: register USSD tables with Base metadata
    import src.database.cbdc_models  # noqa: register eCFA CBDC tables with Base metadata
    import src.database.cbdc_payment_models  # noqa: register cross-border payment tables
    import src.database.forecast_models  # noqa: register forecast tables
    import src.database.tokenization_models  # noqa: register tokenization tables
    import src.database.valuation_models  # noqa: register DCF valuation tables
    import src.database.legislative_models  # noqa: register legislative monitoring tables
    import src.database.fx_models  # noqa: register FX analytics tables
    import src.database.corridor_models  # noqa: register trade corridor tables
    import src.database.alert_models  # noqa: register alert/webhook tables
    import src.database.reconciliation_models  # noqa: register data integrity tables
    import src.database.world_news_models  # noqa: register world news intelligence tables
    Base.metadata.create_all(bind=engine)
