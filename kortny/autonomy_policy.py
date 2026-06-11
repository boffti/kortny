"""DB-backed resolution + governance for autonomy policies (HIG-223).

Separates the pure classifier (:mod:`kortny.autonomy`) from the persistence
seam. ``resolve_level`` reads the scoped ``autonomy_policies`` rows and applies
channel -> workspace -> default precedence; ``set_level`` upserts one scope row
(used by the dashboard governance surface).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.autonomy import (
    DEFAULT_AUTONOMY_LEVEL,
    AutonomyLevel,
    resolve_autonomy_level,
)
from kortny.db.models import AutonomyPolicy


class AutonomyPolicyService:
    """Resolve and govern scoped autonomy levels."""

    def __init__(
        self, session: Session, *, default_level: str = DEFAULT_AUTONOMY_LEVEL
    ):
        self.session = session
        self.default_level = default_level

    def resolve_level(
        self,
        *,
        installation_id: uuid.UUID,
        channel_id: str | None,
    ) -> AutonomyLevel:
        """Resolve the effective level for a channel (channel -> ws -> default)."""

        workspace_level = self._level_for(
            installation_id=installation_id, scope_type="workspace", scope_id=None
        )
        channel_level = None
        if channel_id:
            channel_level = self._level_for(
                installation_id=installation_id,
                scope_type="channel",
                scope_id=channel_id,
            )
        return resolve_autonomy_level(
            channel_level=channel_level,
            workspace_level=workspace_level,
            default_level=self.default_level,
        )

    def workspace_policy(self, installation_id: uuid.UUID) -> AutonomyPolicy | None:
        return self.session.scalar(
            select(AutonomyPolicy).where(
                AutonomyPolicy.installation_id == installation_id,
                AutonomyPolicy.scope_type == "workspace",
                AutonomyPolicy.scope_id.is_(None),
            )
        )

    def channel_policies(self, installation_id: uuid.UUID) -> Sequence[AutonomyPolicy]:
        return tuple(
            self.session.scalars(
                select(AutonomyPolicy)
                .where(
                    AutonomyPolicy.installation_id == installation_id,
                    AutonomyPolicy.scope_type == "channel",
                )
                .order_by(AutonomyPolicy.scope_id)
            )
        )

    def set_level(
        self,
        *,
        installation_id: uuid.UUID,
        scope_type: str,
        scope_id: str | None,
        level: AutonomyLevel,
        updated_by_user_id: str | None,
    ) -> AutonomyPolicy:
        """Upsert one scope's autonomy level."""

        existing = self.session.scalar(
            select(AutonomyPolicy)
            .where(
                AutonomyPolicy.installation_id == installation_id,
                AutonomyPolicy.scope_type == scope_type,
                AutonomyPolicy.scope_id.is_(None)
                if scope_id is None
                else AutonomyPolicy.scope_id == scope_id,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        if existing is not None:
            existing.level = level.value
            existing.updated_by_user_id = updated_by_user_id
            existing.updated_at = now
            self.session.flush()
            return existing

        policy = AutonomyPolicy(
            installation_id=installation_id,
            scope_type=scope_type,
            scope_id=scope_id,
            level=level.value,
            updated_by_user_id=updated_by_user_id,
        )
        try:
            with self.session.begin_nested():
                self.session.add(policy)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(AutonomyPolicy).where(
                    AutonomyPolicy.installation_id == installation_id,
                    AutonomyPolicy.scope_type == scope_type,
                    AutonomyPolicy.scope_id.is_(None)
                    if scope_id is None
                    else AutonomyPolicy.scope_id == scope_id,
                )
            )
            if existing is None:
                raise
            existing.level = level.value
            existing.updated_by_user_id = updated_by_user_id
            existing.updated_at = now
            self.session.flush()
            return existing
        return policy

    def clear_level(
        self,
        *,
        installation_id: uuid.UUID,
        scope_type: str,
        scope_id: str | None,
    ) -> bool:
        """Delete one scope's autonomy override. Returns whether a row was removed."""

        policy = self.session.scalar(
            select(AutonomyPolicy).where(
                AutonomyPolicy.installation_id == installation_id,
                AutonomyPolicy.scope_type == scope_type,
                AutonomyPolicy.scope_id.is_(None)
                if scope_id is None
                else AutonomyPolicy.scope_id == scope_id,
            )
        )
        if policy is None:
            return False
        self.session.delete(policy)
        self.session.flush()
        return True

    def _level_for(
        self,
        *,
        installation_id: uuid.UUID,
        scope_type: str,
        scope_id: str | None,
    ) -> str | None:
        policy = self.session.scalar(
            select(AutonomyPolicy).where(
                AutonomyPolicy.installation_id == installation_id,
                AutonomyPolicy.scope_type == scope_type,
                AutonomyPolicy.scope_id.is_(None)
                if scope_id is None
                else AutonomyPolicy.scope_id == scope_id,
            )
        )
        return policy.level if policy is not None else None


__all__ = ["AutonomyPolicyService"]
