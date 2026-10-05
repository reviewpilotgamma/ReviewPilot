"""Shared fixtures: isolated settings/.env, migrated SQLite per test, mocked HTTP, auth helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

GITHUB_API = "https://api.github.test"
GITHUB_OAUTH = "https://github.test"
GEMINI_API = "https://gemini.test/v1beta"
WEBHOOK_SECRET = "test-webhook-secret"
FIXTURES = Path(__file__).parent / "fixtures"

# Must be set before any ``app`` import so module-level engine/settings never touch real files.
_BOOT_DIR = Path(os.environ.get("TEMP", "/tmp")) / "reviewpilot-tests"
_BOOT_DIR.mkdir(parents=True, exist_ok=True)
os.environ["REVIEWPILOT_ENV_FILE"] = str(_BOOT_DIR / "boot.env")
os.environ["DATABASE_URL"] = f"sqlite:///{(_BOOT_DIR / 'boot.db').as_posix()}"
os.environ["WORKER_ENABLED"] = "false"

from app.core import database, http  # noqa: E402
from app.core.config import reload_settings  # noqa: E402
from app.core.security import SESSION_COOKIE, create_session_token, encrypt_token  # noqa: E402
from app.services import access, github_app  # noqa: E402


@pytest.fixture(scope="session")
def rsa_keys(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    path = tmp_path_factory.mktemp("keys") / "app.pem"
    path.write_bytes(pem)
    return path, public


@pytest.fixture(scope="session")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Migrate once; each test gets a copy (keeps tests fast while exercising real migrations)."""
    path = tmp_path_factory.mktemp("db") / "template.db"
    database.run_migrations(f"sqlite:///{path.as_posix()}")
    return path


@pytest.fixture(autouse=True)
def env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rsa_keys: tuple[Path, bytes], template_db: Path
) -> Iterator[Path]:
    env_file = tmp_path / ".env"
    env_file.write_text("# test env\nGEMINI_MODEL=gemini-2.0-flash\n", encoding="utf-8")
    replies_file = tmp_path / "bot_replies.json"
    shutil.copy(Path(__file__).parents[1] / "app" / "data" / "bot_replies.json", replies_file)
    db_path = tmp_path / "test.db"
    shutil.copy(template_db, db_path)

    values = {
        "REVIEWPILOT_ENV_FILE": str(env_file),
        "REVIEWPILOT_REPLIES_FILE": str(replies_file),
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "ENV": "development",
        "API_BASE_URL": "http://api.test",
        "FRONTEND_ORIGIN": "http://app.test",
        "GITHUB_APP_ID": "12345",
        "GITHUB_APP_SLUG": "reviewpilot-test",
        "GITHUB_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "GITHUB_PRIVATE_KEY_PATH": str(rsa_keys[0]),
        "GITHUB_CLIENT_ID": "Iv1.client",
        "GITHUB_CLIENT_SECRET": "client-secret",
        "GITHUB_API_URL": GITHUB_API,
        "GITHUB_OAUTH_URL": GITHUB_OAUTH,
        "GEMINI_API_KEY": "gemini-key-1234",
        "GEMINI_API_URL": GEMINI_API,
        "SESSION_SECRET": "s" * 48,
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "ADMIN_GITHUB_LOGINS": "admin-user",
        "WORKER_ENABLED": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    reload_settings()
    database.configure_engine(values["DATABASE_URL"])
    github_app.clear_caches()
    access.clear_cache()
    http.set_http_client(None)
    yield tmp_path
    http.set_http_client(None)
    database.engine.dispose()


@pytest.fixture
def db():
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def mock_http() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="http://api.test") as test_client:
        yield test_client


# --------------------------------------------------------------------------- helpers
def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def post_webhook(client, event: str, payload: dict, delivery: str = "d-1"):
    body = json.dumps(payload).encode()
    return client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": sign(body),
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "Content-Type": "application/json",
        },
    )


def make_user(db, login: str = "alice", github_id: int = 1001):
    from app.models import User

    user = User(github_id=github_id, username=login, avatar_url=None, access_token=encrypt_token("gho_user"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def repo_info(full_name: str, installation_id: int = 99):
    from app.services.access import RepoInfo

    return RepoInfo(
        full_name=full_name.lower(),
        installation_id=installation_id,
        account_login=full_name.split("/")[0],
        account_type="Organization",
        account_avatar_url="",
        private=False,
        html_url=f"https://github.com/{full_name}",
    )


@pytest.fixture
def login(app, client, db):
    """Return a function that logs a user in with a given set of accessible repositories."""
    from app.api.deps import get_accessible

    def _login(login_name: str = "alice", repos: tuple[str, ...] = ("acme/api",), github_id: int = 1001):
        user = make_user(db, login_name, github_id)
        client.cookies.set(SESSION_COOKIE, create_session_token(user.id, user.username))
        client.headers["X-Requested-With"] = "ReviewPilot"
        app.dependency_overrides[get_accessible] = lambda: {r.lower(): repo_info(r) for r in repos}
        return user

    yield _login
    app.dependency_overrides.clear()
