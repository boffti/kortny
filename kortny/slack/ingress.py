"""Slack event ingress into durable Kortny tasks."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import Installation, Task, TaskEventType
from kortny.slack.acknowledgement import (
    AcknowledgementGenerator,
    StaticAcknowledgementGenerator,
    generate_acknowledgement,
)
from kortny.tasks import TaskService

LEADING_MENTION_RE = re.compile(r"^\s*<@[^>]+>\s*")
logger = logging.getLogger(__name__)


class SlackPostMessageClient(Protocol):
    """Subset of the Slack WebClient used by ingress."""

    def chat_postMessage(
        self,
        *,
        channel: str,
        text: str,
        thread_ts: str | None = None,
    ) -> Mapping[str, Any]:
        """Post a Slack message and return the API response."""


@dataclass(frozen=True, slots=True)
class AppMentionResult:
    """Result of processing a Slack app_mention event."""

    task: Task
    created: bool
    thread_ts: str
    acknowledgement_ts: str | None = None


class SlackIngress:
    """Turns Slack trigger events into queued tasks."""

    def __init__(
        self,
        *,
        session: Session,
        client: SlackPostMessageClient,
        task_service: TaskService | None = None,
        acknowledgement_generator: AcknowledgementGenerator | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.task_service = task_service or TaskService(session)
        self.acknowledgement_generator = (
            acknowledgement_generator or StaticAcknowledgementGenerator()
        )

    def handle_app_mention(
        self,
        *,
        body: Mapping[str, Any],
        event: Mapping[str, Any],
    ) -> AppMentionResult:
        """Create a task for a Slack app_mention and post the immediate reply."""

        event_id = _required_str(body, "event_id")
        channel_id = _required_str(event, "channel")
        message_ts = _required_str(event, "ts")
        existing = self.task_service.get_by_slack_event_id(event_id)
        if existing is None:
            existing = self._get_by_slack_message(channel_id, message_ts)
        if existing is not None:
            logger.info(
                "slack app_mention duplicate task_id=%s event_id=%s channel=%s thread_ts=%s",
                existing.id,
                event_id,
                channel_id,
                existing.slack_thread_ts or _event_thread_ts(event),
            )
            return AppMentionResult(
                task=existing,
                created=False,
                thread_ts=existing.slack_thread_ts or _event_thread_ts(event),
            )

        team_id = _team_id(body, event)
        user_id = _required_str(event, "user")
        thread_ts = _event_thread_ts(event)
        installation = self._get_or_create_installation(team_id)

        task = self.task_service.create_task(
            installation_id=installation.id,
            slack_event_id=event_id,
            slack_channel_id=channel_id,
            slack_thread_ts=thread_ts,
            slack_message_ts=message_ts,
            slack_user_id=user_id,
            input=_task_input(event),
        )
        logger.info(
            "slack app_mention created task_id=%s event_id=%s channel=%s thread_ts=%s user=%s input_len=%s",
            task.id,
            event_id,
            channel_id,
            thread_ts,
            user_id,
            len(task.input),
        )

        if _is_thread_follow_up(event):
            logger.info(
                "slack follow-up acknowledgement skipped task_id=%s channel=%s thread_ts=%s",
                task.id,
                channel_id,
                thread_ts,
            )
            return AppMentionResult(
                task=task,
                created=True,
                thread_ts=thread_ts,
            )

        acknowledgement_text = generate_acknowledgement(
            self.acknowledgement_generator,
            session=self.session,
            task=task,
            task_service=self.task_service,
        )
        acknowledgement = self.client.chat_postMessage(
            channel=channel_id,
            text=acknowledgement_text,
            thread_ts=thread_ts,
        )
        acknowledgement_ts = _optional_response_ts(acknowledgement)
        self.task_service.append_event(
            task,
            TaskEventType.message_posted,
            {
                "channel": channel_id,
                "thread_ts": thread_ts,
                "message_ts": acknowledgement_ts,
                "text": acknowledgement_text,
                "purpose": "acknowledgement",
            },
        )
        logger.info(
            "slack acknowledgement posted task_id=%s channel=%s thread_ts=%s message_ts=%s",
            task.id,
            channel_id,
            thread_ts,
            acknowledgement_ts,
        )

        return AppMentionResult(
            task=task,
            created=True,
            thread_ts=thread_ts,
            acknowledgement_ts=acknowledgement_ts,
        )

    def _get_or_create_installation(self, slack_team_id: str) -> Installation:
        existing = self.session.scalar(
            select(Installation).where(Installation.slack_team_id == slack_team_id)
        )
        if existing is not None:
            return existing

        installation = Installation(slack_team_id=slack_team_id)
        try:
            with self.session.begin_nested():
                self.session.add(installation)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(Installation).where(Installation.slack_team_id == slack_team_id)
            )
            if existing is None:
                raise
            return existing

        return installation

    def _get_by_slack_message(self, channel_id: str, message_ts: str) -> Task | None:
        return self.session.scalar(
            select(Task)
            .where(
                Task.slack_channel_id == channel_id,
                Task.slack_message_ts == message_ts,
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )


def _required_str(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Slack event is missing {key!r}")
    return value


def _team_id(body: Mapping[str, Any], event: Mapping[str, Any]) -> str:
    team_id = body.get("team_id") or event.get("team")
    if not isinstance(team_id, str) or not team_id:
        raise ValueError("Slack event is missing team_id")
    return team_id


def _event_thread_ts(event: Mapping[str, Any]) -> str:
    thread_ts = event.get("thread_ts") or event.get("ts")
    if not isinstance(thread_ts, str) or not thread_ts:
        raise ValueError("Slack event is missing ts")
    return thread_ts


def _is_thread_follow_up(event: Mapping[str, Any]) -> bool:
    thread_ts = event.get("thread_ts")
    message_ts = event.get("ts")
    return (
        isinstance(thread_ts, str)
        and bool(thread_ts)
        and isinstance(message_ts, str)
        and thread_ts != message_ts
    )


def _task_input(event: Mapping[str, Any]) -> str:
    text = event.get("text")
    if not isinstance(text, str):
        return ""
    stripped = LEADING_MENTION_RE.sub("", text, count=1).strip()
    return stripped or text.strip()


def _optional_response_ts(response: Mapping[str, Any]) -> str | None:
    ts = response.get("ts")
    if isinstance(ts, str) and ts:
        return ts
    message = response.get("message")
    if isinstance(message, Mapping):
        message_ts = message.get("ts")
        if isinstance(message_ts, str) and message_ts:
            return message_ts
    return None
