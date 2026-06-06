"""Deterministic Tier 0 routing for system-of-record task paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kortny.db.models import Task
from kortny.routing.trace import RoutingDecisionTrace
from kortny.schedule_intent import (
    is_schedule_state_question,
    schedule_state_query_text,
    schedule_state_status_filter,
)
from kortny.tools.types import JsonObject


class Tier0RouteKind(StrEnum):
    """System-of-record routes that bypass the general agent runtime."""

    schedule_state_query = "schedule_state_query"


@dataclass(frozen=True, slots=True)
class Tier0RouteDecision:
    """High-confidence Tier 0 decision and handler metadata."""

    kind: Tier0RouteKind
    runtime_class: str
    intent: str
    selected_runtime: str
    actual_path: str
    reason: str
    confidence: float
    reason_codes: tuple[str, ...]
    metadata: JsonObject

    def to_trace(self) -> RoutingDecisionTrace:
        """Return the standard routing trace payload object."""

        return RoutingDecisionTrace(
            stage="tier0_system_of_record",
            route_tier="tier0",
            source=self.selected_runtime,
            runtime_class=self.runtime_class,
            intent=self.intent,
            confidence=self.confidence,
            escalated=False,
            selected_runtime=self.selected_runtime,
            selected_backend="inline",
            actual_path=self.actual_path,
            reason=self.reason,
            reason_codes=self.reason_codes,
            metadata=self.metadata,
        )


class Tier0Router:
    """Resolve direct system-of-record paths before semantic orchestration."""

    def route(self, task: Task) -> Tier0RouteDecision | None:
        """Return a Tier 0 route decision when a direct path owns the task."""

        if task.identity_kind == "scheduled":
            return None
        if not is_schedule_state_question(task.input):
            return None

        query = schedule_state_query_text(task.input)
        status = schedule_state_status_filter(task.input)
        return Tier0RouteDecision(
            kind=Tier0RouteKind.schedule_state_query,
            runtime_class="inline_tool_task",
            intent="scheduler.query",
            selected_runtime="schedule_state_fast_path",
            actual_path="schedule_state_fast_path",
            reason="schedule_truth_lookup",
            confidence=1.0,
            reason_codes=("schedule_state_query",),
            metadata={
                "query": query,
                "status": status,
                "system_of_record": "scheduler",
            },
        )
