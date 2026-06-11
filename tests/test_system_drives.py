"""HIG-233: ambient drives surfaced as user-visible system Schedule rows.

These tests run against real Postgres (serial). They cover the control surface
(idempotent seeding, materializer skip, tick-time pause/cadence/last-run gate)
and the user surfaces (list_schedules labeling, mutation refusal, dashboard
grouping).
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.ambient.supervisor import run_gated_forever
from kortny.ambient.system_drives import (
    INTEGRATION_CATALOG_SYNC_DRIVE_KEY,
    MEMORY_CONSOLIDATION_DRIVE_KEY,
    SYSTEM_DRIVE_METADATA_KEY,
    WITNESS_SCAN_DRIVE_KEY,
    SystemDriveGate,
    is_system_drive,
    mark_drive_ran,
    resolve_drive_state,
    seed_system_drives,
    system_drive_purpose,
)
from kortny.config import Settings
from kortny.dashboard.schedules import apply_schedule_action, get_schedule_dashboard
from kortny.db.models import (
    Installation,
    LLMUsage,
    Schedule,
    Task,
    TaskEvent,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.scheduler import ScheduleMaterializer
from kortny.tasks import TaskService
from kortny.tools.schedules import (
    CancelScheduleTool,
    ListSchedulesTool,
    PauseScheduleTool,
    ResumeScheduleTool,
    UpdateScheduleTool,
)
from kortny.tools.types import RecoverableToolError

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for system drive tests",
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


def cleanup_database(session: Session) -> None:
    for model in (LLMUsage, TaskEvent, Task, Schedule, Installation):
        session.execute(delete(model))


def make_settings(**overrides: Any) -> Settings:
    payload: dict[str, Any] = {
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_APP_TOKEN": "xapp-test",
        "SLACK_SIGNING_SECRET": "signing-secret",
        "LLM_PROVIDER": "openrouter",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "openai/gpt-test",
        "COMPOSIO_API_KEY": "composio-key",
        "POSTGRES_URL": TEST_POSTGRES_URL,
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex[:10].upper()}")
    session.add(installation)
    session.flush()
    return installation


def create_task(session: Session, *, installation: Installation) -> Task:
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="DUser",
        slack_thread_ts="DUser",
        slack_message_ts="1780200000.000001",
        slack_user_id="UUser",
        input="What schedules are running?",
    )


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


def test_seeding_is_idempotent_double_boot_no_dupes(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()

    first = seed_system_drives(
        db_session, installation_id=installation.id, settings=settings
    )
    db_session.commit()
    assert len(first) == 3
    assert {
        WITNESS_SCAN_DRIVE_KEY,
        MEMORY_CONSOLIDATION_DRIVE_KEY,
        INTEGRATION_CATALOG_SYNC_DRIVE_KEY,
    } == {
        schedule.metadata_json[SYSTEM_DRIVE_METADATA_KEY]["key"] for schedule in first
    }

    second = seed_system_drives(
        db_session, installation_id=installation.id, settings=settings
    )
    db_session.commit()

    rows = db_session.scalars(
        select(Schedule).where(Schedule.installation_id == installation.id)
    ).all()
    assert len(rows) == 3  # double boot created no dupes
    assert {row.id for row in first} == {row.id for row in second}
    for row in rows:
        assert row.owner_type == "system"
        assert row.owner_slack_user_id is None
        assert row.next_run_at is None
        assert is_system_drive(row)
        assert system_drive_purpose(row)


def test_seeded_drive_uses_env_default_cadence(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings(KORTNY_COMPOSIO_SYNC_INTERVAL_HOURS=6.0)
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    db_session.commit()
    drive = db_session.scalar(
        select(Schedule).where(
            Schedule.installation_id == installation.id,
            Schedule.title == "Integration catalog sync",
        )
    )
    assert drive is not None
    assert drive.interval_seconds == 6 * 3600
    assert drive.metadata_json["cadence_label"] == "Every 6 hours"


# --------------------------------------------------------------------------- #
# Materializer
# --------------------------------------------------------------------------- #


def test_materializer_skips_system_drives(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    # Defensive: force a due next_run_at + active status so the only thing
    # keeping it out of materialization is the system-drive filter.
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    drive.next_run_at = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.commit()

    results = ScheduleMaterializer(db_session).materialize_due_schedules(
        now=datetime(2026, 6, 1, tzinfo=UTC),
        use_advisory_lock=False,
    )
    db_session.commit()

    assert results == ()
    tasks = db_session.scalars(select(Task)).all()
    assert tasks == []


# --------------------------------------------------------------------------- #
# Tick-time gate: pause, interval override, last-run
# --------------------------------------------------------------------------- #


def test_paused_drive_skips_loop_tick(db_session: Session, engine: Engine) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    drive.status = "paused"
    db_session.commit()

    session_factory = make_session_factory(engine=engine)
    gate = SystemDriveGate(key=WITNESS_SCAN_DRIVE_KEY, session_factory=session_factory)
    calls: list[int] = []

    stop = threading.Event()

    def run_once() -> None:
        calls.append(1)

    def fake_sleep(_seconds: float) -> None:
        stop.set()  # run exactly one iteration

    run_gated_forever(
        gate=gate,
        run_once=run_once,
        poll_interval_seconds=300.0,
        stop=stop,
        sleep=fake_sleep,
    )

    assert calls == []  # paused drive => work skipped


def test_active_drive_runs_and_stamps_last_run(
    db_session: Session, engine: Engine
) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    db_session.commit()

    session_factory = make_session_factory(engine=engine)
    gate = SystemDriveGate(key=WITNESS_SCAN_DRIVE_KEY, session_factory=session_factory)
    calls: list[int] = []
    stop = threading.Event()

    def run_once() -> None:
        calls.append(1)

    def fake_sleep(_seconds: float) -> None:
        stop.set()

    run_gated_forever(
        gate=gate,
        run_once=run_once,
        poll_interval_seconds=300.0,
        stop=stop,
        sleep=fake_sleep,
    )

    assert calls == [1]
    db_session.expire_all()
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    assert drive.last_run_at is not None  # productive tick stamped last-run


def test_interval_override_drives_sleep(db_session: Session, engine: Engine) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    drive.interval_seconds = 42  # operator cadence override
    db_session.commit()

    session_factory = make_session_factory(engine=engine)
    gate = SystemDriveGate(key=WITNESS_SCAN_DRIVE_KEY, session_factory=session_factory)
    sleeps: list[float] = []
    stop = threading.Event()

    def run_once() -> None:
        pass

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        stop.set()

    run_gated_forever(
        gate=gate,
        run_once=run_once,
        poll_interval_seconds=300.0,  # env default, should be overridden
        stop=stop,
        sleep=fake_sleep,
    )

    assert sleeps == [42.0]


def test_resolve_and_mark_helpers(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    db_session.commit()

    state = resolve_drive_state(
        db_session, installation_id=installation.id, key=MEMORY_CONSOLIDATION_DRIVE_KEY
    )
    assert state.found is True
    assert state.paused is False
    assert state.should_run is True

    # Missing drive => env-var fallthrough (found False, should_run True).
    missing = resolve_drive_state(
        db_session, installation_id=installation.id, key="does_not_exist"
    )
    assert missing.found is False
    assert missing.should_run is True

    now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)
    assert mark_drive_ran(
        db_session,
        installation_id=installation.id,
        key=MEMORY_CONSOLIDATION_DRIVE_KEY,
        now=now,
    )
    db_session.flush()
    drive = db_session.scalar(
        select(Schedule).where(Schedule.title == "Memory consolidation")
    )
    assert drive is not None
    assert drive.last_run_at == now


# --------------------------------------------------------------------------- #
# list_schedules tool
# --------------------------------------------------------------------------- #


def test_list_schedules_labels_system_drives(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    task = create_task(db_session, installation=installation)
    db_session.commit()

    result = ListSchedulesTool(session=db_session, task=task).invoke(
        {"scope": "visible", "status": "active"}
    )

    payloads = result.output["schedules"]
    assert result.output["count"] == 3
    assert all(payload["is_system_drive"] for payload in payloads)
    assert all(payload["system_purpose"] for payload in payloads)
    assert "system drive" in result.output["assistant_summary"]


# --------------------------------------------------------------------------- #
# Mutation tools: cancel refused, pause/resume allowed
# --------------------------------------------------------------------------- #


def test_cancel_system_drive_is_refused(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    task = create_task(db_session, installation=installation)
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    db_session.commit()

    with pytest.raises(RecoverableToolError) as exc_info:
        CancelScheduleTool(session=db_session, task=task).invoke(
            {"schedule_id": str(drive.id)}
        )
    assert exc_info.value.code == "system_drive_not_cancellable"

    with pytest.raises(RecoverableToolError) as update_exc:
        UpdateScheduleTool(session=db_session, task=task).invoke(
            {"schedule_id": str(drive.id), "update_request": "every hour"}
        )
    assert update_exc.value.code == "system_drive_not_cancellable"


def test_pause_and_resume_system_drive_allowed(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    task = create_task(db_session, installation=installation)
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    db_session.commit()

    pause = PauseScheduleTool(session=db_session, task=task).invoke(
        {"schedule_id": str(drive.id)}
    )
    db_session.flush()
    assert pause.output["action"] == "paused"
    db_session.expire(drive)
    assert drive.status == "paused"

    resume = ResumeScheduleTool(session=db_session, task=task).invoke(
        {"schedule_id": str(drive.id)}
    )
    db_session.flush()
    assert resume.output["action"] == "resumed"
    db_session.expire(drive)
    assert drive.status == "active"


# --------------------------------------------------------------------------- #
# Dashboard grouping + action refusal
# --------------------------------------------------------------------------- #


def test_dashboard_groups_system_rows(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    # One ordinary user schedule to confirm grouping splits them.
    db_session.add(
        Schedule(
            installation_id=installation.id,
            owner_type="user",
            owner_slack_user_id="UUser",
            title="User daily digest",
            spec_kind="cron",
            cron_expr="0 8 * * *",
            next_run_at=datetime(2026, 6, 12, 13, 0, tzinfo=UTC),
            status="active",
            delivery_kind="slack_dm",
            delivery_slack_user_id="UUser",
            delivery_slack_channel_id="DUser",
        )
    )
    db_session.commit()

    page = get_schedule_dashboard(
        db_session,
        installation_id=installation.id,
        slack_user_id="UUser",
        is_admin=True,
        view="all",
        status="all",
    )

    assert len(page.system_rows) == 3
    assert len(page.user_rows) == 1
    for row in page.system_rows:
        assert row.is_system is True
        assert row.purpose
        assert row.can_cancel is False  # pause/resume only
        assert row.can_activate is False


def test_dashboard_refuses_cancel_of_system_drive(db_session: Session) -> None:
    installation = create_installation(db_session)
    settings = make_settings()
    seed_system_drives(db_session, installation_id=installation.id, settings=settings)
    drive = db_session.scalar(select(Schedule).where(Schedule.title == "Witness scan"))
    assert drive is not None
    db_session.commit()

    with pytest.raises(ValueError, match="System drives can only be paused"):
        apply_schedule_action(
            db_session,
            schedule_id=drive.id,
            action="cancel",
            installation_id=installation.id,
            slack_user_id=None,
            is_admin=True,
        )

    # Pause is allowed.
    notice = apply_schedule_action(
        db_session,
        schedule_id=drive.id,
        action="pause",
        installation_id=installation.id,
        slack_user_id=None,
        is_admin=True,
    )
    assert "paused" in notice.lower()
