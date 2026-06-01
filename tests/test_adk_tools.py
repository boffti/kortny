import asyncio
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from kortny.agent.adk_tools import KortnyAdkTool, KortnyRegistryToolset
from kortny.approvals import TOOL_APPROVAL_REQUIRED_MESSAGE, ToolApprovalRequired
from kortny.db.models import TaskEventType
from kortny.tools import ToolRegistry
from kortny.tools.types import JsonObject, ToolResult


def test_adk_tool_declaration_preserves_provider_neutral_schema() -> None:
    adapter = KortnyAdkTool(
        tool=_MarketLookupTool(),
        task=cast(Any, None),
        session=cast(Any, None),
        task_service=cast(Any, None),
    )

    declaration = adapter._get_declaration()

    assert declaration.name == "market_lookup"
    assert declaration.description == "Looks up market data."
    assert declaration.parameters_json_schema == _MarketLookupTool.parameters


def test_adk_tool_enforces_existing_approval_policy() -> None:
    task_service = _RecordingTaskService()
    adapter = KortnyAdkTool(
        tool=_ForgetFactTool(),
        task=cast(Any, SimpleNamespace(id=uuid.uuid4())),
        session=cast(Any, _NoApprovalSession()),
        task_service=cast(Any, task_service),
    )

    with pytest.raises(ToolApprovalRequired) as exc:
        asyncio.run(
            adapter.run_async(
                args={"key": "pdf_branding"},
                tool_context=cast(
                    Any,
                    SimpleNamespace(function_call_id="call-approval"),
                ),
            )
        )

    assert exc.value.request.tool_name == "forget_fact"
    assert task_service.events == [
        (
            TaskEventType.log,
            {
                "message": TOOL_APPROVAL_REQUIRED_MESSAGE,
                "runtime": "adk",
                "turn": 1,
                "step_id": "adk_tool_call",
                "request": exc.value.request.to_payload(),
            },
        )
    ]


def test_adk_registry_toolset_loads_registry_lazily_once() -> None:
    task_service = _RecordingTaskService()
    load_count = 0

    def registry_factory() -> ToolRegistry:
        nonlocal load_count
        load_count += 1
        return ToolRegistry([_MarketLookupTool()])

    toolset = KortnyRegistryToolset(
        registry_factory=registry_factory,
        task=cast(Any, SimpleNamespace(id=uuid.uuid4())),
        session=cast(Any, None),
        task_service=cast(Any, task_service),
    )

    first_tools = asyncio.run(toolset.get_tools())
    second_tools = asyncio.run(toolset.get_tools())

    assert load_count == 1
    assert [tool.name for tool in first_tools] == ["market_lookup"]
    assert [tool.name for tool in second_tools] == ["market_lookup"]
    assert task_service.events == [
        (
            TaskEventType.log,
            {
                "message": "adk_lazy_toolset_loaded",
                "runtime": "adk",
                "tool_count": 1,
                "tool_names": ["market_lookup"],
            },
        )
    ]


class _MarketLookupTool:
    name = "market_lookup"
    description = "Looks up market data."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "period": {"type": "string", "enum": ["1d", "1mo"]},
        },
        "required": ["ticker"],
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(output={"args": args}, cost_usd=Decimal("0"))


class _ForgetFactTool:
    name = "forget_fact"
    description = "Deletes a stored fact."
    parameters = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(output={"deleted": args["key"]})


class _NoApprovalSession:
    def scalar(self, statement: object) -> None:
        del statement
        return None


class _RecordingTaskService:
    def __init__(self) -> None:
        self.events: list[tuple[TaskEventType, dict[str, Any]]] = []

    def append_event(
        self,
        task: object,
        event_type: TaskEventType,
        payload: dict[str, Any],
    ) -> None:
        del task
        self.events.append((event_type, payload))
