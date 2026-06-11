"""Seed, inspect, and remove backdated synthetic workspace history.

The seeder writes rows that are indistinguishable from real ones to their
consumers (witness profile scans, episode retrieval, observation queries),
except that every row carries a simulator marker so ``clean`` can remove
exactly what ``seed`` created:

- ``observation_events.visibility_metadata`` contains ``{"sim": true}``;
- the channel profile's ``metadata_json`` contains ``{"sim": true}``;
- synthetic tasks use ``synthetic:sim:{slug}`` identity keys;
- a sim-created channel membership carries ``{"sim_created": true}``.

No Slack messages are posted and no LLM is called at seed time.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Delete, delete, func, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from kortny.db.models import (
    Episode,
    Installation,
    ObservationEvent,
    ObserveChannelProfile,
    SlackChannelMembership,
    Task,
    TaskEvent,
    TaskStatus,
    WitnessOpportunityCandidate,
)
from kortny.memory.episodes import EpisodeService
from kortny.observe.service import ObserveService
from kortny.simulator.fixtures import (
    DEFAULT_SIM_DAYS,
    JEN,
    MARCO,
    PERSONAS,
    PRIYA,
    SIM_EVENT_ID_PREFIX,
    SIM_MARKER_KEY,
    SIM_SOURCE,
    SIM_TASK_IDENTITY_PREFIX,
    SIM_TASK_IDENTITY_SOURCE,
    SimMessage,
    SimPersona,
    build_story,
)
from kortny.tasks import TaskService
from kortny.tasks.identity import TaskIdentity

PROFILE_CONFIDENCE_SCORE = Decimal("0.750")


class SimulatorError(RuntimeError):
    """Raised when the simulator cannot run safely (e.g. no installation)."""


@dataclass(frozen=True, slots=True)
class SimTaskSpec:
    """One synthetic completed task that feeds the task-response extractors."""

    slug: str
    persona: SimPersona
    window_fraction: float
    input: str
    result_summary: str


SIM_TASK_SPECS: tuple[SimTaskSpec, ...] = (
    SimTaskSpec(
        slug="trading-summary-recap",
        persona=PRIYA,
        window_fraction=0.70,
        input=(
            "What did the desk post for yesterday's end-of-day trading "
            "summary? I need the numbers for the morning meeting."
        ),
        result_summary=(
            "Compiled the trading summary numbers the team posts manually "
            "every weekday around 5pm: yesterday closed at +212k PnL across "
            "187 fills with ACME-B as the top book. Priya copies these from "
            "the blotter export by hand each evening."
        ),
    ),
    SimTaskSpec(
        slug="weekly-status-compile",
        persona=JEN,
        window_fraction=0.45,
        input=(
            "Pull together the status updates from this week's Friday thread "
            "so I can paste them into the leadership report."
        ),
        result_summary=(
            "Drafted the weekly status report Jen compiles by hand every "
            "Friday: collected the thread replies (signals backtest at 80%, "
            "rack migration done, telemetry collectors pending) and formatted "
            "them into the usual leadership summary."
        ),
    ),
    SimTaskSpec(
        slug="q2-pipeline-verification",
        persona=MARCO,
        window_fraction=0.20,
        input=(
            "Can you sanity-check the Q2 pipeline numbers doc? Nobody has "
            "double-checked it and finance needs it before Thursday."
        ),
        result_summary=(
            "Cross-checked the Q2 pipeline numbers doc Marco asked the team "
            "to verify before Thursday; flagged two stale rows in the revenue "
            "tab. The doc still needs a final owner sign-off — nobody has "
            "claimed the verification yet."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class SeedReport:
    """Counts and flags from one ``seed`` run."""

    channel_id: str
    days: int
    installation_team_id: str
    observation_events_created: int
    observation_events_existing: int
    distinct_message_days: int
    policy_observable: bool
    membership_created: bool
    membership_active: bool
    profile_created: bool
    profile_version: int
    tasks_created: int
    tasks_existing: int
    episodes_recorded: int


@dataclass(frozen=True, slots=True)
class CleanReport:
    """Row counts removed by one ``clean`` run."""

    candidates_deleted: int
    automated_candidate_notes: tuple[str, ...]
    episodes_deleted: int
    profiles_deleted: int
    task_events_deleted: int
    tasks_deleted: int
    observation_events_deleted: int
    memberships_deleted: int


@dataclass(frozen=True, slots=True)
class StatusReport:
    """Current simulator row counts."""

    observation_events: int
    distinct_message_days: int
    profiles: int
    profile_versions: tuple[int, ...]
    tasks: int
    task_events: int
    episodes: int
    candidates_by_status: dict[str, int] = field(default_factory=dict)
    memberships: int = 0


def seed_simulation(
    session: Session,
    *,
    channel_id: str,
    days: int = DEFAULT_SIM_DAYS,
    now: datetime | None = None,
) -> SeedReport:
    """Inject the backdated fixture story for ``channel_id``.

    Idempotent for a fixed ``now``: observation events dedupe on their
    deterministic ``slack_event_id``, tasks dedupe on their synthetic
    identity keys, and the channel profile is upserted (its version is
    bumped on re-seed so the witness runner treats it as scan-due again).
    """

    channel_id = channel_id.strip()
    if not channel_id:
        raise SimulatorError("A non-empty --channel is required.")
    run_at = (now or datetime.now(UTC)).astimezone(UTC)
    installation = _require_installation(session)
    messages = build_story(now=run_at, days=days)

    membership_created, membership_active = _ensure_membership(
        session,
        installation=installation,
        channel_id=channel_id,
    )
    observe_service = ObserveService(session)
    policy = observe_service.ensure_channel_policy(
        installation=installation,
        channel_id=channel_id,
        enabled_by_user_id=None,
    )
    policy_observable = ObserveService.is_observable(policy)

    created, existing = _seed_observation_events(
        session,
        installation=installation,
        channel_id=channel_id,
        messages=messages,
        policy_id=policy.id,
    )

    tasks, tasks_created, tasks_existing, episodes_recorded = _seed_tasks(
        session,
        installation=installation,
        channel_id=channel_id,
        days=days,
        now=run_at,
    )

    profile, profile_created = _upsert_profile(
        session,
        installation=installation,
        channel_id=channel_id,
        messages=messages,
        days=days,
        now=run_at,
        source_task=tasks[0] if tasks else None,
    )

    session.flush()
    return SeedReport(
        channel_id=channel_id,
        days=days,
        installation_team_id=installation.slack_team_id,
        observation_events_created=created,
        observation_events_existing=existing,
        distinct_message_days=len({message.sent_at.date() for message in messages}),
        policy_observable=policy_observable,
        membership_created=membership_created,
        membership_active=membership_active,
        profile_created=profile_created,
        profile_version=profile.profile_version,
        tasks_created=tasks_created,
        tasks_existing=tasks_existing,
        episodes_recorded=episodes_recorded,
    )


def clean_simulation(session: Session) -> CleanReport:
    """Delete every row ``seed`` created plus derived witness candidates.

    Schedules created by accepting an automated candidate are intentionally
    left in place; they are reported in ``automated_candidate_notes``.
    """

    sim_task_ids = list(
        session.scalars(
            select(Task.id).where(
                Task.identity_key.like(f"{SIM_TASK_IDENTITY_PREFIX}%")
            )
        )
    )
    sim_profile_ids = list(
        session.scalars(
            select(ObserveChannelProfile.id).where(
                ObserveChannelProfile.metadata_json[SIM_MARKER_KEY]
                .as_boolean()
                .is_(True)
            )
        )
    )

    candidates = _linked_candidates(
        session,
        sim_task_ids=sim_task_ids,
        sim_profile_ids=sim_profile_ids,
    )
    automated_notes: list[str] = []
    for candidate in candidates:
        if candidate.status == "automated" or (
            candidate.automated_schedule_id is not None
        ):
            automated_notes.append(
                f"candidate {candidate.id} ({candidate.title!r}) was "
                f"automated; schedule {candidate.automated_schedule_id} "
                "was left in place"
            )
    candidate_ids = [candidate.id for candidate in candidates]
    candidates_deleted = 0
    if candidate_ids:
        candidates_deleted = _delete_rows(
            session,
            delete(WitnessOpportunityCandidate).where(
                WitnessOpportunityCandidate.id.in_(candidate_ids)
            ),
        )

    episodes_deleted = 0
    task_events_deleted = 0
    tasks_deleted = 0
    if sim_task_ids:
        episodes_deleted = _delete_rows(
            session,
            delete(Episode).where(Episode.task_id.in_(sim_task_ids)),
        )

    profiles_deleted = 0
    if sim_profile_ids:
        profiles_deleted = _delete_rows(
            session,
            delete(ObserveChannelProfile).where(
                ObserveChannelProfile.id.in_(sim_profile_ids)
            ),
        )

    if sim_task_ids:
        task_events_deleted = _delete_rows(
            session,
            delete(TaskEvent).where(TaskEvent.task_id.in_(sim_task_ids)),
        )
        tasks_deleted = _delete_rows(
            session,
            delete(Task).where(Task.id.in_(sim_task_ids)),
        )

    observation_events_deleted = _delete_rows(
        session,
        delete(ObservationEvent).where(
            ObservationEvent.visibility_metadata[SIM_MARKER_KEY].as_boolean().is_(True)
        ),
    )
    memberships_deleted = _delete_rows(
        session,
        delete(SlackChannelMembership).where(
            SlackChannelMembership.metadata_json["sim_created"].as_boolean().is_(True)
        ),
    )

    session.flush()
    return CleanReport(
        candidates_deleted=candidates_deleted,
        automated_candidate_notes=tuple(automated_notes),
        episodes_deleted=episodes_deleted,
        profiles_deleted=profiles_deleted,
        task_events_deleted=task_events_deleted,
        tasks_deleted=tasks_deleted,
        observation_events_deleted=observation_events_deleted,
        memberships_deleted=memberships_deleted,
    )


def simulation_status(session: Session) -> StatusReport:
    """Report current simulator row counts without modifying anything."""

    observation_rows = list(
        session.execute(
            select(
                func.count(ObservationEvent.id),
                func.count(func.distinct(func.date(ObservationEvent.observed_at))),
            ).where(
                ObservationEvent.visibility_metadata[SIM_MARKER_KEY]
                .as_boolean()
                .is_(True)
            )
        )
    )[0]
    profile_versions = tuple(
        session.scalars(
            select(ObserveChannelProfile.profile_version).where(
                ObserveChannelProfile.metadata_json[SIM_MARKER_KEY]
                .as_boolean()
                .is_(True)
            )
        )
    )
    sim_task_ids = list(
        session.scalars(
            select(Task.id).where(
                Task.identity_key.like(f"{SIM_TASK_IDENTITY_PREFIX}%")
            )
        )
    )
    sim_profile_ids = list(
        session.scalars(
            select(ObserveChannelProfile.id).where(
                ObserveChannelProfile.metadata_json[SIM_MARKER_KEY]
                .as_boolean()
                .is_(True)
            )
        )
    )
    task_events = 0
    episodes = 0
    if sim_task_ids:
        task_events = int(
            session.scalar(
                select(func.count(TaskEvent.id)).where(
                    TaskEvent.task_id.in_(sim_task_ids)
                )
            )
            or 0
        )
        episodes = int(
            session.scalar(
                select(func.count(Episode.id)).where(Episode.task_id.in_(sim_task_ids))
            )
            or 0
        )
    candidates_by_status: dict[str, int] = {}
    for candidate in _linked_candidates(
        session,
        sim_task_ids=sim_task_ids,
        sim_profile_ids=sim_profile_ids,
    ):
        candidates_by_status[candidate.status] = (
            candidates_by_status.get(candidate.status, 0) + 1
        )
    memberships = int(
        session.scalar(
            select(func.count(SlackChannelMembership.id)).where(
                SlackChannelMembership.metadata_json["sim_created"]
                .as_boolean()
                .is_(True)
            )
        )
        or 0
    )
    return StatusReport(
        observation_events=int(observation_rows[0] or 0),
        distinct_message_days=int(observation_rows[1] or 0),
        profiles=len(profile_versions),
        profile_versions=profile_versions,
        tasks=len(sim_task_ids),
        task_events=task_events,
        episodes=episodes,
        candidates_by_status=candidates_by_status,
        memberships=memberships,
    )


def _require_installation(session: Session) -> Installation:
    installation = session.scalar(
        select(Installation).order_by(Installation.created_at).limit(1)
    )
    if installation is None:
        raise SimulatorError(
            "No installation found; the simulator needs an installed "
            "workspace to attach history to. Run the Slack app once first."
        )
    return installation


def _ensure_membership(
    session: Session,
    *,
    installation: Installation,
    channel_id: str,
) -> tuple[bool, bool]:
    membership = session.scalar(
        select(SlackChannelMembership).where(
            SlackChannelMembership.installation_id == installation.id,
            SlackChannelMembership.channel_id == channel_id,
        )
    )
    if membership is not None:
        return False, membership.membership_status == "active"
    membership = SlackChannelMembership(
        installation_id=installation.id,
        channel_id=channel_id,
        channel_name=None,
        channel_type="public_channel",
        membership_status="active",
        discovered_via="manual_backfill",
        added_by_user_id=None,
        onboarding_status="skipped",
        metadata_json={"sim_created": True, "source": SIM_SOURCE},
    )
    session.add(membership)
    session.flush()
    return True, True


def _seed_observation_events(
    session: Session,
    *,
    installation: Installation,
    channel_id: str,
    messages: tuple[SimMessage, ...],
    policy_id: uuid.UUID | None,
) -> tuple[int, int]:
    event_ids = {
        f"{SIM_EVENT_ID_PREFIX}{channel_id}:{message.slug}": message
        for message in messages
    }
    existing_ids = set(
        session.scalars(
            select(ObservationEvent.slack_event_id).where(
                ObservationEvent.installation_id == installation.id,
                ObservationEvent.slack_event_id.in_(list(event_ids)),
            )
        )
    )
    ts_by_slug = {message.slug: message.message_ts for message in messages}
    created = 0
    for event_id, message in event_ids.items():
        if event_id in existing_ids:
            continue
        thread_ts = (
            ts_by_slug.get(message.thread_slug)
            if message.thread_slug is not None
            else None
        )
        sim_file_id: str | None = None
        if message.files:
            raw_file_id = message.files[0].get("id")
            if isinstance(raw_file_id, str):
                sim_file_id = raw_file_id
        visibility_metadata: dict[str, Any] = {
            "scope_type": "channel",
            "scope_id": channel_id,
            "channel_type": "channel",
            "subtype": None,
            "file_count": len(message.files),
            "policy_id": str(policy_id) if policy_id else None,
            SIM_MARKER_KEY: True,
            "sim_source": SIM_SOURCE,
            "sim_pattern": message.pattern,
            "persona_display_name": message.persona.display_name,
            "persona_role": message.persona.role,
        }
        if message.files:
            visibility_metadata["files"] = [dict(entry) for entry in message.files]
        session.add(
            ObservationEvent(
                installation_id=installation.id,
                slack_team_id=installation.slack_team_id,
                channel_id=channel_id,
                user_id=message.persona.user_id,
                event_type="file_share" if message.files else "message",
                slack_event_id=event_id,
                message_ts=message.message_ts,
                thread_ts=thread_ts,
                file_id=sim_file_id,
                raw_payload_checksum=_checksum(
                    {
                        "source": SIM_SOURCE,
                        "slug": message.slug,
                        "channel": channel_id,
                        "text": message.text,
                    }
                ),
                text_preview=message.text,
                visibility_metadata=visibility_metadata,
                observed_at=message.sent_at,
                created_at=message.sent_at,
            )
        )
        created += 1
    session.flush()
    return created, len(existing_ids)


def _seed_tasks(
    session: Session,
    *,
    installation: Installation,
    channel_id: str,
    days: int,
    now: datetime,
) -> tuple[list[Task], int, int, int]:
    task_service = TaskService(session)
    episode_service = EpisodeService(session, task_service=task_service)
    tasks: list[Task] = []
    tasks_created = 0
    tasks_existing = 0
    episodes_recorded = 0
    for spec in SIM_TASK_SPECS:
        identity = TaskIdentity.synthetic(
            source=SIM_TASK_IDENTITY_SOURCE,
            source_id=spec.slug,
            input_text=spec.input,
            payload={SIM_MARKER_KEY: True, "channel_id": channel_id},
        )
        existing = task_service.get_by_identity_key(installation.id, identity.key)
        if existing is not None:
            tasks.append(existing)
            tasks_existing += 1
            continue

        task_time = now - timedelta(days=days * spec.window_fraction)
        message_ts = f"{task_time.timestamp():.6f}"
        task = task_service.create_task(
            installation_id=installation.id,
            slack_event_id=f"{SIM_EVENT_ID_PREFIX}task:{spec.slug}",
            slack_channel_id=channel_id,
            slack_thread_ts=message_ts,
            slack_message_ts=message_ts,
            slack_user_id=spec.persona.user_id,
            input=spec.input,
            identity=identity,
            source_surface=SIM_SOURCE,
        )
        task_service.transition(task, TaskStatus.running)
        task.result_summary = spec.result_summary
        task_service.transition(task, TaskStatus.succeeded)
        if episode_service.record_task(task) is not None:
            episodes_recorded += 1
        _backdate_task(session, task, task_time=task_time)
        tasks.append(task)
        tasks_created += 1
    session.flush()
    return tasks, tasks_created, tasks_existing, episodes_recorded


def _backdate_task(session: Session, task: Task, *, task_time: datetime) -> None:
    finished_at = task_time + timedelta(minutes=3)
    task.created_at = task_time
    task.started_at = task_time + timedelta(minutes=1)
    task.finished_at = finished_at
    task.updated_at = finished_at
    events = session.scalars(
        select(TaskEvent).where(TaskEvent.task_id == task.id).order_by(TaskEvent.seq)
    )
    for event in events:
        event.created_at = task_time + timedelta(seconds=30 * event.seq)
    episode = session.scalar(select(Episode).where(Episode.task_id == task.id))
    if episode is not None:
        episode.created_at = finished_at
        episode.updated_at = finished_at
    session.flush()


def _upsert_profile(
    session: Session,
    *,
    installation: Installation,
    channel_id: str,
    messages: tuple[SimMessage, ...],
    days: int,
    now: datetime,
    source_task: Task | None,
) -> tuple[ObserveChannelProfile, bool]:
    range_start_ts = messages[0].message_ts if messages else None
    range_end_ts = messages[-1].message_ts if messages else None
    summary = _profile_summary(channel_id)
    semantic_extraction = _semantic_extraction()

    profile = session.scalar(
        select(ObserveChannelProfile).where(
            ObserveChannelProfile.installation_id == installation.id,
            ObserveChannelProfile.channel_id == channel_id,
        )
    )
    created = profile is None
    if profile is None:
        profile = ObserveChannelProfile(
            installation_id=installation.id,
            channel_id=channel_id,
            profile_status="active",
            profile_version=1,
            created_at=now,
        )
        session.add(profile)
    else:
        # Bumping the version makes the witness runner treat the profile as
        # scan-due even if it recorded a scan of the previous version.
        profile.profile_version += 1

    profile.profile_status = "active"
    profile.summary = summary
    profile.profile_json = {
        "kind": "slack_channel_profile",
        "source": SIM_SOURCE,
        "summary": summary,
        "fresh_context": {
            "window_days": 30,
            "use_for": "current working context and recent channel patterns",
        },
        "archive_context": {
            "window_days": 365,
            "use_for": "older files, recurring workflows, and resurfacing lost context",
        },
        "observed": {
            "channel_id": channel_id,
            "message_count": len(messages),
            "file_count": 0,
            "range_start_ts": range_start_ts,
            "range_end_ts": range_end_ts,
            "last_scanned_message_ts": range_end_ts,
        },
        "semantic_extraction": semantic_extraction,
    }
    profile.assumptions_json = [
        {
            "type": "channel_assumption",
            "text": assumption,
            "confidence": "high",
            "source": "semantic_extraction",
            "staleness": "fresh_profile_seed",
        }
        for assumption in semantic_extraction["assumptions"]
    ]
    profile.evidence_refs_json = [
        {
            "type": "simulator",
            SIM_MARKER_KEY: True,
            "note": "Seeded by the workspace simulator (synthetic history).",
            "message_count": len(messages),
            "observed_range_start_ts": range_start_ts,
            "observed_range_end_ts": range_end_ts,
        }
    ]
    profile.confidence_score = PROFILE_CONFIDENCE_SCORE
    profile.confidence_reason = (
        "Profile distilled from a full multi-week channel history sample."
    )
    profile.fresh_window_days = 30
    profile.archive_window_days = 365
    profile.observed_range_start_ts = range_start_ts
    profile.observed_range_end_ts = range_end_ts
    profile.message_count = len(messages)
    profile.file_count = 0
    profile.last_scanned_message_ts = range_end_ts
    profile.last_profiled_at = now
    profile.source_task_id = source_task.id if source_task is not None else None
    # No "witness_runner" key here on purpose: its absence makes the witness
    # runner consider the profile scan-due on its next tick.
    profile.metadata_json = {
        SIM_MARKER_KEY: True,
        "source": SIM_SOURCE,
        "channel_id": channel_id,
        "seeded_at": now.isoformat(),
        "window_days": days,
        "personas": [
            {"user_id": persona.user_id, "display_name": persona.display_name}
            for persona in PERSONAS
        ],
        "semantic_extraction": semantic_extraction,
    }
    profile.updated_at = now
    session.flush()
    return profile, created


def _profile_summary(channel_id: str) -> str:
    return (
        f"Channel {channel_id} is Acme Robotics' trading-operations channel. "
        "Priya posts a hand-compiled end-of-day trading summary every weekday "
        "around 17:00. Jen collects status updates in a thread every Friday "
        "morning and pastes a manually compiled weekly report around noon. "
        "Marco asked for someone to double-check the Q2 pipeline numbers doc "
        "before Thursday and nobody picked it up. A fleet telemetry vendor "
        "decision between TelemetryHub and GridWatch was debated and trailed "
        "off without an owner. The rest is greetings, memes, and ops chatter."
    )


def _semantic_extraction() -> dict[str, Any]:
    return {
        "likely_purpose": (
            "Trading operations coordination: daily numbers, weekly status, "
            "and infrastructure decisions for Acme Robotics."
        ),
        "recurring_topics": [
            "end-of-day trading summary",
            "weekly status report",
            "Q2 pipeline numbers doc",
            "fleet telemetry vendor decision",
        ],
        "workflows": [
            "Priya hand-compiles an EOD trading summary from the blotter "
            "every weekday at about 17:00.",
            "Jen asks for thread updates every Friday at 10:00 and pastes a "
            "hand-compiled weekly status report around 12:00.",
        ],
        "important_entities": [
            "Priya Raman (trading operations lead)",
            "Jen Park (program manager)",
            "Marco Diaz (quant developer)",
            "Sam Okafor (infrastructure engineer)",
            "TelemetryHub",
            "GridWatch",
        ],
        "assumptions": [
            "The daily trading summary is compiled manually and could be "
            "automated on a weekday 5pm cadence.",
            "The Friday status report is compiled by hand from thread "
            "replies every week.",
            "The Q2 pipeline numbers doc still needs a one-time verification "
            "before Thursday.",
            "The fleet telemetry vendor decision (TelemetryHub vs GridWatch) "
            "is unresolved and has no owner.",
        ],
        "help_opportunities": [
            "Post the end-of-day trading summary automatically every weekday at 5pm.",
            "Compile the Friday status report from the thread replies.",
            "Verify the Q2 pipeline numbers doc once before Thursday.",
            "Track the open TelemetryHub vs GridWatch vendor decision.",
        ],
        "evidence": [
            "EOD trading summary posts appear every weekday at 17:00.",
            "Friday threads collect updates that are pasted into a manual "
            "weekly report.",
            "'Someone needs to double-check the Q2 pipeline numbers doc "
            "before Thursday' was never resolved.",
            "'Let's revisit next week' ended the vendor decision thread.",
        ],
        "confidence": "high",
    }


def _linked_candidates(
    session: Session,
    *,
    sim_task_ids: list[uuid.UUID],
    sim_profile_ids: list[uuid.UUID],
) -> tuple[WitnessOpportunityCandidate, ...]:
    conditions: list[ColumnElement[bool]] = []
    if sim_task_ids:
        conditions.append(WitnessOpportunityCandidate.source_task_id.in_(sim_task_ids))
    if sim_profile_ids:
        conditions.append(
            WitnessOpportunityCandidate.source_profile_id.in_(sim_profile_ids)
        )
        conditions.append(
            WitnessOpportunityCandidate.source_id.in_(
                [str(profile_id) for profile_id in sim_profile_ids]
            )
        )
    # Candidate evidence copies profile evidence refs verbatim, so candidates
    # derived from the sim profile carry the marker even after FKs are nulled.
    conditions.append(
        WitnessOpportunityCandidate.evidence_json.contains([{SIM_MARKER_KEY: True}])
    )
    return tuple(
        session.scalars(select(WitnessOpportunityCandidate).where(or_(*conditions)))
    )


def _delete_rows(session: Session, statement: Delete) -> int:
    result = session.execute(statement)
    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)
    return 0


def _checksum(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
