"""
Tests for the scraper resilience utility (retry + circuit breaker).
"""
import time
from unittest.mock import patch, MagicMock

import requests

from src.pipelines.scrapers.resilience import (
    resilient_get,
    get_circuit_status,
    _scraper_state,
    _state_lock,
    CIRCUIT_FAILURE_THRESHOLD,
)


def _reset_state():
    """Clear module-level state between tests."""
    with _state_lock:
        _scraper_state.clear()


def test_successful_request():
    """resilient_get returns response on first attempt success."""
    _reset_state()
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    with patch("src.pipelines.scrapers.resilience.requests.get", return_value=mock_resp):
        resp = resilient_get("test_ok", "http://example.com/api")

    assert resp is not None
    assert resp.status_code == 200
    status = get_circuit_status()
    assert status["test_ok"]["consecutive_failures"] == 0
    assert status["test_ok"]["last_success"] is not None


def test_retry_on_failure_then_success():
    """resilient_get retries and succeeds on second attempt."""
    _reset_state()
    fail_resp = MagicMock(spec=requests.Response)
    fail_resp.raise_for_status.side_effect = requests.HTTPError("500")

    ok_resp = MagicMock(spec=requests.Response)
    ok_resp.status_code = 200
    ok_resp.raise_for_status = MagicMock()

    with patch("src.pipelines.scrapers.resilience.requests.get", side_effect=[fail_resp, ok_resp]):
        with patch("src.pipelines.scrapers.resilience.time.sleep"):
            resp = resilient_get("test_retry", "http://example.com/api", max_retries=2)

    assert resp is not None
    assert resp.status_code == 200
    status = get_circuit_status()
    assert status["test_retry"]["consecutive_failures"] == 0


def test_all_retries_exhausted():
    """resilient_get returns None when all retries fail."""
    _reset_state()
    fail_resp = MagicMock(spec=requests.Response)
    fail_resp.raise_for_status.side_effect = requests.HTTPError("503")

    with patch("src.pipelines.scrapers.resilience.requests.get", return_value=fail_resp):
        with patch("src.pipelines.scrapers.resilience.time.sleep"):
            resp = resilient_get("test_exhaust", "http://example.com/api", max_retries=3)

    assert resp is None
    status = get_circuit_status()
    assert status["test_exhaust"]["consecutive_failures"] == 1
    assert status["test_exhaust"]["total_failures"] == 1


def test_circuit_breaker_opens_after_threshold():
    """Circuit breaker opens after CIRCUIT_FAILURE_THRESHOLD consecutive failures."""
    _reset_state()
    fail_resp = MagicMock(spec=requests.Response)
    fail_resp.raise_for_status.side_effect = requests.ConnectionError("refused")

    with patch("src.pipelines.scrapers.resilience.requests.get", return_value=fail_resp):
        with patch("src.pipelines.scrapers.resilience.time.sleep"):
            for _ in range(CIRCUIT_FAILURE_THRESHOLD):
                resilient_get("test_circuit", "http://example.com/api", max_retries=1)

    status = get_circuit_status()
    assert status["test_circuit"]["circuit_open"] is True
    assert status["test_circuit"]["consecutive_failures"] == CIRCUIT_FAILURE_THRESHOLD


def test_circuit_open_skips_request():
    """When circuit is open, resilient_get returns None without making HTTP call."""
    _reset_state()
    fail_resp = MagicMock(spec=requests.Response)
    fail_resp.raise_for_status.side_effect = requests.ConnectionError("refused")

    with patch("src.pipelines.scrapers.resilience.requests.get", return_value=fail_resp) as mock_get:
        with patch("src.pipelines.scrapers.resilience.time.sleep"):
            # Open the circuit
            for _ in range(CIRCUIT_FAILURE_THRESHOLD):
                resilient_get("test_skip", "http://example.com/api", max_retries=1)

            call_count_after_open = mock_get.call_count

            # This should be skipped — no HTTP call
            resp = resilient_get("test_skip", "http://example.com/api", max_retries=1)

    assert resp is None
    assert mock_get.call_count == call_count_after_open  # No new calls


def test_get_circuit_status_empty():
    """get_circuit_status returns empty dict when no scrapers have been called."""
    _reset_state()
    status = get_circuit_status()
    assert status == {}


def test_connection_timeout_triggers_retry():
    """Connection timeouts trigger retries."""
    _reset_state()
    with patch(
        "src.pipelines.scrapers.resilience.requests.get",
        side_effect=requests.ConnectionError("timeout"),
    ):
        with patch("src.pipelines.scrapers.resilience.time.sleep"):
            resp = resilient_get("test_timeout", "http://example.com/api", max_retries=2)

    assert resp is None
    status = get_circuit_status()
    assert status["test_timeout"]["consecutive_failures"] == 1
