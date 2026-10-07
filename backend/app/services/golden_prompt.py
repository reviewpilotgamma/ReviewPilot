"""The org-wide golden review prompt: validation, segments for the UI, and the stored override."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.database import utcnow
from app.models import ReviewPrompt
from app.services.prompts import DEFAULT_REVIEW_TEMPLATE, REVIEW_SLOTS, TOKEN_RE

PROMPT_ROW_ID = 1
REQUIRED_SLOTS = ("custom_instructions",)
META_MARKER = "reviewpilot-meta"
MAX_TEMPLATE_CHARS = 20_000
SLOT_LABELS = {
    "custom_instructions": "Your instructions",
    "verbosity_directive": "Verbosity",
    "security_directive": "Security",
    "requester_note": "Requester note",
}


class PromptValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class EffectivePrompt:
    template: str
    is_default: bool
    updated_at: datetime | None = None
    updated_by: str | None = None


def segments(template: str) -> list[dict[str, str]]:
    """Split a template into ordered ``text`` and ``slot`` segments (unknown tokens stay text)."""
    out: list[dict[str, str]] = []
    cursor = 0
    for match in TOKEN_RE.finditer(template):
        name = match.group(1)
        if name not in REVIEW_SLOTS:
            continue
        if match.start() > cursor:
            out.append({"type": "text", "text": template[cursor : match.start()]})
        out.append({"type": "slot", "name": name})
        cursor = match.end()
    if cursor < len(template):
        out.append({"type": "text", "text": template[cursor:]})
    return out


def validate_template(template: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors block saving."""
    errors: list[str] = []
    warnings: list[str] = []
    if not template.strip():
        return ["The prompt cannot be empty."], warnings
    if len(template) > MAX_TEMPLATE_CHARS:
        errors.append(f"The prompt is longer than {MAX_TEMPLATE_CHARS:,} characters.")
    used = set(TOKEN_RE.findall(template))
    for slot in REQUIRED_SLOTS:
        if slot not in used:
            errors.append(f"Missing {{{{{slot}}}}}: repository instructions would be ignored.")
    unknown = sorted(used - set(REVIEW_SLOTS))
    if unknown:
        errors.append("Unknown placeholder(s): " + ", ".join(f"{{{{{name}}}}}" for name in unknown) + ".")
    if META_MARKER not in template:
        errors.append(f"Keep the '{META_MARKER}' output line: the score and verdict are read from it.")
    for slot in REVIEW_SLOTS:
        if slot not in REQUIRED_SLOTS and slot not in used:
            warnings.append(f"{{{{{slot}}}}} is not used; that setting will have no effect.")
    return errors, warnings


def load_effective(db: Session) -> EffectivePrompt:
    row = db.get(ReviewPrompt, PROMPT_ROW_ID)
    if row is None:
        return EffectivePrompt(template=DEFAULT_REVIEW_TEMPLATE, is_default=True)
    return EffectivePrompt(
        template=row.template, is_default=False, updated_at=row.updated_at, updated_by=row.updated_by
    )


def save_template(db: Session, template: str, username: str) -> EffectivePrompt:
    errors, _ = validate_template(template)
    if errors:
        raise PromptValidationError(errors)
    row = db.get(ReviewPrompt, PROMPT_ROW_ID)
    if row is None:
        row = ReviewPrompt(id=PROMPT_ROW_ID, template=template)
        db.add(row)
    row.template = template
    row.updated_by = username
    row.updated_at = utcnow()
    db.commit()
    return load_effective(db)


def reset_template(db: Session) -> EffectivePrompt:
    row = db.get(ReviewPrompt, PROMPT_ROW_ID)
    if row is not None:
        db.delete(row)
        db.commit()
    return load_effective(db)
