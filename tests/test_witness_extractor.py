import json
from decimal import Decimal

from kortny.witness import (
    WITNESS_CHANNEL_PROFILE_EXTRACTOR_PROMPT_NAME,
    parse_witness_channel_profile_extraction,
    parse_witness_task_response_extraction,
)


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


def test_parse_witness_channel_profile_extraction_tags_profile_extractor() -> None:
    result = parse_witness_channel_profile_extraction(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_type": "data_quality_issue",
                        "title": "Blotter placeholders",
                        "summary": "Watch for unresolved placeholders in reports.",
                        "suggested_action": "Flag broken report placeholders.",
                        "suggested_message": "I can flag report placeholders here.",
                        "evidence": ["The profile mentioned {TICKER} placeholders."],
                        "confidence_score": 0.81,
                        "confidence_reason": "Profile evidence names this issue.",
                    }
                ],
                "skipped_reason": None,
            }
        )
    )

    assert result.skipped_reason is None
    assert result.raw_candidate_count == 1
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.candidate_type == "data_quality_issue"
    assert candidate.metadata_json["extractor"] == (
        WITNESS_CHANNEL_PROFILE_EXTRACTOR_PROMPT_NAME
    )
