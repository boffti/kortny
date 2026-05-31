"""Budget-aware helpers for tool-selection prompts."""

from __future__ import annotations

from dataclasses import dataclass

from kortny.tool_selection.models import ToolCard


@dataclass(frozen=True, slots=True)
class ToolCatalogCompaction:
    """Traceable summary of a selector catalog compaction decision."""

    original_candidate_count: int
    selected_candidate_count: int
    omitted_candidate_count: int
    max_candidates: int
    selected_candidate_names: tuple[str, ...]
    omitted_candidate_names: tuple[str, ...]
    reason: str

    @property
    def compacted(self) -> bool:
        return self.omitted_candidate_count > 0

    def to_payload(self) -> dict[str, object]:
        return {
            "original_candidate_count": self.original_candidate_count,
            "selected_candidate_count": self.selected_candidate_count,
            "omitted_candidate_count": self.omitted_candidate_count,
            "max_candidates": self.max_candidates,
            "selected_candidate_names": list(self.selected_candidate_names),
            "omitted_candidate_names": list(self.omitted_candidate_names),
            "reason": self.reason,
        }


def compact_tool_cards(
    *,
    task_input: str,
    cards: tuple[ToolCard, ...],
    max_candidates: int,
) -> tuple[tuple[ToolCard, ...], ToolCatalogCompaction]:
    """Return a bounded, relevance-ranked selector catalog."""

    if max_candidates < 1:
        raise ValueError("max_candidates must be at least 1")
    if len(cards) <= max_candidates:
        return cards, ToolCatalogCompaction(
            original_candidate_count=len(cards),
            selected_candidate_count=len(cards),
            omitted_candidate_count=0,
            max_candidates=max_candidates,
            selected_candidate_names=tuple(card.registry_name for card in cards),
            omitted_candidate_names=(),
            reason="within_budget",
        )

    scored = [
        (_score_tool_card(task_input, card), index, card)
        for index, card in enumerate(cards)
    ]
    ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
    selected_ranked = ranked[:max_candidates]
    selected_by_index = sorted(selected_ranked, key=lambda item: item[1])
    selected = tuple(item[2] for item in selected_by_index)
    selected_names = {card.registry_name for card in selected}
    omitted = tuple(card for card in cards if card.registry_name not in selected_names)
    return selected, ToolCatalogCompaction(
        original_candidate_count=len(cards),
        selected_candidate_count=len(selected),
        omitted_candidate_count=len(omitted),
        max_candidates=max_candidates,
        selected_candidate_names=tuple(card.registry_name for card in selected),
        omitted_candidate_names=tuple(card.registry_name for card in omitted),
        reason="relevance_cap",
    )


def _score_tool_card(task_input: str, card: ToolCard) -> float:
    words = _words(task_input)
    if not words:
        return 0.0

    text_parts = [
        card.registry_name,
        card.display_name,
        card.description,
        card.toolkit_slug or "",
        " ".join(card.tool_slugs),
        " ".join(card.capabilities),
    ]
    card_words = set().union(*(_words(part) for part in text_parts if part))
    overlap = words & card_words

    score = min(0.35, len(overlap) * 0.04)
    if card.toolkit_slug and card.toolkit_slug.casefold() in words:
        score += 0.45
    if card.side_effect == "read":
        score += 0.05
    for capability in card.capabilities:
        capability_words = set(capability.casefold().split("_"))
        if words & capability_words:
            score += 0.12
    if card.toolkit_slug == "firecrawl":
        if words & FIRECRAWL_SEARCH_WORDS:
            score += 0.16
        if words & FIRECRAWL_SCRAPE_WORDS:
            score += 0.38
    return min(1.0, score)


def _words(text: str) -> set[str]:
    return {
        "".join(char for char in raw.casefold() if char.isalnum())
        for raw in text.replace("/", " ").replace("-", " ").replace("_", " ").split()
        if raw.strip()
    } - {""}


FIRECRAWL_SEARCH_WORDS = frozenset(
    {
        "latest",
        "recent",
        "research",
        "search",
        "source",
        "sources",
    }
)

FIRECRAWL_SCRAPE_WORDS = frozenset(
    {
        "crawl",
        "extract",
        "scrape",
        "url",
        "website",
    }
)
