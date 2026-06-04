import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.db.models import Installation, Schedule, Task, TaskEvent, TaskEventType
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.scheduler import (
    ScheduleCommandService,
    ScheduleCreationContext,
)
from kortny.tasks import TaskService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for scheduler command tests",
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


def test_schedule_command_activates_latest_proposed_schedule(
    db_session: Session,
) -> None:
    task, context = create_source_task(db_session, input_text="yes set it up")
    schedule = create_proposed_schedule(db_session, context=context)
    db_session.commit()

    result = ScheduleCommandService(db_session).handle_text(
        task=task,
        context=context,
        text="yes set it up",
        now=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )
    db_session.commit()

    assert result is not None
    assert result.action == "activate"
    db_session.refresh(schedule)
    assert schedule.status == "active"
    assert schedule.metadata_json["activated_by"] == "UTestUser"
    assert "activated" in result.response_text
    event = latest_log_event(db_session, task)
    assert event.payload["message"] == "schedule_activated"
    assert event.payload["schedule_id"] == str(schedule.id)


def test_schedule_command_edits_schedule_cadence_without_activating_it(
    db_session: Session,
) -> None:
    task, context = create_source_task(
        db_session,
        input_text="make that Tuesday afternoon instead",
    )
    schedule = create_proposed_schedule(db_session, context=context)
    db_session.commit()

    result = ScheduleCommandService(db_session).handle_text(
        task=task,
        context=context,
        text="make that Tuesday afternoon instead",
        now=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )
    db_session.commit()

    assert result is not None
    assert result.action == "edit"
    db_session.refresh(schedule)
    assert schedule.status == "proposed"
    assert schedule.cron_expr == "0 13 * * 2"
    assert schedule.next_run_at == datetime(2026, 6, 9, 13, 0, tzinfo=UTC)
    assert schedule.task_template["input"] == "check unresolved decisions"
    assert schedule.metadata_json["cadence_label"] == "Every Tuesday afternoon"
    event = latest_log_event(db_session, task)
    assert event.payload["message"] == "schedule_updated"


def test_schedule_command_pauses_resumes_and_cancels_active_schedule(
    db_session: Session,
) -> None:
    task, context = create_source_task(db_session, input_text="pause that schedule")
    schedule = create_proposed_schedule(db_session, context=context)
    schedule.status = "active"
    db_session.commit()

    service = ScheduleCommandService(db_session)
    pause = service.handle_text(
        task=task,
        context=context,
        text="pause that schedule",
        now=datetime(2026, 6, 4, 12, 0, tzinfo=UTC),
    )
    assert pause is not None
    assert pause.action == "pause"
    assert schedule.status == "paused"

    resume_task = create_command_task(
        db_session,
        context=context,
        input_text="resume that schedule",
    )
    resume = service.handle_text(
        task=resume_task,
        context=context,
        text="resume that schedule",
        now=datetime(2026, 6, 4, 12, 1, tzinfo=UTC),
    )
    assert resume is not None
    assert resume.action == "resume"
    assert schedule.status == "active"

    cancel_task = create_command_task(
        db_session,
        context=context,
        input_text="cancel that schedule",
    )
    cancel = service.handle_text(
        task=cancel_task,
        context=context,
        text="cancel that schedule",
        now=datetime(2026, 6, 4, 12, 2, tzinfo=UTC),
    )
    db_session.commit()

    assert cancel is not None
    assert cancel.action == "cancel"
    assert schedule.status == "cancelled"
    assert schedule.next_run_at is None
    event = latest_log_event(db_session, cancel_task)
    assert event.payload["message"] == "schedule_cancelled"


def cleanup_database(session: Session) -> None:
    for model in (TaskEvent, Task, Schedule, Installation):
        session.execute(delete(model))


def create_source_task(
    session: Session,
    *,
    input_text: str,
) -> tuple[Task, ScheduleCreationContext]:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    task = TaskService(session).create_task(
        installation_id=installation.id,
        slack_channel_id="DTestUser",
        slack_user_id="UTestUser",
        input=input_text,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_thread_ts="DTestUser",
        slack_message_ts=f"1716500000.{uuid.uuid4().hex[:6]}",
        source_surface="dm",
    )
    context = ScheduleCreationContext(
        installation_id=installation.id,
        slack_channel_id="DTestUser",
        slack_user_id="UTestUser",
        slack_thread_ts="DTestUser",
        source_surface="dm",
        source_task_id=task.id,
    )
    return task, context


def create_proposed_schedule(
    session: Session,
    *,
    context: ScheduleCreationContext,
) -> Schedule:
    schedule = Schedule(
        installation_id=context.installation_id,
        owner_type="user",
        owner_slack_user_id=context.slack_user_id,
        title="Check unresolved decisions",
        spec_kind="cron",
        cron_expr="0 9 * * 1",
        timezone="UTC",
        next_run_at=datetime(2026, 6, 8, 9, 0, tzinfo=UTC),
        catchup_policy="skip",
        catchup_window_seconds=300,
        overlap_policy="skip",
        status="proposed",
        delivery_kind="slack_dm",
        delivery_slack_user_id=context.slack_user_id,
        delivery_slack_channel_id=context.slack_channel_id,
        delivery_slack_thread_ts=context.slack_thread_ts,
        artifact_delivery_policy="message_only",
        task_template={
            "input": "check unresolved decisions",
            "slack_channel_id": context.slack_channel_id,
            "slack_user_id": context.slack_user_id,
            "slack_thread_ts": context.slack_thread_ts,
            "delivery_surface": context.delivery_surface,
            "artifact_delivery_policy": "message_only",
        },
        planned_cost_ceiling_usd=Decimal("0.2500"),
        created_by_slack_user_id=context.slack_user_id,
        metadata_json={
            "source_task_id": str(context.source_task_id),
            "source_surface": context.source_surface,
            "original_input": "Draft a schedule before running: check unresolved decisions",
            "cadence_label": "Every Monday morning",
            "delivery_surface": context.delivery_surface,
            "confirmation_required": True,
            "parse_strategy": "rules",
        },
    )
    session.add(schedule)
    session.flush()
    return schedule


def create_command_task(
    session: Session,
    *,
    context: ScheduleCreationContext,
    input_text: str,
) -> Task:
    return TaskService(session).create_task(
        installation_id=context.installation_id,
        slack_channel_id=context.slack_channel_id,
        slack_user_id=context.slack_user_id,
        input=input_text,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_thread_ts=context.slack_thread_ts,
        slack_message_ts=f"1716500001.{uuid.uuid4().hex[:6]}",
        source_surface="dm",
    )


def latest_log_event(session: Session, task: Task) -> TaskEvent:
    event = session.scalar(
        select(TaskEvent)
        .where(TaskEvent.task_id == task.id, TaskEvent.type == TaskEventType.log)
        .order_by(TaskEvent.seq.desc())
        .limit(1)
    )
    assert event is not None
    return event
