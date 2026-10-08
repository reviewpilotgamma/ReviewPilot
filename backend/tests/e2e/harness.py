"""End-to-end harness: fake GitHub, mock Gemini, stage timing, worker draining and the perf report.

Nothing here changes production code. Stage timing wraps existing service functions with ``monkeypatch`` on the
namespace the caller resolves them from.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import inspect
import json
import os
import re
import statistics
import time
import warnings
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import func, select, update

from app.core import http
from app.core.database import SessionLocal, utcnow
from app.models import Job, PRReview, WebhookEvent
from app.services import gemini, reviewer, worker
from app.services import github_app as gh
from app.services.reviewer import count_changed_lines
from tests.conftest import GEMINI_API, GITHUB_API, post_webhook
from tests.e2e.diffs import DiffScenario, all_named_scenarios, scenario_for_tier

INSTALLATION_TOKEN = "ghs_e2e_installation_token"
SCENARIO_TAG_RE = re.compile(r"\[(tier_[a-z_]+|[a-z_]+)\]")
STAGES = (
    "ingest",
    "claim",
    "github_pr_fetch",
    "diff_fetch",
    "rules_load",
    "docs_load",
    "prompt_build",
    "llm",
    "parse",
    "persist",
    "comment_post",
)


def budget_scale() -> float:
    """Multiplier for perf budgets on slow machines (``REVIEWPILOT_E2E_BUDGET_SCALE``)."""
    try:
        return float(os.environ.get("REVIEWPILOT_E2E_BUDGET_SCALE", "1"))
    except ValueError:
        return 1.0


# --------------------------------------------------------------------------- fake GitHub
@dataclass
class PostedComment:
    owner: str
    repo: str
    number: int
    body: str
    id: int


class FakeGitHub:
    """Serves PR metadata and diffs and records comments/reactions. Failures can be injected per route kind."""

    def __init__(self, router: respx.MockRouter) -> None:
        self.prs: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.diffs: dict[tuple[str, str, int], str] = {}
        self.comments: list[PostedComment] = []
        self.reactions: list[tuple[str, str, int, str]] = []
        self.calls: defaultdict[str, int] = defaultdict(int)
        self._failures: defaultdict[str, deque[int]] = defaultdict(deque)
        self._next_comment_id = 9_000
        base = re.escape(GITHUB_API)
        router.post(url__regex=rf"{base}/app/installations/\d+/access_tokens").respond(
            201, json={"token": INSTALLATION_TOKEN}
        )
        router.get(url__regex=rf"{base}/repos/[^/]+/[^/]+/pulls/\d+$").mock(side_effect=self._pull)
        router.post(url__regex=rf"{base}/repos/[^/]+/[^/]+/issues/\d+/comments$").mock(side_effect=self._comment)
        router.post(url__regex=rf"{base}/repos/[^/]+/[^/]+/issues/comments/\d+/reactions$").mock(
            side_effect=self._reaction
        )
        router.get(url__regex=rf"{base}/repos/[^/]+/[^/]+/compare/.+").mock(side_effect=self._compare)

    # -- setup
    def add_pr(
        self,
        number: int,
        scenario: DiffScenario,
        *,
        owner: str = "acme",
        repo: str = "api",
        state: str = "open",
        author: str = "bob",
        head_sha: str | None = None,
    ) -> dict[str, Any]:
        additions = sum(1 for line in scenario.diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in scenario.diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        data = {
            "number": number,
            "title": scenario.title,
            "body": scenario.body,
            "user": {"login": author, "type": "User"},
            "base": {"ref": "main"},
            "head": {
                "ref": f"feature/{scenario.name}",
                "sha": head_sha or hashlib.sha1(f"{owner}/{repo}#{number}:{scenario.name}".encode()).hexdigest(),
            },
            "state": state,
            "draft": False,
            "additions": additions,
            "deletions": deletions,
            "changed_files": scenario.diff.count("diff --git "),
        }
        key = (owner.lower(), repo.lower(), number)
        self.prs[key] = data
        self.diffs[key] = scenario.diff
        return data

    def push(self, number: int, scenario: DiffScenario, *, head_sha: str, owner: str = "acme", repo: str = "api") -> None:
        """Replace the PR's diff and head commit, as a new push does."""
        key = (owner.lower(), repo.lower(), number)
        self.diffs[key] = scenario.diff
        self.prs[key]["head"]["sha"] = head_sha
        self.prs[key]["changed_files"] = scenario.diff.count("diff --git ")

    def fail_next(self, kind: str, status: int, times: int = 1) -> None:
        """Make the next ``times`` calls of ``kind`` (``pull``, ``diff``, ``comment``) return ``status``."""
        self._failures[kind].extend([status] * times)

    def comments_for(self, number: int, owner: str = "acme", repo: str = "api") -> list[str]:
        return [c.body for c in self.comments if (c.owner, c.repo, c.number) == (owner, repo, number)]

    # -- route handlers
    @staticmethod
    def _parts(request: httpx.Request) -> list[str]:
        return request.url.path.strip("/").split("/")

    def _maybe_fail(self, kind: str) -> httpx.Response | None:
        self.calls[kind] += 1
        if self._failures[kind]:
            status = self._failures[kind].popleft()
            return httpx.Response(status, json={"message": f"injected {kind} failure"})
        return None

    def _pull(self, request: httpx.Request) -> httpx.Response:
        _, owner, repo, _, number = self._parts(request)
        key = (owner.lower(), repo.lower(), int(number))
        is_diff = request.headers.get("Accept") == "application/vnd.github.v3.diff"
        failure = self._maybe_fail("diff" if is_diff else "pull")
        if failure is not None:
            return failure
        if key not in self.prs:
            return httpx.Response(404, json={"message": "Not Found"})
        if is_diff:
            return httpx.Response(200, content=self.diffs[key].encode("utf-8"), headers={"Content-Type": "text/plain; charset=utf-8"})
        return httpx.Response(200, json=self.prs[key])

    def _comment(self, request: httpx.Request) -> httpx.Response:
        _, owner, repo, _, number, _ = self._parts(request)
        failure = self._maybe_fail("comment")
        if failure is not None:
            return failure
        self._next_comment_id += 1
        body = json.loads(request.content)["body"]
        self.comments.append(PostedComment(owner.lower(), repo.lower(), int(number), body, self._next_comment_id))
        return httpx.Response(201, json={"id": self._next_comment_id})

    def _compare(self, request: httpx.Request) -> httpx.Response:
        """Files of the PR's current diff (the mock keeps no commit history)."""
        _, owner, repo, *_ = self._parts(request)
        self.calls["compare"] += 1
        diffs = [d for (o, r, _), d in self.diffs.items() if (o, r) == (owner.lower(), repo.lower())]
        paths = re.findall(r"^diff --git a/(\S+) b/", diffs[-1] if diffs else "", re.MULTILINE)
        return httpx.Response(200, json={"files": [{"filename": p, "additions": 1, "deletions": 0} for p in paths]})

    def _reaction(self, request: httpx.Request) -> httpx.Response:
        parts = self._parts(request)
        self.calls["reaction"] += 1
        content = json.loads(request.content)["content"]
        self.reactions.append((parts[1].lower(), parts[2].lower(), int(parts[5]), content))
        return httpx.Response(201, json={})


# --------------------------------------------------------------------------- mock Gemini
def markdown_for_tag(tag: str) -> str | None:
    if tag.startswith("tier_"):
        return scenario_for_tier(tag.removeprefix("tier_")).mock_review_markdown
    scenario = all_named_scenarios().get(tag)
    return scenario.mock_review_markdown if scenario and scenario.mock_review_markdown else None


class MockGemini:
    """Mock ``generateContent`` and ``cachedContents``.

    The reply is picked from the ``[scenario]`` tag in the PR title (inside the user content), unless a reply was
    queued with ``respond_with``. Failures are queued with ``fail_next``.
    """

    def __init__(self, router: respx.MockRouter, default_markdown: str) -> None:
        self.requests: list[dict[str, Any]] = []
        self.cache_creates: list[dict[str, Any]] = []
        self.cache_deletes: list[str] = []
        self.delay_s = 0.0
        self._default = default_markdown
        self._replies: deque[str] = deque()
        self._failures: deque[int] = deque()
        self._cache_seq = 0
        base = re.escape(GEMINI_API)
        router.post(url__regex=rf"{base}/models/[^/]+:generateContent$").mock(side_effect=self._generate)
        router.post(f"{GEMINI_API}/cachedContents").mock(side_effect=self._create_cache)
        router.delete(url__regex=rf"{base}/cachedContents/.+").mock(side_effect=self._delete_cache)

    @property
    def generate_calls(self) -> int:
        return len(self.requests)

    def respond_with(self, *markdown: str) -> None:
        self._replies.extend(markdown)

    def fail_next(self, status: int, times: int = 1) -> None:
        self._failures.extend([status] * times)

    @staticmethod
    def system_prompt(body: dict[str, Any]) -> str:
        return "".join(p.get("text", "") for p in body["systemInstruction"]["parts"])

    @staticmethod
    def user_content(body: dict[str, Any]) -> str:
        return "".join(p.get("text", "") for p in body["contents"][0]["parts"])

    async def _generate(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self._failures:
            status = self._failures.popleft()
            return httpx.Response(status, json={"error": {"message": f"injected gemini {status}"}})
        if self._replies:
            text = self._replies.popleft()
        else:
            match = SCENARIO_TAG_RE.search(self.user_content(body))
            text = (markdown_for_tag(match.group(1)) if match else None) or self._default
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": len(json.dumps(body)) // 4},
            },
        )

    def _create_cache(self, request: httpx.Request) -> httpx.Response:
        if self._failures:
            status = self._failures.popleft()
            return httpx.Response(status, json={"error": {"message": f"injected cache {status}"}})
        self._cache_seq += 1
        body = json.loads(request.content)
        self.cache_creates.append(body)
        expire = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        return httpx.Response(200, json={"name": f"cachedContents/e2e{self._cache_seq}", "expireTime": expire})

    def _delete_cache(self, request: httpx.Request) -> httpx.Response:
        self.cache_deletes.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={})


# --------------------------------------------------------------------------- stage timing
_current_job: contextvars.ContextVar[int | None] = contextvars.ContextVar("e2e_current_job", default=None)


class StageTimer:
    """Accumulates wall-clock seconds per (job id, stage)."""

    # (module, attribute, stage). Patched on the module the caller looks the name up in.
    TARGETS: tuple[tuple[Any, str, str], ...] = (
        (gh, "get_pull", "github_pr_fetch"),
        (gh, "get_pull_diff", "diff_fetch"),
        (gh, "post_issue_comment", "comment_post"),
        (reviewer, "_load_rules", "rules_load"),
        (reviewer, "_docs_for_prompt", "docs_load"),
        (reviewer, "build_review_system_prompt", "prompt_build"),
        (reviewer, "build_plan_system_prompt", "prompt_build"),
        (reviewer, "build_pr_context", "prompt_build"),
        (gemini, "generate", "llm"),
        (reviewer, "parse_review", "parse"),
        (reviewer, "_save_review", "persist"),
    )

    def __init__(self) -> None:
        self.stages: defaultdict[int, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.totals: dict[int, float] = {}
        self.kinds: dict[int, str] = {}

    def record(self, job_id: int | None, stage: str, seconds: float) -> None:
        if job_id is not None:
            self.stages[job_id][stage] += seconds

    def summary(self, job_id: int) -> dict[str, float]:
        return {stage: round(self.stages[job_id].get(stage, 0.0), 6) for stage in STAGES}

    def _wrap(self, fn: Any, stage: str) -> Any:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    self.record(_current_job.get(), stage, time.perf_counter() - start)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                self.record(_current_job.get(), stage, time.perf_counter() - start)

        return sync_wrapper

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for module, name, stage in self.TARGETS:
            monkeypatch.setattr(module, name, self._wrap(getattr(module, name), stage))

        original_claim = worker.claim_next_job
        original_execute = worker.execute_job

        def timed_claim() -> Any:
            start = time.perf_counter()
            ctx = original_claim()
            if ctx is not None:
                self.record(ctx.job_id, "claim", time.perf_counter() - start)
            return ctx

        async def timed_execute(ctx: reviewer.JobContext) -> None:
            token = _current_job.set(ctx.job_id)
            self.kinds[ctx.job_id] = ctx.kind
            start = time.perf_counter()
            try:
                await original_execute(ctx)
            finally:
                self.totals[ctx.job_id] = self.totals.get(ctx.job_id, 0.0) + time.perf_counter() - start
                _current_job.reset(token)

        monkeypatch.setattr(worker, "claim_next_job", timed_claim)
        monkeypatch.setattr(worker, "execute_job", timed_execute)


# --------------------------------------------------------------------------- report
@dataclass
class ScenarioResult:
    scenario: str
    mode: str
    diff_bytes: int
    changed_lines: int
    verdict: str | None
    score: float | None
    total_s: float
    stages: dict[str, float]
    extra: dict[str, Any] = field(default_factory=dict)


class ReportCollector:
    """Collects per-scenario timings and throughput runs, and writes ``report.json`` / ``report.md``."""

    def __init__(self) -> None:
        self.results: list[ScenarioResult] = []
        self.throughput: list[dict[str, Any]] = []
        self.secrets: set[str] = set()

    def add(self, result: ScenarioResult) -> None:
        self.results.append(result)

    def add_throughput(self, **data: Any) -> None:
        self.throughput.append(data)

    def __bool__(self) -> bool:
        return bool(self.results or self.throughput)

    def _redact(self, text: str) -> str:
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, "***")
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "stages": list(STAGES),
            "scenarios": [asdict(r) for r in self.results],
            "throughput": self.throughput,
        }

    def to_markdown(self) -> str:
        out = ["# ReviewPilot E2E pipeline report", "", f"_Generated {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC_", ""]
        if self.results:
            stage_cols = [s for s in STAGES if any(r.stages.get(s) for r in self.results)]
            out += ["## Scenarios (ms)", ""]
            header = ["scenario", "mode", "diff KB", "changed lines", "verdict", "score", "total", *stage_cols]
            out += ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
            for r in self.results:
                row = [
                    r.scenario,
                    r.mode,
                    f"{r.diff_bytes / 1024:,.1f}",
                    f"{r.changed_lines:,}",
                    r.verdict or "-",
                    f"{r.score:.1f}" if r.score is not None else "-",
                    f"{r.total_s * 1000:,.1f}",
                    *(f"{r.stages.get(s, 0.0) * 1000:,.1f}" for s in stage_cols),
                ]
                out.append("| " + " | ".join(row) + " |")
            quality = [r for r in self.results if "keyword_hit_rate" in r.extra or "error" in r.extra]
            if quality:
                out += ["", "## Live review quality", "", "| scenario | verdict | keyword hit rate | ok | error |"]
                out.append("| --- | --- | --- | --- | --- |")
                for r in quality:
                    rate = r.extra.get("keyword_hit_rate")
                    out.append(
                        f"| {r.scenario} | {r.verdict or '-'} | {f'{rate:.0%}' if rate is not None else '-'} | "
                        f"{r.extra.get('ok', '-')} | {r.extra.get('error', '')} |"
                    )
        if self.throughput:
            out += ["", "## Throughput", ""]
            keys = list(self.throughput[0])
            out += ["| " + " | ".join(keys) + " |", "|" + " --- |" * len(keys)]
            for t in self.throughput:
                out.append("| " + " | ".join(str(t.get(k, "")) for k in keys) + " |")
        return "\n".join(out) + "\n"

    def write(self, directory: Path) -> tuple[Path, Path] | None:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            json_path, md_path = directory / "report.json", directory / "report.md"
            json_path.write_text(self._redact(json.dumps(self.to_dict(), indent=2, ensure_ascii=False)), encoding="utf-8")
            md_path.write_text(self._redact(self.to_markdown()), encoding="utf-8")
        except OSError as exc:
            warnings.warn(f"Could not write E2E report to {directory}: {exc}", stacklevel=2)
            return None
        return json_path, md_path


# --------------------------------------------------------------------------- worker helpers
def fast_forward_jobs() -> int:
    """Make every queued job due now (skips retry backoff without sleeping)."""
    with SessionLocal() as db:
        result = db.execute(update(Job).where(Job.status == "queued").values(next_run_at=utcnow()))
        db.commit()
        return result.rowcount or 0


def pending_jobs() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(("queued", "running")))) or 0


class LoopHttpClient:
    """Use an HTTP client bound to the current event loop (the app lifespan made one on TestClient's loop)."""

    async def __aenter__(self) -> None:
        self._previous = http._client
        self._client = http.create_client()
        http.set_http_client(self._client)

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()
        http.set_http_client(self._previous)


async def drain_worker(*, w: worker.Worker | None = None, max_iterations: int = 1_000) -> int:
    """Run jobs until none are queued, fast-forwarding backoff. Returns the number of jobs executed."""
    w = w or worker.Worker()
    executed = 0
    async with LoopHttpClient():
        for _ in range(max_iterations):
            if await w.run_once():
                executed += 1
                continue
            if not pending_jobs():
                return executed
            fast_forward_jobs()
    raise AssertionError(f"worker did not drain within {max_iterations} iterations")


# --------------------------------------------------------------------------- webhook payloads
def pr_opened_payload(number: int, scenario: DiffScenario, *, owner: str = "acme", repo: str = "api") -> dict:
    return {
        "action": "opened",
        "number": number,
        "pull_request": {"number": number, "title": scenario.title, "user": {"login": "bob", "type": "User"}},
        "repository": {"full_name": f"{owner}/{repo}", "private": False},
        "installation": {"id": 99},
        "sender": {"login": "bob", "type": "User"},
    }


def comment_payload(
    number: int,
    body: str,
    *,
    comment_id: int,
    owner: str = "acme",
    repo: str = "api",
    commenter: str = "alice",
    commenter_type: str = "User",
) -> dict:
    user = {"login": commenter, "type": commenter_type}
    return {
        "action": "created",
        "issue": {"number": number, "title": "PR", "user": {"login": "bob"}, "pull_request": {"url": "x"}},
        "comment": {"id": comment_id, "body": body, "user": user},
        "repository": {"full_name": f"{owner}/{repo}", "private": False},
        "installation": {"id": 99},
        "sender": user,
    }


# --------------------------------------------------------------------------- pipeline facade
class Pipeline:
    """One handle over the app client, fake GitHub, mock Gemini, timer and report for a test."""

    def __init__(
        self, client: Any, github: FakeGitHub, llm: MockGemini | None, timer: StageTimer, report: ReportCollector
    ) -> None:
        self.client = client
        self.github = github
        self.llm = llm
        self.timer = timer
        self.report = report
        self._delivery = 0
        self._comment_id = 500

    def _next_delivery(self) -> str:
        self._delivery += 1
        return f"e2e-{self._delivery}"

    def _send(self, event: str, payload: dict, delivery: str | None) -> tuple[httpx.Response, str]:
        delivery = delivery or self._next_delivery()
        start = time.perf_counter()
        response = post_webhook(self.client, event, payload, delivery)
        elapsed = time.perf_counter() - start
        for job_id in self.job_ids(delivery):
            self.timer.record(job_id, "ingest", elapsed)
        return response, delivery

    def open_pr(
        self, number: int, scenario: DiffScenario, *, delivery: str | None = None, state: str = "open", **kw: Any
    ) -> str:
        self.github.add_pr(number, scenario, state=state, **kw)
        response, delivery = self._send("pull_request", pr_opened_payload(number, scenario, **kw), delivery)
        assert response.status_code == 200, response.text
        return delivery

    def push(self, number: int, scenario: DiffScenario, *, head_sha: str, delivery: str | None = None) -> str:
        self.github.push(number, scenario, head_sha=head_sha)
        payload = {**pr_opened_payload(number, scenario), "action": "synchronize", "after": head_sha}
        response, delivery = self._send("pull_request", payload, delivery)
        assert response.status_code == 200, response.text
        return delivery

    def comment(self, number: int, body: str, *, delivery: str | None = None, **kw: Any) -> str:
        self._comment_id += 1
        payload = comment_payload(number, body, comment_id=self._comment_id, **kw)
        response, delivery = self._send("issue_comment", payload, delivery)
        assert response.status_code == 200, response.text
        return delivery

    @property
    def last_comment_id(self) -> int:
        return self._comment_id

    async def drain(self, w: worker.Worker | None = None) -> int:
        return await drain_worker(w=w)

    async def run_once(self) -> bool:
        """Claim and run a single due job, without fast-forwarding backoff."""
        async with LoopHttpClient():
            return await worker.Worker().run_once()

    # -- DB reads
    @staticmethod
    def job_ids(delivery: str) -> list[int]:
        with SessionLocal() as db:
            return list(
                db.scalars(
                    select(Job.id).join(WebhookEvent, Job.event_id == WebhookEvent.id).where(
                        WebhookEvent.delivery_id == delivery
                    )
                )
            )

    @staticmethod
    def jobs(delivery: str | None = None) -> list[Job]:
        with SessionLocal() as db:
            query = select(Job).order_by(Job.id)
            if delivery:
                query = query.join(WebhookEvent, Job.event_id == WebhookEvent.id).where(
                    WebhookEvent.delivery_id == delivery
                )
            return list(db.scalars(query))

    @staticmethod
    def event(delivery: str) -> WebhookEvent | None:
        with SessionLocal() as db:
            return db.scalar(select(WebhookEvent).where(WebhookEvent.delivery_id == delivery))

    @staticmethod
    def reviews() -> list[PRReview]:
        with SessionLocal() as db:
            return list(db.scalars(select(PRReview).order_by(PRReview.id)))

    def record(
        self, scenario: DiffScenario, delivery: str, *, mode: str = "mocked", label: str | None = None, **extra: Any
    ) -> ScenarioResult:
        """Add the review job of ``delivery`` to the report and return its result."""
        review_jobs = [j for j in self.jobs(delivery) if j.kind == "review"]
        assert review_jobs, f"no review job for delivery {delivery}"
        job = review_jobs[0]
        review = None
        if job.review_id is not None:
            with SessionLocal() as db:
                review = db.get(PRReview, job.review_id)
        stages = self.timer.summary(job.id)
        total = self.timer.totals.get(job.id, 0.0) + stages["ingest"] + stages["claim"]
        result = ScenarioResult(
            scenario=label or scenario.name,
            mode=mode,
            diff_bytes=scenario.diff_bytes,
            changed_lines=count_changed_lines(scenario.diff),
            verdict=review.verdict if review else None,
            score=review.score if review else None,
            total_s=round(total, 6),
            stages=stages,
            extra=extra,
        )
        self.report.add(result)
        return result


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]
