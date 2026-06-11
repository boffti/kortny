"""Write actions for the dashboard Autonomy governance surface (HIG-223)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from kortny.autonomy import AutonomyLevel
from kortny.autonomy_policy import AutonomyPolicyService


def _coerce_level(value: str) -> AutonomyLevel:
    try:
        return AutonomyLevel(value.strip().casefold())
    except ValueError as exc:
        raise ValueError(f"Unknown autonomy level: {value!r}") from exc


def set_workspace_level(
    session: Session,
    *,
    installation_id: uuid.UUID,
    level: str,
    by_user_id: str,
) -> None:
    """Set the workspace-default autonomy level."""

    AutonomyPolicyService(session).set_level(
        installation_id=installation_id,
        scope_type="workspace",
        scope_id=None,
        level=_coerce_level(level),
        updated_by_user_id=by_user_id,
    )


def set_channel_level(
    session: Session,
    *,
    installation_id: uuid.UUID,
    channel_id: str,
    level: str,
    by_user_id: str,
) -> None:
    """Set or update a per-channel autonomy override."""

    normalized = channel_id.strip()
    if not normalized:
        raise ValueError("Channel ID is required.")
    AutonomyPolicyService(session).set_level(
        installation_id=installation_id,
        scope_type="channel",
        scope_id=normalized,
        level=_coerce_level(level),
        updated_by_user_id=by_user_id,
    )


def clear_channel_level(
    session: Session,
    *,
    installation_id: uuid.UUID,
    channel_id: str,
) -> bool:
    """Remove a per-channel override so it falls back to the workspace level."""

    normalized = channel_id.strip()
    if not normalized:
        raise ValueError("Channel ID is required.")
    return AutonomyPolicyService(session).clear_level(
        installation_id=installation_id,
        scope_type="channel",
        scope_id=normalized,
    )


__all__ = [
    "clear_channel_level",
    "set_channel_level",
    "set_workspace_level",
]
