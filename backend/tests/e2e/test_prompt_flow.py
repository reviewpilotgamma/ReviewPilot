"""Golden prompt end to end: an admin edit reaches the next review, and each review records what it used."""

from __future__ import annotations

from app.services.documents import MIN_CACHE_CHARS
from app.services.prompts import NO_INSTRUCTIONS
from tests.e2e.diffs import PLANTED_SCENARIOS

PROMPT_URL = "/api/v1/prompt"
CUSTOM = (
    "ACME GOLDEN PROMPT v2. Review strictly.\n"
    "Team rules:\n{{custom_instructions}}\n"
    "Verbosity: {{verbosity_directive}}\n"
    'As the VERY LAST line, output exactly:\n<!-- reviewpilot-meta: {"score": <number>, "verdict": "<v>"} -->'
)


async def review(pipeline, number: int) -> tuple[dict, dict]:
    pipeline.open_pr(number, PLANTED_SCENARIOS["no_timeout_retry"])
    await pipeline.drain()
    review_id = pipeline.reviews()[-1].id
    detail = pipeline.client.get(f"/api/v1/reviews/{review_id}").json()
    return pipeline.llm.requests[-1], detail


async def test_admin_prompt_edit_reaches_next_review_and_is_recorded(pipeline, login):
    login("admin-user", github_id=2001)
    client = pipeline.client
    rules = {"custom_instructions": "- Billing calls need idempotency keys.", "verbosity": "detailed",
             "review_mode": "auto", "enable_security": True}
    assert client.put("/api/v1/rules/acme/api", json=rules).status_code == 200

    body, detail = await review(pipeline, 60)
    assert "ReviewPilot, a senior software architect" in pipeline.llm.system_prompt(body)
    assert detail["review_context"]["prompt"] == "default"
    assert detail["review_context"]["prompt_updated_at"] is None

    assert client.put(PROMPT_URL, json={"template": CUSTOM}).status_code == 200
    body, detail = await review(pipeline, 61)

    system = pipeline.llm.system_prompt(body)
    assert system.startswith("ACME GOLDEN PROMPT v2.")
    assert "- Billing calls need idempotency keys." in system
    assert "ReviewPilot, a senior software architect" not in system
    context = detail["review_context"]
    assert (context["prompt"], context["verbosity"], context["security"]) == ("custom", "detailed", True)
    assert context["prompt_updated_at"] is not None
    assert context["instructions_chars"] == len(rules["custom_instructions"])
    # The custom prompt still carries the meta line, so the verdict is parsed normally.
    assert pipeline.reviews()[-1].verdict == "warning"

    assert client.delete(PROMPT_URL).status_code == 204
    body, detail = await review(pipeline, 62)
    assert "ReviewPilot, a senior software architect" in pipeline.llm.system_prompt(body)
    assert detail["review_context"]["prompt"] == "default"


async def test_review_context_tracks_documents_and_note(pipeline, login):
    login()
    client = pipeline.client
    big = "Services own their data.\n" * (MIN_CACHE_CHARS // 25 + 50)
    upload = client.post(
        "/api/v1/rules/acme/api/documents", files={"file": ("arch.md", big.encode(), "text/markdown")}
    )
    assert upload.json()["cache_status"] == "cached"

    pipeline.github.add_pr(63, PLANTED_SCENARIOS["clean"])
    pipeline.comment(63, "@review focus on retries")
    await pipeline.drain()
    detail = client.get(f"/api/v1/reviews/{pipeline.reviews()[-1].id}").json()

    context = detail["review_context"]
    assert (context["documents"], context["documents_mode"], context["requester_note"]) == (
        ["arch.md"], "cached", True,
    )
    assert context["instructions_chars"] == 0
    assert NO_INSTRUCTIONS in pipeline.llm.system_prompt(pipeline.llm.requests[-1])
    assert "Services own their data" not in str(context)
