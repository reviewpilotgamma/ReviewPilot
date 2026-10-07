"""Schemas for repository architecture / requirements documents."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_full_name: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    char_count: int = Field(description="Extracted text length")
    uploaded_at: datetime


CacheStatus = Literal["none", "inline", "cached", "pending"]


class DocumentUploadOut(DocumentOut):
    cache_status: CacheStatus
    cache_error: str | None = Field(None, description="Why the Gemini cache could not be built, if it failed")


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    cache_status: CacheStatus = Field(description="none | inline | cached | pending")
