"""Sync client bridge over the official ``mcp`` SDK.

Each entry point opens a fresh MCP session per call (connect, initialize, run
one request, close). This is stateless by design: stdio servers spawn a
subprocess per call (an accepted V1 tradeoff, see HIG-207), and HTTP transports
open a fresh connection. All async work runs under ``asyncio.run`` because
kortny tools are synchronous and the worker has no shared event loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from mcp import types as mcp_types
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from kortny.db.models import McpServer
from kortny.secrets import SecretEncryptionError, decrypt_secret_value

_T = TypeVar("_T")


class McpClientError(RuntimeError):
    """Raised on MCP connection or protocol failures."""


@dataclass(frozen=True, slots=True)
class DiscoveredTool:
    """A tool reported by an MCP server's ``tools/list`` response."""

    name: str
    description: str
    input_schema: dict
    read_only_hint: bool | None
    destructive_hint: bool | None


@dataclass(frozen=True, slots=True)
class McpToolCallResult:
    """Normalized result of an MCP ``tools/call``."""

    text: str
    structured: dict | None
    is_error: bool


def discover_server_tools(
    server: McpServer,
    *,
    encryption_key: str,
    timeout_seconds: int = 30,
) -> list[DiscoveredTool]:
    """Connect, initialize, list tools, and close. Returns discovered tools."""

    async def _run() -> list[DiscoveredTool]:
        async with _open_session(server, encryption_key=encryption_key) as session:
            result = await session.list_tools()
            return [_discovered_tool(tool) for tool in result.tools]

    return _run_sync(_run(), timeout_seconds=timeout_seconds, server=server)


def check_server(
    server: McpServer,
    *,
    encryption_key: str,
    timeout_seconds: int = 15,
) -> str:
    """Connect + initialize. Returns the server-reported ``name version``."""

    async def _run() -> str:
        async with _open_session(
            server, encryption_key=encryption_key, return_init=True
        ) as (session, init):
            del session
            info = init.serverInfo
            name = info.name or "unknown"
            version = info.version or "?"
            return f"{name} {version}"

    return _run_sync(_run(), timeout_seconds=timeout_seconds, server=server)


def call_server_tool(
    server: McpServer,
    tool_name: str,
    arguments: dict,
    *,
    encryption_key: str,
    timeout_seconds: int,
) -> McpToolCallResult:
    """Connect, initialize, call one tool, and close."""

    async def _run() -> McpToolCallResult:
        async with _open_session(server, encryption_key=encryption_key) as session:
            result = await session.call_tool(tool_name, arguments)
            return _tool_call_result(result)

    return _run_sync(_run(), timeout_seconds=timeout_seconds, server=server)


def _run_sync(
    coro: Coroutine[Any, Any, _T],
    *,
    timeout_seconds: int,
    server: McpServer,
) -> _T:
    async def _with_timeout() -> _T:
        try:
            return await asyncio.wait_for(coro, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise McpClientError(
                f"MCP server '{server.name}' timed out after {timeout_seconds}s"
            ) from exc

    try:
        return _run_coroutine(_with_timeout())
    except McpClientError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize every transport/proto error
        raise McpClientError(
            f"MCP server '{server.name}' ({server.transport}) failed: {exc}"
        ) from exc


def _run_coroutine(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run a coroutine to completion from sync code, loop or no loop.

    The worker calls these helpers from plain sync code where ``asyncio.run``
    is fine. Dashboard routes call them from threads that already host a
    running event loop (FastAPI/anyio), where ``asyncio.run`` raises — there
    we drive the coroutine on a fresh loop in a short-lived thread instead.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


@asynccontextmanager
async def _open_session(
    server: McpServer,
    *,
    encryption_key: str,
    return_init: bool = False,
) -> AsyncIterator[Any]:
    secrets = _decrypt_secret_env(server, encryption_key=encryption_key)
    async with (
        _open_transport(server, secrets=secrets) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        if return_init:
            yield session, init
        else:
            yield session


@asynccontextmanager
async def _open_transport(
    server: McpServer,
    *,
    secrets: dict[str, str],
) -> AsyncIterator[tuple[Any, Any]]:
    transport = server.transport
    if transport == "stdio":
        env = {**_string_dict(server.env_json), **secrets}
        params = StdioServerParameters(
            command=server.command or "",
            args=[str(arg) for arg in (server.args or [])],
            env=env or None,
        )
        async with stdio_client(params) as (read, write):
            yield read, write
    elif transport == "streamable_http":
        headers = {**_string_dict(server.headers_json), **secrets}
        async with streamablehttp_client(server.url or "", headers=headers) as (
            read,
            write,
            _get_session_id,
        ):
            yield read, write
    elif transport == "sse":
        headers = {**_string_dict(server.headers_json), **secrets}
        async with sse_client(server.url or "", headers=headers) as (read, write):
            yield read, write
    else:
        raise McpClientError(f"Unsupported MCP transport: {transport!r}")


def _decrypt_secret_env(
    server: McpServer,
    *,
    encryption_key: str,
) -> dict[str, str]:
    if not server.secret_env:
        return {}
    try:
        plaintext = decrypt_secret_value(
            bytes(server.secret_env), encryption_key=encryption_key
        )
    except SecretEncryptionError as exc:
        raise McpClientError(
            f"Could not decrypt secrets for MCP server '{server.name}'"
        ) from exc
    try:
        loaded = json.loads(plaintext)
    except json.JSONDecodeError as exc:
        raise McpClientError(
            f"Stored secrets for MCP server '{server.name}' are not valid JSON"
        ) from exc
    if not isinstance(loaded, dict):
        raise McpClientError(
            f"Stored secrets for MCP server '{server.name}' must be a JSON object"
        )
    return _string_dict(loaded)


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if v is not None}


def _discovered_tool(tool: mcp_types.Tool) -> DiscoveredTool:
    annotations = tool.annotations
    read_only = annotations.readOnlyHint if annotations is not None else None
    destructive = annotations.destructiveHint if annotations is not None else None
    schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else {}
    return DiscoveredTool(
        name=tool.name,
        description=tool.description or "",
        input_schema=dict(schema),
        read_only_hint=read_only,
        destructive_hint=destructive,
    )


def _tool_call_result(result: mcp_types.CallToolResult) -> McpToolCallResult:
    text_parts: list[str] = []
    for block in result.content:
        if isinstance(block, mcp_types.TextContent):
            text_parts.append(block.text)
        else:
            text_parts.append(_non_text_summary(block))
    structured = (
        dict(result.structuredContent)
        if isinstance(result.structuredContent, dict)
        else None
    )
    return McpToolCallResult(
        text="\n".join(part for part in text_parts if part),
        structured=structured,
        is_error=bool(result.isError),
    )


def _non_text_summary(block: Any) -> str:
    block_type = getattr(block, "type", "content")
    return f"[{block_type} content block]"


__all__ = [
    "DiscoveredTool",
    "McpClientError",
    "McpToolCallResult",
    "call_server_tool",
    "check_server",
    "discover_server_tools",
]
