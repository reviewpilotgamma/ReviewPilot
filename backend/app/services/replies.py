"""Canned bot replies stored in ``bot_replies.json``."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from app.core.config import BACKEND_DIR

REPLY_KEYS = ("welcome", "plan", "error", "empty_diff")
DEFAULT_REPLIES = {
    "welcome": "👋 Thanks @{author}! Comment `@review` to request an architectural review.",
    "plan": "## 🧭 ReviewPilot Execution Plan\n- [ ] Verify the change\n- [ ] Add tests\n- [ ] Update docs",
    "error": "⚠️ ReviewPilot couldn't complete the review ({reason}). Please try again later.",
    "empty_diff": "ℹ️ ReviewPilot found no file changes to review in this PR.",
}

_lock = threading.Lock()


def replies_path() -> Path:
    return Path(os.environ.get("REVIEWPILOT_REPLIES_FILE", BACKEND_DIR / "app" / "data" / "bot_replies.json"))


_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def load_replies() -> dict[str, str]:
    try:
        data = json.loads(replies_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {key: str(data.get(key) or DEFAULT_REPLIES[key]) for key in REPLY_KEYS}


def save_replies(replies: dict[str, str]) -> dict[str, str]:
    payload = {key: replies[key] for key in REPLY_KEYS}
    path = replies_path()
    tmp = path.with_suffix(".json.tmp")
    with _lock:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return payload


def render_reply(key: str, **values: str) -> str:
    """Substitute ``{name}`` placeholders; unknown placeholders and stray braces are left untouched."""
    template = load_replies()[key]
    return _PLACEHOLDER_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)
