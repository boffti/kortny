import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from kortny.db.models import Task
from kortny.workflow.planning_classifier import classify_planned_workflow

BENCHMARK_PATH = Path("tests/fixtures/kortny_product_benchmark.json")

ALLOWED_GUARDRAILS = {
    "slack_response_quality",
    "latency_cost",
    "correct_context_tool_selection",
    "operator_trust_debuggability",
}
ALLOWED_ROUTES = {"inline", "planned_candidate"}
EXPECTED_SURFACES = {"dm", "channel_mention"}
EXPECTED_SECTIONS = {"slack", "logs", "db", "dashboard"}


def test_product_benchmark_fixture_is_well_formed() -> None:
    benchmark = _load_benchmark()
    scenarios = benchmark["scenarios"]
    ids = [scenario["id"] for scenario in scenarios]

    assert benchmark["version"] == 1
    assert len(scenarios) == 10
    assert len(ids) == len(set(ids))
    assert {
        scenario["primary_guardrail"] for scenario in scenarios
    } == ALLOWED_GUARDRAILS
    assert {scenario["surface"] for scenario in scenarios} == EXPECTED_SURFACES

    for scenario in scenarios:
        assert scenario["desired_runtime_route"] in ALLOWED_ROUTES
        assert scenario["baseline_classifier_route"] in ALLOWED_ROUTES
        assert scenario["primary_guardrail"] in ALLOWED_GUARDRAILS
        assert scenario["prompt"].strip()
        assert set(scenario["expected"]) == EXPECTED_SECTIONS
        for checks in scenario["expected"].values():
            assert isinstance(checks, list)
            assert checks
            assert all(isinstance(check, str) and check.strip() for check in checks)


def test_product_benchmark_records_current_planned_classifier_baseline() -> None:
    benchmark = _load_benchmark()

    for scenario in benchmark["scenarios"]:
        decision = classify_planned_workflow(task=_task(scenario["prompt"]))

        assert decision.route.value == scenario["baseline_classifier_route"], (
            f"{scenario['id']} classifier route changed from benchmark baseline. "
            "If this is an intended product improvement, update the benchmark "
            "baseline and known_gap note."
        )


def test_product_benchmark_tracks_known_route_gaps() -> None:
    benchmark = _load_benchmark()
    known_gap_ids = {
        scenario["id"]
        for scenario in benchmark["scenarios"]
        if scenario["desired_runtime_route"] != scenario["baseline_classifier_route"]
    }

    assert known_gap_ids == {
        "james_bond_ranked_research",
        "website_cpt_audit",
        "memory_forget_no_match",
    }
    for scenario in benchmark["scenarios"]:
        if scenario["id"] in known_gap_ids:
            assert scenario["known_gap"]


def _load_benchmark() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(BENCHMARK_PATH.read_text()))


def _task(input_text: str) -> Task:
    return cast(
        Task,
        SimpleNamespace(
            input=input_text,
            identity_kind=None,
        ),
    )
