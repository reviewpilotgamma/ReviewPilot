from __future__ import annotations

from app.models import RepoRule


def test_get_defaults_when_no_rule(client, login):
    login()
    data = client.get("/api/v1/rules/acme/api").json()
    assert data == {
        "repo_full_name": "acme/api",
        "custom_instructions": "",
        "verbosity": "concise",
        "review_mode": "auto",
        "enable_security": True,
        "updated_at": None,
        "is_default": True,
    }


def test_put_upserts_and_normalizes_name(client, login, db):
    user = login(repos=("Acme/API",))
    body = {
        "custom_instructions": "Check idempotency",
        "verbosity": "detailed",
        "review_mode": "on_demand",
        "enable_security": False,
    }
    response = client.put("/api/v1/rules/Acme/API", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["is_default"] is False and data["repo_full_name"] == "acme/api"
    rule = db.get(RepoRule, "acme/api")
    assert rule.verbosity == "detailed" and rule.updated_by_user_id == user.id

    body["verbosity"] = "concise"
    assert client.put("/api/v1/rules/acme/api", json=body).json()["verbosity"] == "concise"


def test_delete_resets_to_defaults(client, login):
    login()
    client.put("/api/v1/rules/acme/api", json={"custom_instructions": "x"})
    assert client.delete("/api/v1/rules/acme/api").status_code == 204
    assert client.get("/api/v1/rules/acme/api").json()["is_default"] is True


def test_list_covers_all_accessible_repos(client, login):
    login(repos=("acme/api", "acme/web"))
    client.put("/api/v1/rules/acme/web", json={"custom_instructions": "y"})
    data = client.get("/api/v1/rules").json()
    assert [(r["repo_full_name"], r["is_default"]) for r in data] == [("acme/api", True), ("acme/web", False)]


def test_inaccessible_repo_is_404(client, login):
    login(repos=("acme/api",))
    assert client.get("/api/v1/rules/other/repo").status_code == 404
    assert client.put("/api/v1/rules/other/repo", json={}).status_code == 404


def test_validation_errors(client, login):
    login()
    assert client.put("/api/v1/rules/acme/api", json={"verbosity": "loud"}).status_code == 422
    assert client.put("/api/v1/rules/acme/api", json={"custom_instructions": "x" * 10_001}).status_code == 422
    assert client.get("/api/v1/rules/acme/bad%20name").status_code == 422


def test_mutation_requires_csrf_header(client, login):
    login()
    del client.headers["X-Requested-With"]
    assert client.put("/api/v1/rules/acme/api", json={}).status_code == 403


def test_presets_public(client):
    data = client.get("/api/v1/rules/presets").json()
    assert {p["name"] for p in data} == {"Standard Microservices", "Strict Security", "Performance & Async"}


def test_rules_require_auth(client):
    assert client.get("/api/v1/rules").status_code == 401
