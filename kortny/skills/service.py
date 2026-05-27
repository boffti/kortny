"""Procedural skill registry service."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import (
    ProceduralSkill,
    ProceduralSkillInvocation,
    ProceduralSkillVersion,
    Task,
    TaskEventType,
)
from kortny.skills.builtins import BUILTIN_SKILLS, BuiltInSkillDefinition
from kortny.tasks import TaskService
from kortny.tools.types import JsonObject

SKILL_CATALOG_BUILT_MESSAGE = "procedural_skill_catalog_built"
SKILL_INVOKED_MESSAGE = "procedural_skill_invoked"
RESPONSE_HUMANIZER_INVOCATION = "response_humanizer"


@dataclass(frozen=True, slots=True)
class SkillActivation:
    """Selected procedural skill and the exact version used for a task."""

    skill_id: uuid.UUID
    skill_version_id: uuid.UUID
    slug: str
    name: str
    version: str
    owner_type: str
    trust_level: str
    instructions_md: str
    selected_reason: str

    def to_response_payload(self) -> JsonObject:
        return {
            "slug": self.slug,
            "name": self.name,
            "version": self.version,
            "owner_type": self.owner_type,
            "trust_level": self.trust_level,
            "selected_reason": self.selected_reason,
            "instructions_md": self.instructions_md,
        }

    def to_trace_payload(self) -> JsonObject:
        return {
            "skill_id": str(self.skill_id),
            "skill_version_id": str(self.skill_version_id),
            "slug": self.slug,
            "name": self.name,
            "version": self.version,
            "owner_type": self.owner_type,
            "trust_level": self.trust_level,
            "selected_reason": self.selected_reason,
        }


class SkillRegistryService:
    """Application service for built-in procedural skills."""

    def __init__(
        self,
        session: Session,
        *,
        task_service: TaskService | None = None,
    ) -> None:
        self.session = session
        self.task_service = task_service or TaskService(session)

    def ensure_builtin_skills(self) -> None:
        """Idempotently seed system-owned built-in skill definitions."""

        for definition in BUILTIN_SKILLS:
            self._ensure_builtin_skill(definition)
        self.session.flush()

    def select_for_response(
        self,
        task: Task,
        *,
        response_mode: str,
        invocation_kind: str = RESPONSE_HUMANIZER_INVOCATION,
    ) -> list[SkillActivation]:
        """Return active system skills for a response path and record selection."""

        self.ensure_builtin_skills()
        candidates = self._candidate_system_skills(response_mode=response_mode)
        self.task_service.append_event(
            task,
            TaskEventType.log,
            {
                "message": SKILL_CATALOG_BUILT_MESSAGE,
                "invocation_kind": invocation_kind,
                "response_mode": response_mode,
                "candidate_count": len(candidates),
                "candidate_slugs": [candidate.slug for candidate in candidates],
            },
        )
        selected = self._select_candidates(
            candidates,
            invocation_kind=invocation_kind,
        )
        for activation in selected:
            self.record_invocation(
                task,
                activation=activation,
                invocation_kind=invocation_kind,
                response_mode=response_mode,
            )
        return selected

    def record_invocation(
        self,
        task: Task,
        *,
        activation: SkillActivation,
        invocation_kind: str,
        response_mode: str,
    ) -> ProceduralSkillInvocation:
        """Persist a skill invocation and mirror it into task_events."""

        invocation = ProceduralSkillInvocation(
            installation_id=task.installation_id,
            task_id=task.id,
            skill_id=activation.skill_id,
            skill_version_id=activation.skill_version_id,
            invocation_kind=invocation_kind,
            response_mode=response_mode,
            selected_reason=activation.selected_reason,
            payload=activation.to_trace_payload(),
        )
        self.session.add(invocation)
        self.session.flush()
        self.task_service.append_event(
            task,
            TaskEventType.log,
            {
                "message": SKILL_INVOKED_MESSAGE,
                "invocation_id": str(invocation.id),
                "invocation_kind": invocation_kind,
                "response_mode": response_mode,
                **activation.to_trace_payload(),
            },
        )
        return invocation

    def _ensure_builtin_skill(self, definition: BuiltInSkillDefinition) -> None:
        skill = self.session.scalar(
            select(ProceduralSkill).where(
                ProceduralSkill.owner_type == "system",
                ProceduralSkill.owner_id.is_(None),
                ProceduralSkill.slug == definition.slug,
            )
        )
        if skill is None:
            skill = ProceduralSkill(
                slug=definition.slug,
                owner_type="system",
                owner_id=None,
                status="active",
                trust_level="trusted",
                visibility="catalog",
            )
            self.session.add(skill)
            self.session.flush()
        else:
            skill.status = "active"
            skill.trust_level = "trusted"
            skill.visibility = "catalog"

        content_hash = _content_sha256(definition)
        version = self.session.scalar(
            select(ProceduralSkillVersion).where(
                ProceduralSkillVersion.skill_id == skill.id,
                ProceduralSkillVersion.version == definition.version,
            )
        )
        if version is None:
            version = ProceduralSkillVersion(
                skill_id=skill.id,
                version=definition.version,
                status="active",
                name=definition.name,
                description=definition.description,
                instructions_md=definition.instructions_md,
                intent_tags=list(definition.intent_tags),
                response_modes=list(definition.response_modes),
                trigger_phrases=list(definition.trigger_phrases),
                allowed_tools=[],
                metadata_json=definition.metadata or {},
                content_sha256=content_hash,
                created_by="system",
                approved_by="system",
                published_at=datetime.now(UTC),
            )
            self.session.add(version)
            return

        version.status = "active"
        version.name = definition.name
        version.description = definition.description
        version.instructions_md = definition.instructions_md
        version.intent_tags = list(definition.intent_tags)
        version.response_modes = list(definition.response_modes)
        version.trigger_phrases = list(definition.trigger_phrases)
        version.allowed_tools = []
        version.metadata_json = definition.metadata or {}
        version.content_sha256 = content_hash
        version.created_by = "system"
        version.approved_by = "system"
        if version.published_at is None:
            version.published_at = datetime.now(UTC)

    def _candidate_system_skills(self, *, response_mode: str) -> list[SkillActivation]:
        rows = self.session.execute(
            select(ProceduralSkill, ProceduralSkillVersion)
            .join(
                ProceduralSkillVersion,
                ProceduralSkillVersion.skill_id == ProceduralSkill.id,
            )
            .where(
                ProceduralSkill.owner_type == "system",
                ProceduralSkill.status == "active",
                ProceduralSkill.visibility == "catalog",
                ProceduralSkillVersion.status == "active",
            )
            .order_by(ProceduralSkill.slug, ProceduralSkillVersion.version.desc())
        )
        candidates: list[SkillActivation] = []
        seen_slugs: set[str] = set()
        for skill, version in rows:
            if skill.slug in seen_slugs:
                continue
            modes = _string_set(version.response_modes)
            if response_mode not in modes and "all" not in modes:
                continue
            seen_slugs.add(skill.slug)
            candidates.append(
                SkillActivation(
                    skill_id=skill.id,
                    skill_version_id=version.id,
                    slug=skill.slug,
                    name=version.name,
                    version=version.version,
                    owner_type=skill.owner_type,
                    trust_level=skill.trust_level,
                    instructions_md=version.instructions_md,
                    selected_reason=f"matches response_mode={response_mode}",
                )
            )
        return candidates

    def _select_candidates(
        self,
        candidates: list[SkillActivation],
        *,
        invocation_kind: str,
    ) -> list[SkillActivation]:
        if invocation_kind == RESPONSE_HUMANIZER_INVOCATION:
            for candidate in candidates:
                if candidate.slug == "slack-humanizer":
                    return [
                        SkillActivation(
                            skill_id=candidate.skill_id,
                            skill_version_id=candidate.skill_version_id,
                            slug=candidate.slug,
                            name=candidate.name,
                            version=candidate.version,
                            owner_type=candidate.owner_type,
                            trust_level=candidate.trust_level,
                            instructions_md=candidate.instructions_md,
                            selected_reason=(
                                "built-in rendering skill for response humanizer"
                            ),
                        )
                    ]
        return candidates[:1]


def _content_sha256(definition: BuiltInSkillDefinition) -> str:
    payload: dict[str, Any] = {
        "slug": definition.slug,
        "name": definition.name,
        "version": definition.version,
        "description": definition.description,
        "instructions_md": definition.instructions_md,
        "intent_tags": list(definition.intent_tags),
        "response_modes": list(definition.response_modes),
        "trigger_phrases": list(definition.trigger_phrases),
        "metadata": definition.metadata or {},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}
