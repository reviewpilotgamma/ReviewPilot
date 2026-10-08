from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORMModel):
    id: int
    username: str
    role: str
    avatar_url: str | None
    email: str | None
    github_id: int | None
    github_login: str | None
    github_linked: bool = False
    is_admin: bool = False
