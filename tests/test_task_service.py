import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    Artifact,
    EncryptedSecret,
    Installation,
    LLMProvider,
    LLMUsage,
    ModelPricing,
    SlackSideEffect,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.tasks import TaskIdentity, TaskService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for task service integration tests",
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


def test_create_task_is_idempotent_on_slack_event_id(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)

    first = service.create_task(
        installation_id=installation.id,
        slack_event_id="Ev123",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input="research pandas",
    )
    second = service.create_task(
        installation_id=installation.id,
        slack_event_id="Ev123",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input="duplicate delivery",
    )

    task_count = db_session.scalar(select(func.count()).select_from(Task))
    event_count = db_session.scalar(select(func.count()).select_from(TaskEvent))
    mismatch_event = db_session.scalar(
        select(TaskEvent).where(
            TaskEvent.task_id == first.id,
            TaskEvent.payload["message"].as_string() == "task_identity_mismatch",
        )
    )

    assert first.id == second.id
    assert second.input == "research pandas"
    assert first.identity_kind == "slack_message"
    assert first.identity_key == (
        "slack-message:C123:1716400000.000001:1716400000.000001"
    )
    assert task_count == 1
    assert event_count == 2
    assert mismatch_event is not None
    assert mismatch_event.payload["requested_identity_kind"] == "slack_message"


def test_create_task_dedupes_equivalent_slack_message_identity(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)

    first = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvAppMention",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input="summarize the decisions",
        source_surface="app_mention",
    )
    second = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvGenericMessage",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input="summarize the decisions",
        source_surface="channel_message",
    )

    task_count = db_session.scalar(select(func.count()).select_from(Task))
    event_count = db_session.scalar(select(func.count()).select_from(TaskEvent))

    assert second.id == first.id
    assert task_count == 1
    assert event_count == 1
    assert first.slack_event_id == "EvAppMention"


def test_create_task_uses_explicit_synthetic_identity(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    identity = TaskIdentity.synthetic(
        source="channel_assessment",
        source_id="membership-123",
        input_text="assess channel",
        payload={"channel_id": "C123"},
    )

    first = service.create_task(
        installation_id=installation.id,
        slack_event_id="observe:membership-123:channel_assessment",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000010",
        slack_message_ts="1716400000.000010",
        slack_user_id="system",
        input="assess channel",
        identity=identity,
        source_surface="member_joined_channel",
    )
    second = service.create_task(
        installation_id=installation.id,
        slack_event_id="observe:membership-123:channel_assessment",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000010",
        slack_message_ts="1716400000.000010",
        slack_user_id="system",
        input="assess channel",
        identity=identity,
        source_surface="app_mention",
    )

    assert second.id == first.id
    assert first.identity_kind == "synthetic"
    assert first.identity_key == "synthetic:channel_assessment:membership-123"
    assert db_session.scalar(select(func.count()).select_from(Task)) == 1


def test_concurrent_create_task_same_identity_is_single(
    db_session: Session,
    engine: Engine,
) -> None:
    installation = create_installation(db_session)
    installation_id = installation.id
    db_session.commit()
    session_factory = make_session_factory(engine=engine)
    barrier = Barrier(2)

    def create_with_event(event_id: str) -> uuid.UUID:
        with session_factory() as session:
            barrier.wait(timeout=5)
            task = TaskService(session).create_task(
                installation_id=installation_id,
                slack_event_id=event_id,
                slack_channel_id="CRace",
                slack_thread_ts="1716400000.000099",
                slack_message_ts="1716400000.000099",
                slack_user_id="URace",
                input="race-safe task",
            )
            session.commit()
            return task.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        task_ids = list(executor.map(create_with_event, ["EvRaceA", "EvRaceB"]))

    task_count = db_session.scalar(select(func.count()).select_from(Task))

    assert len(set(task_ids)) == 1
    assert task_count == 1


def test_lookup_and_transition_write_status_event(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    task = service.create_task(
        installation_id=installation.id,
        slack_event_id="Ev456",
        slack_channel_id="C456",
        slack_thread_ts="1716400000.000002",
        slack_message_ts="1716400000.000002",
        slack_user_id="U456",
        input="make a report",
    )

    found_by_id = service.get_task(task.id)
    found_by_thread = service.get_by_thread("C456", "1716400000.000002")
    transitioned = service.transition(task, TaskStatus.running)

    events = db_session.scalars(
        select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.seq)
    ).all()

    assert found_by_id is task
    assert found_by_thread is task
    assert transitioned.status is TaskStatus.running
    assert transitioned.started_at is not None
    assert [event.seq for event in events] == [1, 2]
    assert events[1].type is TaskEventType.status_changed
    assert events[1].payload == {"from": "pending", "to": "running"}


def test_list_by_thread_returns_tasks_in_creation_order(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    created_at = datetime(2026, 5, 23, 11, 0, tzinfo=UTC)

    first = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvThreadFirst",
        slack_channel_id="CThread",
        slack_thread_ts="1716400000.000010",
        slack_message_ts="1716400000.000010",
        slack_user_id="UThread",
        input="research tempfile",
    )
    second = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvThreadSecond",
        slack_channel_id="CThread",
        slack_thread_ts="1716400000.000010",
        slack_message_ts="1716400010.000010",
        slack_user_id="UThread",
        input="make it punchier",
    )
    other_thread = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvOtherThread",
        slack_channel_id="CThread",
        slack_thread_ts="1716500000.000010",
        slack_message_ts="1716500000.000010",
        slack_user_id="UThread",
        input="unrelated",
    )
    first.created_at = created_at
    second.created_at = created_at + timedelta(seconds=10)
    other_thread.created_at = created_at + timedelta(seconds=20)
    db_session.flush()

    assert service.list_by_thread("CThread", "1716400000.000010") == [first, second]


def test_append_event_assigns_monotonic_seq_per_task(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    task = service.create_task(
        installation_id=installation.id,
        slack_event_id="Ev789",
        slack_channel_id="C789",
        slack_thread_ts="1716400000.000003",
        slack_message_ts="1716400000.000003",
        slack_user_id="U789",
        input="search docs",
    )

    first = service.append_event(task, TaskEventType.log, {"message": "first"})
    second = service.append_event(task, TaskEventType.tool_call, {"name": "echo"})

    assert first.seq == 2
    assert second.seq == 3


def test_record_llm_usage_rolls_totals_to_task(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    task = service.create_task(
        installation_id=installation.id,
        slack_event_id="EvCost",
        slack_channel_id="CCost",
        slack_thread_ts="1716400000.000004",
        slack_message_ts="1716400000.000004",
        slack_user_id="UCost",
        input="summarize usage",
    )

    service.record_llm_usage(
        task,
        provider=LLMProvider.openrouter,
        model="openai/gpt-4o",
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.010000"),
    )
    service.record_llm_usage(
        task.id,
        provider="openrouter",
        model="openai/gpt-4o",
        input_tokens=50,
        output_tokens=10,
        cost_usd=Decimal("0.005000"),
    )

    usage_cost_sum = db_session.scalar(
        select(func.sum(LLMUsage.cost_usd)).where(LLMUsage.task_id == task.id)
    )

    assert task.total_input_tokens == 150
    assert task.total_output_tokens == 30
    assert task.total_cost_usd == usage_cost_sum == Decimal("0.015000")


def cleanup_database(session: Session) -> None:
    for model in (
        Artifact,
        LLMUsage,
        TaskEvent,
        SlackSideEffect,
        Task,
        ModelPricing,
        EncryptedSecret,
        Installation,
    ):
        session.execute(delete(model))


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation
