"""Durable task claiming and lease recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import Task, TaskEventType, TaskStatus
from kortny.tasks import TaskRepository

DEFAULT_LEASE_SECONDS = 300
DEFAULT_RECLAIM_LIMIT = 100


class TaskQueue:
    """Queue operations over the `tasks` table."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.tasks = TaskRepository(session)

    def claim_next(
        self,
        *,
        worker_id: str,
        lease_for: timedelta = timedelta(seconds=DEFAULT_LEASE_SECONDS),
        now: datetime | None = None,
    ) -> Task | None:
        """Claim the next available pending task with `FOR UPDATE SKIP LOCKED`."""

        claim_time = _coerce_utc(now)
        task = self.session.scalar(
            select(Task)
            .where(
                Task.status == TaskStatus.pending,
                Task.available_at <= claim_time,
            )
            .order_by(Task.available_at, Task.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None

        previous_status = TaskStatus(task.status).value
        task.status = TaskStatus.running
        task.locked_by = worker_id
        task.locked_at = claim_time
        task.lease_expires_at = claim_time + lease_for
        task.updated_at = claim_time
        if task.started_at is None:
            task.started_at = claim_time

        self.session.flush()
        self.tasks.append_event(
            task,
            TaskEventType.status_changed,
            {
                "from": previous_status,
                "to": TaskStatus.running.value,
                "worker_id": worker_id,
                "lease_expires_at": task.lease_expires_at.isoformat(),
            },
        )
        return task

    def reclaim_expired_leases(
        self,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_RECLAIM_LIMIT,
    ) -> list[Task]:
        """Requeue or fail running tasks whose lease has expired."""

        reclaim_time = _coerce_utc(now)
        expired_tasks = list(
            self.session.scalars(
                select(Task)
                .where(
                    Task.status == TaskStatus.running,
                    Task.lease_expires_at.is_not(None),
                    Task.lease_expires_at <= reclaim_time,
                )
                .order_by(Task.lease_expires_at, Task.created_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )

        for task in expired_tasks:
            self._reclaim_task(task, reclaim_time)

        return expired_tasks

    def _reclaim_task(self, task: Task, reclaim_time: datetime) -> None:
        crashed_payload = {
            "from": TaskStatus.running.value,
            "to": TaskStatus.crashed.value,
            "reason": "lease_expired",
            "locked_by": task.locked_by,
            "lease_expires_at": _isoformat_optional(task.lease_expires_at),
        }

        task.status = TaskStatus.crashed
        task.updated_at = reclaim_time
        self.session.flush()
        self.tasks.append_event(task, TaskEventType.status_changed, crashed_payload)

        next_attempts = task.attempts + 1
        task.attempts = next_attempts
        task.locked_by = None
        task.locked_at = None
        task.lease_expires_at = None
        task.updated_at = reclaim_time

        if next_attempts >= task.max_attempts:
            task.status = TaskStatus.failed
            task.finished_at = reclaim_time
            task.error = {
                "reason": "lease_expired",
                "attempts": next_attempts,
                "max_attempts": task.max_attempts,
            }
        else:
            task.status = TaskStatus.pending
            task.available_at = reclaim_time
            task.error = None

        self.session.flush()
        self.tasks.append_event(
            task,
            TaskEventType.status_changed,
            {
                "from": TaskStatus.crashed.value,
                "to": TaskStatus(task.status).value,
                "reason": "lease_expired",
                "attempts": next_attempts,
                "max_attempts": task.max_attempts,
            },
        )


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _isoformat_optional(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _coerce_utc(value).isoformat()
