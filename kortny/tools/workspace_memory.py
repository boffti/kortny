"""Workspace memory tools backed by WorkspaceStateService."""

from __future__ import annotations

from typing import Any

from kortny.db.models import Task
from kortny.memory import Fact, WorkspaceStateSecretError, WorkspaceStateService
from kortny.tools.types import JsonObject, JsonSchema, ToolResult


class RememberFactTool:
    """Propose a durable memory fact and ask the user to confirm it."""

    name = "remember_fact"
    description = (
        "Proposes a workspace, channel, or user memory fact. The fact is not "
        "saved until the user confirms the Slack prompt. Use this only for "
        "stable user-provided facts or preferences. Preserve every actionable "
        "detail in value and value_text, including concrete names, firm names, "
        "colors, footer/header placement, file formats, conditions, and "
        "exceptions. Prefer a slightly longer faithful proposal over a short "
        "lossy summary."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["workspace", "channel", "user"],
                "description": "Where the memory applies.",
            },
            "key": {
                "type": "string",
                "description": "Stable snake_case key for the memory fact.",
            },
            "value": {
                "type": "object",
                "description": (
                    "Structured JSON object to remember. Include all concrete "
                    "details from the user's preference, not just the broad topic."
                ),
                "additionalProperties": True,
            },
            "value_text": {
                "type": "string",
                "description": (
                    "Human-readable summary shown in the confirmation prompt. "
                    "Keep it concise but faithful: preserve names, colors, "
                    "placement details like footer left, file formats, and "
                    "conditions/exceptions."
                ),
            },
            "reason": {
                "type": "string",
                "description": "Why this fact should be remembered.",
            },
            "confidence_score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Optional confidence score for the proposed fact.",
            },
            "confidence_reason": {
                "type": "string",
                "description": "Optional confidence rationale.",
            },
        },
        "required": ["scope", "key", "value"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        service: WorkspaceStateService,
        task: Task,
    ) -> None:
        self.service = service
        self.task = task

    def invoke(self, args: JsonObject) -> ToolResult:
        scope = _required_string(args, "scope")
        key = _required_string(args, "key")
        value = _required_object(args, "value")
        value_text = _optional_string(args.get("value_text"))
        reason = _optional_string(args.get("reason"))
        confidence_reason = _optional_string(args.get("confidence_reason"))
        confidence_score = args.get("confidence_score")

        try:
            pending = self.service.propose(
                self.task.installation_id,
                scope,
                _scope_id_for_task(scope, self.task),
                key,
                value,
                self.task.id,
                value_text=value_text,
                proposed_reason=reason,
                confidence_score=confidence_score,
                confidence_reason=confidence_reason,
            )
        except WorkspaceStateSecretError as exc:
            return ToolResult(
                output={
                    "status": "blocked",
                    "error": {
                        "code": "secret_not_stored",
                        "message": (
                            "Kortny must not store API keys, tokens, passwords, "
                            "or other secrets in memory. Ask the user to put "
                            "secrets in environment variables or a secret manager."
                        ),
                        "reason": exc.reason,
                        "recoverable": True,
                    },
                }
            )
        return ToolResult(
            output={
                "status": "pending_confirmation",
                "scope": pending.scope_type,
                "scope_id": pending.scope_id,
                "key": pending.key,
                "value": pending.value,
                "value_text": pending.value_text,
                "prompt_channel_id": pending.prompt_channel_id,
                "prompt_message_ts": pending.prompt_message_ts,
                "message": (
                    "A confirmation prompt was posted. The fact is not saved "
                    "until the user reacts with :white_check_mark:."
                ),
            }
        )


class RecallFactTool:
    """Read current active memory facts."""

    name = "recall_fact"
    description = "Reads a current active memory fact for this workspace/channel/user."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["workspace", "channel", "user"],
                "description": "Where to look for the memory fact.",
            },
            "key": {
                "type": "string",
                "description": "Stable key for the memory fact.",
            },
        },
        "required": ["scope", "key"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        service: WorkspaceStateService,
        task: Task,
    ) -> None:
        self.service = service
        self.task = task

    def invoke(self, args: JsonObject) -> ToolResult:
        scope = _required_string(args, "scope")
        key = _required_string(args, "key")
        fact = self.service.get(
            self.task.installation_id,
            scope,
            _scope_id_for_task(scope, self.task),
            key,
        )
        if fact is None:
            return ToolResult(
                output={
                    "found": False,
                    "scope": scope,
                    "scope_id": _scope_id_for_task(scope, self.task),
                    "key": key,
                }
            )
        return ToolResult(
            output={
                "found": True,
                "id": str(fact.id),
                "scope": fact.scope_type,
                "scope_id": fact.scope_id,
                "key": fact.key,
                "value": fact.value,
                "value_text": fact.value_text,
                "source_task_id": str(fact.source_task_id)
                if fact.source_task_id is not None
                else None,
                "source_event_id": fact.source_event_id,
                "source_slack_channel_id": fact.source_slack_channel_id,
                "source_slack_message_ts": fact.source_slack_message_ts,
                "proposed_by": fact.proposed_by,
                "proposed_reason": fact.proposed_reason,
                "confidence_reason": fact.confidence_reason,
                "confirmed_by_user_id": fact.confirmed_by_user_id,
                "confirmed_at": fact.confirmed_at.isoformat()
                if fact.confirmed_at is not None
                else None,
            }
        )


class InspectMemoryTool:
    """Inspect active memory facts or provenance history."""

    name = "inspect_memory"
    description = (
        "Lists current memory facts for this workspace/channel/user, or returns "
        "provenance/history for a specific memory key. Use this when the user "
        "asks what Kortny remembers or why Kortny believes a remembered fact."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["workspace", "channel", "user"],
                "description": "Which memory scope to inspect.",
            },
            "key": {
                "type": "string",
                "description": "Optional memory key to inspect.",
            },
            "include_history": {
                "type": "boolean",
                "description": (
                    "When true and key is provided, include superseded/forgotten "
                    "rows for provenance."
                ),
            },
        },
        "required": ["scope"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        service: WorkspaceStateService,
        task: Task,
    ) -> None:
        self.service = service
        self.task = task

    def invoke(self, args: JsonObject) -> ToolResult:
        scope = _required_string(args, "scope")
        key = _optional_string(args.get("key"))
        include_history = _optional_bool(args.get("include_history", False))
        scope_id = _scope_id_for_task(scope, self.task)

        if key is not None and include_history:
            facts = self.service.list_history(
                self.task.installation_id,
                scope_type=scope,
                scope_id=scope_id,
                key=key,
            )
        elif key is not None:
            fact = self.service.get(
                self.task.installation_id,
                scope,
                scope_id,
                key,
            )
            facts = [] if fact is None else [fact]
        else:
            facts = self.service.list(
                self.task.installation_id,
                scope_type=scope,
                scope_id=scope_id,
            )

        self.service.record_inspection(
            self.task.id,
            scope_type=scope,
            scope_id=scope_id,
            key=key,
            include_history=include_history,
            count=len(facts),
        )
        return ToolResult(
            output={
                "scope": scope,
                "scope_id": scope_id,
                "key": key,
                "include_history": include_history,
                "count": len(facts),
                "facts": [_fact_output(fact, include_history=True) for fact in facts],
            }
        )


class ForgetFactTool:
    """Soft-delete active memory facts by key."""

    name = "forget_fact"
    description = (
        "Forgets an active workspace, channel, or user memory fact by key. "
        "This is an audit-preserving soft delete: forgotten facts are no longer "
        "used in context, but history remains for operator audit."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "enum": ["workspace", "channel", "user"],
                "description": "Which memory scope contains the fact.",
            },
            "key": {
                "type": "string",
                "description": "Stable key for the memory fact to forget.",
            },
        },
        "required": ["scope", "key"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        service: WorkspaceStateService,
        task: Task,
    ) -> None:
        self.service = service
        self.task = task

    def invoke(self, args: JsonObject) -> ToolResult:
        scope = _required_string(args, "scope")
        key = _required_string(args, "key")
        scope_id = _scope_id_for_task(scope, self.task)
        forgotten_count = self.service.forget(
            self.task.installation_id,
            scope,
            scope_id,
            key,
            self.task.slack_user_id,
            audit_task_id=self.task.id,
        )
        return ToolResult(
            output={
                "scope": scope,
                "scope_id": scope_id,
                "key": key,
                "forgotten_count": forgotten_count,
                "message": (
                    "Forgot the active memory fact."
                    if forgotten_count
                    else "No active memory fact matched that scope and key."
                ),
            }
        )


def _fact_output(fact: Fact, *, include_history: bool = False) -> JsonObject:
    output: JsonObject = {
        "id": str(fact.id),
        "scope": fact.scope_type,
        "scope_id": fact.scope_id,
        "key": fact.key,
        "value": fact.value,
        "value_text": fact.value_text,
        "status": fact.status,
        "source_kind": fact.source_kind,
        "source_task_id": str(fact.source_task_id)
        if fact.source_task_id is not None
        else None,
        "source_event_id": fact.source_event_id,
        "source_slack_channel_id": fact.source_slack_channel_id,
        "source_slack_message_ts": fact.source_slack_message_ts,
        "proposed_by": fact.proposed_by,
        "proposed_reason": fact.proposed_reason,
        "confidence_reason": fact.confidence_reason,
        "confirmed_by_user_id": fact.confirmed_by_user_id,
        "confirmed_at": fact.confirmed_at.isoformat()
        if fact.confirmed_at is not None
        else None,
        "created_at": fact.created_at.isoformat(),
        "updated_at": fact.updated_at.isoformat(),
    }
    if not include_history:
        output.pop("status", None)
    return output


def _scope_id_for_task(scope: str, task: Task) -> str | None:
    if scope == "workspace":
        return None
    if scope == "channel":
        return task.slack_channel_id
    if scope == "user":
        return task.slack_user_id
    raise ValueError(f"Unsupported scope: {scope}")


def _required_string(args: JsonObject, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string argument must be a string")
    return value.strip() or None


def _optional_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    raise ValueError("optional boolean argument must be a boolean")


def _required_object(args: JsonObject, key: str) -> dict[str, Any]:
    value = args.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a JSON object")
    return dict(value)
