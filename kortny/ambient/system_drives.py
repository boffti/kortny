"""System drives: ambient loops surfaced as user-visible Schedule rows (HIG-233).

Viktor's entire proactivity layer presents as two visible "System" scheduled
tasks (cadence, last-run, pause). Kortny has superior ambient machinery (the
witness scan loop, the consolidator, the Composio catalog sync) but it lived as
invisible env-var infrastructure. This module surfaces each ambient drive as a
first-class ``Schedule`` row so the dashboard and the ``list_schedules`` Slack
tool can show every drive with a plain-language purpose, cadence, last-run, and
a pause/resume control.

Representation (no migration)
-----------------------------
A drive reuses the existing ``Schedule`` model:

* ``owner_type="system"`` and ``owner_slack_user_id=None`` (the model already
  permits this combination).
* ``metadata_json["system_drive"]`` carries the deterministic ``key``, the
  plain-language ``purpose`` line, and the env-default cadence — this is the
  identity *and* the transparency copy.
* ``spec_kind="interval"`` + ``interval_seconds`` express the cadence the
  dashboard / Slack render; an operator override of ``interval_seconds`` (via
  pause/resume or future edit) is the cadence override the loop honors.
* ``next_run_at`` is always ``None`` — the scheduler materializer never turns a
  drive into a task (it requires ``next_run_at IS NOT NULL``); execution stays
  in the ambient loops. A defensive metadata filter in the materializer makes
  this explicit even if the cadence representation changed.
* ``last_run_at`` is the last-productive-tick timestamp the loop stamps.
* ``status`` is ``active``/``paused`` — pause skips the loop's work that tick.

Identity is deterministic per installation: ``(installation_id,
system_drive_key)``. Seeding is idempotent — a drive that already exists is
left untouched (its operator-set status / cadence override / last-run survive a
re-boot).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from kortny.config import Settings
from kortny.db.models import Installation, Schedule

logger = logging.getLogger(__name__)

SYSTEM_DRIVE_METADATA_KEY = "system_drive"

WITNESS_SCAN_DRIVE_KEY = "witness_scan"
MEMORY_CONSOLIDATION_DRIVE_KEY = "memory_consolidation"
INTEGRATION_CATALOG_SYNC_DRIVE_KEY = "integration_catalog_sync"


@dataclass(frozen=True, slots=True)
class SystemDriveDefinition:
    """A static definition of one ambient drive surfaced as a Schedule row."""

    key: str
    title: str
    purpose: str

    def default_interval_seconds(self, settings: Settings) -> int:
        """Env-default cadence (seconds) used to seed the visible cadence."""

        if self.key == WITNESS_SCAN_DRIVE_KEY:
            return int(settings.witness_scan_interval_seconds)
        if self.key == MEMORY_CONSOLIDATION_DRIVE_KEY:
            return int(settings.consolidator_nightly_floor_hours * 3600)
        if self.key == INTEGRATION_CATALOG_SYNC_DRIVE_KEY:
            return int(settings.composio_sync_interval_hours * 3600)
        raise ValueError(f"unknown system drive key {self.key!r}")


SYSTEM_DRIVE_DEFINITIONS: tuple[SystemDriveDefinition, ...] = (
    SystemDriveDefinition(
        key=WITNESS_SCAN_DRIVE_KEY,
        title="Witness scan",
        purpose=(
            "Looks for ways to help: recurring suggestions drawn from channel activity."
        ),
    ),
    SystemDriveDefinition(
        key=MEMORY_CONSOLIDATION_DRIVE_KEY,
        title="Memory consolidation",
        purpose=("Promotes what Kortny learned into durable workspace knowledge."),
    ),
    SystemDriveDefinition(
        key=INTEGRATION_CATALOG_SYNC_DRIVE_KEY,
        title="Integration catalog sync",
        purpose="Keeps the tool catalog fresh for connected integrations.",
    ),
)

_DEFINITIONS_BY_KEY: dict[str, SystemDriveDefinition] = {
    definition.key: definition for definition in SYSTEM_DRIVE_DEFINITIONS
}


@dataclass(frozen=True, slots=True)
class SystemDriveState:
    """Resolved control state for one drive, read cheaply at tick time."""

    key: str
    found: bool
    paused: bool
    interval_seconds: int | None

    @property
    def should_run(self) -> bool:
        """True when the loop should do its work this tick.

        A missing row means the drive was never seeded (e.g. ambient booted
        before any installation existed): fall back to current env-var
        behavior, so the loop runs.
        """

        return not self.paused


def is_system_drive(schedule: Schedule) -> bool:
    """True when a ``Schedule`` row is an ambient system drive."""

    metadata = (
        schedule.metadata_json if isinstance(schedule.metadata_json, dict) else {}
    )
    drive = metadata.get(SYSTEM_DRIVE_METADATA_KEY)
    return isinstance(drive, dict) and bool(drive.get("key"))


def system_drive_key(schedule: Schedule) -> str | None:
    """Return the drive key for a system drive row, or ``None``."""

    metadata = (
        schedule.metadata_json if isinstance(schedule.metadata_json, dict) else {}
    )
    drive = metadata.get(SYSTEM_DRIVE_METADATA_KEY)
    if isinstance(drive, dict):
        key = drive.get("key")
        if isinstance(key, str) and key:
            return key
    return None


def system_drive_purpose(schedule: Schedule) -> str | None:
    """Return the plain-language purpose line for a system drive row."""

    metadata = (
        schedule.metadata_json if isinstance(schedule.metadata_json, dict) else {}
    )
    drive = metadata.get(SYSTEM_DRIVE_METADATA_KEY)
    if isinstance(drive, dict):
        purpose = drive.get("purpose")
        if isinstance(purpose, str) and purpose.strip():
            return purpose.strip()
    key = system_drive_key(schedule)
    definition = _DEFINITIONS_BY_KEY.get(key or "")
    return definition.purpose if definition is not None else None


def seed_system_drives(
    session: Session,
    *,
    installation_id: uuid.UUID,
    settings: Settings,
    now: datetime | None = None,
) -> tuple[Schedule, ...]:
    """Idempotently ensure all system drive rows exist for an installation.

    Returns the full set of drive rows (created or pre-existing). A drive that
    already exists is left untouched — its operator-set status, cadence
    override, and last-run survive re-boots, so double boot creates no dupes.
    """

    created_at = _coerce_utc(now)
    existing = _existing_drives_by_key(session, installation_id=installation_id)
    drives: list[Schedule] = []
    for definition in SYSTEM_DRIVE_DEFINITIONS:
        current = existing.get(definition.key)
        if current is not None:
            drives.append(current)
            continue
        interval_seconds = definition.default_interval_seconds(settings)
        schedule = Schedule(
            installation_id=installation_id,
            owner_type="system",
            owner_slack_user_id=None,
            title=definition.title,
            spec_kind="interval",
            interval_seconds=max(interval_seconds, 1),
            next_run_at=None,
            last_run_at=None,
            status="active",
            delivery_kind="dashboard_only",
            task_template={},
            metadata_json={
                SYSTEM_DRIVE_METADATA_KEY: {
                    "key": definition.key,
                    "purpose": definition.purpose,
                    "env_default_interval_seconds": interval_seconds,
                },
                "cadence_label": _cadence_label(interval_seconds),
            },
            created_by_slack_user_id=None,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(schedule)
        drives.append(schedule)
    session.flush()
    return tuple(drives)


def seed_system_drives_for_all_installations(
    session_factory: sessionmaker[Session],
    *,
    settings: Settings,
    now: datetime | None = None,
) -> int:
    """Seed system drives for every installation. Returns rows ensured.

    Idempotent and safe to call at every ambient boot.
    """

    with session_factory.begin() as session:
        installation_ids = list(session.scalars(select(Installation.id)))
        ensured = 0
        for installation_id in installation_ids:
            ensured += len(
                seed_system_drives(
                    session,
                    installation_id=installation_id,
                    settings=settings,
                    now=now,
                )
            )
    return ensured


def resolve_drive_state(
    session: Session,
    *,
    installation_id: uuid.UUID,
    key: str,
) -> SystemDriveState:
    """Cheap tick-time read of one drive's control state.

    A missing row (drive not seeded yet) returns ``found=False`` /
    ``paused=False`` so the loop keeps its current env-var behavior.
    """

    schedule = _drive_for_key(session, installation_id=installation_id, key=key)
    if schedule is None:
        return SystemDriveState(
            key=key, found=False, paused=False, interval_seconds=None
        )
    return SystemDriveState(
        key=key,
        found=True,
        paused=schedule.status == "paused",
        interval_seconds=schedule.interval_seconds,
    )


def mark_drive_ran(
    session: Session,
    *,
    installation_id: uuid.UUID,
    key: str,
    now: datetime | None = None,
) -> bool:
    """Stamp a drive's last-run after a productive tick. Returns True if found."""

    schedule = _drive_for_key(session, installation_id=installation_id, key=key)
    if schedule is None:
        return False
    ran_at = _coerce_utc(now)
    schedule.last_run_at = ran_at
    schedule.updated_at = ran_at
    session.flush()
    return True


def _existing_drives_by_key(
    session: Session,
    *,
    installation_id: uuid.UUID,
) -> dict[str, Schedule]:
    rows = session.scalars(
        select(Schedule).where(
            Schedule.installation_id == installation_id,
            Schedule.owner_type == "system",
        )
    )
    found: dict[str, Schedule] = {}
    for schedule in rows:
        key = system_drive_key(schedule)
        if key is not None and key not in found:
            found[key] = schedule
    return found


def _drive_for_key(
    session: Session,
    *,
    installation_id: uuid.UUID,
    key: str,
) -> Schedule | None:
    return _existing_drives_by_key(session, installation_id=installation_id).get(key)


def all_drive_keys() -> Sequence[str]:
    return tuple(definition.key for definition in SYSTEM_DRIVE_DEFINITIONS)


@dataclass(frozen=True, slots=True)
class DriveTickDecision:
    """Per-tick gate decision a loop reads before doing its work."""

    found: bool
    paused: bool
    interval_seconds: int | None

    @property
    def should_run(self) -> bool:
        # Missing row (never seeded) keeps current env-var behavior: run.
        return not self.paused


class SystemDriveGate:
    """Tick-time control surface a ``run_forever`` loop consults for its drive.

    The workers process every installation per tick, so the gate aggregates the
    drive rows across installations: the tick is paused only when *every*
    installation's drive is paused (no installations / no rows => not paused, so
    env-var behavior is preserved). The smallest interval override across the
    rows drives the loop's sleep for that iteration. Pause/resume transitions
    are logged once per transition, never per tick.
    """

    def __init__(
        self,
        *,
        key: str,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.key = key
        self.session_factory = session_factory
        self._last_paused: bool | None = None

    def before_tick(self) -> DriveTickDecision:
        with self.session_factory.begin() as session:
            states = _drive_states_for_all_installations(session, key=self.key)
        found_states = [state for state in states if state.found]
        if not found_states:
            decision = DriveTickDecision(
                found=False, paused=False, interval_seconds=None
            )
        else:
            paused = all(state.paused for state in found_states)
            intervals = [
                state.interval_seconds
                for state in found_states
                if state.interval_seconds is not None
            ]
            decision = DriveTickDecision(
                found=True,
                paused=paused,
                interval_seconds=min(intervals) if intervals else None,
            )
        self._log_transition(decision.paused)
        return decision

    def mark_ran_all(self, *, now: datetime | None = None) -> None:
        """Stamp last-run on every installation's drive after a productive tick."""

        with self.session_factory.begin() as session:
            installation_ids = list(session.scalars(select(Installation.id)))
            for installation_id in installation_ids:
                mark_drive_ran(
                    session,
                    installation_id=installation_id,
                    key=self.key,
                    now=now,
                )

    def _log_transition(self, paused: bool) -> None:
        if self._last_paused is None:
            if paused:
                logger.info("system drive %r is paused; skipping work", self.key)
        elif paused != self._last_paused:
            if paused:
                logger.info("system drive %r paused; skipping work", self.key)
            else:
                logger.info("system drive %r resumed; running work", self.key)
        self._last_paused = paused


def _drive_states_for_all_installations(
    session: Session,
    *,
    key: str,
) -> tuple[SystemDriveState, ...]:
    installation_ids = list(session.scalars(select(Installation.id)))
    return tuple(
        resolve_drive_state(session, installation_id=installation_id, key=key)
        for installation_id in installation_ids
    )


def _cadence_label(interval_seconds: int) -> str:
    seconds = max(int(interval_seconds), 1)
    if seconds % 86400 == 0:
        days = seconds // 86400
        return "Every day" if days == 1 else f"Every {days} days"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return "Hourly" if hours == 1 else f"Every {hours} hours"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return "Every minute" if minutes == 1 else f"Every {minutes} minutes"
    return f"Every {seconds} seconds"


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
