import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    Installation,
    ProceduralSkill,
    ProceduralSkillInvocation,
    ProceduralSkillVersion,
    Task,
    TaskEvent,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.skills import (
    SKILL_CATALOG_BUILT_MESSAGE,
    SKILL_INVOKED_MESSAGE,
    SkillRegistryService,
)
from kortny.tasks import TaskService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for skill registry tests",
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


def test_skill_registry_seeds_builtin_system_skills(db_session: Session) -> None:
    service = SkillRegistryService(db_session)

    service.ensure_builtin_skills()

    skills = list(
        db_session.scalars(select(ProceduralSkill).order_by(ProceduralSkill.slug))
    )
    versions = list(
        db_session.scalars(
            select(ProceduralSkillVersion).order_by(ProceduralSkillVersion.name)
        )
    )

    assert {skill.slug for skill in skills} >= {
        "slack-humanizer",
        "research-synthesis",
        "document-iteration",
        "slack-formatting",
        "status-recap",
    }
    assert all(skill.owner_type == "system" for skill in skills)
    assert all(skill.trust_level == "trusted" for skill in skills)
    assert all(version.status == "active" for version in versions)
    assert all(version.content_sha256 for version in versions)


def test_skill_registry_selects_and_records_humanizer_skill(
    db_session: Session,
) -> None:
    task = create_task(db_session)
    service = SkillRegistryService(db_session)

    activations = service.select_for_response(
        task,
        response_mode="research_summary",
        invocation_kind="response_humanizer",
    )

    events = list(
        db_session.scalars(
            select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.seq)
        )
    )
    invocations = list(
        db_session.scalars(
            select(ProceduralSkillInvocation).where(
                ProceduralSkillInvocation.task_id == task.id
            )
        )
    )

    assert [activation.slug for activation in activations] == ["slack-humanizer"]
    assert len(invocations) == 1
    assert invocations[0].invocation_kind == "response_humanizer"
    assert invocations[0].response_mode == "research_summary"
    assert any(
        event.payload.get("message") == SKILL_CATALOG_BUILT_MESSAGE
        and "slack-humanizer" in event.payload.get("candidate_slugs", [])
        for event in events
    )
    assert any(
        event.payload.get("message") == SKILL_INVOKED_MESSAGE
        and event.payload.get("slug") == "slack-humanizer"
        for event in events
    )


def create_task(session: Session) -> Task:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C123",
        slack_thread_ts="123.456",
        slack_message_ts="123.456",
        slack_user_id="U123",
        input="research current observability tools",
    )


def cleanup_database(session: Session) -> None:
    for model in (
        ProceduralSkillInvocation,
        ProceduralSkillVersion,
        ProceduralSkill,
        TaskEvent,
        Task,
        Installation,
    ):
        session.execute(delete(model))
