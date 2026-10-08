"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.api import auth, documents, github, insights, metrics, prompt, reviews, rules, webhooks
from app.api import settings as settings_api
from app.core.config import get_settings
from app.core.database import SessionLocal, run_migrations
from app.core.http import close_http_client, get_http_client
from app.core.logging import configure_logging, request_id_var
from app.services.accounts import seed_accounts
from app.services.errors import GitHubError, NotConfiguredError, ReauthRequired
from app.services.worker import worker

logger = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def _seed_accounts() -> None:
    with SessionLocal() as db:
        seed_accounts(db, get_settings())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await run_in_threadpool(run_migrations)
    await run_in_threadpool(_seed_accounts)
    get_http_client()
    if settings.WORKER_ENABLED:
        await worker.start()
    logger.info("ReviewPilot started (env=%s)", settings.ENV)
    try:
        yield
    finally:
        await worker.stop()
        await close_http_client()


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ReauthRequired)
    async def _reauth(_: Request, __: ReauthRequired) -> JSONResponse:
        return JSONResponse({"detail": "reauth_required"}, status_code=401)

    @app.exception_handler(NotConfiguredError)
    async def _not_configured(_: Request, exc: NotConfiguredError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(GitHubError)
    async def _github(_: Request, exc: GitHubError) -> JSONResponse:
        logger.warning("GitHub error surfaced to API: %s", exc)
        return JSONResponse({"detail": "GitHub API request failed"}, status_code=502)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        rid = request_id_var.get()
        logger.exception("Unhandled error: %s", exc.__class__.__name__)
        return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="ReviewPilot API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # noqa: ANN001, ANN202
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With", "X-Request-ID"],
    )
    _register_exception_handlers(app)

    for module in (auth, webhooks, rules, documents, prompt, reviews, insights, metrics, github, settings_api):
        app.include_router(module.router, prefix=API_PREFIX)

    # Legacy PoC webhook URL so existing GitHub App configurations keep working.
    app.add_api_route("/webhook", webhooks.receive, methods=["POST"], include_in_schema=False)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:  # noqa: BLE001
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "db": db_ok,
            "worker": "running" if worker.running else "stopped",
            "version": app.version,
        }

    return app


app = create_app()
