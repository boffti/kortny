import json
import os
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.agent import AgentCoordinator, AgentTurnLimitError
from kortny.agent.thread_context import ThreadTranscriptMessage
from kortny.db.models import (
    Artifact,
    EncryptedSecret,
    Installation,
    LLMUsage,
    ModelPricing,
    Task,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.llm import ChatMessage, Completion, TokenUsage, ToolCall
from kortny.tasks import TaskService
from kortny.tools import ToolArtifact, ToolRegistry, ToolResult
from kortny.tools.types import JsonObject, JsonSchema

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for agent coordinator tests",
)


class FakeLLM:
    def __init__(self, completions: Sequence[Completion]) -> None:
        self.completions = list(completions)
        self.calls: list[
            tuple[uuid.UUID, tuple[ChatMessage, ...], tuple[JsonSchema, ...]]
        ] = []

    def complete(
        self,
        *,
        task_id: uuid.UUID,
        messages: Sequence[ChatMessage],
        tools: Sequence[JsonSchema] = (),
    ) -> Completion:
        self.calls.append((task_id, tuple(messages), tuple(tools)))
        if not self.completions:
            raise AssertionError("FakeLLM received more calls than expected")
        return self.completions.pop(0)


class FakeThreadTranscriptProvider:
    def __init__(self, messages: Sequence[ThreadTranscriptMessage]) -> None:
        self.messages = tuple(messages)
        self.calls: list[tuple[str, str, int]] = []

    def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> tuple[ThreadTranscriptMessage, ...]:
        self.calls.append((channel_id, thread_ts, limit))
        return self.messages[:limit]


class EchoJsonTool:
    name = "echo_json"
    description = "Echoes JSON arguments."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(output={"echoed": args["message"]}, cost_usd=Decimal("0.1"))


class ArtifactTool:
    name = "make_artifact"
    description = "Returns an artifact."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(
            output={"created": True},
            artifacts=(
                ToolArtifact(
                    filename="report.pdf",
                    path="/tmp/report.pdf",
                    mime_type="application/pdf",
                    size_bytes=42,
                ),
            ),
        )


class RecordingPdfTool:
    name = "pdf_generator"
    description = "Records PDF arguments."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    def __init__(self) -> None:
        self.calls: list[JsonObject] = []

    def invoke(self, args: JsonObject) -> ToolResult:
        self.calls.append(args)
        return ToolResult(
            output={"created": True},
            artifacts=(
                ToolArtifact(
                    filename="report.pdf",
                    path="/tmp/report.pdf",
                    mime_type="application/pdf",
                    size_bytes=42,
                ),
            ),
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


def test_coordinator_finishes_with_final_answer(db_session: Session) -> None:
    task = create_task(db_session, input_text="summarize this")
    llm = FakeLLM(
        [
            Completion(
                content="Here is the summary.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=10, output_tokens=5),
                response_id="gen-final",
                model="openai/gpt-4o-mini",
            )
        ]
    )

    result = AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
    ).run(task)

    assert result.result_summary == "Here is the summary."
    assert result.turns == 1
    assert result.artifact_count == 0
    assert task.result_summary == "Here is the summary."
    assert llm.calls[0][1] == (ChatMessage(role="user", content="summarize this"),)

    events = task_events(db_session, task)
    assert event_messages(events) == [
        "agent_started",
        "agent_llm_turn_started",
        "agent_llm_turn_completed",
        "agent_completed",
    ]
    assert events[-1].payload["reason"] == "final_answer"


def test_coordinator_includes_prior_thread_context_for_follow_up(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    first = create_task(
        db_session,
        input_text="research Python tempfile best practices and make a PDF",
        installation=installation,
        slack_event_id="EvResearchTurn",
        created_at=datetime(2026, 5, 23, 11, 0, tzinfo=UTC),
    )
    first.result_summary = "Generated a PDF about Python tempfile best practices."
    service.transition(first, TaskStatus.succeeded)
    service.append_event(
        first,
        TaskEventType.tool_call,
        {
            "turn": 1,
            "tool": "web_search",
            "arguments": {"query": "Python tempfile best practices"},
        },
    )
    service.append_event(
        first,
        TaskEventType.tool_result,
        {
            "turn": 1,
            "tool": "web_search",
            "output": {
                "results": [{"url": "https://docs.python.org/3/library/tempfile.html"}]
            },
        },
    )
    follow_up = create_task(
        db_session,
        input_text="make it punchier",
        installation=installation,
        slack_event_id="EvFollowUp",
        slack_message_ts="1716400100.000001",
        created_at=datetime(2026, 5, 23, 11, 1, tzinfo=UTC),
    )
    transcript_provider = FakeThreadTranscriptProvider(
        (
            ThreadTranscriptMessage(
                ts="1716400000.000001",
                user_id="U123",
                text="research Python tempfile best practices and make a PDF",
            ),
            ThreadTranscriptMessage(
                ts="1716400100.000001",
                user_id="U123",
                text="make it punchier",
            ),
        )
    )
    llm = FakeLLM(
        [
            Completion(
                content="Punchier version ready.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=100, output_tokens=20),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
        thread_transcript_provider=transcript_provider,
    ).run(follow_up)

    first_call_messages = llm.calls[0][1]
    prior_context = first_call_messages[0].content or ""

    assert first_call_messages[0].role == "system"
    assert "<prior_context>" in prior_context
    assert "Generated a PDF about Python tempfile best practices." in prior_context
    assert "web_search" in prior_context
    assert "https://docs.python.org/3/library/tempfile.html" in prior_context
    assert "Slack thread transcript" in prior_context
    assert first_call_messages[-1] == ChatMessage(
        role="user", content="make it punchier"
    )
    assert transcript_provider.calls == [("C123", "1716400000.000001", 30)]


def test_coordinator_orders_three_turn_thread_context(db_session: Session) -> None:
    installation = create_installation(db_session)
    first = create_task(
        db_session,
        input_text="research FastAPI deployment",
        installation=installation,
        slack_event_id="EvThreadOne",
        created_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
    )
    first.result_summary = "FastAPI can run behind a reverse proxy."
    second = create_task(
        db_session,
        input_text="turn that into a PDF",
        installation=installation,
        slack_event_id="EvThreadTwo",
        slack_message_ts="1716400200.000001",
        created_at=datetime(2026, 5, 23, 12, 1, tzinfo=UTC),
    )
    second.result_summary = "Generated 1 artifact."
    third = create_task(
        db_session,
        input_text="what was the key takeaway?",
        installation=installation,
        slack_event_id="EvThreadThree",
        slack_message_ts="1716400300.000001",
        created_at=datetime(2026, 5, 23, 12, 2, tzinfo=UTC),
    )
    llm = FakeLLM(
        [
            Completion(
                content="The key takeaway was deployment behind a reverse proxy.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=80, output_tokens=15),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
    ).run(third)

    context = llm.calls[0][1][0].content or ""
    recent_context = context.split("Recent prior task details:", maxsplit=1)[1]

    assert recent_context.index("research FastAPI deployment") < recent_context.index(
        "turn that into a PDF"
    )
    assert "what was the key takeaway?" not in context


def test_coordinator_includes_failed_prior_task_context(db_session: Session) -> None:
    installation = create_installation(db_session)
    service = TaskService(db_session)
    failed = create_task(
        db_session,
        input_text="research unavailable source",
        installation=installation,
        slack_event_id="EvFailedPrior",
        created_at=datetime(2026, 5, 23, 13, 0, tzinfo=UTC),
    )
    failed.error = {"type": "ValueError", "message": "source unavailable"}
    service.append_event(
        failed,
        TaskEventType.error,
        {"type": "ValueError", "message": "source unavailable"},
    )
    service.transition(failed, TaskStatus.failed)
    current = create_task(
        db_session,
        input_text="try a different source",
        installation=installation,
        slack_event_id="EvAfterFailedPrior",
        slack_message_ts="1716400400.000001",
        created_at=datetime(2026, 5, 23, 13, 1, tzinfo=UTC),
    )
    llm = FakeLLM(
        [
            Completion(
                content="I will use a different source.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=80, output_tokens=15),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
    ).run(current)

    context = llm.calls[0][1][0].content or ""

    assert "status=failed" in context
    assert "ValueError: source unavailable" in context
    assert "try a different source" not in context


def test_coordinator_preserves_prior_slack_file_ids_for_follow_up(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    long_preview = "This document preview is long. " * 20
    first = create_task(
        db_session,
        input_text=(
            f"Give me a summary of this report\n{long_preview}\n\n"
            "<slack_files>\n"
            "- id: F123\n"
            "  name: pypl_report.pdf\n"
            "  mimetype: application/pdf\n"
            "  size_bytes: 2048\n"
            "</slack_files>"
        ),
        installation=installation,
        slack_event_id="EvDmReport",
        slack_channel_id="D123",
        slack_thread_ts="D123",
        slack_message_ts="1716500000.000001",
        created_at=datetime(2026, 5, 23, 13, 30, tzinfo=UTC),
    )
    first.result_summary = "The report summarizes PayPal Holdings."
    current = create_task(
        db_session,
        input_text="Can you extend this report with more context?",
        installation=installation,
        slack_event_id="EvDmReportFollowUp",
        slack_channel_id="D123",
        slack_thread_ts="D123",
        slack_message_ts="1716500010.000001",
        created_at=datetime(2026, 5, 23, 13, 31, tzinfo=UTC),
    )
    llm = FakeLLM(
        [
            Completion(
                content="I can reuse file F123.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=80, output_tokens=15),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
    ).run(current)

    context = llm.calls[0][1][0].content or ""

    assert "slack_file_ids=F123" in context
    assert "attached Slack files from original request" in context
    assert "pypl_report.pdf" in context
    assert "Can you extend this report" not in context


def test_coordinator_highlights_immediate_previous_exchange_for_short_follow_up(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    previous = create_task(
        db_session,
        input_text="Try now",
        installation=installation,
        slack_event_id="EvDmTryNow",
        slack_channel_id="D123",
        slack_thread_ts="D123",
        slack_message_ts="1716500020.000001",
        created_at=datetime(2026, 5, 23, 13, 32, tzinfo=UTC),
    )
    previous.result_summary = (
        "I've accessed the PDF file, which is a report on PayPal Holdings, Inc. "
        "(PYPL). Now, I'll extend this report to include more context and make "
        "it at least 3 pages long. Do you have any specific topics or additional "
        "details you want included, or should I proceed with general research?"
    )
    current = create_task(
        db_session,
        input_text="general research and market sentiment",
        installation=installation,
        slack_event_id="EvDmMarketSentiment",
        slack_channel_id="D123",
        slack_thread_ts="D123",
        slack_message_ts="1716500030.000001",
        created_at=datetime(2026, 5, 23, 13, 33, tzinfo=UTC),
    )
    transcript_provider = FakeThreadTranscriptProvider(())
    llm = FakeLLM(
        [
            Completion(
                content="I'll expand the PYPL report with general research and market sentiment.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=100, output_tokens=18),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
        thread_transcript_provider=transcript_provider,
    ).run(current)

    context = llm.calls[0][1][0].content or ""

    assert "Immediate previous exchange:" in context
    assert "Do you have any specific topics" in context
    assert "should I proceed with general research?" in context
    assert "general research and market sentiment" not in context
    assert transcript_provider.calls == []


def test_coordinator_includes_prior_generated_artifacts_for_revision_follow_up(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    prior = create_task(
        db_session,
        input_text="Enhance the report",
        installation=installation,
        slack_event_id="EvPriorArtifact",
        created_at=datetime(2026, 5, 23, 13, 34, tzinfo=UTC),
    )
    prior.result_summary = "Generated 1 artifact."
    db_session.add(
        Artifact(
            task_id=prior.id,
            filename="pypl_report_v2.pdf",
            mime_type="application/pdf",
            size_bytes=4096,
            storage_path=None,
            slack_file_id="FGENV2",
        )
    )
    current = create_task(
        db_session,
        input_text="make it more elaborate",
        installation=installation,
        slack_event_id="EvCurrentArtifactRevision",
        slack_message_ts="1716500040.000001",
        created_at=datetime(2026, 5, 23, 13, 35, tzinfo=UTC),
    )
    llm = FakeLLM(
        [
            Completion(
                content="I will revise the latest generated artifact.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=100, output_tokens=18),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
    ).run(current)

    context = llm.calls[0][1][0].content or ""

    assert "generated artifacts:" in context
    assert "pypl_report_v2.pdf" in context
    assert "slack_file_id=FGENV2" in context
    assert "prefer the newest generated artifact" in context


def test_coordinator_compacts_prior_context_when_over_budget(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    first = create_task(
        db_session,
        input_text="research a very long topic",
        installation=installation,
        slack_event_id="EvLongPrior",
        created_at=datetime(2026, 5, 23, 14, 0, tzinfo=UTC),
    )
    first.result_summary = "Summary survives compaction."
    TaskService(db_session).append_event(
        first,
        TaskEventType.tool_result,
        {"output": {"large": "x" * 2_000}},
    )
    current = create_task(
        db_session,
        input_text="refine that",
        installation=installation,
        slack_event_id="EvLongCurrent",
        slack_message_ts="1716400500.000001",
        created_at=datetime(2026, 5, 23, 14, 1, tzinfo=UTC),
    )
    llm = FakeLLM(
        [
            Completion(
                content="Refined.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=40, output_tokens=8),
            )
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry(),
        thread_context_max_chars=500,
    ).run(current)

    context = llm.calls[0][1][0].content or ""

    assert "Context was compacted" in context
    assert "Summary survives compaction." in context
    assert '"large"' not in context


def test_coordinator_injects_pdf_min_pages_from_user_request(
    db_session: Session,
) -> None:
    task = create_task(
        db_session,
        input_text="make it more elaborate. I want 3 pages of data",
    )
    pdf_tool = RecordingPdfTool()
    llm = FakeLLM(
        [
            Completion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="pdf_generator",
                        arguments={
                            "title": "PYPL Report",
                            "sections": [{"heading": "Summary", "body": "Short."}],
                            "filename": "comprehensive_pypl_report.pdf",
                        },
                    ),
                ),
                usage=TokenUsage(input_tokens=20, output_tokens=3),
            ),
        ]
    )

    AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([pdf_tool]),
    ).run(task)

    assert pdf_tool.calls == [
        {
            "title": "PYPL Report",
            "sections": [{"heading": "Summary", "body": "Short."}],
            "filename": "comprehensive_pypl_report.pdf",
            "min_pages": 3,
        }
    ]


def test_coordinator_invokes_tool_and_repeats_until_final_answer(
    db_session: Session,
) -> None:
    task = create_task(db_session, input_text="echo hi")
    llm = FakeLLM(
        [
            Completion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="echo_json",
                        arguments={"message": "hi"},
                    ),
                ),
                usage=TokenUsage(input_tokens=20, output_tokens=3),
            ),
            Completion(
                content="Echoed hi.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=25, output_tokens=6),
            ),
        ]
    )

    result = AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([EchoJsonTool()]),
    ).run(task)

    assert result.result_summary == "Echoed hi."
    assert result.turns == 2
    assert len(llm.calls) == 2
    assert llm.calls[0][2][0]["name"] == "echo_json"

    second_turn_messages = llm.calls[1][1]
    assert second_turn_messages[0] == ChatMessage(role="user", content="echo hi")
    assert second_turn_messages[1].tool_calls == (
        ToolCall(id="call-1", name="echo_json", arguments={"message": "hi"}),
    )
    tool_message = second_turn_messages[2]
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call-1"
    assert json.loads(tool_message.content or "{}")["output"] == {"echoed": "hi"}

    events = task_events(db_session, task)
    assert [event.type for event in events if event.type in tool_event_types()] == [
        TaskEventType.tool_call,
        TaskEventType.tool_result,
    ]
    tool_result = next(
        event for event in events if event.type is TaskEventType.tool_result
    )
    assert tool_result.payload["output"] == {"echoed": "hi"}
    assert tool_result.payload["cost_usd"] == "0.1"


def test_coordinator_stops_when_tool_returns_artifact(db_session: Session) -> None:
    task = create_task(db_session, input_text="make a report")
    llm = FakeLLM(
        [
            Completion(
                content=None,
                tool_calls=(ToolCall(id="call-1", name="make_artifact", arguments={}),),
                usage=TokenUsage(input_tokens=20, output_tokens=3),
            ),
            Completion(
                content="This should not be called.",
                tool_calls=(),
                usage=TokenUsage(input_tokens=1, output_tokens=1),
            ),
        ]
    )

    result = AgentCoordinator(
        session=db_session,
        llm=llm,
        registry=ToolRegistry([ArtifactTool()]),
    ).run(task)

    assert result.result_summary == "Generated 1 artifact."
    assert result.turns == 1
    assert result.artifact_count == 1
    assert task.result_summary == "Generated 1 artifact."
    assert len(llm.calls) == 1

    events = task_events(db_session, task)
    tool_result = next(
        event for event in events if event.type is TaskEventType.tool_result
    )
    assert tool_result.payload["artifacts"] == [
        {
            "filename": "report.pdf",
            "path": "/tmp/report.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 42,
        }
    ]
    assert events[-1].payload["reason"] == "artifact"


def test_coordinator_raises_after_turn_limit(db_session: Session) -> None:
    task = create_task(db_session, input_text="loop")
    llm = FakeLLM(
        [
            Completion(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="echo_json",
                        arguments={"message": "again"},
                    ),
                ),
                usage=TokenUsage(input_tokens=1, output_tokens=1),
            )
        ]
    )

    with pytest.raises(AgentTurnLimitError):
        AgentCoordinator(
            session=db_session,
            llm=llm,
            registry=ToolRegistry([EchoJsonTool()]),
            max_turns=1,
        ).run(task)

    events = task_events(db_session, task)
    assert events[-1].type is TaskEventType.error
    assert events[-1].payload["type"] == "AgentTurnLimitError"


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


def create_task(
    session: Session,
    *,
    input_text: str,
    installation: Installation | None = None,
    slack_event_id: str | None = None,
    slack_channel_id: str = "C123",
    slack_thread_ts: str = "1716400000.000001",
    slack_message_ts: str = "1716400000.000001",
    slack_user_id: str = "U123",
    created_at: datetime | None = None,
) -> Task:
    installation = installation or create_installation(session)
    task = TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=slack_event_id or f"Ev{uuid.uuid4().hex}",
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
        slack_message_ts=slack_message_ts,
        slack_user_id=slack_user_id,
        input=input_text,
    )
    if created_at is not None:
        task.created_at = created_at
        session.flush()
    return task


def task_events(session: Session, task: Task) -> list[TaskEvent]:
    return list(
        session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task.id)
            .order_by(TaskEvent.seq)
        )
    )


def event_messages(events: Sequence[TaskEvent]) -> list[str]:
    return [
        event.payload["message"] for event in events if event.type is TaskEventType.log
    ]


def tool_event_types() -> set[TaskEventType]:
    return {TaskEventType.tool_call, TaskEventType.tool_result}
