from __future__ import annotations

import time

import httpx
import jwt
import pytest

from app.services import github_app
from app.services.errors import (
    GitHubNotConfigured,
    GitHubPermanentError,
    GitHubRateLimited,
    GitHubTransientError,
)
from tests.conftest import GITHUB_API

TOKEN_URL = f"{GITHUB_API}/app/installations/99/access_tokens"
PR_URL = f"{GITHUB_API}/repos/acme/api/pulls/7"


def test_app_jwt_claims(rsa_keys):
    token = github_app.create_app_jwt()
    claims = jwt.decode(token, rsa_keys[1], algorithms=["RS256"])
    now = int(time.time())
    assert claims["iss"] == "12345"
    assert now - 62 <= claims["iat"] <= now - 58
    assert claims["exp"] - claims["iat"] == 660


def test_app_jwt_missing_key(monkeypatch, tmp_path):
    from app.core.config import reload_settings

    monkeypatch.setenv("GITHUB_PRIVATE_KEY_PATH", str(tmp_path / "missing.pem"))
    reload_settings()
    github_app.clear_caches()
    with pytest.raises(GitHubNotConfigured):
        github_app.create_app_jwt()


async def test_installation_token_is_cached(mock_http):
    route = mock_http.post(TOKEN_URL).respond(201, json={"token": "ghs_1"})
    assert await github_app.get_installation_token(99) == "ghs_1"
    assert await github_app.get_installation_token(99) == "ghs_1"
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"].startswith("Bearer ")


async def test_installation_token_refreshed_near_expiry(mock_http):
    route = mock_http.post(TOKEN_URL).respond(201, json={"token": "ghs_1"})
    await github_app.get_installation_token(99)
    github_app._token_cache[99] = ("ghs_1", time.time() + 30)  # inside the 60 s safety margin
    await github_app.get_installation_token(99)
    assert route.call_count == 2


async def test_401_evicts_token_and_retries_once(mock_http):
    mock_http.post(TOKEN_URL).mock(
        side_effect=[httpx.Response(201, json={"token": "old"}), httpx.Response(201, json={"token": "new"})]
    )
    pr_route = mock_http.get(PR_URL).mock(
        side_effect=[httpx.Response(401, json={"message": "Bad credentials"}), httpx.Response(200, json={"number": 7})]
    )
    pr = await github_app.get_pull(99, "acme", "api", 7)
    assert pr.number == 7
    assert pr_route.calls[1].request.headers["Authorization"] == "token new"


async def test_diff_uses_diff_accept_header(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    route = mock_http.get(PR_URL).respond(200, text="diff --git a b")
    assert await github_app.get_pull_diff(99, "acme", "api", 7) == "diff --git a b"
    assert route.calls[0].request.headers["Accept"] == "application/vnd.github.v3.diff"


async def test_post_comment_returns_id(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    route = mock_http.post(f"{GITHUB_API}/repos/acme/api/issues/7/comments").respond(201, json={"id": 42})
    assert await github_app.post_issue_comment(99, "acme", "api", 7, "hello") == 42
    assert b'"body":"hello"' in route.calls[0].request.content.replace(b" ", b"")


async def test_reaction_failure_is_swallowed(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    mock_http.post(f"{GITHUB_API}/repos/acme/api/issues/comments/5/reactions").respond(500)
    await github_app.add_reaction(99, "acme", "api", 5, "eyes")


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(500), GitHubTransientError),
        (httpx.Response(404, json={"message": "Not Found"}), GitHubPermanentError),
        (httpx.Response(422, json={"message": "bad"}), GitHubPermanentError),
        (httpx.Response(429, headers={"retry-after": "12"}), GitHubRateLimited),
        (httpx.Response(403, headers={"x-ratelimit-remaining": "0"}), GitHubRateLimited),
        (httpx.Response(403, json={"message": "forbidden"}), GitHubPermanentError),
    ],
)
def test_error_mapping(response, error):
    with pytest.raises(error):
        github_app.raise_for_github(response)


def test_rate_limit_retry_after_parsed():
    with pytest.raises(GitHubRateLimited) as info:
        github_app.raise_for_github(httpx.Response(429, headers={"retry-after": "12"}))
    assert info.value.retry_after == 12.0
    assert info.value.retryable


async def test_timeout_is_transient(mock_http):
    mock_http.post(TOKEN_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(GitHubTransientError):
        await github_app.get_installation_token(99)


async def test_pull_carries_head_sha(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    mock_http.get(PR_URL).respond(200, json={"number": 7, "head": {"ref": "feat", "sha": "abc123"}})
    assert (await github_app.get_pull(99, "acme", "api", 7)).head_sha == "abc123"


async def test_compare_files(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/compare/old...new").respond(
        200, json={"files": [{"filename": "app/x.py", "additions": 3, "deletions": 1}]}
    )
    assert await github_app.get_compare_files(99, "acme", "api", "old", "new") == [("app/x.py", 3, 1)]


@pytest.mark.parametrize("status", [404, 422])
async def test_compare_unavailable_returns_none(mock_http, status):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/compare/old...new").respond(status, json={"message": "nope"})
    assert await github_app.get_compare_files(99, "acme", "api", "old", "new") is None


async def test_compare_server_error_raises(mock_http):
    mock_http.post(TOKEN_URL).respond(201, json={"token": "t"})
    mock_http.get(f"{GITHUB_API}/repos/acme/api/compare/old...new").respond(502)
    with pytest.raises(GitHubTransientError):
        await github_app.get_compare_files(99, "acme", "api", "old", "new")
