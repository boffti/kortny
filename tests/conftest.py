"""Global pytest safeguards."""

from __future__ import annotations

import os

import pytest

from tests.db_safety import UnsafeTestDatabaseError, assert_safe_test_database


def pytest_configure(config: pytest.Config) -> None:
    """Prevent any DB-backed test from wiping the local development database."""

    del config
    database_url = os.environ.get("KORTNY_TEST_POSTGRES_URL")
    if not database_url:
        return
    try:
        assert_safe_test_database(
            database_url,
            runtime_database_url=os.environ.get("POSTGRES_URL"),
            environment=_environment_marker(),
        )
    except UnsafeTestDatabaseError as exc:
        pytest.exit(str(exc), returncode=2)


def _environment_marker() -> str | None:
    return (
        os.environ.get("KORTNY_ENV")
        or os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
    )
