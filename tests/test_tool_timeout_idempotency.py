"""HIG-195 (per-tool timeouts) and HIG-194 (tool idempotency) tests."""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from kortny.agent import AgentCoordinator, ExecutionGuardrailLimits
from kortny.agent.execution import build_idempotency_key, normalized_tool_args_hash
from kortny.agent.idempotency import (
    TOOL_CALL_DEDUPLICATED_MESSAGE,
    TOOL_CALL_UNKNOWN_OUTCOME_MESSAGE,
    TOOL_LEASE_PRESSURE_MESSAGE,
)
from kortny.agent.planner import ExecutionPlanner, PlannerGateDecision
from kortny.db.models import (
    Installation,
    Task,
    TaskEvent,
    TaskEventType,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.llm import ChatMessage, Completion, TokenUsage, ToolCall
from kortny.tasks import TaskService
from kortny.tools import RecoverableToolError, ToolArtifact, ToolRegistry, ToolResult
from kortny.tools import registry as registry_module
from kortny.tools.catalog import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    tool_metadata,
    tool_timeout_seconds,
)
from kortny.tools.registry import (
    TOOL_TIMEOUT_ERROR_CODE,
    invoke_tool_with_timeout,
)
from kortny.tools.types import JsonObject, JsonSchema

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")


# ---------------------------------------------------------------------------
# HIG-195: registry timeout enforcement (no DB needed)
# ---------------------------------------------------------------------------


class _SleepTool:
    """A tool that blocks for ``sleep_seconds`` and records completion."""

    description = "Sleeps then returns."
    parameters: JsonSchema = {"type": "object", "properties": {}}

    def __init__(self, *, name: str, sleep_seconds: float) -> None:
        self.name = name
        self.sleep_seconds = sleep_seconds
        self.completed = threading.Event()
        self.invoked = threading.Event()

    def invoke(self, args: JsonObject) -> ToolResult:
        self.invoked.set()
        time.sleep(self.sleep_seconds)
        self.completed.set()
        return ToolResult(output={"slept": self.sleep_seconds})


def test_invoke_with_timeout_raises_recoverable_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_module, "tool_timeout_seconds", lambda name: 1)
    tool = _SleepTool(name="slow_tool", sleep_seconds=10)

    started = time.perf_counter()
    with pytest.raises(RecoverableToolError) as exc_info:
        invoke_tool_with_timeout(tool, {})
    elapsed = time.perf_counter() - started

    assert exc_info.value.code == TOOL_TIMEOUT_ERROR_CODE
    # Fires within the deadline plus a small margin, not after the 10s sleep.
    assert elapsed < 3.0
    assert tool.invoked.is_set()
    # The lingering thread is allowed to finish; its result is discarded.
    assert not tool.completed.is_set()


def test_invoke_with_timeout_late_result_is_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_module, "tool_timeout_seconds", lambda name: 1)
    tool = _SleepTool(name="slow_tool", sleep_seconds=2)

    with pytest.raises(RecoverableToolError):
        invoke_tool_with_timeout(tool, {})

    # The thread eventually completes, but the timed-out caller never reads it,
    # so the late result can never be recorded against the task.
    assert tool.completed.wait(timeout=5)


def test_invoke_with_timeout_fast_tool_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_module, "tool_timeout_seconds", lambda name: 5)
    tool = _SleepTool(name="fast_tool", sleep_seconds=0.01)

    result = invoke_tool_with_timeout(tool, {})

    assert result.output == {"slept": 0.01}


def test_invoke_with_timeout_zero_disables_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry_module, "tool_timeout_seconds", lambda name: 0)
    tool = _SleepTool(name="unbounded", sleep_seconds=0.05)

    result = invoke_tool_with_timeout(tool, {})

    assert result.output == {"slept": 0.05}


def test_registry_invoke_enforces_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "tool_timeout_seconds", lambda name: 1)
    tool = _SleepTool(name="slow_tool", sleep_seconds=10)
    registry = ToolRegistry([tool])

    with pytest.raises(RecoverableToolError) as exc_info:
        registry.invoke("slow_tool", {})

    assert exc_info.value.code == TOOL_TIMEOUT_ERROR_CODE


def test_catalog_timeout_defaults_and_overrides() -> None:
    # External / unknown tools fall back to the conservative default.
    assert tool_timeout_seconds("composio.github.create_issue") == (
        DEFAULT_TOOL_TIMEOUT_SECONDS
    )
    # Quick local lookup is short; sandbox/document tools run long.
    assert tool_timeout_seconds("resolve_slack_identity") == 15
    assert tool_timeout_seconds("pdf_generator") == 180
    assert (
        tool_metadata("sandbox_bash").timeout_seconds
        > tool_metadata("sandbox_bash").sandbox.resource_limits.timeout_seconds
    )


# ---------------------------------------------------------------------------
# HIG-194: idempotency (DB-backed)
# ---------------------------------------------------------------------------

pytestmark_db = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for idempotency tests",
)


class _NoPlan(ExecutionPlanner):
    def should_plan(
        self,
        *,
        task: Task,
        tool_schemas: Sequence[JsonSchema],
        intent_decision: Mapping[str, object] | None,
    ) -> PlannerGateDecision:
        del task, tool_schemas, intent_decision
        return PlannerGateDecision(False, "test_no_plan")


class _FakeLLM:
    def __init__(self, completions: Sequence[Completion]) -> None:
        self.completions = list(completions)

    def complete(
        self,
        *,
        task_id: uuid.UUID,
        messages: Sequence[ChatMessage],
        tools: Sequence[JsonSchema] = (),
        response_format: JsonObject | None = None,
        prompt_name: str | None = None,
        prompt_source: str = "code",
    ) -> Completion:
        del task_id, messages, tools, response_format, prompt_name, prompt_source
        if not self.completions:
            raise AssertionError("FakeLLM exhausted")
        return self.completions.pop(0)


class _CountingWriteTool:
    """A side-effecting tool that counts how many times it actually runs."""

    name = "slack_reply_thread"  # side_effect == "write" in catalog
    description = "Posts a reply (counts executions)."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self.invocations = 0

    def invoke(self, args: JsonObject) -> ToolResult:
        self.invocations += 1
        return ToolResult(
            output={"ok": True, "posted": args.get("text")},
            artifacts=(ToolArtifact(filename="receipt.txt"),),
        )


class _CountingReadTool:
    name = "web_search"  # side_effect == "read" in catalog
    description = "Searches (counts executions)."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self) -> None:
        self.invocations = 0

    def invoke(self, args: JsonObject) -> ToolResult:
        self.invocations += 1
        return ToolResult(output={"results": []})


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    assert TEST_POSTGRES_URL is not None
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", normalize_database_url(TEST_POSTGRES_URL))
    command.upgrade(config, "head")
    eng = make_engine(TEST_POSTGRES_URL)
    try:
        yield eng
    finally:
        eng.dispose()


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


def _cleanup(session: Session) -> None:
    session.execute(delete(TaskEvent))
    session.execute(delete(Task))
    session.execute(delete(Installation))


def _make_task(session: Session, *, input_text: str, attempts: int = 0) -> Task:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    task = TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input=input_text,
    )
    task.attempts = attempts
    session.flush()
    return task


def _tool_call_completion(
    *, call_id: str, name: str, arguments: JsonObject
) -> Completion:
    return Completion(
        content=None,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
        usage=TokenUsage(input_tokens=10, output_tokens=2),
    )


def _seed_prior_attempt(
    session: Session,
    task: Task,
    *,
    tool_name: str,
    arguments: JsonObject,
    completed: bool,
    output: JsonObject | None = None,
) -> str:
    """Seed a prior tool_call (and optionally tool_result) for the same key."""

    normalized = normalized_tool_args_hash(arguments)
    key = build_idempotency_key(
        task_id=task.id,
        step_id="step-1",
        tool_name=tool_name,
        normalized_args_hash=normalized,
    )
    svc = TaskService(session)
    svc.append_event(
        task,
        TaskEventType.tool_call,
        {
            "turn": 1,
            "tool_call_id": "prior-call",
            "tool": tool_name,
            "step_id": "step-1",
            "normalized_args_hash": normalized,
            "idempotency_key": key,
            "attempt_no": 1,
            "argument_keys": sorted(arguments),
            "arguments": arguments,
        },
    )
    if completed:
        svc.append_event(
            task,
            TaskEventType.tool_result,
            {
                "turn": 1,
                "tool_call_id": "prior-call",
                "tool": tool_name,
                "step_id": "step-1",
                "normalized_args_hash": normalized,
                "idempotency_key": key,
                "attempt_no": 1,
                "output": output or {"ok": True},
                "cost_usd": "0",
                "artifacts": [],
            },
        )
    session.flush()
    return key


def _events(session: Session, task: Task) -> list[TaskEvent]:
    from sqlalchemy import select

    return list(
        session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task.id)
            .order_by(TaskEvent.seq)
        )
    )


@pytestmark_db
def test_completed_prior_attempt_is_replayed_not_reexecuted(
    db_session: Session,
) -> None:
    task = _make_task(db_session, input_text="post the update", attempts=1)
    arguments = {"text": "hello"}
    _seed_prior_attempt(
        db_session,
        task,
        tool_name="slack_reply_thread",
        arguments=arguments,
        completed=True,
        output={"ok": True, "posted": "hello"},
    )
    tool = _CountingWriteTool()
    llm = _FakeLLM(
        [
            _tool_call_completion(
                call_id="call-1", name="slack_reply_thread", arguments=arguments
            ),
            Completion(
                content="Done.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([tool]),
        execution_planner=_NoPlan(),
    ).run(task)

    # The completed side effect was NOT re-executed.
    assert tool.invocations == 0
    messages = [
        event.payload["message"]
        for event in _events(db_session, task)
        if event.type is TaskEventType.log and "message" in event.payload
    ]
    assert TOOL_CALL_DEDUPLICATED_MESSAGE in messages


@pytestmark_db
def test_write_tool_crash_window_surfaces_unknown_outcome(
    db_session: Session,
) -> None:
    task = _make_task(db_session, input_text="post the update", attempts=1)
    arguments = {"text": "hello"}
    _seed_prior_attempt(
        db_session,
        task,
        tool_name="slack_reply_thread",
        arguments=arguments,
        completed=False,
    )
    tool = _CountingWriteTool()
    llm = _FakeLLM(
        [
            _tool_call_completion(
                call_id="call-1", name="slack_reply_thread", arguments=arguments
            ),
            Completion(
                content="I cannot safely retry that.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([tool]),
        execution_planner=_NoPlan(),
    ).run(task)

    # The side-effecting tool with an unknown prior outcome was NOT re-run.
    assert tool.invocations == 0
    events = _events(db_session, task)
    unknown_event = next(
        event
        for event in events
        if event.type is TaskEventType.log
        and event.payload.get("message") == TOOL_CALL_UNKNOWN_OUTCOME_MESSAGE
    )
    assert unknown_event.payload["side_effect"] == "write"
    assert unknown_event.payload["tool"] == "slack_reply_thread"


@pytestmark_db
def test_read_tool_crash_window_reexecutes(db_session: Session) -> None:
    task = _make_task(db_session, input_text="search it", attempts=1)
    arguments = {"query": "kortny"}
    _seed_prior_attempt(
        db_session,
        task,
        tool_name="web_search",
        arguments=arguments,
        completed=False,
    )
    tool = _CountingReadTool()
    llm = _FakeLLM(
        [
            _tool_call_completion(
                call_id="call-1", name="web_search", arguments=arguments
            ),
            Completion(
                content="Here is what I found.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([tool]),
        execution_planner=_NoPlan(),
    ).run(task)

    # Read-only tools are safe to re-run after an unknown prior outcome.
    assert tool.invocations == 1


@pytestmark_db
def test_fresh_task_never_deduplicates(db_session: Session) -> None:
    task = _make_task(db_session, input_text="post the update", attempts=0)
    arguments = {"text": "hello"}
    # Even with a (stale) completed ledger entry, attempts==0 skips the lookup.
    _seed_prior_attempt(
        db_session,
        task,
        tool_name="slack_reply_thread",
        arguments=arguments,
        completed=True,
        output={"ok": True},
    )
    tool = _CountingWriteTool()
    llm = _FakeLLM(
        [
            _tool_call_completion(
                call_id="call-1", name="slack_reply_thread", arguments=arguments
            ),
            Completion(
                content="Done.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([tool]),
        execution_planner=_NoPlan(),
    ).run(task)

    # Fresh task pays no ledger lookup and runs the tool normally.
    assert tool.invocations == 1
    messages = [
        event.payload.get("message")
        for event in _events(db_session, task)
        if event.type is TaskEventType.log
    ]
    assert TOOL_CALL_DEDUPLICATED_MESSAGE not in messages


@pytestmark_db
def test_lease_pressure_warning_emitted(db_session: Session) -> None:
    from datetime import UTC, datetime, timedelta

    task = _make_task(db_session, input_text="generate the document", attempts=0)
    # pdf_generator has a 180s deadline; a 60s remaining lease makes the
    # deadline exceed half the remaining lease -> warning expected.
    task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
    db_session.flush()

    class _PdfTool:
        name = "pdf_generator"
        description = "Generates a PDF."
        parameters: JsonSchema = {"type": "object", "properties": {}}

        def invoke(self, args: JsonObject) -> ToolResult:
            return ToolResult(output={"ok": True})

    llm = _FakeLLM(
        [
            _tool_call_completion(call_id="call-1", name="pdf_generator", arguments={}),
            Completion(
                content="Generated.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([_PdfTool()]),
        execution_planner=_NoPlan(),
        guardrail_limits=ExecutionGuardrailLimits(),
    ).run(task)

    messages = [
        event.payload.get("message")
        for event in _events(db_session, task)
        if event.type is TaskEventType.log
    ]
    assert TOOL_LEASE_PRESSURE_MESSAGE in messages
