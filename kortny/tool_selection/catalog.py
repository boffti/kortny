"""Build compact tool cards for scoped tool selection."""

from __future__ import annotations

from collections.abc import Sequence

from kortny.tool_selection.models import ToolCard
from kortny.tool_selection.providers import ExternalToolProvider
from kortny.tools import Tool


class ToolCatalogService:
    """Create compact tool-selection cards from registered tool objects."""

    def native_cards(self, tools: Sequence[Tool]) -> tuple[ToolCard, ...]:
        return tuple(_native_tool_card(tool) for tool in tools)

    def external_cards(
        self,
        providers: Sequence[ExternalToolProvider],
    ) -> tuple[ToolCard, ...]:
        cards: list[ToolCard] = []
        for provider in providers:
            cards.extend(provider.tool_cards())
        return tuple(cards)


def _native_tool_card(tool: Tool) -> ToolCard:
    return ToolCard(
        registry_name=tool.name,
        provider="native",
        display_name=tool.name,
        description=tool.description,
        capabilities=_native_capabilities(tool.name),
        side_effect=_native_side_effect(tool.name),
    )


def _native_capabilities(tool_name: str) -> tuple[str, ...]:
    if tool_name == "web_search":
        return ("web_search", "current_research")
    if tool_name == "pdf_generator":
        return ("document_generation", "artifact_generation")
    if tool_name == "slack_channel_history":
        return ("slack_history", "thread_context")
    if tool_name == "slack_file_read":
        return ("slack_file_read", "file_analysis")
    if tool_name in {"remember_fact", "recall_fact", "inspect_memory", "forget_fact"}:
        return ("workspace_memory",)
    return ()


def _native_side_effect(tool_name: str) -> str:
    if tool_name == "pdf_generator":
        return "write"
    if tool_name in {"remember_fact", "forget_fact"}:
        return "write"
    return "read"
