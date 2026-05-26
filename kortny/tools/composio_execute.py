"""Kortny tool adapter for scoped Composio runtime execution."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from kortny.composio import ComposioClient, ComposioConnectionResolver, ComposioTool
from kortny.db.models import Task
from kortny.observability.events import log_observation
from kortny.tools.types import JsonObject, JsonSchema, ToolResult

logger = logging.getLogger(__name__)


class ComposioExecuteTool:
    """Execute approved Composio tools through a scoped connected account."""

    def __init__(
        self,
        *,
        session: Session,
        task: Task,
        client: ComposioClient,
        allowed_tools: Sequence[ComposioTool],
        toolkit_slug: str | None = None,
        name: str | None = None,
    ) -> None:
        self.session = session
        self.task = task
        self.client = client
        self.resolver = ComposioConnectionResolver(session, task)
        self.fixed_toolkit_slug = toolkit_slug.lower() if toolkit_slug else None
        self.allowed_tools_by_toolkit = _group_allowed_tools(
            allowed_tools,
            fixed_toolkit_slug=self.fixed_toolkit_slug,
        )
        self.name = name or (
            composio_runtime_tool_name(self.fixed_toolkit_slug)
            if self.fixed_toolkit_slug
            else "composio_execute"
        )
        self.description = _description(
            self.allowed_tools_by_toolkit,
            fixed_toolkit_slug=self.fixed_toolkit_slug,
        )
        self.parameters = _parameters(
            self.allowed_tools_by_toolkit,
            fixed_toolkit_slug=self.fixed_toolkit_slug,
        )

    @property
    def has_available_connections(self) -> bool:
        if not self.allowed_tools_by_toolkit:
            return False
        return self.resolver.has_allowed_connection(
            toolkit_slugs=tuple(self.allowed_tools_by_toolkit),
        )

    def invoke(self, args: JsonObject) -> ToolResult:
        toolkit_slug = self._toolkit_slug(args)
        tool_slug = _required_string(args.get("tool_slug"), "tool_slug").upper()
        arguments = args.get("arguments")
        if not isinstance(arguments, dict):
            raise ValueError("composio_execute 'arguments' must be an object")
        version = _optional_string(args.get("version"), "version")

        allowed_tools = self.allowed_tools_by_toolkit.get(toolkit_slug)
        if allowed_tools is None:
            raise ValueError(f"Composio toolkit is not enabled for runtime: {toolkit_slug}")
        allowed_tool_slugs = {tool.slug for tool in allowed_tools}
        if tool_slug not in allowed_tool_slugs:
            raise ValueError(f"Composio tool is not approved for runtime: {tool_slug}")

        connection = self.resolver.best_connection(toolkit_slug=toolkit_slug)
        if connection is None:
            raise ValueError(
                f"No active Composio {toolkit_slug} connection is available "
                "for this Slack user/channel/workspace."
            )

        log_observation(
            logger,
            "composio_tool_execution_started",
            task=self.task,
            provider="composio",
            runtime_tool=self.name,
            toolkit_slug=toolkit_slug,
            tool_slug=tool_slug,
            visibility_scope_type=connection.visibility_scope_type,
            argument_keys=sorted(arguments),
        )
        execution = self.client.execute_tool(
            tool_slug=tool_slug,
            user_id=connection.composio_user_id,
            connected_account_id=connection.connected_account_id,
            arguments=arguments,
            version=version,
        )
        log_observation(
            logger,
            "composio_tool_execution_completed",
            task=self.task,
            provider="composio",
            runtime_tool=self.name,
            toolkit_slug=toolkit_slug,
            tool_slug=tool_slug,
            visibility_scope_type=connection.visibility_scope_type,
            successful=execution.successful,
            log_id=execution.log_id,
        )
        return ToolResult(
            output={
                "provider": "composio",
                "toolkit_slug": toolkit_slug,
                "tool_slug": tool_slug,
                "successful": execution.successful,
                "data": execution.data,
                "error": execution.error,
                "log_id": execution.log_id,
                "scope": {
                    "type": connection.visibility_scope_type,
                    "id": connection.visibility_scope_id,
                },
                "connection": {
                    "display_name": connection.display_name,
                    "connected_account_id": connection.connected_account_id,
                },
            }
        )

    def _toolkit_slug(self, args: JsonObject) -> str:
        requested = _optional_string(args.get("toolkit_slug"), "toolkit_slug")
        if self.fixed_toolkit_slug is None:
            if requested is None:
                raise ValueError("composio_execute 'toolkit_slug' must be a non-empty string")
            return requested.lower()
        if requested is not None and requested.lower() != self.fixed_toolkit_slug:
            raise ValueError(
                f"composio_execute cannot use toolkit {requested!r}; "
                f"this runtime tool is scoped to {self.fixed_toolkit_slug!r}"
            )
        return self.fixed_toolkit_slug


def composio_runtime_tool_name(toolkit_slug: str | None) -> str:
    if not toolkit_slug:
        return "composio_execute"
    safe_slug = re.sub(r"[^a-z0-9_]+", "_", toolkit_slug.lower()).strip("_")
    return f"composio_{safe_slug or 'toolkit'}_execute"


def _group_allowed_tools(
    allowed_tools: Sequence[ComposioTool],
    *,
    fixed_toolkit_slug: str | None,
) -> dict[str, tuple[ComposioTool, ...]]:
    grouped: dict[str, list[ComposioTool]] = {}
    for tool in allowed_tools:
        toolkit_slug = (tool.toolkit_slug or fixed_toolkit_slug or "").lower()
        if not toolkit_slug:
            continue
        if fixed_toolkit_slug and toolkit_slug != fixed_toolkit_slug:
            continue
        grouped.setdefault(toolkit_slug, []).append(tool)
    return {
        toolkit_slug: tuple(_dedupe_tools(tools))
        for toolkit_slug, tools in grouped.items()
        if tools
    }


def _dedupe_tools(tools: Sequence[ComposioTool]) -> list[ComposioTool]:
    by_slug: dict[str, ComposioTool] = {}
    for tool in tools:
        by_slug.setdefault(tool.slug, tool)
    return list(by_slug.values())


def _description(
    allowed_tools_by_toolkit: dict[str, tuple[ComposioTool, ...]],
    *,
    fixed_toolkit_slug: str | None,
) -> str:
    if not allowed_tools_by_toolkit:
        return "Executes scoped Composio tools approved by Kortny policy."
    parts: list[str] = []
    for toolkit_slug, tools in allowed_tools_by_toolkit.items():
        slugs = ", ".join(tool.slug for tool in tools[:8])
        suffix = "..." if len(tools) > 8 else ""
        parts.append(f"{toolkit_slug}: {slugs}{suffix}")
    scope_text = (
        f"the connected {fixed_toolkit_slug} toolkit"
        if fixed_toolkit_slug
        else "connected Composio toolkits"
    )
    return (
        f"Executes read-only approved Composio tools from {scope_text} using "
        "Kortny's Slack user/channel/workspace visibility policy. Available "
        f"tool slugs: {'; '.join(parts)}. Do not use this for write or "
        "destructive actions."
    )


def _parameters(
    allowed_tools_by_toolkit: dict[str, tuple[ComposioTool, ...]],
    *,
    fixed_toolkit_slug: str | None,
) -> JsonSchema:
    allowed_slugs = sorted(
        {tool.slug for tools in allowed_tools_by_toolkit.values() for tool in tools}
    )
    properties: dict[str, JsonObject] = {
        "tool_slug": {
            "type": "string",
            "enum": allowed_slugs,
            "description": "Approved Composio tool slug to execute.",
        },
        "arguments": {
            "type": "object",
            "description": "Tool-specific JSON arguments.",
            "additionalProperties": True,
        },
        "version": {
            "type": "string",
            "description": "Optional Composio toolkit version.",
        },
    }
    required = ["tool_slug", "arguments"]
    if fixed_toolkit_slug is None:
        properties["toolkit_slug"] = {
            "type": "string",
            "enum": sorted(allowed_tools_by_toolkit),
            "description": "Connected Composio toolkit to use.",
        }
        required.insert(0, "toolkit_slug")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _required_string(value: Any, name: str) -> str:
    text = _optional_string(value, name)
    if text is None:
        raise ValueError(f"composio_execute {name!r} must be a non-empty string")
    return text


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"composio_execute {name!r} must be a string")
    text = value.strip()
    return text or None
