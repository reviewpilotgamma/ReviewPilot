"""Repository rule persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import RepoRule
from app.services.prompts import DEFAULT_RULES, RuleSettings


def normalize_repo(full_name: str) -> str:
    return full_name.strip().lower()


def get_rule(db: Session, repo_full_name: str) -> RepoRule | None:
    return db.get(RepoRule, normalize_repo(repo_full_name))


def load_rule_settings(db: Session, repo_full_name: str) -> RuleSettings:
    """Stored rules for a repository, or defaults when none exist (never inserts)."""
    rule = get_rule(db, repo_full_name)
    if rule is None:
        return DEFAULT_RULES
    return RuleSettings(
        custom_instructions=rule.custom_instructions,
        verbosity=rule.verbosity,
        review_mode=rule.review_mode,
        enable_security=rule.enable_security,
    )


def upsert_rule(
    db: Session,
    repo_full_name: str,
    *,
    custom_instructions: str,
    verbosity: str,
    review_mode: str,
    enable_security: bool,
    user_id: int | None,
) -> RepoRule:
    key = normalize_repo(repo_full_name)
    rule = db.get(RepoRule, key) or RepoRule(repo_full_name=key)
    rule.custom_instructions = custom_instructions
    rule.verbosity = verbosity
    rule.review_mode = review_mode
    rule.enable_security = enable_security
    rule.updated_by_user_id = user_id
    rule.updated_at = utcnow()
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, repo_full_name: str) -> None:
    rule = get_rule(db, repo_full_name)
    if rule is not None:
        db.delete(rule)
        db.commit()
