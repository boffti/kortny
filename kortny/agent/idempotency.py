"""Tool invocation idempotency ledger (HIG-194).

The coordinator records and flushes a ``tool_call`` event *before* executing the
tool. If the worker crashes mid-invoke, the queue lease expires, the task is
requeued, and a retry would re-execute the tool — producing duplicate external
side effects. The Slack outbox already solves this for Slack posts; this module
closes the gap for the general tool path.

Design:

* The idempotency key is the deterministic
  ``{task_id}:{step_id}:{tool_name}:{normalized_args_hash}`` already produced by
  :func:`kortny.agent.execution.ExecutionBudgetState.record_tool_attempt`. The
  ``normalized_args_hash`` uses the same sorted-keys JSON canonicalization as the
  approval-key path, so dedup and approvals stay consistent.
* Lookup cost is only paid on the retry path: callers gate the ledger lookup on
  ``Task.attempts > 0`` (a prior lease-expiry crash bumps ``attempts`` in the
  queue's reclaim path). A fresh task pays zero extra queries per tool call.
* A prior COMPLETED attempt (a ``tool_result`` event whose payload carries the
  full recorded result) is replayed verbatim. A prior STARTED-but-never-completed
  attempt (the crash window) is resolved by side-effect class: read-only tools
  re-invoke; write/destructive tools raise a recoverable error so the model can
  route around the unknown outcome instead of risking a duplicate side effect.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import TaskEvent, TaskEventType
from kortny.tools.types import JsonObject, ToolArtifact, ToolResult

# Event ``message`` markers (kept on TaskEventType.log to avoid an enum/schema
# change; mirrors how the execution events already namespace via ``message``).
TOOL_CALL_DEDUPLICATED_MESSAGE = "tool_call_deduplicated"
TOOL_CALL_UNKNOWN_OUTCOME_MESSAGE = "tool_call_unknown_prior_outcome"
TOOL_LEASE_PRESSURE_MESSAGE = "tool_lease_pressure"

TOOL_UNKNOWN_OUTCOME_ERROR_CODE = "tool_prior_attempt_outcome_unknown"


class PriorAttemptStatus(StrEnum):
    """Outcome of a prior attempt for the same idempotency key."""

    none = "none"
    completed = "completed"
    started_only = "started_only"


@dataclass(frozen=True, slots=True)
class PriorAttemptLookup:
    """Result of inspecting the ledger for a tool idempotency key."""

    status: PriorAttemptStatus
    result: ToolResult | None = None
    tool_call_id: str | None = None


def find_prior_attempt(
    session: Session,
    *,
    task_id: uuid.UUID,
    idempotency_key: str,
) -> PriorAttemptLookup:
    """Inspect the task event ledger for a prior attempt of this key.

    Returns ``completed`` with a reconstructed :class:`ToolResult` when a prior
    ``tool_result`` carried a full result payload, ``started_only`` when a
    ``tool_call`` was recorded but no matching result followed (the crash
    window), and ``none`` otherwise.
    """

    events = list(
        session.scalars(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task_id,
                TaskEvent.type.in_(
                    (TaskEventType.tool_call, TaskEventType.tool_result)
                ),
                TaskEvent.payload["idempotency_key"].as_string() == idempotency_key,
            )
            .order_by(TaskEvent.seq)
        )
    )
    if not events:
        return PriorAttemptLookup(status=PriorAttemptStatus.none)

    started_call_id: str | None = None
    for event in events:
        payload = event.payload
        if event.type is TaskEventType.tool_result:
            result = _reconstruct_tool_result(payload)
            if result is not None:
                return PriorAttemptLookup(
                    status=PriorAttemptStatus.completed,
                    result=result,
                    tool_call_id=_optional_str(payload.get("tool_call_id")),
                )
        elif event.type is TaskEventType.tool_call:
            started_call_id = _optional_str(payload.get("tool_call_id"))

    if started_call_id is not None or events:
        return PriorAttemptLookup(
            status=PriorAttemptStatus.started_only,
            tool_call_id=started_call_id,
        )
    return PriorAttemptLookup(status=PriorAttemptStatus.none)


def _reconstruct_tool_result(payload: JsonObject) -> ToolResult | None:
    """Rebuild a ToolResult from a recorded ``tool_result`` payload.

    Returns ``None`` when the payload lacks a full ``output`` (e.g. an error
    event that never carried the result), so the caller treats it as incomplete
    rather than replaying a partial result.
    """

    output = payload.get("output")
    if not isinstance(output, dict):
        return None
    cost_usd = _coerce_decimal(payload.get("cost_usd"))
    artifacts = _reconstruct_artifacts(payload.get("artifacts"))
    return ToolResult(output=output, cost_usd=cost_usd, artifacts=artifacts)


def _reconstruct_artifacts(value: object) -> tuple[ToolArtifact, ...]:
    if not isinstance(value, list):
        return ()
    artifacts: list[ToolArtifact] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if not isinstance(filename, str):
            continue
        artifacts.append(
            ToolArtifact(
                filename=filename,
                path=_optional_str(item.get("path")),
                mime_type=_optional_str(item.get("mime_type")),
                size_bytes=item.get("size_bytes")
                if isinstance(item.get("size_bytes"), int)
                else None,
            )
        )
    return tuple(artifacts)


def _coerce_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return Decimal("0")
    return Decimal("0")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
