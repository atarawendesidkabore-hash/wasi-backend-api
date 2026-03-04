"""
Pagination utility + endpoint integration tests.

Tests the PaginationParams dependency, the paginate() helper, and
verifies that paginated endpoints return the correct response shape.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.utils.pagination import PaginationParams, paginate

client = TestClient(app, raise_server_exceptions=False)


# ── Helper: register + login, return Authorization header ───────────────────

def _auth_header(username="pag_user", email="pag@test.com"):
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "TestPass123"},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": "TestPass123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Unit tests: PaginationParams ────────────────────────────────────────────

def test_default_pagination_params():
    """Default page=1, page_size=50."""
    p = PaginationParams(page=1, page_size=50)
    assert p.page == 1
    assert p.page_size == 50
    assert p.offset == 0


def test_custom_pagination_params():
    """Custom page/page_size produces correct offset."""
    p = PaginationParams(page=3, page_size=20)
    assert p.page == 3
    assert p.page_size == 20
    assert p.offset == 40  # (3-1) * 20


# ── Unit tests: paginate() helper ──────────────────────────────────────────

class _FakeQuery:
    """Minimal mock of a SQLAlchemy query for testing paginate()."""

    def __init__(self, items: list):
        self._items = items

    def count(self):
        return len(self._items)

    def offset(self, n):
        self._offset = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def all(self):
        start = getattr(self, "_offset", 0)
        end = start + getattr(self, "_limit", len(self._items))
        return self._items[start:end]


def test_paginate_empty():
    """Empty query returns correct shape with zero items."""
    result = paginate(_FakeQuery([]), PaginationParams(page=1, page_size=50))
    assert result["items"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["pages"] == 1
    assert result["has_next"] is False
    assert result["has_prev"] is False


def test_paginate_has_next():
    """has_next is True when more pages exist."""
    items = list(range(75))
    result = paginate(_FakeQuery(items), PaginationParams(page=1, page_size=50))
    assert result["total"] == 75
    assert result["pages"] == 2
    assert result["has_next"] is True
    assert result["has_prev"] is False
    assert len(result["items"]) == 50


def test_paginate_has_prev():
    """has_prev is True on page 2+."""
    items = list(range(75))
    result = paginate(_FakeQuery(items), PaginationParams(page=2, page_size=50))
    assert result["has_prev"] is True
    assert result["has_next"] is False
    assert len(result["items"]) == 25


def test_paginate_total_matches():
    """Total count matches actual data regardless of page_size."""
    items = list(range(123))
    result = paginate(_FakeQuery(items), PaginationParams(page=1, page_size=10))
    assert result["total"] == 123
    assert result["pages"] == 13


# ── Integration: page_size max enforced (>200 rejected) ────────────────────

def test_page_size_max_enforced():
    """page_size > 200 is rejected by FastAPI validation."""
    headers = _auth_header("pag_max", "pag_max@test.com")
    resp = client.get("/api/indices/history?page_size=201", headers=headers)
    assert resp.status_code == 422  # validation error


# ── Integration: paginated endpoint returns correct shape ───────────────────

def test_paginated_endpoint_response_shape():
    """A paginated endpoint returns {items, total, page, page_size, pages, has_next, has_prev}."""
    headers = _auth_header("pag_shape", "pag_shape@test.com")
    resp = client.get("/api/indices/history?page=1&page_size=10", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data
    assert "has_next" in data
    assert "has_prev" in data
    assert isinstance(data["items"], list)
    assert data["page"] == 1
    assert data["page_size"] == 10
