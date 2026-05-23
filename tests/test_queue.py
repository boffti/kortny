import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from kortny.db.models import (
    Artifact,
    EncryptedSecret,
    Installation,
    LLMUsage,
    ModelPricing,
    Task,
    TaskEvent,
    TaskStatus,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.queue import TaskQueue
from kortny.tasks import TaskService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for queue integration tests",
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


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(engine=engine)


def test_claim_next_sets_running_lock_and_lease(db_session: Session) -> None:
    claim_time = datetime(2026, 5, 23, 2, 20, tzinfo=UTC)
    task = create_task(db_session, event_id="EvClaim")
    task.available_at = claim_time - timedelta(seconds=1)
    db_session.commit()

    claimed = TaskQueue(db_session).claim_next(
        worker_id="worker-a",
        lease_for=timedelta(seconds=60),
        now=claim_time,
    )

    assert claimed is not None
    assert claimed.id == task.id
    assert claimed.status is TaskStatus.running
    assert claimed.locked_by == "worker-a"
    assert claimed.locked_at == claim_time
    assert claimed.lease_expires_at == claim_time + timedelta(seconds=60)
    assert claimed.started_at == claim_time

    events = status_events(db_session, task)
    assert [event.payload["to"] for event in events] == ["running"]


def test_concurrent_claimers_get_different_tasks(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    first = create_task(db_session, event_id="EvConcurrent1")
    second = create_task(db_session, event_id="EvConcurrent2")
    db_session.commit()

    session_one = session_factory()
    session_two = session_factory()
    tx_one = session_one.begin()
    tx_two = session_two.begin()
    try:
        claim_one = TaskQueue(session_one).claim_next(worker_id="worker-a")
        claim_two = TaskQueue(session_two).claim_next(worker_id="worker-b")

        assert claim_one is not None
        assert claim_two is not None
        assert {claim_one.id, claim_two.id} == {first.id, second.id}
        assert claim_one.id != claim_two.id

        tx_one.commit()
        tx_two.commit()
    finally:
        if tx_one.is_active:
            tx_one.rollback()
        if tx_two.is_active:
            tx_two.rollback()
        session_one.close()
        session_two.close()


def test_reclaim_expired_lease_requeues_with_attempt_increment(
    db_session: Session,
) -> None:
    now = datetime(2026, 5, 23, 2, 30, tzinfo=UTC)
    task = create_task(db_session, event_id="EvRequeue")
    task.status = TaskStatus.running
    task.locked_by = "worker-a"
    task.locked_at = now - timedelta(minutes=10)
    task.lease_expires_at = now - timedelta(minutes=5)
    task.attempts = 1
    task.max_attempts = 3
    db_session.commit()

    reclaimed = TaskQueue(db_session).reclaim_expired_leases(now=now)

    assert [task.id for task in reclaimed] == [task.id]
    assert task.status is TaskStatus.pending
    assert task.attempts == 2
    assert task.locked_by is None
    assert task.locked_at is None
    assert task.lease_expires_at is None
    assert task.available_at == now
    assert task.error is None

    events = status_events(db_session, task)
    assert [event.payload["to"] for event in events] == ["crashed", "pending"]


def test_reclaim_expired_lease_fails_exhausted_task(db_session: Session) -> None:
    now = datetime(2026, 5, 23, 2, 35, tzinfo=UTC)
    task = create_task(db_session, event_id="EvFail")
    task.status = TaskStatus.running
    task.locked_by = "worker-a"
    task.locked_at = now - timedelta(minutes=10)
    task.lease_expires_at = now - timedelta(minutes=5)
    task.attempts = 2
    task.max_attempts = 3
    db_session.commit()

    reclaimed = TaskQueue(db_session).reclaim_expired_leases(now=now)

    assert [task.id for task in reclaimed] == [task.id]
    assert task.status is TaskStatus.failed
    assert task.attempts == 3
    assert task.finished_at == now
    assert task.error == {
        "reason": "lease_expired",
        "attempts": 3,
        "max_attempts": 3,
    }

    events = status_events(db_session, task)
    assert [event.payload["to"] for event in events] == ["crashed", "failed"]


def test_reclaim_ignores_unexpired_running_tasks(db_session: Session) -> None:
    now = datetime(2026, 5, 23, 2, 40, tzinfo=UTC)
    task = create_task(db_session, event_id="EvFresh")
    task.status = TaskStatus.running
    task.locked_by = "worker-a"
    task.locked_at = now
    task.lease_expires_at = now + timedelta(minutes=5)
    db_session.commit()

    reclaimed = TaskQueue(db_session).reclaim_expired_leases(now=now)

    assert reclaimed == []
    assert task.status is TaskStatus.running
    assert task.locked_by == "worker-a"


def cleanup_database(session: Session) -> None:
    for model in (
        Artifact,
        LLMUsage,
        TaskEvent,
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


def create_task(session: Session, *, event_id: str) -> Task:
    installation = create_installation(session)
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=event_id,
        slack_channel_id="C123",
        slack_thread_ts=event_id,
        slack_message_ts=event_id,
        slack_user_id="U123",
        input=f"task {event_id}",
    )


def status_events(session: Session, task: Task) -> list[TaskEvent]:
    return list(
        session.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task.id,
                TaskEvent.type == "status_changed",
            )
            .order_by(TaskEvent.seq)
        )
    )
