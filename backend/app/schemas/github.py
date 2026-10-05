from __future__ import annotations

from pydantic import BaseModel


class AppInfo(BaseModel):
    configured: bool
    slug: str
    name: str
    install_url: str
    html_url: str
    local_mode: bool = False


class RepoOut(BaseModel):
    full_name: str
    private: bool
    html_url: str
    has_rules: bool


class InstallationOut(BaseModel):
    installation_id: int
    account_login: str
    account_type: str
    avatar_url: str
    repos: list[RepoOut]
