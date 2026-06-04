from __future__ import annotations

from datetime import UTC, datetime

from kortny.scheduler import looks_like_schedule_request, parse_schedule_request
from kortny.scheduler.creation import format_schedule_proposal


def test_parse_weekly_schedule_request_extracts_cron_contract() -> None:
    draft = parse_schedule_request(
        (
            "Every Monday morning, check for unresolved decisions I was involved "
            "in and DM me only if there is something specific."
        ),
        now=datetime(2026, 6, 3, 14, 0, tzinfo=UTC),
    )

    assert draft is not None
    assert draft.spec_kind == "cron"
    assert draft.cron_expr == "0 9 * * 1"
    assert draft.cadence_label == "Every Monday morning"
    assert draft.next_run_at == datetime(2026, 6, 8, 9, 0, tzinfo=UTC)
    assert draft.task_input == (
        "check for unresolved decisions I was involved in and DM me only if "
        "there is something specific."
    )
    assert draft.needs_confirmation is False


def test_parse_explicit_draft_schedule_still_extracts_schedule_shape() -> None:
    draft = parse_schedule_request(
        "Draft a schedule for every Friday morning to check PYPL.",
        now=datetime(2026, 6, 3, 14, 0, tzinfo=UTC),
    )

    assert draft is not None
    assert draft.spec_kind == "cron"
    assert draft.cron_expr == "0 9 * * 5"
    assert draft.needs_confirmation is False


def test_parse_every_morning_preserves_following_task_words() -> None:
    draft = parse_schedule_request(
        "Every morning can you check on PYPL ticker and give me a market summary",
        now=datetime(2026, 6, 3, 14, 0, tzinfo=UTC),
    )

    assert draft is not None
    assert draft.spec_kind == "cron"
    assert draft.cron_expr == "0 9 * * *"
    assert draft.cadence_label == "Every morning"
    assert draft.task_input == "can you check on PYPL ticker and give me a market summary"


def test_parse_daily_schedule_with_explicit_central_time_humanizes_response() -> None:
    draft = parse_schedule_request(
        "Every morning at 8AM central time I want a stock market update.",
        now=datetime(2026, 6, 4, 19, 29, tzinfo=UTC),
    )

    assert draft is not None
    assert draft.spec_kind == "cron"
    assert draft.cron_expr == "0 8 * * *"
    assert draft.timezone == "America/Chicago"
    assert draft.next_run_at == datetime(2026, 6, 5, 13, 0, tzinfo=UTC)
    assert draft.cadence_label == "Every morning at 8:00 AM Central time"
    assert draft.task_input == "send a stock market update."

    response = format_schedule_proposal(
        schedule=None,
        draft=draft,
        delivery_surface="dm",
        needs_confirmation=False,
    )

    assert "I'll send a stock market update every morning at 8:00 AM Central time" in response
    assert "First check is tomorrow at 8:00 AM Central time" in response
    assert "I'll at" not in response


def test_schedule_detector_ignores_plain_work_requests() -> None:
    assert looks_like_schedule_request("summarize this channel") is False
    assert looks_like_schedule_request("Every Friday, summarize this channel") is True
