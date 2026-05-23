"""Alembic migration environment for Kortny."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from kortny.db.models import Base
from kortny.db.session import normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve the migration database URL without requiring full app settings."""

    load_dotenv()
    configured_url = os.environ.get("POSTGRES_URL") or config.get_main_option(
        "sqlalchemy.url"
    )
    if not configured_url:
        raise RuntimeError("POSTGRES_URL or alembic sqlalchemy.url is required")

    return normalize_database_url(configured_url)


def run_migrations_offline() -> None:
    """Run migrations without creating an engine."""

    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
