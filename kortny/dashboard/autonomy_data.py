"""Read views for the dashboard Autonomy governance surface (HIG-223)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.approvals import TOOL_AUTONOMY_DECISION_MESSAGE
from kortny.autonomy import DEFAULT_AUTONOMY_LEVEL, AutonomyLevel
from kortny.autonomy_policy import AutonomyPolicyService
from kortny.db.models import Task, TaskEvent, TaskEventType

AUTONOMY_LEVELS: tuple[str, ...] = tuple(level.value for level in AutonomyLevel)


@dataclass(frozen=True, slots=True)
class AutonomyChannelRow:
    policy_id: uuid.UUID
    channel_id: str
    level: str
    updated_at: datetime
    updated_by_user_id: str | None


@dataclass(frozen=True, slots=True)
class AutonomyAuditRow:
    occurred_at: datetime
    channel_id: str
    tool: str
    risk: str
    autonomy_level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AutonomyDashboard:
    installation_id: uuid.UUID | None
    workspace_level: str
    workspace_is_default: bool
    default_level: str
    levels: tuple[str, ...]
    channel_rows: tuple[AutonomyChannelRow, ...] = field(default_factory=tuple)
    audit_rows: tuple[AutonomyAuditRow, ...] = field(default_factory=tuple)


def get_autonomy_dashboard(
    session: Session,
    *,
    installation_id: uuid.UUID | None,
    default_level: str = DEFAULT_AUTONOMY_LEVEL,
    audit_limit: int = 50,
) -> AutonomyDashboard:
    """Assemble the autonomy policy + audit view for one installation."""

    if installation_id is None:
        return AutonomyDashboard(
            installation_id=None,
            workspace_level=default_level,
            workspace_is_default=True,
            default_level=default_level,
            levels=AUTONOMY_LEVELS,
        )

    service = AutonomyPolicyService(session, default_level=default_level)
    workspace_policy = service.workspace_policy(installation_id)
    workspace_level = (
        workspace_policy.level if workspace_policy is not None else default_level
    )
    channel_rows = tuple(
        AutonomyChannelRow(
            policy_id=policy.id,
            channel_id=policy.scope_id or "",
            level=policy.level,
            updated_at=policy.updated_at,
            updated_by_user_id=policy.updated_by_user_id,
        )
        for policy in service.channel_policies(installation_id)
    )
    audit_rows = _audit_rows(
        session, installation_id=installation_id, limit=audit_limit
    )
    return AutonomyDashboard(
        installation_id=installation_id,
        workspace_level=workspace_level,
        workspace_is_default=workspace_policy is None,
        default_level=default_level,
        levels=AUTONOMY_LEVELS,
        channel_rows=channel_rows,
        audit_rows=audit_rows,
    )


def _audit_rows(
    session: Session,
    *,
    installation_id: uuid.UUID,
    limit: int,
) -> tuple[AutonomyAuditRow, ...]:
    rows = session.execute(
        select(TaskEvent, Task.slack_channel_id)
        .join(Task, TaskEvent.task_id == Task.id)
        .where(
            Task.installation_id == installation_id,
            TaskEvent.type == TaskEventType.log,
            TaskEvent.payload["message"].as_string() == TOOL_AUTONOMY_DECISION_MESSAGE,
        )
        .order_by(TaskEvent.created_at.desc())
        .limit(limit)
    ).all()
    result: list[AutonomyAuditRow] = []
    for event, channel_id in rows:
        payload = event.payload if isinstance(event.payload, dict) else {}
        reasons_raw = payload.get("reasons")
        reasons = (
            tuple(str(item) for item in reasons_raw)
            if isinstance(reasons_raw, list)
            else ()
        )
        result.append(
            AutonomyAuditRow(
                occurred_at=event.created_at,
                channel_id=channel_id,
                tool=str(payload.get("tool") or "-"),
                risk=str(payload.get("risk") or "-"),
                autonomy_level=str(payload.get("autonomy_level") or "-"),
                reasons=reasons,
            )
        )
    return tuple(result)


__all__ = [
    "AUTONOMY_LEVELS",
    "AutonomyAuditRow",
    "AutonomyChannelRow",
    "AutonomyDashboard",
    "get_autonomy_dashboard",
]
