"""Temporal workflow launch adapter for Kortny tasks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from kortny.config import Settings
from kortny.db.models import Task
from kortny.tools.types import JsonObject
from kortny.workflow.temporal import KortnyTaskWorkflow, KortnyWorkflowInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TemporalWorkflowLaunch:
    """Recorded metadata for a started Temporal workflow."""

    workflow_id: str
    run_id: str | None
    first_execution_run_id: str | None
    result_run_id: str | None
    namespace: str
    task_queue: str

    def to_payload(self) -> JsonObject:
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "first_execution_run_id": self.first_execution_run_id,
            "result_run_id": self.result_run_id,
            "namespace": self.namespace,
            "task_queue": self.task_queue,
        }


def temporal_workflow_id(task_id: uuid.UUID | str) -> str:
    """Return the stable Temporal workflow ID for one Kortny task."""

    return f"kortny-task-{task_id}"


def build_temporal_workflow_input(task: Task) -> KortnyWorkflowInput:
    """Build the serializable workflow input for a task."""

    return KortnyWorkflowInput(
        task_id=str(task.id),
        installation_id=str(task.installation_id),
        slack_channel_id=task.slack_channel_id,
        slack_thread_ts=task.slack_thread_ts,
        slack_user_id=task.slack_user_id,
        input=task.input,
    )


async def start_temporal_task_workflow(
    *,
    settings: Settings,
    task: Task,
    client: Client | None = None,
) -> TemporalWorkflowLaunch:
    """Start or attach to the durable Temporal workflow for a task."""

    temporal_client = client or await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    workflow_id = temporal_workflow_id(task.id)
    workflow_input = build_temporal_workflow_input(task)
    handle = await temporal_client.start_workflow(
        KortnyTaskWorkflow.run,
        workflow_input.to_payload(),
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        static_summary=f"Kortny task {task.id}",
    )
    launch = TemporalWorkflowLaunch(
        workflow_id=handle.id,
        run_id=handle.run_id,
        first_execution_run_id=handle.first_execution_run_id,
        result_run_id=handle.result_run_id,
        namespace=settings.temporal_namespace,
        task_queue=settings.temporal_task_queue,
    )
    logger.info(
        "temporal workflow started task_id=%s workflow_id=%s run_id=%s task_queue=%s",
        task.id,
        launch.workflow_id,
        launch.run_id,
        launch.task_queue,
    )
    return launch


def start_temporal_task_workflow_sync(
    *,
    settings: Settings,
    task: Task,
) -> TemporalWorkflowLaunch:
    """Sync wrapper for the Postgres worker's current execution path."""

    return asyncio.run(start_temporal_task_workflow(settings=settings, task=task))
