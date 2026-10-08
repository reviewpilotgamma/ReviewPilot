"""Read (any signed-in user) and edit (admins) the org-wide golden review prompt."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import AdminUser, CurrentUser, DbSession, csrf_protect
from app.schemas.prompt import PromptIn, PromptOut
from app.services import golden_prompt as gp
from app.services.prompts import (
    NO_INSTRUCTIONS,
    NO_NOTE,
    REVIEW_SLOTS,
    SECURITY_DISABLED_DIRECTIVE,
    SECURITY_ENABLED_DIRECTIVE,
    VERBOSITY_DIRECTIVES,
)

router = APIRouter(prefix="/prompt", tags=["prompt"], dependencies=[Depends(csrf_protect)])


def _out(prompt: gp.EffectivePrompt) -> PromptOut:
    _, warnings = gp.validate_template(prompt.template)
    return PromptOut(
        template=prompt.template,
        is_default=prompt.is_default,
        updated_at=prompt.updated_at,
        updated_by=prompt.updated_by,
        segments=gp.segments(prompt.template),
        slots=[
            {"name": name, "label": gp.SLOT_LABELS[name], "required": name in gp.REQUIRED_SLOTS}
            for name in REVIEW_SLOTS
        ],
        directives={
            "verbosity": dict(VERBOSITY_DIRECTIVES),
            "security": {"enabled": SECURITY_ENABLED_DIRECTIVE, "disabled": SECURITY_DISABLED_DIRECTIVE},
        },
        placeholders={"no_instructions": NO_INSTRUCTIONS, "no_note": NO_NOTE},
        warnings=warnings,
    )


@router.get("", response_model=PromptOut)
def get_prompt(db: DbSession, _user: CurrentUser) -> PromptOut:
    return _out(gp.load_effective(db))


@router.put("", response_model=PromptOut)
def put_prompt(body: PromptIn, db: DbSession, admin: AdminUser) -> PromptOut:
    try:
        saved = gp.save_template(db, body.template, admin.username)
    except gp.PromptValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"errors": exc.errors}) from exc
    return _out(saved)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def reset_prompt(db: DbSession, _admin: AdminUser) -> Response:
    gp.reset_template(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
