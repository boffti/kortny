"""Provider-neutral tool contract."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, TypeAlias

JsonObject: TypeAlias = dict[str, Any]
JsonSchema: TypeAlias = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolArtifact:
    """A file-like artifact produced by a tool invocation."""

    filename: str
    path: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result returned by every Kortny tool."""

    output: JsonObject
    cost_usd: Decimal = Decimal("0")
    artifacts: tuple[ToolArtifact, ...] = ()


class Tool(Protocol):
    """The interface every native or external tool adapter implements."""

    name: str
    description: str
    parameters: JsonSchema

    def invoke(self, args: JsonObject) -> ToolResult:
        """Run the tool with JSON arguments and return a structured result."""
        ...
