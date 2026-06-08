"""Idempotent Slack side-effect records and delivery helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from slack_sdk.errors import SlackApiError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import SlackSideEffect

SLACK_EFFECT_PENDING = "pending"
SLACK_EFFECT_IN_PROGRESS = "in_progress"
SLACK_EFFECT_SUCCEEDED = "succeeded"
SLACK_EFFECT_FAILED = "failed"
DEFAULT_STALE_SIDE_EFFECT_AFTER = timedelta(minutes=5)
DEFAULT_STALE_SIDE_EFFECT_LIMIT = 100


@dataclass(frozen=True, slots=True)
class SlackSideEffectResult:
    """Result of one Slack side-effect delivery attempt."""

    side_effect: SlackSideEffect
    response: Mapping[str, Any]
    delivered: bool
    deduped: bool


@dataclass(frozen=True, slots=True)
class SlackSideEffectRecoveryResult:
    """Summary of one stale side-effect recovery pass."""

    recovered_ids: tuple[uuid.UUID, ...]

    @property
    def recovered_count(self) -> int:
        return len(self.recovered_ids)


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
        call: Callable[[], Any],
    ) -> SlackSideEffectResult:
        """Record and deliver a Slack side effect.

        Delivery is at-least-once while successful rows are deduped by
        ``(installation_id, idempotency_key)``. Stale in-progress rows are
        marked failed by the recovery path instead of being blindly replayed.
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

    def recover_stale_in_progress(
        self,
        *,
        now: datetime | None = None,
        stale_after: timedelta = DEFAULT_STALE_SIDE_EFFECT_AFTER,
        limit: int = DEFAULT_STALE_SIDE_EFFECT_LIMIT,
    ) -> SlackSideEffectRecoveryResult:
        """Mark abandoned in-progress rows failed without replaying Slack calls."""

        if stale_after.total_seconds() <= 0:
            raise ValueError("stale_after must be positive")
        if limit < 1:
            raise ValueError("limit must be at least 1")

        recovered_at = now or datetime.now(UTC)
        cutoff = recovered_at - stale_after
        rows = tuple(
            self.session.scalars(
                select(SlackSideEffect)
                .where(
                    SlackSideEffect.status == SLACK_EFFECT_IN_PROGRESS,
                    or_(
                        SlackSideEffect.started_at.is_(None),
                        SlackSideEffect.started_at <= cutoff,
                    ),
                )
                .order_by(SlackSideEffect.started_at.asc().nullsfirst())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for side_effect in rows:
            side_effect.status = SLACK_EFFECT_FAILED
            side_effect.last_error = {
                "type": "StaleSideEffectLease",
                "message": "Slack side effect was left in progress past its lease window.",
                "delivery_state": "unknown",
                "recovered_at": recovered_at.isoformat(),
                "started_at": side_effect.started_at.isoformat()
                if side_effect.started_at is not None
                else None,
                "stale_after_seconds": int(stale_after.total_seconds()),
            }
            side_effect.available_at = recovered_at
            side_effect.updated_at = recovered_at

        if rows:
            self.session.flush()
        return SlackSideEffectRecoveryResult(
            recovered_ids=tuple(side_effect.id for side_effect in rows),
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


def slack_pin_key(
    *,
    task_id: uuid.UUID,
    channel_id: str,
    message_ts: str,
) -> str:
    """Return the deterministic outbox key for a task-bound Slack pin."""

    return f"slack:pins_add:{task_id}:{channel_id}:{message_ts}"


def slack_bookmark_key(
    *,
    task_id: uuid.UUID,
    channel_id: str,
    digest: str,
) -> str:
    """Return the deterministic outbox key for a task-bound Slack bookmark."""

    return f"slack:bookmarks_add:{task_id}:{channel_id}:{digest}"


def slack_channel_canvas_key(
    *,
    task_id: uuid.UUID,
    channel_id: str,
    digest: str,
) -> str:
    """Return the deterministic outbox key for a channel canvas create call."""

    return f"slack:conversations_canvases_create:{task_id}:{channel_id}:{digest}"


def slack_canvas_edit_key(
    *,
    task_id: uuid.UUID,
    canvas_id: str,
    digest: str,
) -> str:
    """Return the deterministic outbox key for a canvas edit call."""

    return f"slack:canvases_edit:{task_id}:{canvas_id}:{digest}"


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
    if operation == "pins_add" and error == "already_pinned":
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
