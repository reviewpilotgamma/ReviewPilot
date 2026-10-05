from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, ReviewMode, Verbosity

MAX_INSTRUCTIONS_CHARS = 10_000


class RuleIn(BaseModel):
    custom_instructions: str = Field("", max_length=MAX_INSTRUCTIONS_CHARS)
    verbosity: Verbosity = Verbosity.concise
    review_mode: ReviewMode = ReviewMode.auto
    enable_security: bool = True


class RuleOut(RuleIn, ORMModel):
    repo_full_name: str
    updated_at: datetime | None = None
    is_default: bool = False


class PresetOut(BaseModel):
    id: str
    name: str
    description: str
    instructions: str
