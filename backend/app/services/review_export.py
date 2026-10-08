"""Export stored reviews as CSV or JSON for quality reporting."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PRReview

ExportFormat = Literal["csv", "json"]
EXPORT_COLUMNS = ("id", "repo_full_name", "pr_number", "pr_title", "author", "verdict", "score", "created_at")


def _rows(reviews: Iterable[PRReview]) -> list[dict[str, object]]:
    return [{column: getattr(review, column) for column in EXPORT_COLUMNS} for review in reviews]


def export_reviews(db: Session, repos: list[str], fmt: ExportFormat) -> str:
    reviews = db.scalars(select(PRReview).where(PRReview.repo_full_name.in_(repos)).order_by(PRReview.id)).all()
    rows = _rows(reviews)
    if fmt == "json":
        return json.dumps(rows, default=str, indent=2)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
