import uuid
from collections.abc import Sequence

import pytest

from kortny.llm import ChatMessage, Completion, TokenUsage
from kortny.routing.semantic import (
    SEMANTIC_ROUTER_PROMPT_NAME,
    SEMANTIC_ROUTER_RESPONSE_FORMAT,
    LLMSemanticRouter,
    SemanticExecutionPath,
    SemanticRouteRequest,
    SemanticRouterParseError,
    SemanticRouterPromotionGate,
    parse_semantic_route_decision,
)
from kortny.tools.types import JsonObject, JsonSchema
from kortny.workflow.handoff import TaskRuntimeClass


class FakeSemanticLLM:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.calls: list[
            tuple[
                uuid.UUID,
                tuple[ChatMessage, ...],
                JsonObject | None,
                str | None,
            ]
        ] = []

    def complete(
        self,
        *,
        task_id: uuid.UUID,
        messages: Sequence[ChatMessage],
        tools: Sequence[JsonSchema] = (),
        response_format: JsonObject | None = None,
        prompt_name: str | None = None,
        prompt_source: str = "code",
    ) -> Completion:
        del tools, prompt_source
        self.calls.append((task_id, tuple(messages), response_format, prompt_name))
        return Completion(
            content=self.content,
            tool_calls=(),
            usage=TokenUsage(input_tokens=100, output_tokens=30),
            model="test-router-model",
        )


def test_semantic_router_calls_llm_with_json_contract() -> None:
    task_id = uuid.uuid4()
    llm = FakeSemanticLLM(
        """
        {
          "runtime_class": "inline_tool_task",
          "intent": "scheduler.query",
          "execution_path": "inline",
          "confidence": 0.91,
          "margin": 0.32,
          "candidate_capabilities": ["schedules.read"],
          "needs_clarification": false,
          "reason": "User asks whether a schedule exists."
        }
        """
    )

    decision = LLMSemanticRouter(llm).classify(
        task_id=task_id,
        request=SemanticRouteRequest(
            user_request="Do I have an active stock market update scheduled?",
            surface="dm",
        ),
    )

    assert decision.runtime_class is TaskRuntimeClass.inline_tool_task
    assert decision.intent == "scheduler.query"
    assert decision.execution_path is SemanticExecutionPath.inline
    assert decision.confidence == 0.91
    assert decision.margin == 0.32
    assert decision.candidate_capabilities == ("schedules.read",)
    assert llm.calls[0][0] == task_id
    assert llm.calls[0][2] == SEMANTIC_ROUTER_RESPONSE_FORMAT
    assert llm.calls[0][3] == SEMANTIC_ROUTER_PROMPT_NAME
    assert "shadow semantic router" in (llm.calls[0][1][0].content or "")


def test_semantic_router_comparison_payload_flags_disagreement() -> None:
    decision = parse_semantic_route_decision(
        """
        {
          "runtime_class": "durable_workflow_task",
          "intent": "website.audit",
          "execution_path": "durable_workflow",
          "confidence": 0.87,
          "margin": 0.21,
          "candidate_capabilities": ["web.crawl", "web.search"],
          "needs_clarification": false,
          "reason": "Website audit requires external inspection."
        }
        """
    )

    payload = decision.comparison_payload(
        handoff_runtime_class="inline_tool_task",
        handoff_recommended_backend="inline",
        selected_backend="inline",
        planned_classifier_route="inline",
        planned_candidate=False,
    )

    assert payload["behavior"] == "observe_only"
    assert payload["execution_path"] == "durable_workflow"
    assert payload["runtime_disagreement"] is True
    assert payload["execution_path_disagreement"] is True
    assert payload["selected_backend_disagreement"] is True


def test_semantic_router_promotion_gate_marks_high_confidence_shadow_eligible() -> None:
    decision = parse_semantic_route_decision(
        """
        {
          "runtime_class": "inline_tool_task",
          "intent": "integration.linear_project_summary",
          "execution_path": "inline",
          "confidence": 0.91,
          "margin": 0.28,
          "candidate_capabilities": ["linear.read"],
          "needs_clarification": false,
          "reason": "Single scoped Linear read."
        }
        """
    )

    promotion = SemanticRouterPromotionGate().evaluate(decision)

    assert promotion.threshold_eligible is True
    assert promotion.control_allowed is False
    assert promotion.reason_codes == (
        "thresholds_met",
        "control_disabled_shadow_mode",
    )
    assert promotion.to_payload()["mode"] == "shadow_only"


def test_semantic_router_promotion_gate_blocks_low_margin_decision() -> None:
    decision = parse_semantic_route_decision(
        """
        {
          "runtime_class": "durable_workflow_task",
          "intent": "research.synthesis",
          "execution_path": "durable_workflow",
          "confidence": 0.93,
          "margin": 0.05,
          "candidate_capabilities": ["web.search"],
          "needs_clarification": false,
          "reason": "Looks like research, but the margin is weak."
        }
        """
    )

    promotion = SemanticRouterPromotionGate().evaluate(decision)

    assert promotion.threshold_eligible is False
    assert promotion.control_allowed is False
    assert promotion.reason_codes == (
        "below_min_margin",
        "control_disabled_shadow_mode",
    )


def test_semantic_router_promotion_gate_blocks_clarification_need() -> None:
    decision = parse_semantic_route_decision(
        """
        {
          "runtime_class": "inline_tool_task",
          "intent": "scheduler.edit",
          "execution_path": "inline",
          "confidence": 0.89,
          "margin": 0.22,
          "candidate_capabilities": ["schedules.update"],
          "needs_clarification": true,
          "reason": "The target schedule is unclear."
        }
        """
    )

    promotion = SemanticRouterPromotionGate(control_enabled=True).evaluate(decision)

    assert promotion.threshold_eligible is False
    assert promotion.control_allowed is False
    assert promotion.reason_codes == ("needs_clarification",)


def test_semantic_router_rejects_invalid_runtime_class() -> None:
    with pytest.raises(SemanticRouterParseError, match="runtime_class"):
        parse_semantic_route_decision(
            """
            {
              "runtime_class": "agent_magic",
              "intent": "unknown",
              "execution_path": "inline",
              "confidence": 0.7,
              "margin": 0.2,
              "candidate_capabilities": [],
              "needs_clarification": false,
              "reason": "Bad runtime."
            }
            """
        )


def test_semantic_router_rejects_out_of_range_confidence() -> None:
    with pytest.raises(SemanticRouterParseError, match="confidence"):
        parse_semantic_route_decision(
            """
            {
              "runtime_class": "quick_response",
              "intent": "conversation.quick",
              "execution_path": "inline",
              "confidence": 1.5,
              "margin": 0.2,
              "candidate_capabilities": [],
              "needs_clarification": false,
              "reason": "Too confident."
            }
            """
        )
