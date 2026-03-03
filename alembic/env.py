"""Alembic environment — wired to WASI models and DATABASE_URL."""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Import all models so Base.metadata knows every table ─────────
from src.database.models import Base
import src.database.ussd_models           # noqa
import src.database.cbdc_models           # noqa
import src.database.cbdc_payment_models   # noqa
import src.database.forecast_models       # noqa
import src.database.tokenization_models   # noqa
import src.database.valuation_models      # noqa
import src.database.legislative_models    # noqa
import src.database.fx_models             # noqa
import src.database.corridor_models       # noqa

target_metadata = Base.metadata

# ── Alembic config ───────────────────────────────────────────────
config = context.config

# Override sqlalchemy.url with DATABASE_URL env var when available
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    # Render provides postgres:// but SQLAlchemy needs postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
