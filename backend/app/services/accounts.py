"""Seeded sign-in accounts, password authentication and a failed-login throttle."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import utcnow
from app.core.security import hash_password, verify_password
from app.models import User
from app.models.user import ROLE_ADMIN, ROLE_DEV

logger = logging.getLogger(__name__)

DEV_DEFAULT_PASSWORDS = {ROLE_DEV: "dev12345", ROLE_ADMIN: "admin12345"}
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 300
# Verified against unknown usernames so both failure paths cost the same.
_DUMMY_HASH = hash_password("reviewpilot-unknown-user")


def _find(db: Session, username: str) -> User | None:
    """Case-insensitive lookup; prefers rows that can sign in with a password."""
    rows = db.scalars(select(User).where(User.username.ilike(username)).order_by(User.password_hash.is_(None), User.id))
    return next(iter(rows), None)


def seed_accounts(db: Session, settings: Settings) -> None:
    """Create or update the dev and admin accounts from settings (passwords are re-hashed only when changed)."""
    for role, username, secret in (
        (ROLE_DEV, settings.SEED_DEV_USERNAME, settings.SEED_DEV_PASSWORD),
        (ROLE_ADMIN, settings.SEED_ADMIN_USERNAME, settings.SEED_ADMIN_PASSWORD),
    ):
        username = username.strip()
        password = secret.get_secret_value() or ("" if settings.is_production else DEV_DEFAULT_PASSWORDS[role])
        if not username or not password:
            logger.warning("Seed account for role %s is not configured; skipping", role)
            continue
        user = _find(db, username)
        if user is None:
            user = User(username=username, access_token="", created_at=utcnow(), last_login_at=None)
        if user.github_id == 0:  # row left by the removed local "Continue locally" sign-in
            user.github_id = None
        user.role = role
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
        db.add(user)
    db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = _find(db, username.strip())
    if user is None or not user.password_hash:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


class LoginThrottle:
    """In-memory limit on failed sign-ins per username (single-process deployment)."""

    def __init__(self, max_failures: int = MAX_FAILURES, window: float = FAILURE_WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window = window
        self._failures: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        return failures

    def blocked(self, username: str) -> bool:
        with self._lock:
            return len(self._recent(username.strip().lower(), time.time())) >= self.max_failures

    def record_failure(self, username: str) -> None:
        with self._lock:
            now = time.time()
            self._recent(username.strip().lower(), now).append(now)

    def reset(self, username: str | None = None) -> None:
        with self._lock:
            if username is None:
                self._failures.clear()
            else:
                self._failures.pop(username.strip().lower(), None)


throttle = LoginThrottle()
