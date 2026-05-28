"""Task idempotency identity helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

TASK_IDENTITY_MATRIX = """
Current task identity policy:
- Slack user message: installation + channel_id + thread_ts_or_message_ts + message_ts.
- Slack event without message_ts: installation + slack_event_id.
- Synthetic system work: installation + deterministic source + source object id.
- Scheduled work: installation + schedule id + fire time.

Identity payloads carry source details and an input hash. Reusing the same key
with a different fingerprint is allowed to return the original task, but the
mismatch is logged on the task.
""".strip()


@dataclass(frozen=True, slots=True)
class TaskIdentity:
    """Deterministic idempotency identity for one task request."""

    kind: str
    key: str
    payload: dict[str, Any]
    fingerprint: str

    @classmethod
    def for_task_request(
        cls,
        *,
        slack_event_id: str | None,
        slack_channel_id: str,
        slack_thread_ts: str | None,
        slack_message_ts: str | None,
        slack_user_id: str,
        input_text: str,
        source_surface: str | None = None,
    ) -> TaskIdentity:
        if slack_message_ts:
            return cls.slack_message(
                channel_id=slack_channel_id,
                message_ts=slack_message_ts,
                thread_ts=slack_thread_ts,
                user_id=slack_user_id,
                input_text=input_text,
                slack_event_id=slack_event_id,
                source_surface=source_surface,
            )
        if slack_event_id:
            return cls.slack_event(
                slack_event_id=slack_event_id,
                channel_id=slack_channel_id,
                thread_ts=slack_thread_ts,
                user_id=slack_user_id,
                input_text=input_text,
                source_surface=source_surface,
            )
        return cls.manual(
            channel_id=slack_channel_id,
            thread_ts=slack_thread_ts,
            user_id=slack_user_id,
            input_text=input_text,
            source_surface=source_surface,
        )

    @classmethod
    def slack_message(
        cls,
        *,
        channel_id: str,
        message_ts: str,
        thread_ts: str | None,
        user_id: str,
        input_text: str,
        slack_event_id: str | None = None,
        source_surface: str | None = None,
    ) -> TaskIdentity:
        resolved_thread_ts = thread_ts or message_ts
        payload = _payload(
            {
                "kind": "slack_message",
                "channel_id": channel_id,
                "thread_ts": resolved_thread_ts,
                "message_ts": message_ts,
                "user_id": user_id,
                "slack_event_id": slack_event_id,
                "source_surface": source_surface,
            },
            input_text=input_text,
        )
        return cls(
            kind="slack_message",
            key=f"slack-message:{channel_id}:{resolved_thread_ts}:{message_ts}",
            payload=payload,
            fingerprint=_fingerprint(
                _without(payload, {"slack_event_id", "source_surface"})
            ),
        )

    @classmethod
    def slack_event(
        cls,
        *,
        slack_event_id: str,
        channel_id: str,
        thread_ts: str | None,
        user_id: str,
        input_text: str,
        source_surface: str | None = None,
    ) -> TaskIdentity:
        payload = _payload(
            {
                "kind": "slack_event",
                "slack_event_id": slack_event_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "user_id": user_id,
                "source_surface": source_surface,
            },
            input_text=input_text,
        )
        return cls(
            kind="slack_event",
            key=f"slack-event:{slack_event_id}",
            payload=payload,
            fingerprint=_fingerprint(payload),
        )

    @classmethod
    def synthetic(
        cls,
        *,
        source: str,
        source_id: str,
        input_text: str,
        payload: Mapping[str, Any] | None = None,
    ) -> TaskIdentity:
        identity_payload = _payload(
            {
                "kind": "synthetic",
                "source": source,
                "source_id": source_id,
                **dict(payload or {}),
            },
            input_text=input_text,
        )
        return cls(
            kind="synthetic",
            key=f"synthetic:{source}:{source_id}",
            payload=identity_payload,
            fingerprint=_fingerprint(identity_payload),
        )

    @classmethod
    def scheduled(
        cls,
        *,
        schedule_id: str,
        fire_time: str,
        input_text: str,
        payload: Mapping[str, Any] | None = None,
    ) -> TaskIdentity:
        identity_payload = _payload(
            {
                "kind": "scheduled",
                "schedule_id": schedule_id,
                "fire_time": fire_time,
                **dict(payload or {}),
            },
            input_text=input_text,
        )
        return cls(
            kind="scheduled",
            key=f"scheduled:{schedule_id}:{fire_time}",
            payload=identity_payload,
            fingerprint=_fingerprint(identity_payload),
        )

    @classmethod
    def manual(
        cls,
        *,
        channel_id: str,
        thread_ts: str | None,
        user_id: str,
        input_text: str,
        source_surface: str | None = None,
    ) -> TaskIdentity:
        payload = _payload(
            {
                "kind": "manual",
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "user_id": user_id,
                "source_surface": source_surface,
            },
            input_text=input_text,
        )
        return cls(
            kind="manual",
            key=f"manual:{_fingerprint(payload)}",
            payload=payload,
            fingerprint=_fingerprint(payload),
        )


def _payload(values: Mapping[str, Any], *, input_text: str) -> dict[str, Any]:
    clean = {key: value for key, value in values.items() if value is not None}
    clean["input_sha256"] = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
    clean["input_preview"] = input_text[:200]
    return clean


def _fingerprint(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _without(payload: Mapping[str, Any], ignored_keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in ignored_keys}
