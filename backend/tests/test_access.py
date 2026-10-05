from __future__ import annotations

import httpx
import pytest

from app.core.security import SESSION_COOKIE, create_session_token
from app.services import access
from app.services.errors import ReauthRequired
from tests.conftest import GITHUB_API, make_user


@pytest.fixture
def installations(mock_http):
    mock_http.get(f"{GITHUB_API}/user/installations?per_page=100").respond(
        200,
        json={"installations": [{"id": 1, "account": {"login": "Acme", "type": "Organization", "avatar_url": "a"}}]},
    )
    page2 = f"{GITHUB_API}/user/installations/1/repositories?per_page=100&page=2"
    mock_http.get(f"{GITHUB_API}/user/installations/1/repositories?per_page=100").respond(
        200,
        json={"repositories": [{"full_name": "Acme/API", "private": True, "html_url": "https://github.com/Acme/API"}]},
        headers={"link": f'<{page2}>; rel="next"'},
    )
    mock_http.get(page2).respond(200, json={"repositories": [{"full_name": "Acme/Web", "private": False}]})
    return mock_http


async def test_paginated_repos_are_collected(db, installations):
    user = make_user(db)
    repos = await access.get_accessible_repos(user, "gho")
    assert set(repos) == {"acme/api", "acme/web"}
    assert repos["acme/api"].installation_id == 1 and repos["acme/api"].private


async def test_results_are_cached(db, installations):
    user = make_user(db)
    await access.get_accessible_repos(user, "gho")
    await access.get_accessible_repos(user, "gho")
    route = installations.routes[0]
    assert route.call_count == 1
    await access.get_accessible_repos(user, "gho", refresh=True)
    assert route.call_count == 2


async def test_revoked_token_requires_reauth(db, mock_http):
    mock_http.get(f"{GITHUB_API}/user/installations?per_page=100").mock(return_value=httpx.Response(401))
    with pytest.raises(ReauthRequired):
        await access.get_accessible_repos(make_user(db), "gho")


async def test_undecryptable_token_requires_reauth(db):
    with pytest.raises(ReauthRequired):
        await access.get_accessible_repos(make_user(db), None)


def test_api_maps_reauth_to_401(client, db, mock_http):
    mock_http.get(f"{GITHUB_API}/user/installations?per_page=100").mock(return_value=httpx.Response(401))
    user = make_user(db)
    client.cookies.set(SESSION_COOKIE, create_session_token(user.id, user.username))
    response = client.get("/api/v1/github/installations")
    assert response.status_code == 401 and response.json()["detail"] == "reauth_required"


def test_installations_endpoint_groups_repos(client, db, installations):
    user = make_user(db)
    client.cookies.set(SESSION_COOKIE, create_session_token(user.id, user.username))
    data = client.get("/api/v1/github/installations").json()
    assert len(data) == 1 and data[0]["account_login"] == "Acme"
    assert [r["full_name"] for r in data[0]["repos"]] == ["acme/api", "acme/web"]
    assert data[0]["repos"][0]["has_rules"] is False


def test_app_info_endpoint(client, mock_http):
    mock_http.post(f"{GITHUB_API}/app").respond(404)
    mock_http.get(f"{GITHUB_API}/app").respond(200, json={"slug": "reviewpilot-test", "name": "ReviewPilot Test"})
    data = client.get("/api/v1/github/app").json()
    assert data["configured"] is True
    assert data["install_url"] == "https://github.com/apps/reviewpilot-test/installations/new"
