from decimal import Decimal

import pytest

from kortny.tools import (
    DuplicateToolError,
    EchoTool,
    RememberFactTool,
    ToolArtifact,
    ToolNotFoundError,
    ToolRegistry,
    ToolResult,
)
from kortny.tools.types import JsonObject, JsonSchema


class CostingTool:
    name = "costing"
    description = "Returns a cost and artifact."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(
            output={"ok": True},
            cost_usd=Decimal("0.012345"),
            artifacts=(
                ToolArtifact(
                    filename="report.pdf",
                    path="/tmp/report.pdf",
                    mime_type="application/pdf",
                    size_bytes=42,
                ),
            ),
        )


def test_echo_tool_invokes_through_registry() -> None:
    registry = ToolRegistry([EchoTool()])

    result = registry.invoke("echo", {"message": "hello"})

    assert result == ToolResult(output={"message": "hello"})


def test_registry_exposes_provider_neutral_schemas() -> None:
    registry = ToolRegistry([EchoTool()])

    assert registry.schemas() == (
        {
            "name": "echo",
            "description": "Echoes a message back unchanged.",
            "parameters": EchoTool.parameters,
        },
    )


def test_remember_fact_tool_schema_requires_faithful_memory_details() -> None:
    value_text_description = RememberFactTool.parameters["properties"]["value_text"][
        "description"
    ]

    assert "Preserve every actionable detail" in RememberFactTool.description
    assert "footer/header placement" in RememberFactTool.description
    assert "placement details like footer left" in value_text_description


def test_registry_rejects_duplicate_tool_names() -> None:
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(DuplicateToolError):
        registry.register(EchoTool())


def test_registry_reports_missing_tools() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError):
        registry.invoke("missing", {})


def test_tool_result_carries_cost_and_artifacts() -> None:
    registry = ToolRegistry([CostingTool()])

    result = registry.invoke("costing", {})

    assert result.output == {"ok": True}
    assert result.cost_usd == Decimal("0.012345")
    assert result.artifacts == (
        ToolArtifact(
            filename="report.pdf",
            path="/tmp/report.pdf",
            mime_type="application/pdf",
            size_bytes=42,
        ),
    )


def test_echo_tool_validates_required_message() -> None:
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(ValueError, match="string 'message'"):
        registry.invoke("echo", {"message": 123})
