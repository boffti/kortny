import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import Installation, Task, TaskEvent, WorkspaceState
from kortny.db.session import make_engine, make_session_factory, normalize_database_url

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for workspace state tests",
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    assert TEST_POSTGRES_URL is not None

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", normalize_database_url(TEST_POSTGRES_URL))
    command.upgrade(config, "head")

    engine = make_engine(TEST_POSTGRES_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        cleanup_database(session)
        session.commit()
        yield session
        session.rollback()
        cleanup_database(session)
        session.commit()


def test_workspace_state_enforces_one_active_fact_per_scope_key(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    first = workspace_fact(
        installation,
        scope_type="workspace",
        scope_id=None,
        key="report.style",
        value_json={"style": "analyst_grade"},
    )
    db_session.add(first)
    db_session.commit()

    db_session.add(
        workspace_fact(
            installation,
            scope_type="workspace",
            scope_id=None,
            key="report.style",
            value_json={"style": "brief"},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    replacement = workspace_fact(
        installation,
        scope_type="workspace",
        scope_id=None,
        key="report.style",
        value_json={"style": "brief"},
    )
    first.status = "superseded"
    first.superseded_at = datetime(2026, 5, 23, tzinfo=UTC)
    db_session.flush()

    db_session.add(replacement)
    db_session.flush()
    first.superseded_by_id = replacement.id
    db_session.commit()

    active = current_workspace_fact(
        db_session,
        installation,
        scope_type="workspace",
        scope_id=None,
        key="report.style",
    )
    assert active is replacement
    assert active.value_json == {"style": "brief"}


def test_workspace_state_cascades_when_installation_is_deleted(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    db_session.add(
        workspace_fact(
            installation,
            scope_type="user",
            scope_id="U123",
            key="response.verbosity",
            value_json={"level": "concise"},
        )
    )
    db_session.commit()

    db_session.delete(installation)
    db_session.commit()

    assert db_session.scalars(select(WorkspaceState)).all() == []


def test_workspace_state_current_value_query_ignores_non_active_rows(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    proposed = workspace_fact(
        installation,
        scope_type="channel",
        scope_id="C123",
        key="summary.format",
        value_json={"format": "short"},
        status="proposed",
    )
    forgotten = workspace_fact(
        installation,
        scope_type="channel",
        scope_id="C123",
        key="summary.format",
        value_json={"format": "bullets"},
        status="forgotten",
    )
    active = workspace_fact(
        installation,
        scope_type="channel",
        scope_id="C123",
        key="summary.format",
        value_json={"format": "executive"},
    )
    db_session.add_all([proposed, forgotten, active])
    db_session.commit()

    current = current_workspace_fact(
        db_session,
        installation,
        scope_type="channel",
        scope_id="C123",
        key="summary.format",
    )

    assert current is active
    assert current.value_json == {"format": "executive"}


def cleanup_database(session: Session) -> None:
    for model in (
        WorkspaceState,
        TaskEvent,
        Task,
        Installation,
    ):
        session.execute(delete(model))


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation


def workspace_fact(
    installation: Installation,
    *,
    scope_type: str,
    scope_id: str | None,
    key: str,
    value_json: dict,
    status: str = "active",
) -> WorkspaceState:
    return WorkspaceState(
        installation_id=installation.id,
        scope_type=scope_type,
        scope_id=scope_id,
        key=key,
        value_json=value_json,
        status=status,
        source_kind="user_explicit",
        proposed_by="U123",
    )


def current_workspace_fact(
    session: Session,
    installation: Installation,
    *,
    scope_type: str,
    scope_id: str | None,
    key: str,
) -> WorkspaceState:
    return session.scalars(
        select(WorkspaceState).where(
            WorkspaceState.installation_id == installation.id,
            WorkspaceState.scope_type == scope_type,
            WorkspaceState.scope_id.is_(None)
            if scope_id is None
            else WorkspaceState.scope_id == scope_id,
            WorkspaceState.key == key,
            WorkspaceState.status == "active",
            WorkspaceState.expires_at.is_(None),
        )
    ).one()
