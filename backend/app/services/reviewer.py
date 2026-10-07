"""Review orchestration: job handlers for ``review``, ``welcome`` and ``plan`` jobs.

Handlers are async; all database access runs in worker threads via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Job, PRReview
from app.services import gemini, golden_prompt
from app.services import github_app as gh
from app.services.documents import ensure_context_cache
from app.services.errors import DiffFetchError, GitHubPermanentError, ServiceError
from app.services.prompts import (
    RuleSettings,
    build_plan_system_prompt,
    build_pr_context,
    build_review_system_prompt,
)
from app.services.replies import render_reply
from app.services.review_parser import ParsedReview, parse_review
from app.services.rules import load_rule_settings

logger = logging.getLogger(__name__)

BANNER = "## ✈️ ReviewPilot Architectural Audit"
FOOTER = "_Triggered via ReviewPilot · Architecture Gatekeeper_"
PLAN_BANNER = "## 🧭 ReviewPilot Execution Plan"
PLAN_FOOTER = "_Triggered via ReviewPilot · @bot plan_"
COMMENT_TRUNCATION_NOTE = (
    "\n\n_…review truncated to fit GitHub's comment limit. Full report available in the ReviewPilot dashboard._"
)
PLAN_MAX_DIFF_CHARS = 40_000
PLAN_MAX_OUTPUT_TOKENS = 2048
VERDICT_LABELS = {"passed": "🟢 Passed", "warning": "🟡 Warning", "critical": "🔴 Critical Risk"}


@dataclass(frozen=True)
class JobContext:
    job_id: int
    kind: str
    data: dict[str, Any]
    review_id: int | None
    attempts: int
    max_attempts: int

    @property
    def installation_id(self) -> int:
        return int(self.data["installation_id"])

    @property
    def owner(self) -> str:
        return self.data["owner"]

    @property
    def repo(self) -> str:
        return self.data["repo"]

    @property
    def pr_number(self) -> int:
        return int(self.data["pr_number"])

    @property
    def repo_full_name(self) -> str:
        return f"{self.owner}/{self.repo}".lower()


# --------------------------------------------------------------------------- pure helpers
def truncate_diff(diff: str, limit: int) -> tuple[str, bool]:
    """Return (diff, truncated). ``limit <= 0`` means no truncation."""
    if limit <= 0 or len(diff) <= limit:
        return diff, False
    cut = diff.rfind("\n", 0, limit)
    cut = cut if cut > 0 else limit
    omitted = len(diff) - cut
    note = (
        f"\n\n[... DIFF TRUNCATED: {omitted:,} characters omitted (limit {limit:,}). "
        "Review covers only the portion above. ...]\n"
    )
    return diff[:cut] + note, True


def effective_diff_limit(settings_limit: int, *caps: int) -> int:
    """Combine the configured limit with optional secondary caps.

    ``settings_limit <= 0`` means unlimited for reviews. When secondary caps are
    provided (e.g. plan jobs), those caps still apply.
    """
    if caps:
        return min(caps) if settings_limit <= 0 else min(settings_limit, *caps)
    return settings_limit


def count_changed_lines(diff: str) -> int:
    return sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))


def _truncate_to(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit)
    return text[: cut if cut > 0 else limit]


def assemble_comment(
    parsed: ParsedReview,
    *,
    lines_reviewed: int,
    trigger: str,
    requester: str | None,
    requester_note: str | None,
    diff_truncated: bool,
    max_chars: int,
    max_diff_chars: int,
) -> str:
    header = [
        BANNER,
        "",
        f"**Verdict:** {VERDICT_LABELS[parsed.verdict]}   ·   "
        f"**Health score:** {parsed.score:.1f}/10   ·   **Lines reviewed:** {lines_reviewed:,}",
    ]
    if trigger == "comment" and requester:
        note = f": “{requester_note}”" if requester_note else ""
        header.append(f"_Requested by @{requester}{note}_")
    if diff_truncated:
        header.append(
            f"> ⚠️ This PR's diff exceeded {max_diff_chars:,} characters; only the first portion was reviewed."
            if max_diff_chars > 0
            else "> ⚠️ This PR's diff was truncated; only the first portion was reviewed."
        )
    head = "\n".join(header) + "\n\n"
    tail = f"\n\n---\n{FOOTER}"

    body = parsed.body
    budget = max_chars - len(head) - len(tail)
    if len(body) > budget:
        body = _truncate_to(body, budget - len(COMMENT_TRUNCATION_NOTE)) + COMMENT_TRUNCATION_NOTE
    return head + body + tail


# --------------------------------------------------------------------------- DB helpers (sync)
def _load_rules(repo_full_name: str) -> RuleSettings:
    with SessionLocal() as db:
        return load_rule_settings(db, repo_full_name)


def _load_prompt() -> golden_prompt.EffectivePrompt:
    with SessionLocal() as db:
        return golden_prompt.load_effective(db)


async def _docs_for_prompt(repo_full_name: str) -> tuple[str | None, str | None]:
    """Return (cached_content name, inline documents text for fallback)."""
    with SessionLocal() as db:
        cached, inline = await ensure_context_cache(db, repo_full_name)
    return cached, (inline or None)


def _load_review(review_id: int) -> tuple[str, int | None] | None:
    with SessionLocal() as db:
        review = db.get(PRReview, review_id)
        return (review.full_markdown, review.github_comment_id) if review else None


def _save_review(job_id: int, review: PRReview) -> int:
    """Persist the review and link it to the job in a single transaction."""
    with SessionLocal() as db:
        db.add(review)
        db.flush()
        job = db.get(Job, job_id)
        if job is not None:
            job.review_id = review.id
        db.commit()
        return review.id


def _mark_posted(review_id: int, comment_id: int) -> None:
    with SessionLocal() as db:
        review = db.get(PRReview, review_id)
        if review is not None:
            review.github_comment_id = comment_id
            db.commit()


# --------------------------------------------------------------------------- handlers
async def _post_review(ctx: JobContext, review_id: int, markdown: str) -> None:
    comment_id = await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, markdown)
    await asyncio.to_thread(_mark_posted, review_id, comment_id)


async def handle_review(ctx: JobContext) -> None:
    settings = get_settings()

    # Idempotent retry: never call the LLM twice for the same job.
    if ctx.review_id is not None:
        stored = await asyncio.to_thread(_load_review, ctx.review_id)
        if stored is not None:
            markdown, comment_id = stored
            if comment_id is None:
                await _post_review(ctx, ctx.review_id, markdown)
            return

    comment_id = ctx.data.get("comment_id")
    if comment_id and ctx.attempts == 1:
        await gh.add_reaction(ctx.installation_id, ctx.owner, ctx.repo, int(comment_id), "eyes")

    pr = await gh.get_pull(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number)
    if pr.state == "closed":
        logger.info("PR %s#%s is closed; skipping review", ctx.repo_full_name, ctx.pr_number)
        return

    try:
        diff = await gh.get_pull_diff(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number)
    except GitHubPermanentError as exc:
        raise DiffFetchError(str(exc), exc.status_code) from exc

    if not diff.strip():
        await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, render_reply("empty_diff"))
        return

    lines_reviewed = count_changed_lines(diff)
    diff_for_prompt, truncated = truncate_diff(diff, settings.MAX_DIFF_CHARS)
    rules = await asyncio.to_thread(_load_rules, ctx.repo_full_name)
    prompt = await asyncio.to_thread(_load_prompt)
    cached, inline_docs = await _docs_for_prompt(ctx.repo_full_name)

    requester_note = ctx.data.get("requester_note") or None
    result = await gemini.generate(
        build_review_system_prompt(rules, requester_note, prompt.template),
        build_pr_context(pr, ctx.owner, ctx.repo, diff_for_prompt),
        cached_content=cached,
        inline_documents=inline_docs,
    )
    parsed = parse_review(result.text)
    trigger = ctx.data.get("trigger", "comment")
    markdown = assemble_comment(
        parsed,
        lines_reviewed=lines_reviewed,
        trigger=trigger,
        requester=ctx.data.get("requester"),
        requester_note=requester_note,
        diff_truncated=truncated,
        max_chars=settings.MAX_COMMENT_CHARS,
        max_diff_chars=settings.MAX_DIFF_CHARS,
    )

    review = PRReview(
        repo_full_name=ctx.repo_full_name,
        pr_number=ctx.pr_number,
        pr_title=pr.title[:500],
        author=pr.author,
        summary=parsed.summary,
        full_markdown=markdown,
        verdict=parsed.verdict,
        score=parsed.score,
        lines_reviewed=lines_reviewed,
        trigger=trigger,
        requester=ctx.data.get("requester"),
        diff_truncated=truncated,
        model=result.model,
    )
    review_id = await asyncio.to_thread(_save_review, ctx.job_id, review)
    await _post_review(ctx, review_id, markdown)
    logger.info(
        "Posted review %s for %s#%s (verdict=%s score=%.1f)",
        review_id,
        ctx.repo_full_name,
        ctx.pr_number,
        parsed.verdict,
        parsed.score,
    )


async def handle_welcome(ctx: JobContext) -> None:
    body = render_reply("welcome", author=ctx.data.get("author", ""), app_name="ReviewPilot")
    await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, body)


async def handle_plan(ctx: JobContext) -> None:
    pr = await gh.get_pull(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number)
    try:
        diff = await gh.get_pull_diff(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number)
    except GitHubPermanentError as exc:
        raise DiffFetchError(str(exc), exc.status_code) from exc

    limit = effective_diff_limit(get_settings().MAX_DIFF_CHARS, PLAN_MAX_DIFF_CHARS)
    diff_for_prompt, _ = truncate_diff(diff, limit)
    rules = await asyncio.to_thread(_load_rules, ctx.repo_full_name)
    cached, inline_docs = await _docs_for_prompt(ctx.repo_full_name)

    try:
        result = await gemini.generate(
            build_plan_system_prompt(rules),
            build_pr_context(pr, ctx.owner, ctx.repo, diff_for_prompt),
            max_output_tokens=PLAN_MAX_OUTPUT_TOKENS,
            cached_content=cached,
            inline_documents=inline_docs,
        )
        body = f"{PLAN_BANNER}\n{result.text.strip()}\n\n---\n{PLAN_FOOTER}"
    except ServiceError as exc:
        if exc.retryable:
            raise
        logger.warning("Plan generation failed permanently (%s); using canned plan", exc)
        body = render_reply("plan")

    await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, body)


HANDLERS = {"review": handle_review, "welcome": handle_welcome, "plan": handle_plan}


async def post_failure_comment(ctx: JobContext, exc: BaseException) -> None:
    """Tell the developer the job failed. Best effort: never raises."""
    if ctx.kind not in ("review", "plan"):
        return
    reason = exc.user_reason if isinstance(exc, ServiceError) else "unexpected error"
    try:
        await gh.post_issue_comment(
            ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, render_reply("error", reason=reason)
        )
    except ServiceError as post_exc:
        logger.warning("Could not post failure comment for job %s: %s", ctx.job_id, post_exc)
    except Exception:  # noqa: BLE001
        logger.exception("Could not post failure comment for job %s", ctx.job_id)
