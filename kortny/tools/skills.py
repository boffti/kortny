"""Tools for loading enabled procedural skills during task execution.

The L1 name+description block in the task context advertises enabled skills;
these tools are the L2/L3 progressive-disclosure path: ``load_skill`` returns
the full SKILL.md instructions, ``load_skill_resource`` returns one bundled
reference/asset/script file. Script contents are viewable but never executed
here (trust-gated sandbox execution is a later slice).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import ProceduralSkillVersion, SkillFile, Task
from kortny.skills import (
    EXECUTION_INVOCATION,
    EnabledSkill,
    SkillActivation,
    SkillRegistryService,
)
from kortny.tasks import TaskService
from kortny.tools.types import (
    JsonObject,
    JsonSchema,
    RecoverableToolError,
    ToolResult,
)

MAX_RESOURCE_CHARS = 60_000


class LoadSkillTool:
    """Load the full instructions for a skill enabled in this task's scope."""

    name = "load_skill"
    description = (
        "Loads the full instructions for one of the available skills listed "
        "in <available_skills>. Call this BEFORE doing the work whenever a "
        "skill's description matches the task, then follow the returned "
        "instructions."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "The skill slug from the available skills list.",
            },
        },
        "required": ["slug"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        session: Session,
        task: Task,
        task_service: TaskService,
    ) -> None:
        self.session = session
        self.task = task
        self.registry = SkillRegistryService(session, task_service=task_service)

    def invoke(self, args: JsonObject) -> ToolResult:
        slug = str(args.get("slug") or "").strip()
        enabled = _enabled_skill_or_raise(self.registry, self.task, slug)
        version = self.session.get(ProceduralSkillVersion, enabled.version_id)
        if version is None:  # pragma: no cover - enablement implies a version
            raise RecoverableToolError(
                code="skill_version_missing",
                message=f"Skill '{slug}' has no active version.",
            )
        resource_paths = list(
            self.session.scalars(
                select(SkillFile.path)
                .where(SkillFile.skill_version_id == enabled.version_id)
                .order_by(SkillFile.path)
            )
        )
        self.registry.record_invocation(
            self.task,
            activation=SkillActivation(
                skill_id=enabled.skill_id,
                skill_version_id=enabled.version_id,
                slug=enabled.slug,
                name=enabled.name,
                version=enabled.version,
                owner_type=enabled.owner_type,
                trust_level=enabled.trust_level,
                instructions_md=version.instructions_md,
                selected_reason="model-triggered via load_skill",
            ),
            invocation_kind=EXECUTION_INVOCATION,
            response_mode="execution",
        )
        output: JsonObject = {
            "slug": enabled.slug,
            "name": enabled.name,
            "version": enabled.version,
            "trust_level": enabled.trust_level,
            "instructions_md": version.instructions_md,
            "resources": resource_paths,
        }
        if any(path.startswith("scripts/") for path in resource_paths):
            output["scripts_note"] = (
                "Bundled scripts are viewable with load_skill_resource but are "
                "not executable at this skill's trust level."
            )
        return ToolResult(output=output)


class LoadSkillResourceTool:
    """Load one bundled file (reference/asset/script) from an enabled skill."""

    name = "load_skill_resource"
    description = (
        "Loads a bundled resource file from an enabled skill, e.g. "
        "'references/guide.md'. Use the resource paths returned by load_skill."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "The skill slug from the available skills list.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Relative resource path, e.g. 'references/guide.md', "
                    "'assets/template.txt', or 'scripts/run.py'."
                ),
            },
        },
        "required": ["slug", "path"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        session: Session,
        task: Task,
        task_service: TaskService,
    ) -> None:
        self.session = session
        self.task = task
        self.registry = SkillRegistryService(session, task_service=task_service)

    def invoke(self, args: JsonObject) -> ToolResult:
        slug = str(args.get("slug") or "").strip()
        path = str(args.get("path") or "").strip()
        enabled = _enabled_skill_or_raise(self.registry, self.task, slug)
        resource = self.session.scalar(
            select(SkillFile).where(
                SkillFile.skill_version_id == enabled.version_id,
                SkillFile.path == path,
            )
        )
        if resource is None:
            available = list(
                self.session.scalars(
                    select(SkillFile.path)
                    .where(SkillFile.skill_version_id == enabled.version_id)
                    .order_by(SkillFile.path)
                )
            )
            raise RecoverableToolError(
                code="skill_resource_not_found",
                message=f"Resource '{path}' not found in skill '{slug}'.",
                hint=f"Available resources: {', '.join(available) or 'none'}",
            )
        if resource.content_text is None:
            raise RecoverableToolError(
                code="skill_resource_binary",
                message=(
                    f"Resource '{path}' is binary and cannot be returned as text."
                ),
            )
        content = resource.content_text
        truncated = False
        if len(content) > MAX_RESOURCE_CHARS:
            content = content[:MAX_RESOURCE_CHARS]
            truncated = True
        return ToolResult(
            output={
                "slug": enabled.slug,
                "path": path,
                "kind": resource.kind,
                "content": content,
                "truncated": truncated,
            }
        )


def _enabled_skill_or_raise(
    registry: SkillRegistryService,
    task: Task,
    slug: str,
) -> EnabledSkill:
    if not slug:
        raise RecoverableToolError(
            code="skill_slug_required",
            message="Argument 'slug' is required.",
        )
    enabled = {skill.slug: skill for skill in registry.enabled_skills_for_task(task)}
    skill = enabled.get(slug)
    if skill is None:
        raise RecoverableToolError(
            code="skill_not_enabled",
            message=f"Skill '{slug}' is not enabled for this task.",
            hint=f"Enabled skills: {', '.join(sorted(enabled)) or 'none'}",
        )
    return skill
