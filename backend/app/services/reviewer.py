"""Review orchestration: job handlers for ``review``, ``welcome`` and ``plan`` jobs.

Handlers are async; all database access runs in worker threads via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.models import Job, PRReview
from app.services import gemini, golden_prompt
from app.services import github_app as gh
from app.services.diff_batching import (
    CHARS_PER_TOKEN,
    BatchPlan,
    DiffBatch,
    count_changed_lines,
    plan_batches,
    token_ceiling_chars,
)
from app.services.documents import ensure_context_cache, list_documents
from app.services.errors import (
    ContextTooLargeError,
    DiffFetchError,
    DiffTooLargeError,
    GeminiTransientError,
    GitHubPermanentError,
    ServiceError,
)
from app.services.github_app import PullRequest
from app.services.prompts import (
    MERGE_SYSTEM_PROMPT,
    RuleSettings,
    build_batch_context,
    build_merge_content,
    build_plan_system_prompt,
    build_pr_context,
    build_review_system_prompt,
)
from app.services.replies import render_reply
from app.services.review_parser import SCORE_RANGES, ParsedReview, _section, parse_review
from app.services.rules import load_rule_settings

logger = logging.getLogger(__name__)

BANNER = "## ReviewPilot Architectural Audit"
FOOTER = "_Triggered via ReviewPilot · Architecture Gatekeeper_"
PLAN_BANNER = "## 🧭 ReviewPilot Execution Plan"
PLAN_FOOTER = "_Triggered via ReviewPilot · @bot plan_"
COMMENT_TRUNCATION_NOTE = (
    "\n\n_…review truncated to fit GitHub's comment limit. Full report available in the ReviewPilot dashboard._"
)
PLAN_MAX_DIFF_CHARS = 40_000
PLAN_MAX_OUTPUT_TOKENS = 2048
VERDICT_LABELS = {"passed": "🟢 Passed", "warning": "🟡 Warning", "critical": "🔴 Critical Risk"}
# Markdown collapses plain spaces, so em-space entities keep the verdict line readable.
META_SEPARATOR = "&emsp;·&emsp;"
VERDICT_RANK = {"passed": 0, "warning": 1, "critical": 2}

# Batched reviews of large diffs.
BATCH_ATTEMPTS = 2
BATCH_RETRY_DELAYS = (2.0,)
MERGE_RESERVE_SECONDS = 120.0
MIN_BATCH_PHASE_RATIO = 0.6
MAX_LISTED_FILES = 50
FALLBACK_SUMMARY = "This PR was reviewed in {total} parts; the combined summary was generated automatically."
MERGED_SECTIONS = ("Architectural Findings", "Specific Recommendations", "What Looks Solid")


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


def list_files(paths: Sequence[str], limit: int = MAX_LISTED_FILES) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:limit])
    return shown + (f" and {len(paths) - limit} more" if len(paths) > limit else "")


def worst_verdict(*verdicts: str) -> str:
    return max(verdicts, key=VERDICT_RANK.__getitem__)


def enforce_verdict_floor(merged: ParsedReview, batch_verdicts: Sequence[str]) -> ParsedReview:
    """Never let the merged verdict be better than the worst batch verdict; keep the score in the verdict's range."""
    verdict = worst_verdict(merged.verdict, *batch_verdicts)
    low, high = SCORE_RANGES[verdict]
    score = round(min(high, max(low, merged.score)), 1)
    return dataclasses.replace(merged, verdict=verdict, score=score)


def fallback_merge(parts: Sequence[tuple[int, ParsedReview]], total: int) -> ParsedReview:
    """Join batch reviews section by section when the merge call fails."""
    summary = FALLBACK_SUMMARY.format(total=total)
    sections = [f"### Executive Summary\n{summary}"]
    for title in MERGED_SECTIONS:
        chunks = [f"_Part {n} of {total}_\n\n{text}" for n, p in parts if (text := _section(p.body, title))]
        sections.append(f"### {title}\n" + ("\n\n".join(chunks) if chunks else "_None._"))
    verdict = worst_verdict(*(p.verdict for _, p in parts))
    return ParsedReview(
        body="\n\n".join(sections),
        summary=summary,
        score=min(p.score for _, p in parts),
        verdict=verdict,
        meta_found=False,
    )


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
    total_files: int = 0,
    not_reviewed: Sequence[str] = (),
    split_files: Sequence[str] = (),
    filtered: Sequence[str] = (),
) -> str:
    header = [
        BANNER,
        "",
        f"**Verdict:** {VERDICT_LABELS[parsed.verdict]}{META_SEPARATOR}"
        f"**Health score:** {parsed.score:.1f}/10{META_SEPARATOR}**Lines reviewed:** {lines_reviewed:,}",
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
    if not_reviewed:
        reviewed = max(0, total_files - len(not_reviewed))
        header.append(
            f"> ⚠️ Partially reviewed: {reviewed:,} of {total_files:,} files. Not reviewed: {list_files(not_reviewed)}"
        )
    if split_files:
        header.append(f"> ⚠️ Lines too long to review whole were split in: {list_files(split_files)}")
    if filtered:
        header.append(f"_Not reviewed (generated or lockfiles): {list_files(filtered)}_")
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


async def _docs_for_prompt(repo_full_name: str) -> tuple[str | None, str | None, list[str]]:
    """Return (cached_content name, inline documents text for fallback, document filenames)."""
    with SessionLocal() as db:
        cached, inline = await ensure_context_cache(db, repo_full_name)
        filenames = sorted(doc.filename for doc in list_documents(db, repo_full_name))
    return cached, (inline or None), filenames


def build_review_context(
    prompt: golden_prompt.EffectivePrompt,
    rules: RuleSettings,
    *,
    cached: str | None,
    inline_docs: str | None,
    filenames: list[str],
    requester_note: str | None,
) -> dict[str, Any]:
    """What this review was reviewed with. Filenames only; never document content."""
    return {
        "prompt": "default" if prompt.is_default else "custom",
        "prompt_updated_at": prompt.updated_at.isoformat() if prompt.updated_at else None,
        "instructions_chars": len(rules.custom_instructions.strip()),
        "verbosity": rules.verbosity,
        "security": rules.enable_security,
        "documents": filenames if (cached or inline_docs) else [],
        "documents_mode": "cached" if cached else "inline" if inline_docs else "none",
        "requester_note": bool(requester_note),
    }


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


# --------------------------------------------------------------------------- batched review
@dataclass(frozen=True)
class BatchOutcome:
    number: int
    batch: DiffBatch
    parsed: ParsedReview | None = None
    model: str | None = None
    error: BaseException | None = None


@dataclass(frozen=True)
class BatchedReview:
    parsed: ParsedReview
    model: str
    lines_reviewed: int
    not_reviewed: list[str]


async def _fetch_diff(ctx: JobContext) -> str:
    try:
        return await gh.get_pull_diff(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number)
    except GitHubPermanentError as exc:
        if exc.status_code == 406:
            raise DiffTooLargeError(str(exc), exc.status_code) from exc
        raise DiffFetchError(str(exc), exc.status_code) from exc


def _plan_review(
    settings: Settings,
    pr: PullRequest,
    ctx: JobContext,
    diff: str,
    system_prompt: str,
    inline_docs: str | None,
) -> BatchPlan:
    """Batch the diff so each request (system prompt + documents + batch context) fits the context window."""
    files_hint = [("x" * 80, 0, 0)] * min(pr.changed_files, 500)
    context_overhead = len(build_batch_context(pr, ctx.owner, ctx.repo, "", index=99, total=99, manifest=files_hint))
    ceiling = token_ceiling_chars(
        context_tokens=settings.GEMINI_CONTEXT_TOKENS,
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        reserved_chars=len(system_prompt) + len(inline_docs or "") + context_overhead,
    )
    try:
        return plan_batches(
            diff,
            target_chars=settings.DIFF_BATCH_TOKENS * CHARS_PER_TOKEN,
            ceiling_chars=ceiling,
            max_batches=settings.MAX_DIFF_BATCHES,
        )
    except ValueError as exc:
        raise ContextTooLargeError(str(exc)) from exc


async def _review_one_batch(
    number: int,
    batch: DiffBatch,
    user_content: str,
    *,
    system_prompt: str,
    cached: str | None,
    inline_docs: str | None,
    semaphore: asyncio.Semaphore,
    deadline: float,
) -> BatchOutcome:
    """Review one batch with a bounded retry. Never raises: failures are returned in the outcome."""
    loop = asyncio.get_running_loop()
    error: BaseException = GeminiTransientError("batch time limit reached")
    for attempt in range(BATCH_ATTEMPTS):
        if attempt:
            delay = BATCH_RETRY_DELAYS[min(attempt, len(BATCH_RETRY_DELAYS)) - 1]
            if loop.time() + delay >= deadline:
                break
            await asyncio.sleep(delay)
        async with semaphore:
            if loop.time() >= deadline:
                return BatchOutcome(number, batch, error=GeminiTransientError("batch time limit reached"))
            try:
                result = await gemini.generate(
                    system_prompt, user_content, cached_content=cached, inline_documents=inline_docs
                )
            except GeminiTransientError as exc:
                error = exc
                continue
            except Exception as exc:  # noqa: BLE001 - a failed batch must not fail the whole review
                return BatchOutcome(number, batch, error=exc)
        return BatchOutcome(number, batch, parsed=parse_review(result.text), model=result.model)
    return BatchOutcome(number, batch, error=error)


async def _review_batches(
    settings: Settings,
    ctx: JobContext,
    pr: PullRequest,
    plan: BatchPlan,
    *,
    system_prompt: str,
    cached: str | None,
    inline_docs: str | None,
) -> list[BatchOutcome]:
    loop = asyncio.get_running_loop()
    budget = settings.JOB_TIMEOUT_SECONDS
    deadline = loop.time() + max(budget - MERGE_RESERVE_SECONDS, budget * MIN_BATCH_PHASE_RATIO)
    semaphore = asyncio.Semaphore(settings.DIFF_BATCH_CONCURRENCY)
    manifest = [(f.path, f.additions, f.deletions) for f in plan.files]
    total = len(plan.batches)
    tasks = [
        asyncio.create_task(
            _review_one_batch(
                number,
                batch,
                build_batch_context(pr, ctx.owner, ctx.repo, batch.text, index=number, total=total, manifest=manifest),
                system_prompt=system_prompt,
                cached=cached,
                inline_docs=inline_docs,
                semaphore=semaphore,
                deadline=deadline,
            )
        )
        for number, batch in enumerate(plan.batches, start=1)
    ]
    try:
        await asyncio.wait(tasks, timeout=max(0.0, deadline - loop.time()))
    finally:
        pending = [t for t in tasks if not t.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    outcomes = []
    for number, (task, batch) in enumerate(zip(tasks, plan.batches, strict=True), start=1):
        if task.cancelled():
            outcomes.append(BatchOutcome(number, batch, error=GeminiTransientError("batch time limit reached")))
        else:
            outcomes.append(task.result())
    return outcomes


async def _merge_reviews(
    ctx: JobContext, pr: PullRequest, parts: list[tuple[int, list[str], ParsedReview]], total: int
) -> tuple[ParsedReview, str | None]:
    """One LLM call that merges the batch reviews; joined in code if the call fails."""
    content = build_merge_content(
        pr, ctx.owner, ctx.repo, [(n, paths, p.verdict, p.score, p.body) for n, paths, p in parts], total
    )
    try:
        result = await gemini.generate(MERGE_SYSTEM_PROMPT, content)
    except ServiceError as exc:
        logger.warning("Merging %s batch reviews failed (%s); joining them in code", len(parts), exc)
        return fallback_merge([(n, p) for n, _, p in parts], total), None
    return parse_review(result.text), result.model


async def _review_in_batches(
    settings: Settings,
    ctx: JobContext,
    pr: PullRequest,
    plan: BatchPlan,
    *,
    system_prompt: str,
    cached: str | None,
    inline_docs: str | None,
) -> BatchedReview:
    outcomes = await _review_batches(
        settings, ctx, pr, plan, system_prompt=system_prompt, cached=cached, inline_docs=inline_docs
    )
    succeeded = [o for o in outcomes if o.parsed is not None]
    failed = [o for o in outcomes if o.parsed is None]
    for outcome in failed:
        logger.warning("Batch %s of %s was not reviewed: %s", outcome.number, len(outcomes), outcome.error)
    if not succeeded:
        error = failed[0].error
        if isinstance(error, ServiceError):
            raise error
        raise GeminiTransientError("all review batches failed") from error

    parts = [(o.number, o.batch.paths, o.parsed) for o in succeeded if o.parsed is not None]
    merged, merge_model = await _merge_reviews(ctx, pr, parts, len(outcomes))
    merged = enforce_verdict_floor(merged, [p.verdict for _, _, p in parts])

    not_reviewed: list[str] = []
    for path in [p for o in failed for p in o.batch.paths] + plan.overflow:
        if path not in not_reviewed:
            not_reviewed.append(path)
    logger.info(
        "Reviewed %s#%s in %s batches (%s failed, %s files not reviewed)",
        ctx.repo_full_name,
        ctx.pr_number,
        len(outcomes),
        len(failed),
        len(not_reviewed),
    )
    return BatchedReview(
        parsed=merged,
        model=merge_model or succeeded[0].model or settings.GEMINI_MODEL,
        lines_reviewed=sum(o.batch.changed_lines for o in succeeded),
        not_reviewed=not_reviewed,
    )


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

    diff = await _fetch_diff(ctx)
    if not diff.strip():
        await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, render_reply("empty_diff"))
        return

    diff_for_prompt, truncated = truncate_diff(diff, settings.MAX_DIFF_CHARS)
    rules = await asyncio.to_thread(_load_rules, ctx.repo_full_name)
    prompt = await asyncio.to_thread(_load_prompt)
    cached, inline_docs, filenames = await _docs_for_prompt(ctx.repo_full_name)

    requester_note = ctx.data.get("requester_note") or None
    system_prompt = build_review_system_prompt(rules, requester_note, prompt.template)
    plan = _plan_review(settings, pr, ctx, diff_for_prompt, system_prompt, inline_docs)

    if not plan.batches:
        reply = render_reply("empty_diff")
        if plan.filtered:
            reply += f"\n\n_Not reviewed (generated or lockfiles): {list_files(plan.filtered)}_"
        await gh.post_issue_comment(ctx.installation_id, ctx.owner, ctx.repo, ctx.pr_number, reply)
        return

    if len(plan.batches) == 1 and not plan.cut_files and not plan.overflow:
        # Same request as before batching existed; only the noise files are dropped when there are any.
        batch_diff = plan.batches[0].text if plan.filtered else diff_for_prompt
        result = await gemini.generate(
            system_prompt,
            build_pr_context(pr, ctx.owner, ctx.repo, batch_diff),
            cached_content=cached,
            inline_documents=inline_docs,
        )
        parsed, model = parse_review(result.text), result.model
        lines_reviewed = plan.batches[0].changed_lines if plan.filtered else count_changed_lines(diff)
        not_reviewed: list[str] = []
    else:
        outcome = await _review_in_batches(
            settings, ctx, pr, plan, system_prompt=system_prompt, cached=cached, inline_docs=inline_docs
        )
        parsed, model, lines_reviewed, not_reviewed = (
            outcome.parsed,
            outcome.model,
            outcome.lines_reviewed,
            outcome.not_reviewed,
        )

    diff_truncated = truncated or bool(not_reviewed) or bool(plan.cut_files)
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
        total_files=len(plan.files) - len(plan.filtered),
        not_reviewed=not_reviewed,
        split_files=plan.cut_files,
        filtered=plan.filtered,
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
        diff_truncated=diff_truncated,
        model=model,
        review_context=json.dumps(
            build_review_context(
                prompt,
                rules,
                cached=cached,
                inline_docs=inline_docs,
                filenames=filenames,
                requester_note=requester_note,
            )
        ),
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
    diff = await _fetch_diff(ctx)

    limit = effective_diff_limit(get_settings().MAX_DIFF_CHARS, PLAN_MAX_DIFF_CHARS)
    diff_for_prompt, _ = truncate_diff(diff, limit)
    rules = await asyncio.to_thread(_load_rules, ctx.repo_full_name)
    cached, inline_docs, _ = await _docs_for_prompt(ctx.repo_full_name)

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
