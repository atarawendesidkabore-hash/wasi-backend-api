"""
Scraper Resilience Utilities — retry with exponential backoff + circuit breaker.

Usage:
    from src.pipelines.scrapers.resilience import resilient_get, get_circuit_status

    # Instead of: resp = requests.get(url, timeout=30)
    # Use:        resp = resilient_get("worldbank", url, timeout=30)
    #             if resp is None: <circuit open or all retries failed>

    # Health dashboard:
    status = get_circuit_status()  # {"worldbank": {last_success: ..., failures: 0, ...}}
"""
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0          # 1s → 2s → 4s
JITTER_SECONDS = 0.5              # ±500ms
CIRCUIT_FAILURE_THRESHOLD = 3     # Open circuit after N consecutive failures
CIRCUIT_COOLDOWN_SECONDS = 1800   # 30 minutes

# ── Module State ───────────────────────────────────────────────────────────
_state_lock = threading.Lock()
_scraper_state: dict[str, dict] = {}


def _get_state(scraper_name: str) -> dict:
    """Get or initialize state for a named scraper."""
    with _state_lock:
        if scraper_name not in _scraper_state:
            _scraper_state[scraper_name] = {
                "consecutive_failures": 0,
                "circuit_open_until": None,
                "last_run": None,
                "last_success": None,
                "last_error": None,
                "total_calls": 0,
                "total_failures": 0,
            }
        return _scraper_state[scraper_name]


def _is_circuit_open(state: dict) -> bool:
    """Check if circuit breaker is currently open."""
    open_until = state.get("circuit_open_until")
    if open_until is None:
        return False
    now = datetime.now(timezone.utc)
    if now >= open_until:
        # Cooldown expired — half-open (allow one attempt)
        state["circuit_open_until"] = None
        state["consecutive_failures"] = 0
        logger.info("Circuit breaker reset (cooldown expired)")
        return False
    return True


def resilient_get(
    scraper_name: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    max_retries: int = MAX_RETRIES,
) -> Optional[requests.Response]:
    """
    HTTP GET with exponential backoff retry and circuit breaker.

    Returns requests.Response on success, None on failure (all retries
    exhausted or circuit open).

    Parameters
    ----------
    scraper_name : str
        Identifier for circuit breaker state (e.g., "worldbank", "imf")
    url : str
        Target URL
    params : dict, optional
        Query parameters
    headers : dict, optional
        HTTP headers
    timeout : float
        Request timeout in seconds (default 30)
    max_retries : int
        Maximum retry attempts (default 3)
    """
    state = _get_state(scraper_name)

    with _state_lock:
        state["last_run"] = datetime.now(timezone.utc).isoformat()
        state["total_calls"] += 1

    # Circuit breaker check
    if _is_circuit_open(state):
        logger.warning(
            "Circuit OPEN for %s — skipping request (cooldown until %s)",
            scraper_name, state["circuit_open_until"],
        )
        return None

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()

            # Success — reset failure counter
            with _state_lock:
                state["consecutive_failures"] = 0
                state["last_success"] = datetime.now(timezone.utc).isoformat()
                state["last_error"] = None

            return resp

        except (requests.RequestException, requests.HTTPError) as exc:
            last_exc = exc
            logger.warning(
                "%s attempt %d/%d failed: %s",
                scraper_name, attempt, max_retries, exc,
            )

            if attempt < max_retries:
                delay = BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                jitter = random.uniform(-JITTER_SECONDS, JITTER_SECONDS)
                sleep_time = max(0.1, delay + jitter)
                time.sleep(sleep_time)

    # All retries exhausted
    with _state_lock:
        state["consecutive_failures"] += 1
        state["total_failures"] += 1
        state["last_error"] = str(last_exc)

        if state["consecutive_failures"] >= CIRCUIT_FAILURE_THRESHOLD:
            open_until = datetime.now(timezone.utc)
            from datetime import timedelta
            open_until += timedelta(seconds=CIRCUIT_COOLDOWN_SECONDS)
            state["circuit_open_until"] = open_until
            logger.error(
                "Circuit OPEN for %s — %d consecutive failures, cooldown until %s",
                scraper_name, state["consecutive_failures"], open_until.isoformat(),
            )

    return None


def get_circuit_status() -> dict:
    """
    Return circuit breaker status for all scrapers.

    Used by /api/health/detailed to expose scraper health.
    """
    with _state_lock:
        result = {}
        now = datetime.now(timezone.utc)
        for name, state in _scraper_state.items():
            open_until = state.get("circuit_open_until")
            is_open = open_until is not None and now < open_until
            result[name] = {
                "last_run": state["last_run"],
                "last_success": state["last_success"],
                "consecutive_failures": state["consecutive_failures"],
                "circuit_open": is_open,
                "total_calls": state["total_calls"],
                "total_failures": state["total_failures"],
            }
        return result
