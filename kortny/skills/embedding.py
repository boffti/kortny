"""Shared embedding-text composition for procedural skills.

Both the ingestion path (embed-on-upsert) and the per-task context ranker embed
the *same* canonical text so the sha-gated embedding index never thrashes. The
composition deliberately mirrors ``tool_card_embedding_text`` — name +
description plus the selection signals (intent tags, trigger phrases) — so skill
retrieval matches the tool-RAG quality bar.

Changing the composition changes the embedded string, which changes the content
sha the index keys on, so existing ``tool_embeddings`` rows (kind='skill')
re-embed automatically on the next ``ensure``.
"""

from __future__ import annotations

from collections.abc import Sequence

# Embedding-index "kind" partition for procedural-skill cards. Shared by the
# ingestion embed-on-upsert path and the per-task context ranker.
SKILL_EMBEDDING_KIND = "skill"


def skill_embedding_text(
    *,
    name: str,
    description: str,
    intent_tags: Sequence[str] = (),
    trigger_phrases: Sequence[str] = (),
) -> str:
    """Compose the canonical embedding text for one procedural skill."""

    parts = [f"{name}. {description}"]
    tags = [tag for tag in intent_tags if tag]
    if tags:
        parts.append(f"Tags: {', '.join(tags)}.")
    phrases = [phrase for phrase in trigger_phrases if phrase]
    if phrases:
        parts.append(f"Triggers: {', '.join(phrases)}.")
    return " ".join(parts)
