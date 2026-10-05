from __future__ import annotations

from app.schemas.common import ORMModel


class UserOut(ORMModel):
    id: int
    github_id: int
    username: str
    avatar_url: str | None
    email: str | None
    is_admin: bool = False
