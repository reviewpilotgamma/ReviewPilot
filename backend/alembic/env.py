from __future__ import annotations

from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base, build_engine

config = context.config

if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("url") or config.get_main_option("sqlalchemy.url") or get_settings().DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = build_engine(_url())
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
