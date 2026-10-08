from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow

ROLE_DEV = "dev"
ROLE_ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default=ROLE_DEV, server_default=ROLE_DEV)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # None: cannot sign in with a password
    # Linked GitHub identity (set when the user installs the GitHub App or connects GitHub).
    github_id: Mapped[int | None] = mapped_column(Integer, index=True)
    github_login: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(String, nullable=False, default="")  # Fernet-encrypted; "" = not linked
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=utcnow)
