# ── WASI Backend API ─────────────────────────────────────────────
# Multi-stage build: slim Python image with gunicorn + uvicorn workers
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg2-binary
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# ── Dependencies ─────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Application code ─────────────────────────────────────────────
COPY src/ src/
COPY data/ data/
COPY alembic/ alembic/
COPY alembic.ini .

# ── Runtime ──────────────────────────────────────────────────────
EXPOSE 8000

# Run migrations then start gunicorn with uvicorn workers
CMD ["sh", "-c", "alembic upgrade head && gunicorn src.main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120"]
