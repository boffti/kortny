"""Slack-native final response synthesis."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.config import Settings
from kortny.db.models import Artifact, Task, TaskEvent, TaskEventType
from kortny.db.models import LLMProvider as DbLLMProvider
from kortny.llm import (
    ChatMessage,
    LLMProvider,
    LLMService,
    ModelRouter,
    ModelRouteTier,
    create_llm_provider,
)
from kortny.slack.formatting import normalize_slack_mrkdwn
from kortny.tasks import TaskService
from kortny.tools.types import JsonObject

RESPONSE_HUMANIZER_PROMPT_NAME = "kortny.response_humanizer"
RESPONSE_HUMANIZER_SYSTEM_PROMPT = """You rewrite Kortny's final answer for Slack.

Return only the Slack-ready message. Do not explain your rewrite.

Rules:
- Preserve the factual meaning of the raw answer.
- Do not add facts, numbers, source claims, tools, or conclusions that are not in
  the provided raw answer or trace summary.
- Lead with the answer, not with boilerplate.
- Make tool usage sound natural when it helps, not mechanical.
- Use Slack mrkdwn: *bold*, simple bullets, and <https://url|label> links.
- Do not use Markdown headings with #.
- Avoid repetitive endings like "If you want..." unless the next step is
  genuinely useful and specific.
- Keep it concise for Slack, but do not omit important recommendations.
"""
MAX_RAW_ANSWER_CHARS = 8000
MAX_TRACE_OUTPUT_CHARS = 1200
MAX_HUMANIZED_CHARS = 12000
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResponseSynthesisResult:
    """Result of a Slack response synthesis pass."""

    text: str
    changed: bool
    reason: str


class ResponseSynthesizer(Protocol):
    """Rewrites raw coordinator output into Slack-facing text."""

    def synthesize(
        self,
        *,
        session: Session,
        task: Task,
        raw_text: str,
        task_service: TaskService,
    ) -> ResponseSynthesisResult:
        """Return Slack-ready text."""


class StaticResponseSynthesizer:
    """Deterministic fallback that only normalizes Slack mrkdwn."""

    def synthesize(
        self,
        *,
        session: Session,
        task: Task,
        raw_text: str,
        task_service: TaskService,
    ) -> ResponseSynthesisResult:
        del session, task, task_service
        normalized = normalize_slack_mrkdwn(raw_text)
        return ResponseSynthesisResult(
            text=normalized,
            changed=normalized != raw_text,
            reason="static_mrkdwn_normalization",
        )


class LLMResponseSynthesizer:
    """LLM-backed final response synthesizer."""

    def __init__(
        self,
        *,
        settings: Settings,
        provider: LLMProvider | None = None,
        provider_name: DbLLMProvider | str | None = None,
        min_chars: int | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.provider_name = DbLLMProvider(provider_name) if provider_name else None
        self.min_chars = (
            settings.response_humanizer_min_chars
            if min_chars is None
            else max(0, min_chars)
        )

    def synthesize(
        self,
        *,
        session: Session,
        task: Task,
        raw_text: str,
        task_service: TaskService,
    ) -> ResponseSynthesisResult:
        raw_text = raw_text.strip()
        if _should_skip(raw_text, min_chars=self.min_chars):
            normalized = normalize_slack_mrkdwn(raw_text)
            return ResponseSynthesisResult(
                text=normalized,
                changed=normalized != raw_text,
                reason="skipped_short_or_artifact",
            )

        model_route = ModelRouter(self.settings).route_for_tier(
            _route_tier(raw_text),
            reason="response_humanizer",
        )
        provider = self.provider or create_llm_provider(
            self.settings,
            model=model_route.model,
        )
        provider_name = self.provider_name or DbLLMProvider(self.settings.llm_provider)
        payload = _synthesis_payload(session=session, task=task, raw_text=raw_text)
        completion = LLMService(
            session=session,
            provider=provider,
            provider_name=provider_name,
            task_service=task_service,
            model_route=model_route,
        ).complete(
            task_id=task.id,
            messages=(
                ChatMessage(role="system", content=RESPONSE_HUMANIZER_SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        payload,
                        default=str,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            ),
            prompt_name=RESPONSE_HUMANIZER_PROMPT_NAME,
        )
        text = sanitize_humanized_response(completion.content, fallback=raw_text)
        return ResponseSynthesisResult(
            text=text,
            changed=text != normalize_slack_mrkdwn(raw_text),
            reason="llm_humanizer",
        )


def synthesize_response(
    synthesizer: ResponseSynthesizer,
    *,
    session: Session,
    task: Task,
    raw_text: str,
    task_service: TaskService,
) -> str:
    """Generate Slack-facing response text, failing open to the raw answer."""

    task_service.append_event(
        task,
        TaskEventType.log,
        {
            "message": "response_humanizer_started",
            "raw_chars": len(raw_text),
        },
    )
    try:
        result = synthesizer.synthesize(
            session=session,
            task=task,
            raw_text=raw_text,
            task_service=task_service,
        )
    except Exception as exc:
        logger.exception("response humanizer failed task_id=%s", task.id)
        task_service.append_event(
            task,
            TaskEventType.log,
            {
                "message": "response_humanizer_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "fallback": "raw_answer",
            },
        )
        return normalize_slack_mrkdwn(raw_text)

    task_service.append_event(
        task,
        TaskEventType.log,
        {
            "message": "response_humanizer_completed",
            "changed": result.changed,
            "reason": result.reason,
            "raw_chars": len(raw_text),
            "output_chars": len(result.text),
        },
    )
    return result.text


def sanitize_humanized_response(text: str | None, *, fallback: str) -> str:
    """Normalize a model-generated Slack response."""

    if text is None:
        return normalize_slack_mrkdwn(fallback)
    normalized = text.strip().strip('"').strip("'").strip()
    if not normalized:
        return normalize_slack_mrkdwn(fallback)
    if len(normalized) > MAX_HUMANIZED_CHARS:
        normalized = normalized[: MAX_HUMANIZED_CHARS - 1].rstrip() + "."
    return normalize_slack_mrkdwn(normalized)


def _should_skip(raw_text: str, *, min_chars: int) -> bool:
    if len(raw_text) < min_chars:
        return True
    normalized = raw_text.casefold().strip()
    return normalized.startswith("generated ") and " artifact" in normalized


def _route_tier(raw_text: str) -> ModelRouteTier:
    if len(raw_text) <= 2000:
        return ModelRouteTier.cheap_fast
    return ModelRouteTier.standard


def _synthesis_payload(
    *,
    session: Session,
    task: Task,
    raw_text: str,
) -> JsonObject:
    return {
        "user_request": task.input,
        "slack_surface": {
            "kind": "dm" if task.slack_channel_id.startswith("D") else "channel",
            "threaded": task.slack_thread_ts != task.slack_message_ts,
        },
        "raw_answer": _shorten(raw_text, max_chars=MAX_RAW_ANSWER_CHARS),
        "tool_trace": _tool_trace_summary(session, task),
        "artifacts": _artifact_summary(session, task),
        "formatting": {
            "target": "Slack mrkdwn",
            "avoid": ["GitHub Markdown headings", "Markdown tables"],
        },
    }


def _tool_trace_summary(session: Session, task: Task) -> list[JsonObject]:
    events = _task_events(session, task)
    calls_by_id: dict[str, JsonObject] = {}
    summaries: list[JsonObject] = []
    for event in events:
        payload = event.payload
        if event.type is TaskEventType.tool_call:
            tool_call_id = _string(payload.get("tool_call_id"))
            if tool_call_id is None:
                continue
            calls_by_id[tool_call_id] = {
                "tool": _string(payload.get("tool")),
                "argument_keys": _string_list(payload.get("argument_keys")),
            }
        elif event.type is TaskEventType.tool_result:
            tool_call_id = _string(payload.get("tool_call_id"))
            call = calls_by_id.get(tool_call_id or "", {})
            output = payload.get("output")
            summaries.append(
                {
                    "tool": _string(payload.get("tool")) or call.get("tool"),
                    "argument_keys": call.get("argument_keys", []),
                    "artifact_count": payload.get("artifact_count"),
                    "recoverable": payload.get("recoverable"),
                    "error_category": payload.get("error_category"),
                    "recovery_action": payload.get("recovery_action"),
                    "source_urls": _extract_urls(output),
                    "output_preview": _output_preview(output),
                }
            )
    return summaries[-8:]


def _artifact_summary(session: Session, task: Task) -> list[JsonObject]:
    artifacts = session.scalars(
        select(Artifact).where(Artifact.task_id == task.id).order_by(Artifact.created_at)
    )
    return [
        {
            "filename": artifact.filename,
            "mime_type": artifact.mime_type,
            "size_bytes": artifact.size_bytes,
            "posted": artifact.posted_at is not None,
        }
        for artifact in artifacts
    ]


def _task_events(session: Session, task: Task) -> Sequence[TaskEvent]:
    return tuple(
        session.scalars(
            select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.seq)
        )
    )


def _extract_urls(value: object) -> list[str]:
    urls: list[str] = []

    def walk(item: object) -> None:
        if len(urls) >= 8:
            return
        if isinstance(item, dict):
            url = item.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                urls.append(url)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return list(dict.fromkeys(urls))


def _output_preview(value: object) -> str | None:
    if value is None:
        return None
    serialized = json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)
    return _shorten(serialized, max_chars=MAX_TRACE_OUTPUT_CHARS)


def _shorten(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
