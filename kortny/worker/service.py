"""Task worker over the durable Postgres queue."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from kortny.db.models import Task, TaskEventType, TaskStatus
from kortny.db.session import make_session_factory
from kortny.logging_config import configure_logging
from kortny.queue import TaskQueue
from kortny.queue.service import DEFAULT_LEASE_SECONDS
from kortny.tasks import TaskService
from kortny.worker.agent_executor import AgentTaskExecutor, TaskExecutor

DEFAULT_POLL_INTERVAL_SECONDS = 2.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    """Outcome from one worker poll cycle."""

    worker_id: str
    status: str
    task_id: uuid.UUID | None = None
    reclaimed_task_ids: tuple[uuid.UUID, ...] = ()

    @property
    def handled_task(self) -> bool:
        """Whether this poll cycle claimed and handled a task."""

        return self.task_id is not None


class TaskWorker:
    """Polls the task queue and runs the MVP task executor."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        worker_id: str | None = None,
        executor: TaskExecutor | None = None,
        lease_for: timedelta = timedelta(seconds=DEFAULT_LEASE_SECONDS),
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.session_factory = session_factory or make_session_factory()
        self.worker_id = worker_id or default_worker_id()
        self.executor = executor or AgentTaskExecutor()
        self.lease_for = lease_for
        self.poll_interval_seconds = poll_interval_seconds

    def run_once(self, *, now: datetime | None = None) -> WorkerRunResult:
        """Reclaim expired leases, claim at most one task, and handle it."""

        with self.session_factory.begin() as session:
            task_service = TaskService(session)
            queue = TaskQueue(session)
            reclaimed = queue.reclaim_expired_leases(now=now)
            if reclaimed:
                logger.info(
                    "worker reclaimed expired tasks worker_id=%s task_ids=%s",
                    self.worker_id,
                    ",".join(str(task.id) for task in reclaimed),
                )
            task = queue.claim_next(
                worker_id=self.worker_id,
                lease_for=self.lease_for,
                now=now,
            )
            reclaimed_task_ids = tuple(task.id for task in reclaimed)

            if task is None:
                logger.debug("worker idle worker_id=%s", self.worker_id)
                return WorkerRunResult(
                    worker_id=self.worker_id,
                    status="idle",
                    reclaimed_task_ids=reclaimed_task_ids,
                )

            logger.info(
                "worker claimed task task_id=%s worker_id=%s input_len=%s",
                task.id,
                self.worker_id,
                len(task.input),
            )
            task_service.append_event(
                task,
                TaskEventType.log,
                {
                    "message": "task_executor_started",
                    "worker_id": self.worker_id,
                },
            )

            try:
                execution_result = self.executor.execute(
                    session=session,
                    task=task,
                    task_service=task_service,
                )
                task.result_summary = execution_result.result_summary
                task.error = None
                self._clear_lease(task)
                task_service.append_event(
                    task,
                    TaskEventType.log,
                    {
                        "message": "task_executor_completed",
                        "worker_id": self.worker_id,
                    },
                )
                task_service.transition(task, TaskStatus.succeeded)
                logger.info(
                    "worker succeeded task_id=%s worker_id=%s",
                    task.id,
                    self.worker_id,
                )
                return WorkerRunResult(
                    worker_id=self.worker_id,
                    status=TaskStatus.succeeded.value,
                    task_id=task.id,
                    reclaimed_task_ids=reclaimed_task_ids,
                )
            except Exception as exc:
                task.error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "worker_id": self.worker_id,
                }
                self._clear_lease(task)
                task_service.append_event(
                    task,
                    TaskEventType.error,
                    {
                        "message": "task_executor_failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "worker_id": self.worker_id,
                    },
                )
                task_service.transition(task, TaskStatus.failed)
                logger.exception(
                    "worker failed task_id=%s worker_id=%s",
                    task.id,
                    self.worker_id,
                )
                return WorkerRunResult(
                    worker_id=self.worker_id,
                    status=TaskStatus.failed.value,
                    task_id=task.id,
                    reclaimed_task_ids=reclaimed_task_ids,
                )

    def run_forever(self) -> None:
        """Poll forever, sleeping only when no task was handled."""

        while True:
            result = self.run_once()
            if not result.handled_task:
                time.sleep(self.poll_interval_seconds)

    @staticmethod
    def _clear_lease(task: Task) -> None:
        task.locked_by = None
        task.locked_at = None
        task.lease_expires_at = None
        task.updated_at = datetime.now(UTC)


def walking_skeleton_handler(task: Task) -> str:
    """Deprecated trivial MVP handler retained for compatibility."""

    return f"Walking skeleton processed task {task.id}: {task.input}"


def default_worker_id() -> str:
    """Return a stable-enough process identifier for lease ownership."""

    return f"{socket.gethostname()}-{os.getpid()}"


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for local and Compose worker runs."""

    configure_logging()
    parser = argparse.ArgumentParser(description="Run the Kortny task worker")
    parser.add_argument("--once", action="store_true", help="Process at most one task")
    parser.add_argument("--worker-id", default=None, help="Override lease worker id")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds to sleep between idle polls",
    )
    args = parser.parse_args(argv)

    worker = TaskWorker(
        worker_id=args.worker_id,
        poll_interval_seconds=args.poll_interval,
    )
    logger.info("worker started worker_id=%s once=%s", worker.worker_id, args.once)
    if args.once:
        result = worker.run_once()
        print(
            "worker_id={worker_id} status={status} task_id={task_id}".format(
                worker_id=result.worker_id,
                status=result.status,
                task_id=result.task_id or "",
            )
        )
        return

    worker.run_forever()
