from typing import Any

from kortny.slack.thread_context import SlackThreadTranscriptProvider


class FakeConversationsClient:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def conversations_replies(
        self,
        *,
        channel: str,
        ts: str,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "channel": channel,
                "ts": ts,
                "cursor": cursor,
                "limit": limit,
            }
        )
        return self.pages.pop(0)


def test_slack_thread_transcript_provider_paginates_with_cursor() -> None:
    client = FakeConversationsClient(
        [
            {
                "ok": True,
                "messages": [
                    {"ts": "1.000001", "user": "U1", "text": "first"},
                    {"ts": "1.000002", "bot_id": "B1", "text": "second"},
                ],
                "response_metadata": {"next_cursor": "cursor-2"},
            },
            {
                "ok": True,
                "messages": [{"ts": "1.000003", "user": "U2", "text": "third"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )

    messages = SlackThreadTranscriptProvider(
        client, page_limit=2
    ).fetch_thread_messages(
        channel_id="C123",
        thread_ts="1.000001",
        limit=3,
    )

    assert [
        (message.ts, message.user_id, message.bot_id, message.text)
        for message in messages
    ] == [
        ("1.000001", "U1", None, "first"),
        ("1.000002", None, "B1", "second"),
        ("1.000003", "U2", None, "third"),
    ]
    assert client.calls == [
        {"channel": "C123", "ts": "1.000001", "cursor": None, "limit": 2},
        {"channel": "C123", "ts": "1.000001", "cursor": "cursor-2", "limit": 1},
    ]


def test_slack_thread_transcript_provider_respects_limit() -> None:
    client = FakeConversationsClient(
        [
            {
                "ok": True,
                "messages": [
                    {"ts": "1.000001", "user": "U1", "text": "first"},
                    {"ts": "1.000002", "user": "U2", "text": "second"},
                ],
                "response_metadata": {"next_cursor": "cursor-2"},
            }
        ]
    )

    messages = SlackThreadTranscriptProvider(
        client, page_limit=2
    ).fetch_thread_messages(
        channel_id="C123",
        thread_ts="1.000001",
        limit=1,
    )

    assert [message.text for message in messages] == ["first"]
    assert client.calls == [
        {"channel": "C123", "ts": "1.000001", "cursor": None, "limit": 1}
    ]
