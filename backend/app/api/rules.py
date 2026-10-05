"""Per-repository review rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from app.api.deps import Accessible, AccessibleRepo, CurrentUser, DbSession, csrf_protect
from app.models import RepoRule
from app.schemas.rules import PresetOut, RuleIn, RuleOut
from app.services import rules as rules_service
from app.services.prompts import DEFAULT_RULES, RULE_PRESETS

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(csrf_protect)])


def _default_rule(repo_full_name: str) -> RuleOut:
    return RuleOut(
        repo_full_name=repo_full_name,
        custom_instructions=DEFAULT_RULES.custom_instructions,
        verbosity=DEFAULT_RULES.verbosity,
        review_mode=DEFAULT_RULES.review_mode,
        enable_security=DEFAULT_RULES.enable_security,
        updated_at=None,
        is_default=True,
    )


@router.get("/presets", response_model=list[PresetOut])
def presets() -> list[dict[str, str]]:
    return RULE_PRESETS


@router.get("", response_model=list[RuleOut])
def list_rules(db: DbSession, accessible: Accessible) -> list[RuleOut]:
    repos = sorted(accessible)
    stored = (
        {rule.repo_full_name: rule for rule in db.scalars(select(RepoRule).where(RepoRule.repo_full_name.in_(repos)))}
        if repos
        else {}
    )
    return [RuleOut.model_validate(stored[name]) if name in stored else _default_rule(name) for name in repos]


@router.get("/{owner}/{repo}", response_model=RuleOut)
def get_rule(db: DbSession, full_name: AccessibleRepo) -> RuleOut:
    rule = rules_service.get_rule(db, full_name)
    return RuleOut.model_validate(rule) if rule else _default_rule(full_name)


@router.put("/{owner}/{repo}", response_model=RuleOut)
def put_rule(body: RuleIn, db: DbSession, user: CurrentUser, full_name: AccessibleRepo) -> RuleOut:
    rule = rules_service.upsert_rule(
        db,
        full_name,
        custom_instructions=body.custom_instructions,
        verbosity=body.verbosity.value,
        review_mode=body.review_mode.value,
        enable_security=body.enable_security,
        user_id=user.id,
    )
    return RuleOut.model_validate(rule)


@router.delete("/{owner}/{repo}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(db: DbSession, full_name: AccessibleRepo) -> Response:
    rules_service.delete_rule(db, full_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
