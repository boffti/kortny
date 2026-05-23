"""Slack thread transcript access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from kortny.agent.thread_context import ThreadTranscriptMessage

DEFAULT_THREAD_TRANSCRIPT_PAGE_LIMIT = 15


class SlackThreadTranscriptClient(Protocol):
    """Subset of Slack WebClient used for thread transcript retrieval."""

    def conversations_replies(
        self,
        *,
        channel: str,
        ts: str,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> Any:
        """Fetch a page of messages from a Slack thread."""


class SlackThreadTranscriptProvider:
    """Fetches Slack thread replies using ``conversations.replies``."""

    def __init__(
        self,
        client: SlackThreadTranscriptClient,
        *,
        page_limit: int = DEFAULT_THREAD_TRANSCRIPT_PAGE_LIMIT,
    ) -> None:
        if page_limit < 1:
            raise ValueError("page_limit must be at least 1")
        self.client = client
        self.page_limit = page_limit

    def fetch_thread_messages(
        self,
        *,
        channel_id: str,
        thread_ts: str,
        limit: int,
    ) -> tuple[ThreadTranscriptMessage, ...]:
        """Return up to ``limit`` messages from a Slack thread."""

        if limit < 1:
            return ()

        cursor: str | None = None
        messages: list[ThreadTranscriptMessage] = []
        while len(messages) < limit:
            page_size = min(self.page_limit, limit - len(messages))
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                cursor=cursor,
                limit=page_size,
            )
            for item in _response_messages(response):
                message = _thread_message(item)
                if message is not None:
                    messages.append(message)
                if len(messages) >= limit:
                    break

            cursor = _next_cursor(response)
            if not cursor:
                break

        return tuple(messages)


def _response_messages(response: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw_messages = response.get("messages")
    if not isinstance(raw_messages, list):
        return ()
    return tuple(item for item in raw_messages if isinstance(item, Mapping))


def _thread_message(message: Mapping[str, Any]) -> ThreadTranscriptMessage | None:
    ts = message.get("ts")
    text = message.get("text")
    if not isinstance(ts, str) or not isinstance(text, str):
        return None

    user_id = message.get("user")
    bot_id = message.get("bot_id")
    thread_ts = message.get("thread_ts")
    return ThreadTranscriptMessage(
        ts=ts,
        text=text,
        user_id=user_id if isinstance(user_id, str) else None,
        bot_id=bot_id if isinstance(bot_id, str) else None,
        thread_ts=thread_ts if isinstance(thread_ts, str) else None,
    )


def _next_cursor(response: Mapping[str, Any]) -> str | None:
    metadata = response.get("response_metadata")
    if not isinstance(metadata, Mapping):
        return None
    cursor = metadata.get("next_cursor")
    if isinstance(cursor, str) and cursor:
        return cursor
    return None
