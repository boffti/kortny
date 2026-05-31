"""Durable task claiming and lease recovery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import Task, TaskEventType, TaskStatus
from kortny.tasks import TaskRepository

DEFAULT_LEASE_SECONDS = 300
DEFAULT_RECLAIM_LIMIT = 100
DEFAULT_RETRY_BACKOFF_SECONDS = 30
DEFAULT_MAX_RETRY_BACKOFF_SECONDS = 300


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

    def renew_lease(
        self,
        *,
        task_id: uuid.UUID,
        worker_id: str,
        lease_for: timedelta = timedelta(seconds=DEFAULT_LEASE_SECONDS),
        now: datetime | None = None,
    ) -> Task | None:
        """Extend a running task lease when the same worker still owns it."""

        if lease_for.total_seconds() <= 0:
            raise ValueError("lease_for must be positive")

        renewal_time = _coerce_utc(now)
        task = self.session.scalar(
            select(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.running,
                Task.locked_by == worker_id,
                Task.lease_expires_at.is_not(None),
                Task.lease_expires_at > renewal_time,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if task is None:
            return None

        task.lease_expires_at = renewal_time + lease_for
        task.updated_at = renewal_time
        self.session.flush()
        self.tasks.append_event(
            task,
            TaskEventType.log,
            {
                "message": "task_lease_renewed",
                "worker_id": worker_id,
                "lease_expires_at": task.lease_expires_at.isoformat(),
            },
        )
        return task

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
                "dead_letter": True,
                "last_worker_id": crashed_payload["locked_by"],
                "lease_expires_at": crashed_payload["lease_expires_at"],
            }
        else:
            retry_backoff = _retry_backoff(next_attempts)
            retry_at = reclaim_time + retry_backoff
            task.status = TaskStatus.pending
            task.available_at = retry_at
            task.error = None

        self.session.flush()
        payload = {
            "from": TaskStatus.crashed.value,
            "to": TaskStatus(task.status).value,
            "reason": "lease_expired",
            "attempts": next_attempts,
            "max_attempts": task.max_attempts,
        }
        if task.status is TaskStatus.pending:
            payload["retry_at"] = task.available_at.isoformat()
            payload["retry_backoff_seconds"] = int(retry_backoff.total_seconds())
        else:
            payload["dead_letter"] = True
        self.tasks.append_event(task, TaskEventType.status_changed, payload)


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


def _retry_backoff(attempts: int) -> timedelta:
    exponent = max(0, attempts - 1)
    seconds = min(
        DEFAULT_RETRY_BACKOFF_SECONDS * (2**exponent),
        DEFAULT_MAX_RETRY_BACKOFF_SECONDS,
    )
    return timedelta(seconds=seconds)
