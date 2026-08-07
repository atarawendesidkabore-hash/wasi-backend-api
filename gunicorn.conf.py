"""
Gunicorn configuration for WASI Backend API.

Sets GUNICORN_WORKER_INDEX so only worker 0 starts the APScheduler.
"""
import os

# Worker count (override via WEB_CONCURRENCY env var)
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
worker_class = "uvicorn.workers.UvicornWorker"
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
timeout = 120

# Track worker index for scheduler singleton
_worker_counter = {"value": 0}


def post_fork(server, worker):
    """Assign each worker a sequential index via environment variable."""
    os.environ["GUNICORN_WORKER_INDEX"] = str(_worker_counter["value"])
    worker.log.info("Worker PID %s assigned index %s", worker.pid, _worker_counter["value"])
    _worker_counter["value"] += 1
