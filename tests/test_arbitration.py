"""Pure unit tests for deterministic tool-selection arbitration (HIG-219)."""

from __future__ import annotations

from kortny.tool_selection import ToolCard, ToolSelection, ToolSelectionResult
from kortny.tool_selection.arbitration import (
    ARBITRATION_DUPLICATES_NATIVE,
    ARBITRATION_PROVIDER_PRECEDENCE,
    ARBITRATION_SIDE_EFFECT_TIEBREAK,
    arbitrate,
)
from kortny.tool_selection.selector import EXPLICIT_REQUEST_REASON_PREFIX


def make_card(
    registry_name: str,
    *,
    provider: str = "composio",
    capabilities: tuple[str, ...] = ("external_tool",),
    side_effect: str = "read",
    toolkit_slug: str | None = None,
    can_replace_native_tools: tuple[str, ...] = (),
    description: str = "Generic integration tool.",
) -> ToolCard:
    return ToolCard(
        registry_name=registry_name,
        provider=provider,
        display_name=registry_name,
        description=description,
        capabilities=capabilities,
        side_effect=side_effect,
        toolkit_slug=toolkit_slug,
        can_replace_native_tools=can_replace_native_tools,
    )


def select(name: str, *, reason: str = "selector judgment") -> ToolSelection:
    return ToolSelection(registry_name=name, confidence=0.9, reason=reason)


def test_composio_dropped_versus_mcp_on_capability_overlap() -> None:
    cards = (
        make_card(
            "mcp__search__query",
            provider="mcp",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
        make_card(
            "composio_search_tool",
            provider="composio",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("mcp__search__query"), select("composio_search_tool")),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ("mcp__search__query",)
    assert arbitrated.rejected_tools[-1].registry_name == "composio_search_tool"
    assert arbitrated.rejected_tools[-1].reason == ARBITRATION_PROVIDER_PRECEDENCE
    assert log == [
        {
            "rule": ARBITRATION_PROVIDER_PRECEDENCE,
            "dropped": "composio_search_tool",
            "kept": ["mcp__search__query"],
            "reason": (
                "mcp__search__query takes precedence over "
                "composio_search_tool on capability overlap."
            ),
        }
    ]


def test_mcp_wins_even_when_selected_after_composio() -> None:
    cards = (
        make_card(
            "composio_search_tool",
            provider="composio",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
        make_card(
            "mcp__search__query",
            provider="mcp",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_search_tool"), select("mcp__search__query")),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ("mcp__search__query",)
    assert log[0]["dropped"] == "composio_search_tool"


def test_read_beats_write_within_same_provider_class() -> None:
    cards = (
        make_card(
            "composio_app_list",
            capabilities=("external_tool", "records", "app_data"),
            side_effect="read",
        ),
        make_card(
            "composio_app_update",
            capabilities=("external_tool", "records", "app_data"),
            side_effect="write",
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_app_list"), select("composio_app_update")),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ("composio_app_list",)
    assert arbitrated.rejected_tools[-1].reason == ARBITRATION_SIDE_EFFECT_TIEBREAK
    assert log[0]["rule"] == ARBITRATION_SIDE_EFFECT_TIEBREAK


def test_same_side_effect_overlap_keeps_both() -> None:
    cards = (
        make_card(
            "composio_app_list",
            capabilities=("external_tool", "records", "app_data"),
        ),
        make_card(
            "composio_app_search",
            capabilities=("external_tool", "records", "app_data"),
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_app_list"), select("composio_app_search")),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated is selection
    assert log == []


def test_no_overlap_is_a_noop() -> None:
    cards = (
        make_card("composio_linear_list", capabilities=("external_tool", "issues")),
        make_card("composio_drive_get", capabilities=("external_tool", "files")),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_linear_list"), select("composio_drive_get")),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated is selection
    assert arbitrated.selected_names == ("composio_linear_list", "composio_drive_get")
    assert log == []


def test_general_web_duplicate_of_active_native_is_dropped() -> None:
    cards = (
        make_card(
            "composio_websearch_search",
            capabilities=("external_tool", "web_search", "current_research"),
            can_replace_native_tools=("web_search",),
            description="Search the public web for current results.",
            toolkit_slug="websearch",
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_websearch_search"),),
        suppressed_native_tools=(),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ()
    assert arbitrated.rejected_tools[-1].reason == ARBITRATION_DUPLICATES_NATIVE
    assert log[0]["rule"] == ARBITRATION_DUPLICATES_NATIVE
    assert log[0]["kept"] == ["web_search"]


def test_native_duplicate_survives_when_native_is_suppressed() -> None:
    cards = (
        make_card(
            "composio_websearch_search",
            capabilities=("external_tool", "web_search", "current_research"),
            can_replace_native_tools=("web_search",),
            description="Search the public web for current results.",
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_websearch_search"),),
        suppressed_native_tools=("web_search",),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ("composio_websearch_search",)
    assert log == []


def test_app_specific_search_is_not_treated_as_native_duplicate() -> None:
    # Provider heuristics tag "search" tools with web_search; a market-data
    # search must not be dropped in favor of native web search.
    cards = (
        make_card(
            "composio_alpha_vantage_search",
            capabilities=("external_tool", "web_search", "current_research"),
            can_replace_native_tools=("web_search",),
            description="Read-only market data lookup tool.",
            toolkit_slug="alpha_vantage",
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(select("composio_alpha_vantage_search"),),
        route_reason="test",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert arbitrated.selected_names == ("composio_alpha_vantage_search",)
    assert log == []


def test_forced_include_survives_all_passes() -> None:
    cards = (
        make_card(
            "mcp__search__query",
            provider="mcp",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
        make_card(
            "composio_firecrawl_search",
            provider="composio",
            capabilities=("external_tool", "web_search", "current_research"),
            can_replace_native_tools=("web_search",),
            description="Search or scrape current web content.",
            toolkit_slug="firecrawl",
        ),
    )
    selection = ToolSelectionResult(
        selected_tools=(
            select("mcp__search__query"),
            select(
                "composio_firecrawl_search",
                reason=f"{EXPLICIT_REQUEST_REASON_PREFIX} firecrawl",
            ),
        ),
        route_reason="test+explicit_toolkit_forced",
    )

    arbitrated, log = arbitrate(selection, cards)

    assert "composio_firecrawl_search" in arbitrated.selected_names
    assert all(entry["dropped"] != "composio_firecrawl_search" for entry in log)


def test_rejected_tools_accumulate_with_arbitration_reasons() -> None:
    cards = (
        make_card(
            "mcp__search__query",
            provider="mcp",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
        make_card(
            "composio_search_tool",
            provider="composio",
            capabilities=("external_tool", "web_search", "current_research"),
        ),
    )
    prior_rejection = ToolSelection(
        registry_name="composio_other",
        confidence=0.2,
        reason="not relevant",
    )
    selection = ToolSelectionResult(
        selected_tools=(select("mcp__search__query"), select("composio_search_tool")),
        rejected_tools=(prior_rejection,),
        route_reason="test",
    )

    arbitrated, _ = arbitrate(selection, cards)

    assert arbitrated.rejected_tools[0] == prior_rejection
    assert arbitrated.rejected_tools[1].reason.startswith("arbitration_")
