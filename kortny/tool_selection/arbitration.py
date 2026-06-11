"""Deterministic post-selection arbitration across tool providers (HIG-219).

Provider precedence on capability overlap: native > mcp > composio.
Runs after the LLM selector (and related-tool expansion) so a cheap-tier
selection can never ship two providers doing the same job, and an external
tool can never shadow a native tool the selector chose to keep.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from kortny.tool_selection.models import ToolCard, ToolSelection, ToolSelectionResult
from kortny.tool_selection.selector import EXPLICIT_REQUEST_REASON_PREFIX

ARBITRATION_DUPLICATES_NATIVE = "arbitration_duplicates_native"
ARBITRATION_PROVIDER_PRECEDENCE = "arbitration_provider_precedence"
ARBITRATION_SIDE_EFFECT_TIEBREAK = "arbitration_side_effect_tiebreak"

_PROVIDER_RANK = {"mcp": 0, "composio": 1}
_MIN_SHARED_CAPABILITIES = 2
# Capability tags that carry no meaning beyond "covered by the native tools
# this card can replace" — used to decide whether an external card ONLY
# duplicates an active native tool.
_GENERIC_CAPABILITY_TAGS = frozenset({"external_tool", "mcp_integration"})
_NATIVE_DUPLICATE_CAPABILITIES = frozenset({"web_search", "current_research"})
# Provider capability heuristics tag any "search"-ish tool with web_search, so
# the native-duplicate rule additionally requires the card to actually be a
# general-web tool (not e.g. a market-data or app-specific search).
_GENERAL_WEB_WORDS = frozenset({"web", "internet", "crawl", "scrape", "serp"})


def arbitrate(
    selection: ToolSelectionResult,
    cards: Sequence[ToolCard],
) -> tuple[ToolSelectionResult, list[dict[str, object]]]:
    """Apply provider-precedence arbitration to a tool selection.

    Returns the (possibly reduced) selection plus a JSON-safe log of every
    arbitration decision. Explicitly requested (forced-include) selections are
    never dropped.
    """

    cards_by_name = {card.registry_name: card for card in cards}
    suppressed_native = set(selection.suppressed_native_tools)
    log: list[dict[str, object]] = []
    dropped: list[ToolSelection] = []
    kept: list[ToolSelection] = []

    # Pass 1 — native precedence: drop an external that only duplicates
    # native tools the selector kept active (none of its replaceable natives
    # were suppressed, and the card offers no distinctive capability beyond
    # what those natives already cover).
    for item in selection.selected_tools:
        card = cards_by_name.get(item.registry_name)
        if (
            card is None
            or _is_forced(item)
            or not card.can_replace_native_tools
            or any(name in suppressed_native for name in card.can_replace_native_tools)
            or _distinctive_capabilities(card)
            or not _is_general_web_card(card)
        ):
            kept.append(item)
            continue
        dropped.append(_dropped(item, ARBITRATION_DUPLICATES_NATIVE))
        log.append(
            {
                "rule": ARBITRATION_DUPLICATES_NATIVE,
                "dropped": item.registry_name,
                "kept": list(card.can_replace_native_tools),
                "reason": (
                    "External tool duplicates active native tools "
                    f"{', '.join(card.can_replace_native_tools)}."
                ),
            }
        )

    # Pass 2 — external-vs-external precedence on capability overlap.
    survivors: list[ToolSelection] = []
    for item in kept:
        card = cards_by_name.get(item.registry_name)
        if card is None:
            survivors.append(item)
            continue
        item_dropped = False
        for kept_item in list(survivors):
            other_card = cards_by_name.get(kept_item.registry_name)
            if other_card is None or not _overlaps(card, other_card):
                continue
            winner = _pick_winner(item, card, kept_item, other_card)
            if winner is None:
                continue
            rule = (
                ARBITRATION_PROVIDER_PRECEDENCE
                if card.provider != other_card.provider
                else ARBITRATION_SIDE_EFFECT_TIEBREAK
            )
            if winner is item:
                survivors.remove(kept_item)
                dropped.append(_dropped(kept_item, rule))
                log.append(_overlap_log(rule, kept_item, item))
            else:
                item_dropped = True
                dropped.append(_dropped(item, rule))
                log.append(_overlap_log(rule, item, kept_item))
                break
        if not item_dropped:
            survivors.append(item)

    if not dropped:
        return selection, log

    arbitrated = replace(
        selection,
        selected_tools=tuple(survivors),
        rejected_tools=selection.rejected_tools + tuple(dropped),
    )
    return arbitrated, log


def _distinctive_capabilities(card: ToolCard) -> set[str]:
    """Capabilities the card offers beyond its replaceable-native coverage."""

    return {
        capability
        for capability in card.capabilities
        if capability not in _GENERIC_CAPABILITY_TAGS
        and capability not in _NATIVE_DUPLICATE_CAPABILITIES
        and not capability.endswith("_integration")
        and not capability.endswith("_mcp")
    }


def _is_general_web_card(card: ToolCard) -> bool:
    """Whether the card reads as a general web search/extraction tool."""

    text = " ".join(
        part
        for part in (card.display_name, card.description, card.toolkit_slug or "")
        if part
    ).casefold()
    words = {
        "".join(char for char in raw if char.isalnum())
        for raw in text.replace("/", " ").replace("-", " ").replace("_", " ").split()
    }
    return bool(words & _GENERAL_WEB_WORDS)


def _overlaps(card: ToolCard, other: ToolCard) -> bool:
    shared_capabilities = set(card.capabilities) & set(other.capabilities)
    if len(shared_capabilities) >= _MIN_SHARED_CAPABILITIES:
        return True
    return bool(
        set(card.can_replace_native_tools) & set(other.can_replace_native_tools)
    )


def _pick_winner(
    item: ToolSelection,
    card: ToolCard,
    other_item: ToolSelection,
    other_card: ToolCard,
) -> ToolSelection | None:
    """Return the selection to keep, or None when both should stay."""

    item_forced = _is_forced(item)
    other_forced = _is_forced(other_item)
    if item_forced and other_forced:
        return None
    if item_forced:
        return item
    if other_forced:
        return other_item

    if card.provider != other_card.provider:
        item_rank = _PROVIDER_RANK.get(card.provider, len(_PROVIDER_RANK))
        other_rank = _PROVIDER_RANK.get(other_card.provider, len(_PROVIDER_RANK))
        if item_rank == other_rank:
            return None
        return item if item_rank < other_rank else other_item

    # Same provider class: read beats write; identical side effects keep both.
    if card.side_effect == other_card.side_effect:
        return None
    if card.side_effect == "read":
        return item
    if other_card.side_effect == "read":
        return other_item
    return None


def _is_forced(item: ToolSelection) -> bool:
    return item.reason.startswith(EXPLICIT_REQUEST_REASON_PREFIX)


def _dropped(item: ToolSelection, rule: str) -> ToolSelection:
    return ToolSelection(
        registry_name=item.registry_name,
        confidence=item.confidence,
        reason=rule,
    )


def _overlap_log(
    rule: str,
    loser: ToolSelection,
    winner: ToolSelection,
) -> dict[str, object]:
    return {
        "rule": rule,
        "dropped": loser.registry_name,
        "kept": [winner.registry_name],
        "reason": (
            f"{winner.registry_name} takes precedence over "
            f"{loser.registry_name} on capability overlap."
        ),
    }
