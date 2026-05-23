"""Thread context abstractions for follow-up task continuity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ThreadTranscriptMessage:
    """One Slack message from a thread transcript."""

    ts: str
    text: str
    user_id: str | None = None
    bot_id: str | None = None
    thread_ts: str | None = None


class ThreadTranscriptProvider(Protocol):
    """Fetches a bounded Slack thread transcript."""

    def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> tuple[ThreadTranscriptMessage, ...]:
        """Return up to ``limit`` messages from the Slack thread."""
