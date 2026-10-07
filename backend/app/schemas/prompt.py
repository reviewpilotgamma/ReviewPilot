"""Schemas for the org-wide golden review prompt."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.golden_prompt import MAX_TEMPLATE_CHARS


class PromptSegment(BaseModel):
    type: Literal["text", "slot"]
    text: str | None = None
    name: str | None = None


class PromptSlot(BaseModel):
    name: str
    label: str
    required: bool


class PromptDirectives(BaseModel):
    verbosity: dict[str, str]
    security: dict[str, str]


class PromptPlaceholders(BaseModel):
    no_instructions: str
    no_note: str


class PromptOut(BaseModel):
    template: str
    is_default: bool
    updated_at: datetime | None
    updated_by: str | None
    segments: list[PromptSegment]
    slots: list[PromptSlot]
    directives: PromptDirectives
    placeholders: PromptPlaceholders
    warnings: list[str] = Field(default_factory=list)


class PromptIn(BaseModel):
    template: str = Field(max_length=MAX_TEMPLATE_CHARS)
