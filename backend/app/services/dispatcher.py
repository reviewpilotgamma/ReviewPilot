"""Translate verified webhook payloads into durable jobs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import utcnow
from app.models import Job, WebhookEvent
from app.services.rules import load_rule_settings

logger = logging.getLogger(__name__)

REVIEW_RE = re.compile(r"(?<![\w@])@review\b[ \t]*(?P<note>[^\n]*)", re.IGNORECASE)
PLAN_RE = re.compile(r"(?<![\w@])@bot\s+plan\b", re.IGNORECASE)
MAX_NOTE_CHARS = 500
MAX_PREVIEW_CHARS = 2_000
INSTALLATION_EVENTS = {"installation", "installation_repositories"}
BOT_SENDER_REASON = "bot sender"


@dataclass
class JobSpec:
    kind: str
    payload: dict[str, Any]


@dataclass
class DispatchResult:
    jobs: list[JobSpec] = field(default_factory=list)
    ignore_reason: str | None = None
    installation_changed: bool = False


def is_bot_event(payload: dict[str, Any]) -> bool:
    sender = payload.get("sender") or {}
    commenter = (payload.get("comment") or {}).get("user") or {}
    return (
        sender.get("type") == "Bot"
        or commenter.get("type") == "Bot"
        or str(sender.get("login", "")).endswith("[bot]")
        or str(commenter.get("login", "")).endswith("[bot]")
    )


def extract_review_note(body: str) -> str | None:
    """Return the note after the first ``@review`` trigger, or ``None`` if there is no trigger."""
    match = REVIEW_RE.search(body)
    if match is None:
        return None
    return match.group("note").strip()[:MAX_NOTE_CHARS]


def has_plan_trigger(body: str) -> bool:
    return PLAN_RE.search(body) is not None


def _repo_parts(payload: dict[str, Any]) -> tuple[str, str] | None:
    full_name = (payload.get("repository") or {}).get("full_name") or ""
    if "/" not in full_name:
        return None
    owner, repo = full_name.split("/", 1)
    return owner, repo


def _review_queued(db: Session, owner: str, repo: str, pr_number: Any) -> bool:
    """True when a review job for this PR is waiting to run (not yet claimed by the worker)."""
    target = (owner.lower(), repo.lower(), pr_number)
    for raw in db.scalars(select(Job.payload).where(Job.kind == "review", Job.status == "queued")):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if (str(data.get("owner", "")).lower(), str(data.get("repo", "")).lower(), data.get("pr_number")) == target:
            return True
    return False


def plan_jobs(db: Session, event: str, payload: dict[str, Any]) -> DispatchResult:
    action = payload.get("action")

    if event in INSTALLATION_EVENTS:
        return DispatchResult(installation_changed=True)

    parts = _repo_parts(payload)
    installation_id = (payload.get("installation") or {}).get("id")

    if event == "pull_request" and action == "opened":
        if parts is None or installation_id is None:
            return DispatchResult(ignore_reason="missing repository or installation")
        owner, repo = parts
        pr = payload.get("pull_request") or {}
        base = {
            "installation_id": installation_id,
            "owner": owner,
            "repo": repo,
            "pr_number": pr.get("number"),
            "author": (pr.get("user") or {}).get("login", ""),
        }
        rules = load_rule_settings(db, f"{owner}/{repo}")
        if rules.review_mode == "auto":
            return DispatchResult(jobs=[JobSpec("review", {**base, "trigger": "auto", "requester": None})])
        return DispatchResult(jobs=[JobSpec("welcome", base)])

    if event == "pull_request" and action == "synchronize":
        if parts is None or installation_id is None:
            return DispatchResult(ignore_reason="missing repository or installation")
        owner, repo = parts
        pr = payload.get("pull_request") or {}
        if load_rule_settings(db, f"{owner}/{repo}").review_mode != "auto":
            return DispatchResult(ignore_reason="on-demand mode")
        if _review_queued(db, owner, repo, pr.get("number")):
            # A burst of pushes gets one follow-up: the queued job reads the newest head when it runs.
            return DispatchResult(ignore_reason="review already queued")
        base = {
            "installation_id": installation_id,
            "owner": owner,
            "repo": repo,
            "pr_number": pr.get("number"),
            "author": (pr.get("user") or {}).get("login", ""),
        }
        return DispatchResult(jobs=[JobSpec("review", {**base, "trigger": "push", "requester": None})])

    if event == "issue_comment" and action == "created":
        issue = payload.get("issue") or {}
        if "pull_request" not in issue:
            return DispatchResult(ignore_reason="not a pull request")
        if parts is None or installation_id is None:
            return DispatchResult(ignore_reason="missing repository or installation")
        owner, repo = parts
        comment = payload.get("comment") or {}
        body = comment.get("body") or ""
        base = {
            "installation_id": installation_id,
            "owner": owner,
            "repo": repo,
            "pr_number": issue.get("number"),
            "author": (issue.get("user") or {}).get("login", ""),
        }
        jobs: list[JobSpec] = []
        note = extract_review_note(body)
        if note is not None:
            jobs.append(
                JobSpec(
                    "review",
                    {
                        **base,
                        "trigger": "comment",
                        "requester": (comment.get("user") or {}).get("login"),
                        "requester_note": note,
                        "comment_id": comment.get("id"),
                    },
                )
            )
        if has_plan_trigger(body):
            jobs.append(JobSpec("plan", base))
        if not jobs:
            return DispatchResult(ignore_reason="no trigger")
        return DispatchResult(jobs=jobs)

    return DispatchResult(ignore_reason="unhandled event")


def build_preview(event: str, payload: dict[str, Any]) -> str:
    pr = payload.get("pull_request") or payload.get("issue") or {}
    comment = payload.get("comment") or {}
    preview = {
        "event": event,
        "action": payload.get("action"),
        "repo": (payload.get("repository") or {}).get("full_name"),
        "sender": (payload.get("sender") or {}).get("login"),
        "pr_number": pr.get("number"),
        "pr_title": pr.get("title"),
        "comment_excerpt": (comment.get("body") or "")[:200] or None,
        "installation_id": (payload.get("installation") or {}).get("id"),
    }
    preview = {k: v for k, v in preview.items() if v is not None}
    return json.dumps(preview, ensure_ascii=False)[:MAX_PREVIEW_CHARS]


@dataclass
class IngestResult:
    status: str
    jobs: int = 0
    installation_changed: bool = False


def ingest(db: Session, *, event: str, delivery_id: str | None, payload: dict[str, Any]) -> IngestResult:
    """Record the event and its jobs atomically. Duplicate deliveries are acknowledged and skipped."""
    if delivery_id and db.scalar(select(WebhookEvent.id).where(WebhookEvent.delivery_id == delivery_id)):
        return IngestResult(status="duplicate")

    record = WebhookEvent(
        delivery_id=delivery_id,
        event=event,
        action=payload.get("action"),
        repo=((payload.get("repository") or {}).get("full_name") or "").lower() or None,
        sender=(payload.get("sender") or {}).get("login"),
        payload_preview=build_preview(event, payload),
        status="ignored",
    )

    result = DispatchResult()
    if event == "ping":
        record.status = "processed"
    elif is_bot_event(payload):
        record.error_message = BOT_SENDER_REASON
    else:
        result = plan_jobs(db, event, payload)
        if result.jobs:
            record.status = "queued"
        elif result.installation_changed:
            record.status = "processed"
        else:
            record.error_message = result.ignore_reason

    db.add(record)
    try:
        db.flush()
        max_attempts = get_settings().JOB_MAX_ATTEMPTS
        now = utcnow()
        for spec in result.jobs:
            db.add(
                Job(
                    event_id=record.id,
                    kind=spec.kind,
                    payload=json.dumps(spec.payload),
                    status="queued",
                    max_attempts=max_attempts,
                    next_run_at=now,
                )
            )
        db.commit()
    except IntegrityError:
        # Concurrent delivery of the same id won the race.
        db.rollback()
        return IngestResult(status="duplicate")

    return IngestResult(status=record.status, jobs=len(result.jobs), installation_changed=result.installation_changed)
