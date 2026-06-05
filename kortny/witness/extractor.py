"""LLM-backed Witness candidate extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from kortny.db.models import Task
from kortny.llm import ChatMessage, LLMService
from kortny.tools.types import JsonObject
from kortny.witness.opportunities import (
    ALLOWED_CANDIDATE_TYPES,
    WitnessOpportunityCandidateInput,
)

WITNESS_TASK_RESPONSE_EXTRACTOR_PROMPT_NAME = (
    "kortny.witness_task_response_extractor"
)
WITNESS_TASK_RESPONSE_EXTRACTOR_RESPONSE_FORMAT: JsonObject = {
    "type": "json_object"
}
MAX_EXTRACTED_CANDIDATES = 5


@dataclass(frozen=True, slots=True)
class WitnessTaskResponseExtraction:
    """Structured result from the Witness extractor."""

    candidates: tuple[WitnessOpportunityCandidateInput, ...]
    skipped_reason: str | None
    raw_candidate_count: int


class WitnessTaskResponseExtractor:
    """Ask an LLM whether a completed task contains Witness opportunities."""

    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    def extract(
        self,
        *,
        task: Task,
        response_text: str,
    ) -> WitnessTaskResponseExtraction:
        completion = self.llm.complete(
            task_id=task.id,
            messages=_messages(task=task, response_text=response_text),
            response_format=WITNESS_TASK_RESPONSE_EXTRACTOR_RESPONSE_FORMAT,
            prompt_name=WITNESS_TASK_RESPONSE_EXTRACTOR_PROMPT_NAME,
        )
        return parse_witness_task_response_extraction(completion.content)


def parse_witness_task_response_extraction(
    content: str | None,
) -> WitnessTaskResponseExtraction:
    """Parse and validate model output from the Witness extractor."""

    if not content:
        return WitnessTaskResponseExtraction(
            candidates=(),
            skipped_reason="empty_model_output",
            raw_candidate_count=0,
        )
    try:
        payload = json.loads(_extract_json_object(content))
    except (json.JSONDecodeError, ValueError):
        return WitnessTaskResponseExtraction(
            candidates=(),
            skipped_reason="invalid_json",
            raw_candidate_count=0,
        )
    if not isinstance(payload, dict):
        return WitnessTaskResponseExtraction(
            candidates=(),
            skipped_reason="invalid_payload",
            raw_candidate_count=0,
        )
    skipped_reason = _optional_text(payload.get("skipped_reason"), max_chars=160)
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        return WitnessTaskResponseExtraction(
            candidates=(),
            skipped_reason=skipped_reason or "missing_candidates",
            raw_candidate_count=0,
        )

    candidates: list[WitnessOpportunityCandidateInput] = []
    for raw_candidate in raw_candidates:
        candidate = _candidate_from_payload(raw_candidate)
        if candidate is None:
            continue
        candidates.append(candidate)
        if len(candidates) >= MAX_EXTRACTED_CANDIDATES:
            break

    return WitnessTaskResponseExtraction(
        candidates=tuple(candidates),
        skipped_reason=None if candidates else skipped_reason or "no_valid_candidates",
        raw_candidate_count=len(raw_candidates),
    )


def _messages(*, task: Task, response_text: str) -> tuple[ChatMessage, ...]:
    return (
        ChatMessage(
            role="system",
            content=(
                "You are Kortny's Witness extractor. Kortny is an AI coworker in "
                "Slack. Decide whether a completed Slack answer contains future "
                "things Kortny should watch for, proactively help with, or remember "
                "as candidate opportunities. Use semantic judgment; do not require "
                "specific headings or phrases. Return JSON only. Schema: "
                "{\"candidates\":[{\"candidate_type\":\"workflow_gap|"
                "artifact_followup|unresolved_decision|data_quality_issue|"
                "recurring_check|project_status_gap|general_help\","
                "\"title\":\"short title\",\"summary\":\"what Kortny should watch "
                "for or help with\",\"suggested_action\":\"operator-facing action\","
                "\"suggested_message\":\"low-pressure Slack DM or channel suggestion\","
                "\"evidence\":[\"short evidence from the answer or request\"],"
                "\"confidence_score\":0.0,\"confidence_reason\":\"why\"}],"
                "\"skipped_reason\":\"only when no candidates\"}. "
                "Only create candidates that would make Kortny more useful later. "
                "Return no candidates for routine greetings, generic answers, or "
                "claims without evidence."
            ),
        ),
        ChatMessage(
            role="user",
            content=json.dumps(
                {
                    "slack_surface": (
                        "dm"
                        if task.slack_channel_id
                        and task.slack_channel_id.startswith("D")
                        else "channel"
                    ),
                    "channel_id": task.slack_channel_id,
                    "user_id": task.slack_user_id,
                    "user_request": task.input,
                    "kortny_response": response_text,
                    "allowed_candidate_types": sorted(ALLOWED_CANDIDATE_TYPES),
                    "max_candidates": MAX_EXTRACTED_CANDIDATES,
                },
                sort_keys=True,
            ),
        ),
    )


def _candidate_from_payload(value: object) -> WitnessOpportunityCandidateInput | None:
    if not isinstance(value, dict):
        return None
    candidate_type = _optional_text(value.get("candidate_type"), max_chars=80)
    title = _optional_text(value.get("title"), max_chars=140)
    summary = _optional_text(value.get("summary"), max_chars=1000)
    if (
        candidate_type not in ALLOWED_CANDIDATE_TYPES
        or title is None
        or summary is None
    ):
        return None
    confidence_score = _confidence(value.get("confidence_score"))
    confidence_reason = _optional_text(
        value.get("confidence_reason"),
        max_chars=500,
    )
    evidence = _string_tuple(value.get("evidence"), max_items=5, max_chars=300)
    return WitnessOpportunityCandidateInput(
        candidate_type=candidate_type,
        title=title,
        summary=summary,
        suggested_action=_optional_text(value.get("suggested_action"), max_chars=500),
        suggested_message=_optional_text(value.get("suggested_message"), max_chars=500),
        evidence=evidence,
        confidence_score=confidence_score,
        confidence_reason=confidence_reason or "Witness extractor proposed this.",
        metadata_json={
            "extractor": WITNESS_TASK_RESPONSE_EXTRACTOR_PROMPT_NAME,
        },
    )


def _optional_text(value: object, *, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not text:
        return None
    return text[:max_chars].strip()


def _string_tuple(
    value: object,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _optional_text(item, max_chars=max_chars)
        if text is None:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= max_items:
            break
    return tuple(output)


def _confidence(value: object) -> Decimal:
    try:
        score = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0.500")
    if score < 0:
        return Decimal("0.000")
    if score > 1:
        return Decimal("1.000")
    return score.quantize(Decimal("0.001"))


def _extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object found")
    return stripped[start : end + 1]
