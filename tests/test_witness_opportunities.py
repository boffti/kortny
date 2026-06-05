import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    Installation,
    ObserveChannelProfile,
    SlackChannelMembership,
    Task,
    TaskEvent,
    WitnessOpportunityCandidate,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.tasks import TaskService
from kortny.witness import WitnessOpportunityService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for witness opportunity tests",
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    assert TEST_POSTGRES_URL is not None

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", normalize_database_url(TEST_POSTGRES_URL))
    command.upgrade(config, "head")

    engine = make_engine(TEST_POSTGRES_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        cleanup_database(session)
        session.commit()
        yield session
        session.rollback()
        cleanup_database(session)
        session.commit()


def test_project_from_channel_profile_creates_and_dedupes_candidates(
    db_session: Session,
) -> None:
    task, membership, profile = create_profile_fixture(db_session)
    service = WitnessOpportunityService(db_session)

    result = service.project_from_channel_profile(
        task=task,
        membership=membership,
        profile=profile,
    )
    db_session.commit()

    candidates = tuple(
        db_session.scalars(
            select(WitnessOpportunityCandidate).order_by(
                WitnessOpportunityCandidate.candidate_type,
                WitnessOpportunityCandidate.title,
            )
        )
    )
    assert result.created_count == 2
    assert result.updated_count == 0
    assert result.skipped_count == 0
    assert len(result.candidate_ids) == 2
    assert {candidate.candidate_type for candidate in candidates} == {
        "data_quality_issue",
        "recurring_check",
    }
    assert all(candidate.status == "candidate" for candidate in candidates)
    assert all(candidate.visibility_scope_type == "channel" for candidate in candidates)
    assert all(candidate.visibility_scope_id == "CWitness" for candidate in candidates)
    assert all(candidate.source_profile_id == profile.id for candidate in candidates)
    assert all(candidate.confidence_score >= Decimal("0.650") for candidate in candidates)
    assert any(
        item.get("type") == "semantic_evidence"
        for candidate in candidates
        for item in candidate.evidence_json
    )

    profile.profile_version = 2
    profile.summary = "Updated profile still sees the same daily blotter workflow."
    db_session.flush()

    second = service.project_from_channel_profile(
        task=task,
        membership=membership,
        profile=profile,
    )
    db_session.commit()

    assert second.created_count == 0
    assert second.updated_count == 2
    assert (
        db_session.scalar(select(func.count()).select_from(WitnessOpportunityCandidate))
        == 2
    )
    refreshed = tuple(db_session.scalars(select(WitnessOpportunityCandidate)))
    assert all(
        candidate.metadata_json["profile_version"] == 2 for candidate in refreshed
    )
    assert all("last_reinforced_at" in candidate.metadata_json for candidate in refreshed)


def test_eligible_private_suggestions_respects_status_and_cooldown(
    db_session: Session,
) -> None:
    task, membership, profile = create_profile_fixture(db_session)
    service = WitnessOpportunityService(db_session)
    service.project_from_channel_profile(
        task=task,
        membership=membership,
        profile=profile,
    )
    candidates = tuple(db_session.scalars(select(WitnessOpportunityCandidate)))
    assert len(candidates) == 2
    now = datetime.now(UTC)
    candidates[0].cooldown_until = now + timedelta(hours=2)
    candidates[1].status = "dismissed"
    db_session.commit()

    eligible = service.eligible_private_suggestions(
        installation_id=task.installation_id,
        now=now,
    )

    assert eligible == ()

    candidates[0].cooldown_until = now - timedelta(minutes=5)
    candidates[1].status = "candidate"
    db_session.commit()

    eligible_after_cooldown = service.eligible_private_suggestions(
        installation_id=task.installation_id,
        now=now,
    )
    assert {candidate.id for candidate in eligible_after_cooldown} == {
        candidate.id for candidate in candidates
    }


def cleanup_database(session: Session) -> None:
    for model in (
        WitnessOpportunityCandidate,
        ObserveChannelProfile,
        SlackChannelMembership,
        TaskEvent,
        Task,
        Installation,
    ):
        session.execute(delete(model))


def create_profile_fixture(
    session: Session,
) -> tuple[Task, SlackChannelMembership, ObserveChannelProfile]:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    membership = SlackChannelMembership(
        installation_id=installation.id,
        channel_id="CWitness",
        channel_name="daily-blotter",
        channel_type="public_channel",
        membership_status="active",
        discovered_via="member_joined_channel",
        added_by_user_id="UInvite",
        onboarding_status="posted",
        onboarding_message_ts="1780000000.000000",
        metadata_json={},
    )
    session.add(membership)
    session.flush()
    task = TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id=membership.channel_id,
        slack_thread_ts="1780000000.000000",
        slack_message_ts="1780000000.000000",
        slack_user_id="UInvite",
        input="Run channel assessment.",
    )
    profile = ObserveChannelProfile(
        installation_id=installation.id,
        channel_id=membership.channel_id,
        profile_status="active",
        profile_version=1,
        summary="Daily blotter review and exception checks.",
        profile_json={
            "semantic_extraction": {
                "likely_purpose": "Daily trade blotter review.",
                "recurring_topics": ["daily blotter"],
                "workflows": ["Review daily blotter files before PM meeting"],
                "important_entities": ["n8n", "blotter.csv"],
                "assumptions": ["The channel is operational and report-driven."],
                "help_opportunities": [
                    "Summarize daily blotter changes",
                    "Flag missing CSV placeholders and failed file formatting",
                ],
                "evidence": [
                    "Morning blotter uploaded.",
                    "Need a review on ticker changes.",
                ],
                "confidence": "medium",
            }
        },
        assumptions_json=[],
        evidence_refs_json=[
            {
                "type": "tool_result",
                "tool": "slack_channel_history",
                "message_count": 12,
            }
        ],
        confidence_score=Decimal("0.650"),
        confidence_reason="Assessment had enough recent messages.",
        fresh_window_days=30,
        archive_window_days=365,
        observed_range_start_ts="1779900000.000001",
        observed_range_end_ts="1779900200.000003",
        message_count=12,
        file_count=2,
        last_scanned_message_ts="1779900200.000003",
        last_profiled_at=datetime.now(UTC),
        source_task_id=task.id,
        metadata_json={"synthesis": "semantic_llm"},
    )
    session.add(profile)
    session.flush()
    return task, membership, profile
