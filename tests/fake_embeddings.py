"""Deterministic fake embedding backends for capability-fabric tests.

No network, no fastembed, no model download: texts map onto a small hand-built
keyword vocabulary so semantically related phrases ("check our issue tracker",
"linear", "jira") land on nearby vectors while unrelated text stays far away.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Concept dimensions for the default 8-dim vocabulary.
_ISSUES = 0
_WEB = 1
_SCRAPE = 2
_DOCS = 3
_CHAT = 4
_FILES = 5
_SCHEDULE = 6
_CODE = 7

DEFAULT_VOCABULARY: dict[str, int] = {
    # Issue tracking: paraphrases and product names land together.
    "issue": _ISSUES,
    "issues": _ISSUES,
    "tracker": _ISSUES,
    "ticket": _ISSUES,
    "tickets": _ISSUES,
    "linear": _ISSUES,
    "jira": _ISSUES,
    "bug": _ISSUES,
    "bugs": _ISSUES,
    "sprint": _ISSUES,
    "backlog": _ISSUES,
    "tracking": _ISSUES,
    # Web search / current research.
    "web": _WEB,
    "search": _WEB,
    "internet": _WEB,
    "news": _WEB,
    "research": _WEB,
    "current": _WEB,
    # Scraping / extraction.
    "crawl": _SCRAPE,
    "scrape": _SCRAPE,
    "extract": _SCRAPE,
    "website": _SCRAPE,
    "url": _SCRAPE,
    "firecrawl": _SCRAPE,
    # Library documentation.
    "docs": _DOCS,
    "documentation": _DOCS,
    "library": _DOCS,
    "reference": _DOCS,
    "context7": _DOCS,
    # Slack/chat context.
    "slack": _CHAT,
    "message": _CHAT,
    "messages": _CHAT,
    "channel": _CHAT,
    "thread": _CHAT,
    # Files and documents.
    "file": _FILES,
    "files": _FILES,
    "pdf": _FILES,
    "report": _FILES,
    "upload": _FILES,
    # Scheduling.
    "schedule": _SCHEDULE,
    "calendar": _SCHEDULE,
    "meeting": _SCHEDULE,
    "remind": _SCHEDULE,
    "reminder": _SCHEDULE,
    # Code execution.
    "code": _CODE,
    "python": _CODE,
    "script": _CODE,
    "sandbox": _CODE,
    "execute": _CODE,
}


class FakeEmbeddingBackend:
    """Keyword-vocabulary embedding backend (deterministic, offline)."""

    def __init__(
        self,
        *,
        model_name: str = "fake-embeddings-8d",
        dim: int = 8,
        vocabulary: dict[str, int] | None = None,
    ) -> None:
        self.model_name = model_name
        self.dim = dim
        self.vocabulary = DEFAULT_VOCABULARY if vocabulary is None else vocabulary
        self.query_texts: list[str] = []
        self.passage_texts: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.query_texts.append(text)
        return self._embed(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        self.passage_texts.extend(texts)
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.casefold()):
            index = self.vocabulary.get(token)
            if index is not None and index < self.dim:
                vector[index] += 1.0
        if not any(vector):
            # Unrelated text: uniform direction, far from every concept axis.
            vector = [1.0] * self.dim
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]


class RaisingEmbeddingBackend:
    """Backend whose embed calls always fail — for failure-isolation tests."""

    model_name = "raising-embeddings"

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend exploded")

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend exploded")
