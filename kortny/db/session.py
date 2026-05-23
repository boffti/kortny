"""SQLAlchemy engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kortny.config import load_settings


def normalize_database_url(database_url: str) -> str:
    """Use the installed psycopg v3 driver for conventional Postgres URLs."""

    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def make_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine from an explicit URL or app settings."""

    resolved_url = database_url or load_settings().postgres_url
    return create_engine(
        normalize_database_url(resolved_url),
        echo=echo,
        pool_pre_ping=True,
    )


def make_session_factory(
    engine: Engine | None = None,
    *,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    """Create a configured sync Session factory."""

    bind = engine or make_engine(database_url)
    return sessionmaker(bind=bind, expire_on_commit=False)


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Open a transaction-scoped session and close it after use."""

    factory = session_factory or make_session_factory()
    with factory.begin() as session:
        yield session
