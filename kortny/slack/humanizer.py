"""Slack-native final response synthesis."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
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
RESPONSE_HUMANIZER_SYSTEM_PROMPT = """You write Kortny's final Slack response from a typed ResponseRecord.

Return only the Slack-ready message. Do not explain your rewrite.

Rules:
- Use only facts, actions, artifacts, failures, uncertainties, links, and the raw
  answer present in the ResponseRecord.
- Do not add new facts, numbers, source claims, tools, or conclusions.
- Lead with the answer, not with boilerplate.
- Make tool usage sound natural when it helps, not mechanical.
- Use Slack mrkdwn: *bold*, simple bullets, and <https://url|label> links.
- Do not use Markdown headings with #.
- Avoid repetitive endings like "If you want..." unless a next step is
  genuinely useful and specific.
- Keep it concise for Slack, but do not omit important recommendations.
- Apply human editing principles: remove inflated/promotional language, cut
  chatbot artifacts, vary rhythm naturally, and preserve substance.
"""
MAX_RAW_ANSWER_CHARS = 8000
MAX_TRACE_OUTPUT_CHARS = 1200
MAX_HUMANIZED_CHARS = 12000
logger = logging.getLogger(__name__)


class ResponseMode(StrEnum):
    """High-level response shape selected from execution evidence."""

    quick_answer = "quick_answer"
    research_summary = "research_summary"
    file_analysis = "file_analysis"
    artifact_delivery = "artifact_delivery"
    failure_recovery = "failure_recovery"
    memory_recall = "memory_recall"
    multi_step_recap = "multi_step_recap"


@dataclass(frozen=True, slots=True)
class SlackSurface:
    """Slack delivery surface for the response."""

    kind: str
    threaded: bool

    def to_payload(self) -> JsonObject:
        return {"kind": self.kind, "threaded": self.threaded}


@dataclass(frozen=True, slots=True)
class ResponseStyleProfile:
    """Small, typed style profile for response synthesis."""

    tone: str = "approachable, steady, direct"
    brevity: str = "concise"
    polish: str = "professional"
    humor: str = "off_by_default"
    proactive_suggestions: str = "only_when_clearly_useful"

    def to_payload(self) -> JsonObject:
        return {
            "tone": self.tone,
            "brevity": self.brevity,
            "polish": self.polish,
            "humor": self.humor,
            "proactive_suggestions": self.proactive_suggestions,
        }


@dataclass(frozen=True, slots=True)
class ResponseAction:
    """One action the agent took while completing the task."""

    tool: str
    status: str
    argument_keys: list[str]
    summary: str | None = None

    def to_payload(self) -> JsonObject:
        return {
            "tool": self.tool,
            "status": self.status,
            "argument_keys": self.argument_keys,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class ResponseEvidence:
    """Evidence available to the synthesizer."""

    source_type: str
    source_id: str
    tool: str | None = None
    urls: list[str] | None = None
    preview: str | None = None

    def to_payload(self) -> JsonObject:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "tool": self.tool,
            "urls": self.urls or [],
            "preview": self.preview,
        }


@dataclass(frozen=True, slots=True)
class ResponseArtifact:
    """Artifact produced during the task."""

    filename: str
    mime_type: str | None
    size_bytes: int | None
    posted: bool

    def to_payload(self) -> JsonObject:
        return {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "posted": self.posted,
        }


@dataclass(frozen=True, slots=True)
class ResponseFailure:
    """Tool or execution failure that may need user-facing caveats."""

    source: str
    code: str | None
    message: str | None
    recoverable: bool | None
    recovery_action: str | None

    def to_payload(self) -> JsonObject:
        return {
            "source": self.source,
            "code": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "recovery_action": self.recovery_action,
        }


@dataclass(frozen=True, slots=True)
class ResponseRecord:
    """Typed terminal response contract for the Slack humanizer."""

    user_request: str
    raw_answer: str
    response_mode: ResponseMode
    task_status: str
    slack_surface: SlackSurface
    style_profile: ResponseStyleProfile
    actions_taken: list[ResponseAction]
    evidence: list[ResponseEvidence]
    artifacts: list[ResponseArtifact]
    failures: list[ResponseFailure]
    uncertainties: list[str]
    suggested_next_actions: list[str]

    def to_payload(self) -> JsonObject:
        return {
            "user_request": self.user_request,
            "raw_answer": _shorten(
                self.raw_answer,
                max_chars=MAX_RAW_ANSWER_CHARS,
            ),
            "response_mode": self.response_mode.value,
            "task_status": self.task_status,
            "slack_surface": self.slack_surface.to_payload(),
            "style_profile": self.style_profile.to_payload(),
            "actions_taken": [action.to_payload() for action in self.actions_taken],
            "evidence": [item.to_payload() for item in self.evidence],
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "failures": [failure.to_payload() for failure in self.failures],
            "uncertainties": self.uncertainties,
            "suggested_next_actions": self.suggested_next_actions,
        }

    def summary_payload(self) -> JsonObject:
        """Return a compact trace payload for task events."""

        return {
            "response_mode": self.response_mode.value,
            "task_status": self.task_status,
            "action_count": len(self.actions_taken),
            "evidence_count": len(self.evidence),
            "artifact_count": len(self.artifacts),
            "failure_count": len(self.failures),
            "uncertainty_count": len(self.uncertainties),
            "suggested_next_action_count": len(self.suggested_next_actions),
        }


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
        response_record: ResponseRecord,
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
        response_record: ResponseRecord,
        task_service: TaskService,
    ) -> ResponseSynthesisResult:
        del session, task, task_service
        raw_text = response_record.raw_answer
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
        response_record: ResponseRecord,
        task_service: TaskService,
    ) -> ResponseSynthesisResult:
        if _should_skip(response_record, min_chars=self.min_chars):
            normalized = normalize_slack_mrkdwn(response_record.raw_answer)
            return ResponseSynthesisResult(
                text=normalized,
                changed=normalized != response_record.raw_answer,
                reason="skipped_short_or_artifact",
            )

        model_route = ModelRouter(self.settings).route_for_tier(
            _route_tier(response_record),
            reason="response_humanizer",
        )
        provider = self.provider or create_llm_provider(
            self.settings,
            model=model_route.model,
        )
        provider_name = self.provider_name or DbLLMProvider(self.settings.llm_provider)
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
                        _synthesis_payload(response_record),
                        default=str,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                ),
            ),
            prompt_name=RESPONSE_HUMANIZER_PROMPT_NAME,
        )
        text = sanitize_humanized_response(
            completion.content,
            fallback=response_record.raw_answer,
        )
        return ResponseSynthesisResult(
            text=text,
            changed=text != normalize_slack_mrkdwn(response_record.raw_answer),
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

    response_record = build_response_record(
        session=session,
        task=task,
        raw_text=raw_text,
    )
    task_service.append_event(
        task,
        TaskEventType.log,
        {
            "message": "response_record_built",
            **response_record.summary_payload(),
        },
    )
    task_service.append_event(
        task,
        TaskEventType.log,
        {
            "message": "response_humanizer_started",
            "raw_chars": len(raw_text),
            "response_mode": response_record.response_mode.value,
        },
    )
    try:
        result = synthesizer.synthesize(
            session=session,
            task=task,
            response_record=response_record,
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
            "response_mode": response_record.response_mode.value,
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


def build_response_record(
    *,
    session: Session,
    task: Task,
    raw_text: str,
) -> ResponseRecord:
    """Build the typed response contract from task events and artifacts."""

    events = _task_events(session, task)
    calls_by_id = _tool_calls_by_id(events)
    actions: list[ResponseAction] = []
    evidence: list[ResponseEvidence] = []
    failures: list[ResponseFailure] = []
    uncertainties: list[str] = []

    for event in events:
        if event.type is TaskEventType.tool_result:
            action, evidence_item, failure = _response_items_from_tool_result(
                event,
                calls_by_id,
            )
            if action is not None:
                actions.append(action)
            if evidence_item is not None:
                evidence.append(evidence_item)
            if failure is not None:
                failures.append(failure)
                if failure.message:
                    uncertainties.append(failure.message)
        elif event.type is TaskEventType.error:
            failure = _response_failure_from_error_event(event)
            failures.append(failure)
            if failure.message:
                uncertainties.append(failure.message)

    artifacts = _artifact_summary(session, task)
    response_mode = _select_response_mode(
        raw_text=raw_text,
        actions=actions,
        evidence=evidence,
        artifacts=artifacts,
        failures=failures,
    )
    return ResponseRecord(
        user_request=task.input,
        raw_answer=raw_text.strip(),
        response_mode=response_mode,
        task_status=_response_status(failures),
        slack_surface=SlackSurface(
            kind="dm" if task.slack_channel_id.startswith("D") else "channel",
            threaded=task.slack_thread_ts != task.slack_message_ts,
        ),
        style_profile=ResponseStyleProfile(),
        actions_taken=actions[-10:],
        evidence=evidence[-10:],
        artifacts=artifacts,
        failures=failures[-10:],
        uncertainties=list(dict.fromkeys(uncertainties))[-8:],
        suggested_next_actions=_suggested_next_actions(
            response_mode,
            failures,
            artifacts,
        ),
    )


def _should_skip(response_record: ResponseRecord, *, min_chars: int) -> bool:
    raw_text = response_record.raw_answer
    if len(raw_text) < min_chars:
        return True
    return response_record.response_mode is ResponseMode.artifact_delivery


def _route_tier(response_record: ResponseRecord) -> ModelRouteTier:
    if response_record.response_mode in {
        ResponseMode.quick_answer,
        ResponseMode.memory_recall,
    }:
        return ModelRouteTier.cheap_fast
    return ModelRouteTier.standard


def _synthesis_payload(response_record: ResponseRecord) -> JsonObject:
    return {
        "response_record": response_record.to_payload(),
        "renderer_constraints": {
            "target": "Slack mrkdwn",
            "avoid": ["GitHub Markdown headings", "Markdown tables"],
        },
    }


def _tool_calls_by_id(events: Sequence[TaskEvent]) -> dict[str, JsonObject]:
    calls_by_id: dict[str, JsonObject] = {}
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
    return calls_by_id


def _response_items_from_tool_result(
    event: TaskEvent,
    calls_by_id: dict[str, JsonObject],
) -> tuple[ResponseAction | None, ResponseEvidence | None, ResponseFailure | None]:
    payload = event.payload
    tool_call_id = _string(payload.get("tool_call_id")) or f"event-{event.id}"
    call = calls_by_id.get(tool_call_id, {})
    tool = _string(payload.get("tool")) or _string(call.get("tool")) or "tool"
    output = payload.get("output")
    recoverable = _optional_bool(payload.get("recoverable"))
    error = _tool_error_payload(output)
    status = "failed" if error is not None or recoverable is True else "succeeded"
    action = ResponseAction(
        tool=tool,
        status=status,
        argument_keys=_string_list(call.get("argument_keys")),
        summary=_tool_result_summary(output),
    )
    urls = _extract_urls(output)
    evidence = ResponseEvidence(
        source_type="tool_result",
        source_id=tool_call_id,
        tool=tool,
        urls=urls,
        preview=_output_preview(output),
    )
    failure = None
    if error is not None:
        failure = ResponseFailure(
            source=tool,
            code=_string(error.get("code")),
            message=_string(error.get("message")),
            recoverable=_optional_bool(error.get("recoverable")),
            recovery_action=_string(error.get("recovery_action"))
            or _string(payload.get("recovery_action")),
        )
    return action, evidence, failure


def _response_failure_from_error_event(event: TaskEvent) -> ResponseFailure:
    payload = event.payload
    return ResponseFailure(
        source=_string(payload.get("phase")) or "task",
        code=_string(payload.get("type")),
        message=_string(payload.get("message")) or _string(payload.get("error")),
        recoverable=False,
        recovery_action=_string(payload.get("recovery_action")),
    )


def _artifact_summary(session: Session, task: Task) -> list[ResponseArtifact]:
    artifacts = session.scalars(
        select(Artifact).where(Artifact.task_id == task.id).order_by(Artifact.created_at)
    )
    return [
        ResponseArtifact(
            filename=artifact.filename,
            mime_type=artifact.mime_type,
            size_bytes=artifact.size_bytes,
            posted=artifact.posted_at is not None,
        )
        for artifact in artifacts
    ]


def _select_response_mode(
    *,
    raw_text: str,
    actions: Sequence[ResponseAction],
    evidence: Sequence[ResponseEvidence],
    artifacts: Sequence[ResponseArtifact],
    failures: Sequence[ResponseFailure],
) -> ResponseMode:
    tool_names = {action.tool for action in actions}
    if artifacts:
        return ResponseMode.artifact_delivery
    if failures:
        return ResponseMode.failure_recovery
    if "slack_file_read" in tool_names:
        return ResponseMode.file_analysis
    if tool_names & {"remember_fact", "recall_fact", "inspect_memory", "forget_fact"}:
        return ResponseMode.memory_recall
    if _has_research_evidence(tool_names, evidence):
        return ResponseMode.research_summary
    if len(actions) >= 2 or len(raw_text) > 1800:
        return ResponseMode.multi_step_recap
    return ResponseMode.quick_answer


def _has_research_evidence(
    tool_names: set[str],
    evidence: Sequence[ResponseEvidence],
) -> bool:
    if "web_search" in tool_names:
        return True
    if any(tool.startswith("composio_") for tool in tool_names):
        return True
    return any(item.urls for item in evidence)


def _suggested_next_actions(
    response_mode: ResponseMode,
    failures: Sequence[ResponseFailure],
    artifacts: Sequence[ResponseArtifact],
) -> list[str]:
    if response_mode is ResponseMode.failure_recovery and failures:
        return ["retry with corrected input", "use an alternate path", "ask for access"]
    if response_mode is ResponseMode.artifact_delivery and artifacts:
        return ["review the artifact", "request a revision"]
    if response_mode is ResponseMode.research_summary:
        return ["deepen the comparison", "turn findings into a brief"]
    return []


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


def _tool_result_summary(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("summary"), str):
        return _shorten(value["summary"], max_chars=240)
    if isinstance(value.get("message"), str):
        return _shorten(value["message"], max_chars=240)
    error = _tool_error_payload(value)
    if error is not None and isinstance(error.get("message"), str):
        return _shorten(error["message"], max_chars=240)
    return None


def _output_preview(value: object) -> str | None:
    if value is None:
        return None
    serialized = json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)
    return _shorten(serialized, max_chars=MAX_TRACE_OUTPUT_CHARS)


def _tool_error_payload(value: object) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    error = value.get("error")
    if isinstance(error, dict):
        return error
    if isinstance(error, str) and error.strip():
        return {
            "message": error.strip(),
            "code": _string(value.get("status_code")),
            "recoverable": _optional_bool(value.get("recoverable")),
        }
    if value.get("successful") is False:
        message = _string(value.get("message"))
        data = value.get("data")
        if message is None and isinstance(data, dict):
            message = _string(data.get("message"))
        return {
            "message": message or "Tool reported an unsuccessful result.",
            "code": _string(value.get("status_code")),
            "recoverable": _optional_bool(value.get("recoverable")),
        }
    return None


def _response_status(failures: Sequence[ResponseFailure]) -> str:
    if failures:
        return "ready_to_post_with_caveats"
    return "ready_to_post"


def _shorten(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
