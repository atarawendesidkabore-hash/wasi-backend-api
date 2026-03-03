"""
WASI Auth Tokens — Refresh Token + Blacklist Tests

Tests the refresh token rotation, access token blacklisting (logout),
replay detection, backward compatibility, and admin session revocation.
"""
import jwt
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from src.main import app
from src.database.models import User, RefreshToken
from src.utils.security import hash_refresh_token
from src.config import settings
from tests.conftest import TestingSessionLocal

client = TestClient(app, raise_server_exceptions=False)


# ── Helpers ──────────────────────────────────────────────────────

def _register_and_login(username="authuser", email="auth@test.com", password="AuthPass1"):
    """Register + login, return full response dict."""
    client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(username):
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == username).first()
    uid = user.id
    db.close()
    return uid


# ── Test 1: Login returns refresh token ─────────────────────────

def test_login_returns_refresh_token():
    data = _register_and_login()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


# ── Test 2: Access token contains jti ───────────────────────────

def test_access_token_has_jti():
    data = _register_and_login(username="jtiuser", email="jti@test.com")
    decoded = jwt.decode(
        data["access_token"],
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert "jti" in decoded
    assert len(decoded["jti"]) == 36  # UUID format


# ── Test 3: Refresh exchange returns new pair ───────────────────

def test_refresh_returns_new_pair():
    data = _register_and_login(username="ref1", email="ref1@test.com")
    resp = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200
    new_data = resp.json()
    assert new_data["access_token"] != data["access_token"]
    assert new_data["refresh_token"] != data["refresh_token"]
    # New access token works
    me = client.get("/api/auth/me", headers=_auth_header(new_data["access_token"]))
    assert me.status_code == 200


# ── Test 4: Old refresh token invalid after rotation ────────────

def test_old_refresh_invalid_after_rotation():
    data = _register_and_login(username="rot1", email="rot1@test.com")
    old_refresh = data["refresh_token"]
    # Rotate
    client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    # Try old token again — should be revoked
    resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401


# ── Test 5: Replay detection revokes all sessions ──────────────

def test_replay_detection_revokes_all():
    data = _register_and_login(username="replay1", email="replay1@test.com")
    old_refresh = data["refresh_token"]
    # Rotate to get new token
    new_data = client.post(
        "/api/auth/refresh", json={"refresh_token": old_refresh}
    ).json()
    # Replay old token — triggers full revocation
    resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401
    assert "reuse" in resp.json()["detail"].lower()
    # Even the new refresh token should now be revoked
    resp2 = client.post("/api/auth/refresh", json={"refresh_token": new_data["refresh_token"]})
    assert resp2.status_code == 401


# ── Test 6: Expired refresh token rejected ──────────────────────

def test_expired_refresh_token():
    data = _register_and_login(username="exp1", email="exp1@test.com")
    # Manually expire the token in DB
    db = TestingSessionLocal()
    token_hash = hash_refresh_token(data["refresh_token"])
    db_token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    db_token.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    db.commit()
    db.close()
    # Try to use it
    resp = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


# ── Test 7: Logout blacklists access token ──────────────────────

def test_logout_blacklists_access_token():
    data = _register_and_login(username="logout1", email="logout1@test.com")
    # Verify token works
    assert client.get("/api/auth/me", headers=_auth_header(data["access_token"])).status_code == 200
    # Logout
    resp = client.post(
        "/api/auth/logout",
        json={"refresh_token": data["refresh_token"]},
        headers=_auth_header(data["access_token"]),
    )
    assert resp.status_code == 200
    # Token should now be rejected
    me = client.get("/api/auth/me", headers=_auth_header(data["access_token"]))
    assert me.status_code == 401


# ── Test 8: Logout without refresh token still works ────────────

def test_logout_without_refresh_token():
    data = _register_and_login(username="logout2", email="logout2@test.com")
    resp = client.post(
        "/api/auth/logout",
        json={},
        headers=_auth_header(data["access_token"]),
    )
    assert resp.status_code == 200


# ── Test 9: Invalid refresh token returns 401 ──────────────────

def test_invalid_refresh_token():
    resp = client.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 401


# ── Test 10: Backward compat — old tokens without jti ──────────

def test_old_token_without_jti_still_works():
    """Tokens minted before the jti change should still be accepted."""
    _register_and_login(username="oldtok", email="oldtok@test.com")
    # Manually create a token without jti
    old_payload = {
        "sub": str(_get_user_id("oldtok")),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "iat": datetime.now(timezone.utc),
    }
    old_token = jwt.encode(old_payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    me = client.get("/api/auth/me", headers=_auth_header(old_token))
    assert me.status_code == 200


# ── Test 11: Admin revoke all sessions ──────────────────────────

def test_admin_revoke_sessions():
    # Create admin
    _register_and_login(username="superadm", email="superadm@test.com")
    db = TestingSessionLocal()
    admin = db.query(User).filter(User.username == "superadm").first()
    admin.is_admin = True
    db.commit()
    db.close()
    admin_resp = client.post(
        "/api/auth/login",
        data={"username": "superadm", "password": "AuthPass1"},
    )
    admin_token = admin_resp.json()["access_token"]

    # Create target user with a session
    target_data = _register_and_login(username="target1", email="target1@test.com")
    target_id = _get_user_id("target1")

    # Admin revokes
    resp = client.post(
        f"/api/auth/admin/revoke-sessions/{target_id}",
        headers=_auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["revoked_count"] >= 1

    # Target's refresh token should now be invalid
    resp2 = client.post(
        "/api/auth/refresh",
        json={"refresh_token": target_data["refresh_token"]},
    )
    assert resp2.status_code == 401


# ── Test 12: Inactive user cannot refresh ───────────────────────

def test_inactive_user_cannot_refresh():
    data = _register_and_login(username="inactive1", email="inactive1@test.com")
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == "inactive1").first()
    user.is_active = False
    db.commit()
    db.close()
    resp = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 401


# ── Test 13: Login response backward compatibility ─────────────

def test_login_response_backward_compatible():
    data = _register_and_login(username="compat1", email="compat1@test.com")
    # All original fields still present (TokenResponse superset)
    assert "access_token" in data
    assert "token_type" in data
    assert "expires_in" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["expires_in"], int)
