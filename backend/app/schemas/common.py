from __future__ import annotations

import re
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

REPO_SEGMENT_PATTERN = r"^[A-Za-z0-9_.-]{1,100}$"
_REPO_SEGMENT = re.compile(REPO_SEGMENT_PATTERN)


def parse_repo_full_name(value: str) -> str:
    """Return ``owner/repo`` or raise ``ValueError`` when the name is not two safe segments."""
    parts = value.strip().split("/")
    if len(parts) != 2 or not _REPO_SEGMENT.fullmatch(parts[0]) or not _REPO_SEGMENT.fullmatch(parts[1]):
        raise ValueError("Repository must look like owner/name")
    return f"{parts[0]}/{parts[1]}".lower()


class Verdict(StrEnum):
    passed = "passed"
    warning = "warning"
    critical = "critical"


class Verbosity(StrEnum):
    concise = "concise"
    detailed = "detailed"


class ReviewMode(StrEnum):
    auto = "auto"
    on_demand = "on_demand"


class Rating(StrEnum):
    helpful = "helpful"
    unhelpful = "unhelpful"


class EventStatus(StrEnum):
    queued = "queued"
    processed = "processed"
    ignored = "ignored"
    failed = "failed"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
