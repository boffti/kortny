"""HIG-223 autonomy policy: DB resolution, approval matrix, audit emission."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Sequence

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.approvals import (
    TOOL_AUTONOMY_DECISION_MESSAGE,
    ApprovalScope,
    ToolApprovalPolicy,
)
from kortny.autonomy import AutonomyLevel, AutonomyTier, RiskAssessment
from kortny.autonomy_policy import AutonomyPolicyService
from kortny.db.models import (
    AutonomyPolicy,
    Installation,
    Task,
    TaskEvent,
    TaskEventType,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.llm import ChatMessage, Completion, ToolCall
from kortny.tasks import TaskService
from kortny.tools import ToolRegistry
from kortny.tools.types import JsonObject, JsonSchema, ToolResult

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for autonomy policy tests",
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


def _cleanup(session: Session) -> None:
    for model in (AutonomyPolicy, TaskEvent, Task, Installation):
        session.execute(delete(model))


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        _cleanup(session)
        session.commit()
        yield session
        session.rollback()
        _cleanup(session)
        session.commit()


def _installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation


# --- Stub external write tool -----------------------------------------------


class _StubWriteTool:
    name = "external_create_issue"
    description = "Create an issue in an external tracker."
    parameters: JsonObject = {"type": "object", "properties": {}}

    def invoke(self, args: JsonObject) -> ToolResult:  # pragma: no cover
        return ToolResult(output={})


class _FakeLLM:
    """The approval-gate path never calls the LLM; this satisfies the protocol."""

    def complete(
        self,
        *,
        task_id: uuid.UUID,
        messages: Sequence[ChatMessage],
        tools: Sequence[JsonSchema] = (),
        response_format: JsonObject | None = None,
        prompt_name: str | None = None,
        prompt_source: str = "code",
    ) -> Completion:  # pragma: no cover
        raise NotImplementedError


# --- Resolution --------------------------------------------------------------


def test_resolution_missing_rows_default_balanced(db_session: Session) -> None:
    installation = _installation(db_session)
    service = AutonomyPolicyService(db_session)
    level = service.resolve_level(installation_id=installation.id, channel_id="C1")
    assert level is AutonomyLevel.balanced


def test_channel_override_beats_workspace(db_session: Session) -> None:
    installation = _installation(db_session)
    service = AutonomyPolicyService(db_session)
    service.set_level(
        installation_id=installation.id,
        scope_type="workspace",
        scope_id=None,
        level=AutonomyLevel.conservative,
        updated_by_user_id="dashboard:admin",
    )
    service.set_level(
        installation_id=installation.id,
        scope_type="channel",
        scope_id="C1",
        level=AutonomyLevel.autonomous,
        updated_by_user_id="dashboard:admin",
    )
    db_session.flush()

    assert (
        service.resolve_level(installation_id=installation.id, channel_id="C1")
        is AutonomyLevel.autonomous
    )
    # A different channel falls back to the workspace level.
    assert (
        service.resolve_level(installation_id=installation.id, channel_id="C2")
        is AutonomyLevel.conservative
    )


def test_set_level_is_idempotent_upsert(db_session: Session) -> None:
    installation = _installation(db_session)
    service = AutonomyPolicyService(db_session)
    service.set_level(
        installation_id=installation.id,
        scope_type="channel",
        scope_id="C1",
        level=AutonomyLevel.balanced,
        updated_by_user_id="u",
    )
    service.set_level(
        installation_id=installation.id,
        scope_type="channel",
        scope_id="C1",
        level=AutonomyLevel.autonomous,
        updated_by_user_id="u2",
    )
    db_session.flush()
    rows: Sequence[AutonomyPolicy] = tuple(
        db_session.scalars(
            select(AutonomyPolicy).where(
                AutonomyPolicy.installation_id == installation.id,
                AutonomyPolicy.scope_type == "channel",
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].level == "autonomous"


def test_clear_channel_override(db_session: Session) -> None:
    installation = _installation(db_session)
    service = AutonomyPolicyService(db_session)
    service.set_level(
        installation_id=installation.id,
        scope_type="channel",
        scope_id="C1",
        level=AutonomyLevel.autonomous,
        updated_by_user_id="u",
    )
    db_session.flush()
    removed = service.clear_level(
        installation_id=installation.id, scope_type="channel", scope_id="C1"
    )
    assert removed is True
    assert (
        service.resolve_level(installation_id=installation.id, channel_id="C1")
        is AutonomyLevel.balanced
    )


# --- Approval matrix ---------------------------------------------------------


def _implicit_risk() -> RiskAssessment:
    return RiskAssessment(
        tier=AutonomyTier.implicit, reasons=("metadata_side_effect:write",)
    )


def _explicit_risk() -> RiskAssessment:
    return RiskAssessment(
        tier=AutonomyTier.explicit, reasons=("capability_outward:send",)
    )


def test_conservative_gates_insert() -> None:
    policy = ToolApprovalPolicy()
    requirement = policy.requirement_for(
        _StubWriteTool(),
        {"sql": "INSERT INTO t VALUES (1)"},
        autonomy_level=AutonomyLevel.conservative,
        risk=_implicit_risk(),
    )
    assert requirement.required is True
    assert requirement.scope is ApprovalScope.user


def test_balanced_auto_audits_insert() -> None:
    policy = ToolApprovalPolicy()
    requirement = policy.requirement_for(
        _StubWriteTool(),
        {},
        autonomy_level=AutonomyLevel.balanced,
        risk=_implicit_risk(),
    )
    assert requirement.required is False
    assert requirement.audit_autonomy is True


def test_balanced_gates_delete() -> None:
    policy = ToolApprovalPolicy()
    requirement = policy.requirement_for(
        _StubWriteTool(),
        {},
        autonomy_level=AutonomyLevel.balanced,
        risk=_explicit_risk(),
    )
    assert requirement.required is True
    assert requirement.scope is ApprovalScope.user


def test_autonomous_auto_audits_everything_except_explicit() -> None:
    policy = ToolApprovalPolicy()
    implicit = policy.requirement_for(
        _StubWriteTool(),
        {},
        autonomy_level=AutonomyLevel.autonomous,
        risk=_implicit_risk(),
    )
    assert implicit.required is False
    assert implicit.audit_autonomy is True

    explicit = policy.requirement_for(
        _StubWriteTool(),
        {},
        autonomy_level=AutonomyLevel.autonomous,
        risk=_explicit_risk(),
    )
    assert explicit.required is True
    assert explicit.scope is ApprovalScope.user


def test_existing_native_gates_survive_every_level() -> None:
    policy = ToolApprovalPolicy()

    class _Named:
        def __init__(self, name: str) -> None:
            self.name = name
            self.description = name

    for level in AutonomyLevel:
        deploy = policy.requirement_for(_Named("deploy_site"), {}, autonomy_level=level)
        assert deploy.required is True
        forget = policy.requirement_for(_Named("forget_fact"), {}, autonomy_level=level)
        assert forget.required is True


# --- Audit emission ----------------------------------------------------------


def test_tier1_auto_approval_appends_audit_event(db_session: Session) -> None:
    from kortny.agent.coordinator import AgentCoordinator
    from kortny.agent.execution import ToolAttemptRecord

    installation = _installation(db_session)
    task = TaskService(db_session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C1",
        slack_thread_ts="1716500000.000001",
        slack_message_ts="1716500000.000001",
        slack_user_id="U1",
        input="create an issue",
    )
    db_session.flush()

    registry = ToolRegistry()
    registry.register(_StubWriteTool())
    coordinator = AgentCoordinator(
        session=db_session,
        llm=_FakeLLM(),
        registry=registry,
    )
    attempt = ToolAttemptRecord(
        tool_name="external_create_issue",
        normalized_args_hash="abc123",
        attempt_no=1,
        status="ok",
    )
    tool_call = ToolCall(
        id="call-1", name="external_create_issue", arguments={"title": "x"}
    )

    # Balanced default -> implicit tier auto-approves and emits the audit event.
    coordinator._raise_if_tool_approval_required(
        task_obj=task,
        tool_call=tool_call,
        arguments={"title": "x"},
        attempt=attempt,
        turn=1,
        step_id="s1",
    )
    db_session.flush()

    events = tuple(
        db_session.scalars(
            select(TaskEvent).where(
                TaskEvent.task_id == task.id,
                TaskEvent.type == TaskEventType.log,
                TaskEvent.payload["message"].as_string()
                == TOOL_AUTONOMY_DECISION_MESSAGE,
            )
        )
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["tool"] == "external_create_issue"
    assert payload["risk"] == "implicit"
    assert payload["autonomy_level"] == "balanced"
    assert payload["reasons"]
