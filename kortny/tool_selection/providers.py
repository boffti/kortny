"""Provider-neutral external tool provider contracts."""

from __future__ import annotations

from typing import Protocol

from kortny.tool_selection.models import ToolCard
from kortny.tools.types import Tool


class ExternalToolProvider(Protocol):
    """A source of scoped external tools for one task."""

    provider_name: str

    def tool_cards(self) -> tuple[ToolCard, ...]:
        """Return compact selector cards for tools visible to the current task."""
        ...

    def runtime_tools(self) -> tuple[Tool, ...]:
        """Return executable tools that may be registered after selection."""
        ...
