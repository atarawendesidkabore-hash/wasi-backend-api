"""
Test Suite — Global Error Handling + Request ID Tracing

Tests request ID middleware and global exception handler.
"""
import re
import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from src.main import app
from src.config import settings


# ── Test route that raises an unhandled exception ──────────────────
_error_router = APIRouter()


@_error_router.get("/api/test/crash")
async def crash_endpoint():
    """Deliberately raises an unhandled exception for testing."""
    raise RuntimeError("deliberate test crash")


# Register the test route once
app.include_router(_error_router)

client = TestClient(app, raise_server_exceptions=False)


# ── Tests ──────────────────────────────────────────────────────────

def test_response_has_request_id_header():
    """Every response should include an X-Request-ID header."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    # Should look like a UUID4
    assert re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        rid,
    )


def test_client_provided_request_id_is_echoed():
    """If the client sends X-Request-ID, the server should echo it back."""
    custom_id = "client-trace-abc-123"
    resp = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id


def test_unhandled_exception_returns_structured_json():
    """Unhandled exceptions should return JSON with 'error' and 'request_id'."""
    resp = client.get("/api/test/crash")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "Internal Server Error"
    assert "request_id" in body
    assert len(body["request_id"]) > 0


def test_error_request_id_matches_header():
    """The request_id in the error body should match the X-Request-ID header."""
    resp = client.get("/api/test/crash")
    assert resp.status_code == 500
    body = resp.json()
    header_rid = resp.headers.get("X-Request-ID")
    assert body["request_id"] == header_rid


def test_debug_mode_includes_traceback():
    """In DEBUG mode, error response should include detail and traceback."""
    original = settings.DEBUG
    try:
        settings.DEBUG = True
        resp = client.get("/api/test/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert "deliberate test crash" in body["detail"]
        assert "traceback" in body
        assert isinstance(body["traceback"], list)
        assert len(body["traceback"]) > 0
    finally:
        settings.DEBUG = original


def test_production_mode_hides_traceback():
    """In production mode, error response should NOT include detail or traceback."""
    original = settings.DEBUG
    try:
        settings.DEBUG = False
        resp = client.get("/api/test/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" not in body
        assert "traceback" not in body
        assert body["error"] == "Internal Server Error"
        assert "request_id" in body
    finally:
        settings.DEBUG = original


def test_request_id_in_log_output(caplog):
    """Request ID should appear in log output for traceability."""
    custom_id = "log-trace-xyz-789"
    with caplog.at_level(logging.INFO):
        resp = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    # The request logging middleware should include the request ID
    assert any(custom_id in record.message for record in caplog.records)


def test_http_exception_not_intercepted():
    """HTTPException (401, 404, etc.) should pass through normally, not be caught by the error handler."""
    # Hit a protected endpoint without auth — should get 401, not 500
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    # Should be FastAPI's normal error format, not our error handler
    assert "detail" in body
    assert body.get("error") != "Internal Server Error"
