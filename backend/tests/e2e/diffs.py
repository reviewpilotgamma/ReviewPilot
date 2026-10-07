"""Deterministic dummy git diffs for end-to-end pipeline tests.

Three families:

* size tiers   — generated, seeded diffs from ~20 lines to ~5 MB (performance scaling);
* planted      — small hand-written diffs with one known architectural/security problem each;
* edge         — empty, whitespace-only, binary, rename-only and unicode diffs.

Every scenario carries the canned LLM markdown used in mocked mode, and the expectations used in live mode.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from functools import cache

HUNK_LINES = 40
VERDICT_SCORES = {"passed": 9.0, "warning": 6.5, "critical": 3.0}


@dataclass(frozen=True)
class DiffScenario:
    name: str
    diff: str
    title: str
    body: str = ""
    # Verdict the mocked LLM returns (and the pipeline must store).
    expected_verdict: str = "passed"
    # Live mode: verdicts that would mean the model missed the planted problem.
    live_forbidden_verdicts: tuple[str, ...] = ()
    # Live mode: words a good review should mention (reported as a hit rate, not asserted).
    expected_keywords: tuple[str, ...] = ()
    mock_review_markdown: str = field(default="", repr=False)

    @property
    def diff_bytes(self) -> int:
        return len(self.diff.encode("utf-8"))


# --------------------------------------------------------------------------- canned LLM output
def review_markdown(
    summary: str,
    findings: list[tuple[str, str, str, str]],
    *,
    verdict: str,
    score: float | None = None,
    with_meta: bool = True,
) -> str:
    """Build review markdown in the exact format the review prompt asks Gemini for.

    ``findings`` items are ``(severity, title, file, explanation)``.
    """
    lines = ["### Executive Summary", summary, "", "### Architectural Findings"]
    for severity, title, path, explanation in findings or [("Passed", "No issues", "-", "Change looks sound.")]:
        lines.append(f"- **{severity}** {title} — `{path}`: {explanation}")
    lines += [
        "",
        "### Specific Recommendations",
        "1. Address the findings above before merging.",
        "",
        "### What Looks Solid",
        "- The change is small and focused.",
    ]
    if with_meta:
        meta = {"score": score if score is not None else VERDICT_SCORES[verdict], "verdict": verdict}
        lines += ["", f"<!-- reviewpilot-meta: {json.dumps(meta)} -->"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- unified diff building
def file_diff(
    path: str,
    added: list[str],
    removed: list[str] | None = None,
    *,
    context: list[str] | None = None,
    new_file: bool = False,
    start: int = 1,
) -> str:
    """One file with a single valid hunk: context lines, then removed lines, then added lines."""
    removed = removed or []
    context = [] if new_file else (context or [])
    old_count = len(context) + len(removed)
    new_count = len(context) + len(added)
    header = [f"diff --git a/{path} b/{path}"]
    if new_file:
        header += ["new file mode 100644", "index 0000000..1a2b3c4", "--- /dev/null", f"+++ b/{path}"]
        hunk = f"@@ -0,0 +1,{new_count} @@"
    else:
        header += ["index 1111111..2222222 100644", f"--- a/{path}", f"+++ b/{path}"]
        hunk = f"@@ -{start},{old_count} +{start},{new_count} @@"
    body = [f" {line}" for line in context] + [f"-{line}" for line in removed] + [f"+{line}" for line in added]
    return "\n".join([*header, hunk, *body]) + "\n"


_WORDS = (
    "account", "ledger", "payment", "invoice", "session", "tenant", "order", "cart", "price", "quota",
    "token", "client", "retry", "batch", "queue", "event", "record", "cursor", "window", "metric",
)  # fmt: skip


def _code_line(rng: random.Random, width: int) -> str:
    indent = "    " * rng.randint(1, 2)
    target = f"{rng.choice(_WORDS)}_{rng.randint(0, 999)}"
    call = f"{rng.choice(_WORDS)}_{rng.choice(_WORDS)}"
    args = ", ".join(f"{rng.choice(_WORDS)}_{rng.randint(0, 99)}" for _ in range(rng.randint(1, 3)))
    line = f"{indent}{target} = {call}({args})"
    if len(line) < width:
        line += "  # " + " ".join(rng.choice(_WORDS) for _ in range((width - len(line)) // 7 + 1))
    return line[:width].rstrip()


def generate_diff(*, files: int, lines_per_file: int, seed: int, line_width: int = 72) -> str:
    """Generate a valid multi-file unified diff. Same arguments → identical output."""
    rng = random.Random(seed)
    out: list[str] = []
    for index in range(files):
        path = f"src/{rng.choice(_WORDS)}_{index}/{rng.choice(_WORDS)}_service.py"
        out += [f"diff --git a/{path} b/{path}", "index 1111111..2222222 100644", f"--- a/{path}", f"+++ b/{path}"]
        remaining, old_line, new_line = lines_per_file, 1, 1
        while remaining > 0:
            size = min(HUNK_LINES, remaining)
            remaining -= size
            body: list[str] = []
            old_count = new_count = 0
            for _ in range(size):
                kind = rng.choices((" ", "+", "-"), weights=(4, 4, 2))[0]
                body.append(kind + _code_line(rng, line_width))
                old_count += kind in (" ", "-")
                new_count += kind in (" ", "+")
            out.append(f"@@ -{old_line},{old_count} +{new_line},{new_count} @@ def handler_{index}():")
            out += body
            # Leave a gap of unchanged lines between hunks, like a real diff.
            old_line += old_count + 10
            new_line += new_count + 10
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- size tiers
@dataclass(frozen=True)
class SizeTier:
    files: int
    lines_per_file: int
    line_width: int
    target_bytes: int


SIZE_TIERS: dict[str, SizeTier] = {
    "small": SizeTier(files=1, lines_per_file=20, line_width=60, target_bytes=1_400),
    "medium": SizeTier(files=10, lines_per_file=100, line_width=60, target_bytes=60_000),
    "large": SizeTier(files=50, lines_per_file=160, line_width=60, target_bytes=500_000),
    "very_large": SizeTier(files=200, lines_per_file=330, line_width=72, target_bytes=5_000_000),
}


@cache
def scenario_for_tier(name: str, seed: int = 7) -> DiffScenario:
    """Build (and memoize) a size-tier scenario; the 5 MB string only exists once it is used."""
    tier = SIZE_TIERS[name]
    diff = generate_diff(files=tier.files, lines_per_file=tier.lines_per_file, seed=seed, line_width=tier.line_width)
    return DiffScenario(
        name=f"tier_{name}",
        diff=diff,
        title=f"[tier_{name}] Refactor services ({tier.files} files)",
        body="Mechanical refactor across services.",
        expected_verdict="warning",
        mock_review_markdown=review_markdown(
            "Large mechanical refactor across many services. No contract changes detected.",
            [("Warning", "Wide blast radius", "src/", "Many services change at once; roll out behind a flag.")],
            verdict="warning",
        ),
    )


# --------------------------------------------------------------------------- planted issues
def _planted() -> dict[str, DiffScenario]:
    scenarios = [
        DiffScenario(
            name="sql_injection",
            title="[sql_injection] Add customer search endpoint",
            body="Lets support staff search customers by name.",
            diff=file_diff(
                "app/repositories/customers.py",
                added=[
                    "def search_customers(conn, name: str):",
                    "    query = f\"SELECT id, email FROM customers WHERE name LIKE '%{name}%'\"",
                    "    return conn.execute(query).fetchall()",
                ],
                context=["from app.db import get_connection", ""],
            ),
            expected_verdict="critical",
            live_forbidden_verdicts=("passed",),
            expected_keywords=("injection", "parameter", "sql"),
            mock_review_markdown=review_markdown(
                "Adds a customer search that interpolates user input into SQL.",
                [("Critical", "SQL injection", "app/repositories/customers.py", "Use parameterized queries.")],
                verdict="critical",
            ),
        ),
        DiffScenario(
            name="hardcoded_secret",
            title="[hardcoded_secret] Wire up S3 uploads",
            body="Uploads invoices to S3.",
            diff=file_diff(
                "app/storage/s3.py",
                added=[
                    "import boto3",
                    "",
                    'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"',
                    'AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
                    'GITHUB_TOKEN = "ghp_exampleexampleexampleexample0000"',
                    "",
                    "def client():",
                    '    return boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY_ID,',
                    "                        aws_secret_access_key=AWS_SECRET_ACCESS_KEY)",
                ],
                new_file=True,
            ),
            expected_verdict="critical",
            live_forbidden_verdicts=("passed",),
            expected_keywords=("secret", "credential", "environment"),
            mock_review_markdown=review_markdown(
                "Adds an S3 client with credentials committed in source.",
                [("Critical", "Hardcoded credentials", "app/storage/s3.py", "Load secrets from the environment.")],
                verdict="critical",
            ),
        ),
        DiffScenario(
            name="no_timeout_retry",
            title="[no_timeout_retry] Call the billing service",
            body="Charges via the billing microservice.",
            diff=file_diff(
                "app/clients/billing.py",
                added=[
                    "def charge(amount):",
                    "    while True:",
                    '        resp = requests.post(BILLING_URL, json={"amount": amount})',
                    "        if resp.ok:",
                    "            return resp.json()",
                ],
                removed=["def charge(amount):", '    return billing_sdk.charge(amount, idempotency_key=uuid4().hex)'],
                context=["import requests", ""],
            ),
            expected_verdict="warning",
            live_forbidden_verdicts=(),
            expected_keywords=("timeout", "retry", "idempot"),
            mock_review_markdown=review_markdown(
                "Replaces the SDK call with an unbounded raw HTTP retry loop.",
                [
                    ("Warning", "No timeout", "app/clients/billing.py", "requests.post has no timeout."),
                    ("Warning", "Unbounded retry", "app/clients/billing.py", "Retry without backoff or idempotency."),
                ],
                verdict="warning",
            ),
        ),
        DiffScenario(
            name="breaking_api",
            title="[breaking_api] Rename order total field",
            body="Renames `total` to `amount_cents` in the public order response.",
            diff=file_diff(
                "app/api/orders.py",
                added=[
                    "class OrderOut(BaseModel):",
                    "    id: int",
                    "    amount_cents: int",
                    "",
                    '@router.get("/v2/order/{order_id}")',
                ],
                removed=["class OrderOut(BaseModel):", "    id: int", "    total: float", "", '@router.get("/v1/orders/{order_id}")'],
                context=["from pydantic import BaseModel", ""],
            ),
            expected_verdict="warning",
            live_forbidden_verdicts=(),
            expected_keywords=("breaking", "backward", "version"),
            mock_review_markdown=review_markdown(
                "Renames a public response field and moves the route.",
                [("Warning", "Breaking API contract", "app/api/orders.py", "Keep v1 and add the field compatibly.")],
                verdict="warning",
            ),
        ),
        DiffScenario(
            name="blocking_async",
            title="[blocking_async] Poll export status",
            body="Polls the export service until the file is ready.",
            diff=file_diff(
                "app/services/exports.py",
                added=[
                    "async def wait_for_export(export_id: str) -> dict:",
                    "    while True:",
                    '        status = requests.get(f"{EXPORTS_URL}/{export_id}").json()',
                    '        if status["ready"]:',
                    "            return status",
                    "        time.sleep(5)",
                ],
                context=["import time", "import requests", ""],
            ),
            expected_verdict="warning",
            live_forbidden_verdicts=(),
            expected_keywords=("block", "event loop", "async"),
            mock_review_markdown=review_markdown(
                "Adds an async poller that blocks the event loop.",
                [("Warning", "Blocking I/O in async code", "app/services/exports.py", "Use httpx.AsyncClient.")],
                verdict="warning",
            ),
        ),
        DiffScenario(
            name="clean",
            title="[clean] Add health check endpoint",
            body="Adds /healthz returning 200 with a test.",
            diff=file_diff(
                "app/api/health.py",
                added=[
                    "from fastapi import APIRouter",
                    "",
                    "router = APIRouter()",
                    "",
                    '@router.get("/healthz")',
                    "def healthz() -> dict[str, str]:",
                    '    return {"status": "ok"}',
                ],
                new_file=True,
            )
            + file_diff(
                "tests/test_health.py",
                added=["def test_healthz(client):", '    assert client.get("/healthz").json() == {"status": "ok"}'],
                new_file=True,
            ),
            expected_verdict="passed",
            live_forbidden_verdicts=("critical",),
            expected_keywords=("health",),
            mock_review_markdown=review_markdown(
                "Adds a small, tested health endpoint.",
                [("Passed", "Isolated, tested change", "app/api/health.py", "No architectural risk.")],
                verdict="passed",
            ),
        ),
    ]
    return {s.name: s for s in scenarios}


PLANTED_SCENARIOS: dict[str, DiffScenario] = _planted()


# --------------------------------------------------------------------------- edge cases
UNICODE_MARKER = "Unicode ✓ 日本語 🚀 �"


def _edge() -> dict[str, DiffScenario]:
    passed_md = review_markdown("Trivial change.", [], verdict="passed")
    scenarios = [
        DiffScenario(name="empty", title="[empty] Empty PR", diff=""),
        DiffScenario(name="whitespace", title="[whitespace] Whitespace-only diff", diff="\n  \n\t\n"),
        DiffScenario(
            name="binary",
            title="[binary] Update logo",
            diff=(
                "diff --git a/static/logo.png b/static/logo.png\n"
                "index 3b18e51..a9c7f02 100644\n"
                "Binary files a/static/logo.png and b/static/logo.png differ\n"
            )
            + file_diff("static/README.md", added=["Logo updated."], new_file=True),
            mock_review_markdown=passed_md,
        ),
        DiffScenario(
            name="rename_only",
            title="[rename_only] Move utils module",
            diff=(
                "diff --git a/app/util.py b/app/utils/__init__.py\n"
                "similarity index 100%\n"
                "rename from app/util.py\n"
                "rename to app/utils/__init__.py\n"
            )
            + file_diff("app/main.py", added=["from app.utils import helper"], removed=["from app.util import helper"]),
            mock_review_markdown=passed_md,
        ),
        DiffScenario(
            name="unicode",
            title="[unicode] Localize greetings 🌍",
            body="Adds greetings in several languages — 日本語, emoji.",
            diff=file_diff(
                "app/i18n/greetings.py",
                added=['GREETINGS = {"ja": "こんにちは", "emoji": "👋🚀", "de": "Grüße"}', f"# {UNICODE_MARKER}"],
                new_file=True,
            ),
            mock_review_markdown=review_markdown(f"Adds localized greetings. {UNICODE_MARKER}", [], verdict="passed"),
        ),
    ]
    return {s.name: s for s in scenarios}


EDGE_SCENARIOS: dict[str, DiffScenario] = _edge()


def all_named_scenarios() -> dict[str, DiffScenario]:
    """Planted + edge scenarios by name (size tiers are built lazily via ``scenario_for_tier``)."""
    return {**PLANTED_SCENARIOS, **EDGE_SCENARIOS}
