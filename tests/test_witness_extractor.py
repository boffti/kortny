import json
from decimal import Decimal

from kortny.witness import parse_witness_task_response_extraction


def test_parse_witness_task_response_extraction_validates_model_candidates() -> None:
    result = parse_witness_task_response_extraction(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_type": "workflow_gap",
                        "title": "Repeated status summaries",
                        "summary": "Offer to summarize repeated status threads.",
                        "suggested_action": "Watch for recurring status asks.",
                        "suggested_message": (
                            "I can keep an eye on repeated status asks here."
                        ),
                        "evidence": ["The answer named repeated summary requests."],
                        "confidence_score": 0.73,
                        "confidence_reason": "The model saw a recurring pattern.",
                    },
                    {
                        "candidate_type": "not_allowed",
                        "title": "Bad type",
                        "summary": "This should be ignored.",
                        "confidence_score": 0.9,
                        "confidence_reason": "Invalid type.",
                    },
                ],
                "skipped_reason": None,
            }
        )
    )

    assert result.skipped_reason is None
    assert result.raw_candidate_count == 2
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.candidate_type == "workflow_gap"
    assert candidate.title == "Repeated status summaries"
    assert candidate.evidence == ("The answer named repeated summary requests.",)
    assert candidate.confidence_score == Decimal("0.730")


def test_parse_witness_task_response_extraction_allows_no_candidates() -> None:
    result = parse_witness_task_response_extraction(
        json.dumps(
            {
                "candidates": [],
                "skipped_reason": "routine greeting with no future watch item",
            }
        )
    )

    assert result.candidates == ()
    assert result.raw_candidate_count == 0
    assert result.skipped_reason == "routine greeting with no future watch item"
