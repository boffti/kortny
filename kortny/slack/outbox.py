"""Idempotent Slack side-effect records and delivery helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from slack_sdk.errors import SlackApiError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import SlackSideEffect

SLACK_EFFECT_PENDING = "pending"
SLACK_EFFECT_IN_PROGRESS = "in_progress"
SLACK_EFFECT_SUCCEEDED = "succeeded"
SLACK_EFFECT_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SlackSideEffectResult:
    """Result of one Slack side-effect delivery attempt."""

    side_effect: SlackSideEffect
    response: Mapping[str, Any]
    delivered: bool
    deduped: bool


class SlackSideEffectOutbox:
    """Records Slack side effects and prevents duplicate visible delivery."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def deliver(
        self,
        *,
        installation_id: uuid.UUID,
        idempotency_key: str,
        operation: str,
        request: Mapping[str, Any],
        target_channel_id: str | None = None,
        target_thread_ts: str | None = None,
        target_message_ts: str | None = None,
        task_id: uuid.UUID | None = None,
        purpose: str | None = None,
        call: Callable[[], Mapping[str, Any]],
    ) -> SlackSideEffectResult:
        """Record and deliver a Slack side effect.

        Delivery is at-least-once while successful rows are deduped by
        ``(installation_id, idempotency_key)``. HIG-96 can add a relay/lease
        around rows left failed or in-progress after crashes.
        """

        side_effect = self._get_or_create(
            installation_id=installation_id,
            idempotency_key=idempotency_key,
            operation=operation,
            request=request,
            target_channel_id=target_channel_id,
            target_thread_ts=target_thread_ts,
            target_message_ts=target_message_ts,
            task_id=task_id,
            purpose=purpose,
        )
        if side_effect.status == SLACK_EFFECT_SUCCEEDED:
            return SlackSideEffectResult(
                side_effect=side_effect,
                response=side_effect.response_json or {"ok": True},
                delivered=False,
                deduped=True,
            )

        now = datetime.now(UTC)
        side_effect.status = SLACK_EFFECT_IN_PROGRESS
        side_effect.attempts += 1
        side_effect.started_at = now
        side_effect.updated_at = now
        side_effect.last_error = None
        self.session.flush()

        try:
            response = call()
        except Exception as exc:
            idempotent_response = _idempotent_success_response(operation, exc)
            if idempotent_response is None:
                side_effect.status = SLACK_EFFECT_FAILED
                side_effect.last_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                side_effect.updated_at = datetime.now(UTC)
                self.session.flush()
                raise
            response = idempotent_response

        payload = _jsonable_mapping(response)
        delivered_at = datetime.now(UTC)
        side_effect.response_json = payload
        side_effect.status = SLACK_EFFECT_SUCCEEDED
        side_effect.delivered_at = delivered_at
        side_effect.updated_at = delivered_at
        self.session.flush()
        return SlackSideEffectResult(
            side_effect=side_effect,
            response=payload,
            delivered=True,
            deduped=False,
        )

    def _get_or_create(
        self,
        *,
        installation_id: uuid.UUID,
        idempotency_key: str,
        operation: str,
        request: Mapping[str, Any],
        target_channel_id: str | None,
        target_thread_ts: str | None,
        target_message_ts: str | None,
        task_id: uuid.UUID | None,
        purpose: str | None,
    ) -> SlackSideEffect:
        existing = self._find_by_key(installation_id, idempotency_key)
        if existing is not None:
            return existing

        try:
            with self.session.begin_nested():
                side_effect = SlackSideEffect(
                    installation_id=installation_id,
                    task_id=task_id,
                    idempotency_key=idempotency_key,
                    operation=operation,
                    purpose=purpose,
                    target_channel_id=target_channel_id,
                    target_thread_ts=target_thread_ts,
                    target_message_ts=target_message_ts,
                    request_json=_jsonable_mapping(request),
                )
                self.session.add(side_effect)
                self.session.flush()
        except IntegrityError:
            existing = self._find_by_key(installation_id, idempotency_key)
            if existing is None:
                raise
            return existing
        return side_effect

    def _find_by_key(
        self,
        installation_id: uuid.UUID,
        idempotency_key: str,
    ) -> SlackSideEffect | None:
        return self.session.scalar(
            select(SlackSideEffect).where(
                SlackSideEffect.installation_id == installation_id,
                SlackSideEffect.idempotency_key == idempotency_key,
            )
        )


def slack_message_key(task_id: uuid.UUID, purpose: str) -> str:
    """Return the deterministic outbox key for a task-bound Slack message."""

    return f"slack:message:{task_id}:{purpose}"


def slack_file_upload_key(artifact_id: uuid.UUID) -> str:
    """Return the deterministic outbox key for a Slack file upload."""

    return f"slack:file_upload:{artifact_id}"


def slack_reaction_key(
    *,
    task_id: uuid.UUID,
    operation: str,
    channel_id: str,
    message_ts: str,
    reaction: str,
) -> str:
    """Return the deterministic outbox key for a task-bound Slack reaction."""

    return f"slack:{operation}:{task_id}:{channel_id}:{message_ts}:{reaction}"


def slack_channel_intro_key(*, installation_id: uuid.UUID, channel_id: str) -> str:
    """Return the deterministic outbox key for channel onboarding intro posts."""

    return f"slack:channel_intro:{installation_id}:{channel_id}"


def _idempotent_success_response(
    operation: str,
    exc: Exception,
) -> Mapping[str, Any] | None:
    if not isinstance(exc, SlackApiError):
        return None
    error = _slack_api_error(exc)
    if operation == "reactions_add" and error == "already_reacted":
        return {"ok": True, "deduped_by_slack": True, "error": error}
    if operation == "reactions_remove" and error in {"no_reaction", "not_reacted"}:
        return {"ok": True, "deduped_by_slack": True, "error": error}
    return None


def _slack_api_error(exc: SlackApiError) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("error")
        return error if isinstance(error, str) else None
    get = getattr(response, "get", None)
    if callable(get):
        error = get("error")
        return error if isinstance(error, str) else None
    return None


def _jsonable_mapping(value: Any) -> dict[str, Any]:
    mapping = _coerce_mapping(value)
    if mapping is not None:
        return {str(key): _jsonable(item) for key, item in mapping.items()}
    return {"value": _jsonable(value)}


def _coerce_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    data = getattr(value, "data", None)
    if isinstance(data, Mapping):
        return data
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)
