from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.core.security import OAUTH_NEXT_COOKIE, OAUTH_STATE_COOKIE, SESSION_COOKIE, decrypt_token
from app.models import User
from tests.conftest import GITHUB_API, GITHUB_OAUTH


def _start_login(client, next_path: str | None = None) -> str:
    params = {"next": next_path} if next_path else {}
    response = client.get("/api/v1/auth/login", params=params, follow_redirects=False)
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == GITHUB_OAUTH
    query = parse_qs(location.query)
    assert query["client_id"] == ["Iv1.client"]
    assert query["redirect_uri"] == ["http://api.test/api/v1/auth/callback"]
    assert client.cookies.get(OAUTH_STATE_COOKIE) == query["state"][0]
    return query["state"][0]


def _mock_github(mock_http, login: str = "alice"):
    mock_http.post(f"{GITHUB_OAUTH}/login/oauth/access_token").respond(200, json={"access_token": "gho_abc"})
    mock_http.get(f"{GITHUB_API}/user").respond(
        200, json={"id": 1001, "login": login, "avatar_url": "https://avatars/x", "email": None}
    )
    mock_http.get(f"{GITHUB_API}/user/emails").respond(
        200, json=[{"email": "a@example.com", "primary": True, "verified": True}]
    )


def test_login_redirects_with_state(client):
    _start_login(client)


def test_callback_success_creates_user_and_session(client, db, mock_http):
    _mock_github(mock_http)
    state = _start_login(client, "/rules")
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "http://app.test/rules"

    user = db.scalars(select(User)).one()
    assert user.username == "alice" and user.email == "a@example.com"
    assert user.access_token != "gho_abc" and decrypt_token(user.access_token) == "gho_abc"

    set_cookie = ",".join(response.headers.get_list("set-cookie"))
    assert SESSION_COOKIE in set_cookie and "HttpOnly" in set_cookie and "samesite=lax" in set_cookie.lower()

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice" and me.json()["is_admin"] is False


def test_callback_updates_existing_user(client, db, mock_http):
    _mock_github(mock_http)
    for _ in range(2):
        state = _start_login(client)
        client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert len(db.scalars(select(User)).all()) == 1


def test_callback_state_mismatch(client):
    _start_login(client)
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": "wrong"}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/?auth_error=state"


def test_callback_exchange_error(client, mock_http):
    mock_http.post(f"{GITHUB_OAUTH}/login/oauth/access_token").respond(200, json={"error": "bad_verification_code"})
    state = _start_login(client)
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/?auth_error=exchange"


def test_open_redirect_rejected(client, mock_http):
    _mock_github(mock_http)
    state = _start_login(client, "//evil.example.com")
    assert client.cookies.get(OAUTH_NEXT_COOKIE).strip('"') == "/dashboard"
    response = client.get("/api/v1/auth/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert response.headers["location"] == "http://app.test/dashboard"


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
    response = client.post("/api/v1/auth/logout", headers={"X-Requested-With": "ReviewPilot"})
    assert response.status_code == 204
    assert SESSION_COOKIE in response.headers.get("set-cookie", "")
