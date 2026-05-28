"""Durable inbound Slack event ledger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import (
    Installation,
    ObservationEvent,
    SlackInboundEvent,
    Task,
)

logger = logging.getLogger(__name__)

INBOUND_STATUS_RECEIVED = "received"
INBOUND_STATUS_IGNORED = "ignored"
INBOUND_STATUS_TASK_CREATED = "task_created"
INBOUND_STATUS_OBSERVED = "observed"
INBOUND_STATUS_FAILED = "failed"
INBOUND_STATUS_DEAD_LETTERED = "dead_lettered"
INBOUND_STATUS_REPLAYED = "replayed"

_NON_DEGRADABLE_STATUSES = frozenset(
    {
        INBOUND_STATUS_TASK_CREATED,
        INBOUND_STATUS_OBSERVED,
        INBOUND_STATUS_DEAD_LETTERED,
        INBOUND_STATUS_REPLAYED,
    }
)


@dataclass(frozen=True, slots=True)
class InboundEventRecordResult:
    """Result of recording a Slack inbound delivery."""

    event: SlackInboundEvent
    created: bool


class SlackInboundEventService:
    """Record Slack deliveries before downstream side effects happen."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        installation: Installation,
        slack_team_id: str,
        body: Mapping[str, Any],
        event: Mapping[str, Any],
        surface: str,
    ) -> InboundEventRecordResult:
        """Insert or update a delivery row keyed by Slack event id."""

        slack_event_id = _optional_str(body.get("event_id"))
        existing = self._existing(installation.id, slack_event_id)
        if existing is not None:
            self._mark_delivery_seen(existing, body=body, surface=surface)
            self.session.flush()
            return InboundEventRecordResult(event=existing, created=False)

        inbound = SlackInboundEvent(
            installation_id=installation.id,
            slack_team_id=slack_team_id,
            slack_event_id=slack_event_id,
            event_type=_event_type(body, event),
            event_subtype=_optional_str(event.get("subtype")),
            surface=surface,
            channel_id=_channel_id(event),
            user_id=_optional_str(event.get("user")),
            message_ts=_message_ts(event),
            thread_ts=_thread_ts(event),
            event_time=_event_time(body),
            retry_num=_retry_num(body),
            retry_reason=_retry_reason(body),
            raw_body=dict(body),
            raw_event=dict(event),
            metadata_json={"delivery_count": 1, "surfaces": [surface]},
        )
        try:
            with self.session.begin_nested():
                self.session.add(inbound)
                self.session.flush()
        except IntegrityError:
            existing = self._existing(installation.id, slack_event_id)
            if existing is None:
                raise
            self._mark_delivery_seen(existing, body=body, surface=surface)
            self.session.flush()
            return InboundEventRecordResult(event=existing, created=False)

        logger.info(
            "slack inbound event recorded event_id=%s surface=%s channel=%s inbound_event_id=%s",
            slack_event_id,
            surface,
            inbound.channel_id,
            inbound.id,
        )
        return InboundEventRecordResult(event=inbound, created=True)

    def mark_ignored(
        self,
        inbound: SlackInboundEvent | None,
        *,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None or inbound.processing_status in _NON_DEGRADABLE_STATUSES:
            return
        self._mark(
            inbound,
            status=INBOUND_STATUS_IGNORED,
            metadata={"reason": reason, **dict(metadata or {})},
        )

    def mark_observed(
        self,
        inbound: SlackInboundEvent | None,
        *,
        observation: ObservationEvent | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None or inbound.processing_status == INBOUND_STATUS_TASK_CREATED:
            return
        if observation is not None:
            inbound.observation_event_id = observation.id
        self._mark(inbound, status=INBOUND_STATUS_OBSERVED, metadata=metadata)

    def mark_task_created(
        self,
        inbound: SlackInboundEvent | None,
        *,
        task: Task,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None:
            return
        inbound.task_id = task.id
        self._mark(inbound, status=INBOUND_STATUS_TASK_CREATED, metadata=metadata)

    def mark_failed(
        self,
        inbound: SlackInboundEvent | None,
        *,
        error: BaseException,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None:
            return
        inbound.processing_attempts = (inbound.processing_attempts or 0) + 1
        inbound.last_error = {
            "error_type": type(error).__name__,
            "error": str(error),
        }
        if inbound.processing_status != INBOUND_STATUS_TASK_CREATED:
            self._mark(inbound, status=INBOUND_STATUS_FAILED, metadata=metadata)
        else:
            self._merge_metadata(inbound, metadata or {})
            self.session.flush()

    def mark_dead_lettered(
        self,
        inbound: SlackInboundEvent | None,
        *,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None:
            return
        self._mark(
            inbound,
            status=INBOUND_STATUS_DEAD_LETTERED,
            metadata={"reason": reason, **dict(metadata or {})},
        )

    def mark_replayed(
        self,
        inbound: SlackInboundEvent | None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if inbound is None:
            return
        self._mark(inbound, status=INBOUND_STATUS_REPLAYED, metadata=metadata)

    def _existing(
        self,
        installation_id: object,
        slack_event_id: str | None,
    ) -> SlackInboundEvent | None:
        if slack_event_id is None:
            return None
        return self.session.scalar(
            select(SlackInboundEvent).where(
                SlackInboundEvent.installation_id == installation_id,
                SlackInboundEvent.slack_event_id == slack_event_id,
            )
        )

    def _mark_delivery_seen(
        self,
        inbound: SlackInboundEvent,
        *,
        body: Mapping[str, Any],
        surface: str,
    ) -> None:
        metadata = dict(inbound.metadata_json or {})
        retry_num = _retry_num(body)
        retry_reason = _retry_reason(body)
        surfaces = metadata.get("surfaces")
        if not isinstance(surfaces, list):
            surfaces = [inbound.surface]
        if surface not in surfaces:
            surfaces.append(surface)
        metadata["surfaces"] = surfaces
        if retry_num is not None or retry_reason is not None:
            metadata["delivery_count"] = int(metadata.get("delivery_count") or 1) + 1
            metadata["last_delivery_at"] = datetime.now(UTC).isoformat()
        inbound.metadata_json = metadata
        if retry_num is not None:
            inbound.retry_num = retry_num
        if retry_reason is not None:
            inbound.retry_reason = retry_reason

    def _mark(
        self,
        inbound: SlackInboundEvent,
        *,
        status: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        inbound.processing_status = status
        inbound.processed_at = datetime.now(UTC)
        self._merge_metadata(inbound, metadata or {})
        self.session.flush()

    def _merge_metadata(
        self,
        inbound: SlackInboundEvent,
        metadata: Mapping[str, Any],
    ) -> None:
        if not metadata:
            return
        merged = dict(inbound.metadata_json or {})
        merged.update(dict(metadata))
        inbound.metadata_json = merged


def _event_type(body: Mapping[str, Any], event: Mapping[str, Any]) -> str:
    value = event.get("type") or body.get("type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def _channel_id(event: Mapping[str, Any]) -> str | None:
    direct = _optional_str(event.get("channel"))
    if direct is not None:
        return direct
    item = event.get("item")
    if isinstance(item, Mapping):
        return _optional_str(item.get("channel"))
    return None


def _message_ts(event: Mapping[str, Any]) -> str | None:
    direct = _optional_str(event.get("ts"))
    if direct is not None:
        return direct
    item = event.get("item")
    if isinstance(item, Mapping):
        return _optional_str(item.get("ts"))
    return None


def _thread_ts(event: Mapping[str, Any]) -> str | None:
    return _optional_str(event.get("thread_ts")) or _message_ts(event)


def _event_time(body: Mapping[str, Any]) -> datetime | None:
    value = body.get("event_time")
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromtimestamp(float(value), UTC)
        except ValueError:
            return None
    return None


def _retry_num(body: Mapping[str, Any]) -> int | None:
    value = (
        body.get("retry_num")
        or body.get("X-Slack-Retry-Num")
        or _header_value(body, "x-slack-retry-num")
    )
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _retry_reason(body: Mapping[str, Any]) -> str | None:
    return (
        _optional_str(body.get("retry_reason"))
        or _optional_str(body.get("X-Slack-Retry-Reason"))
        or _header_value(body, "x-slack-retry-reason")
    )


def _header_value(body: Mapping[str, Any], header_name: str) -> str | None:
    headers = body.get("headers")
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == header_name:
            return _optional_str(value)
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
