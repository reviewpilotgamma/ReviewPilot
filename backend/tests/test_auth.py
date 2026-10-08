from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.core.config import reload_settings
from app.core.security import OAUTH_STATE_COOKIE, SESSION_COOKIE, decrypt_token, hash_password, verify_password
from app.models import User
from app.services import accounts
from tests.conftest import GITHUB_API, GITHUB_OAUTH

CSRF = {"X-Requested-With": "ReviewPilot"}


def _sign_in(client, username: str = "dev", password: str = "dev-pass-123"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password}, headers=CSRF)


def _mock_github(mock_http, login: str = "octo", gh_id: int = 4242):
    mock_http.post(f"{GITHUB_OAUTH}/login/oauth/access_token").respond(200, json={"access_token": "gho_abc"})
    mock_http.get(f"{GITHUB_API}/user").respond(
        200, json={"id": gh_id, "login": login, "avatar_url": "https://avatars/x", "email": None}
    )
    mock_http.get(f"{GITHUB_API}/user/emails").respond(
        200, json=[{"email": "o@example.com", "primary": True, "verified": True}]
    )


def _connect(client, mode: str = "install") -> str:
    response = client.get("/api/v1/auth/github/connect", params={"mode": mode}, follow_redirects=False)
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    state = parse_qs(location.query)["state"][0]
    assert client.cookies.get(OAUTH_STATE_COOKIE) == state
    return response.headers["location"]


# --------------------------------------------------------------------------- passwords
def test_password_hash_round_trip():
    stored = hash_password("s3cret")
    assert stored.startswith("scrypt$") and "s3cret" not in stored
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", None) and not verify_password("s3cret", "garbage")
    assert hash_password("s3cret") != stored  # random salt


# --------------------------------------------------------------------------- sign-in
def test_seeded_accounts_sign_in_with_roles(client):
    response = _sign_in(client)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "dev" and body["role"] == "dev" and body["is_admin"] is False
    assert body["github_linked"] is False and body["github_login"] is None
    set_cookie = ",".join(response.headers.get_list("set-cookie"))
    assert SESSION_COOKIE in set_cookie and "HttpOnly" in set_cookie and "samesite=lax" in set_cookie.lower()
    assert "password" not in response.text

    admin = _sign_in(client, "admin", "admin-pass-123").json()
    assert admin["role"] == "admin" and admin["is_admin"] is True
    assert client.get("/api/v1/auth/me").json()["username"] == "admin"


def test_sign_in_is_case_insensitive_on_username(client):
    assert _sign_in(client, "DEV").status_code == 200


@pytest.mark.parametrize("username,password", [("dev", "nope"), ("ghost", "dev-pass-123")])
def test_invalid_credentials_get_one_generic_error(client, username, password):
    response = _sign_in(client, username, password)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")


def test_sign_in_requires_csrf_header(client):
    response = client.post("/api/v1/auth/login", json={"username": "dev", "password": "dev-pass-123"})
    assert response.status_code == 403


def test_repeated_failures_are_throttled(client):
    for _ in range(accounts.MAX_FAILURES):
        assert _sign_in(client, "dev", "nope").status_code == 401
    blocked = _sign_in(client)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Too many attempts, try again later"


def test_old_github_only_users_cannot_sign_in(client, db, login):
    login("alice")
    client.cookies.clear()
    assert _sign_in(client, "alice", "anything").status_code == 401


def test_removed_login_routes(client):
    assert client.get("/api/v1/auth/login", follow_redirects=False).status_code == 405
    assert client.post("/api/v1/auth/dev-login", headers=CSRF).status_code == 404


# --------------------------------------------------------------------------- seeding
def test_seed_updates_role_and_password_and_keeps_rows(client, db, monkeypatch):
    accounts.seed_accounts(db, reload_settings())
    assert {u.username: u.role for u in db.scalars(select(User))} == {"dev": "dev", "admin": "admin"}

    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "rotated-pass")
    accounts.seed_accounts(db, reload_settings())
    assert len(db.scalars(select(User)).all()) == 2
    assert _sign_in(client, "admin", "admin-pass-123").status_code == 401
    assert _sign_in(client, "admin", "rotated-pass").status_code == 200


def test_dev_defaults_outside_production_only(db, monkeypatch):
    monkeypatch.setenv("SEED_DEV_PASSWORD", "")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "")
    accounts.seed_accounts(db, reload_settings())
    dev = db.scalar(select(User).where(User.username == "dev"))
    assert verify_password("dev12345", dev.password_hash)

    db.query(User).delete()
    db.commit()
    monkeypatch.setenv("ENV", "production")
    accounts.seed_accounts(db, reload_settings())
    assert db.scalars(select(User)).all() == []


def test_seed_converts_legacy_local_user(db):
    db.add(User(github_id=0, username="dev", access_token=""))
    db.commit()
    accounts.seed_accounts(db, reload_settings())
    dev = db.scalar(select(User).where(User.username == "dev"))
    assert dev.github_id is None and dev.password_hash and dev.role == "dev"


# --------------------------------------------------------------------------- GitHub linking
def test_connect_requires_session(client):
    response = client.get("/api/v1/auth/github/connect", follow_redirects=False)
    assert response.headers["location"] == "http://app.test/login?next=/dashboard"


def test_connect_install_redirects_to_app_install_page(client):
    _sign_in(client)
    location = _connect(client, "install")
    assert location.startswith("https://github.com/apps/reviewpilot-test/installations/new?state=")


def test_connect_not_configured(client, monkeypatch):
    _sign_in(client)
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    reload_settings()
    response = client.get("/api/v1/auth/github/connect", follow_redirects=False)
    assert response.headers["location"] == "http://app.test/dashboard?github_error=not_configured"


def test_install_callback_links_github_to_signed_in_user(client, db, mock_http):
    _mock_github(mock_http)
    _sign_in(client)
    state = parse_qs(urlparse(_connect(client)).query)["state"][0]
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "c", "state": state, "installation_id": 77, "setup_action": "install"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "http://app.test/dashboard"

    dev = db.scalar(select(User).where(User.username == "dev"))
    assert dev.github_id == 4242 and dev.github_login == "octo" and dev.email == "o@example.com"
    assert dev.access_token != "gho_abc" and decrypt_token(dev.access_token) == "gho_abc"
    me = client.get("/api/v1/auth/me").json()
    assert me["username"] == "dev" and me["github_linked"] is True and me["github_login"] == "octo"


def test_same_github_account_can_link_two_users(client, db, mock_http):
    _mock_github(mock_http)
    for username, password in (("dev", "dev-pass-123"), ("admin", "admin-pass-123")):
        _sign_in(client, username, password)
        state = parse_qs(urlparse(_connect(client, "authorize")).query)["state"][0]
        client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert {u.github_id for u in db.scalars(select(User))} == {4242}


def test_install_without_code_continues_with_authorize(client):
    _sign_in(client)
    state = parse_qs(urlparse(_connect(client)).query)["state"][0]
    response = client.get(
        "/api/v1/auth/callback",
        params={"state": state, "installation_id": 77, "setup_action": "install"},
        follow_redirects=False,
    )
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{GITHUB_OAUTH}/login/oauth/authorize"
    query = parse_qs(location.query)
    assert query["state"] == [state] and query["redirect_uri"] == ["http://api.test/api/v1/auth/callback"]


def test_callback_state_mismatch(client):
    _sign_in(client)
    _connect(client)
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": "wrong"}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/dashboard?github_error=state"


def test_callback_without_session(client):
    _sign_in(client)
    state = parse_qs(urlparse(_connect(client)).query)["state"][0]
    client.cookies.delete(SESSION_COOKIE)
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/dashboard?github_error=state"


def test_callback_exchange_error(client, mock_http):
    mock_http.post(f"{GITHUB_OAUTH}/login/oauth/access_token").respond(200, json={"error": "bad_verification_code"})
    _sign_in(client)
    state = parse_qs(urlparse(_connect(client)).query)["state"][0]
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/dashboard?github_error=exchange"


# --------------------------------------------------------------------------- session
def test_unlinked_user_sees_no_repositories_without_calling_github(client, mock_http):
    _sign_in(client)
    assert client.get("/api/v1/github/installations").json() == []
    assert mock_http.calls.call_count == 0


def test_revoked_github_token_does_not_end_session(client, db, mock_http):
    from app.core.security import encrypt_token

    _sign_in(client)
    dev = db.scalar(select(User).where(User.username == "dev"))
    dev.access_token = encrypt_token("gho_revoked")
    db.commit()
    mock_http.get(f"{GITHUB_API}/user/installations").respond(401)
    assert client.get("/api/v1/github/installations").json() == []
    assert client.get("/api/v1/auth/me").status_code == 200


def test_me_requires_session(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(SESSION_COOKIE, "garbage")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_admin_flag(client, login):
    login("admin-user")
    assert client.get("/api/v1/auth/me").json()["is_admin"] is True


def test_logout_requires_csrf_header_and_clears_cookie(client, login):
    login()
    del client.headers["X-Requested-With"]
    assert client.post("/api/v1/auth/logout").status_code == 403
    response = client.post("/api/v1/auth/logout", headers=CSRF)
    assert response.status_code == 204
    assert SESSION_COOKIE in response.headers.get("set-cookie", "")
