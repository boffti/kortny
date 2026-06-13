"""DB-backed tests for HIG-169 P0.3 tool pinning + drift, and P0.2 gating.

Real Postgres (per the project's no-mock-DB rule): exercises pin-on-first-sight,
drift detection that flips a pin to ``drifted``, admin re-pin, the MCP discovery
hook in ``upsert_discovered_tools``, and the McpExecuteTool read-only bypass
gate driven by server trust tier + pin status.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.approvals import ApprovalScope, ToolApprovalPolicy
from kortny.autonomy import AutonomyLevel
from kortny.dashboard.mcp_actions import (
    add_mcp_server,
    repin_mcp_tool,
    set_mcp_trust_tier,
    upsert_discovered_tools,
)
from kortny.db.models import (
    Installation,
    McpServer,
    McpServerTool,
    Task,
    TaskEvent,
    ToolPin,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.tools.mcp_execute import McpExecuteTool
from kortny.tools.pinning import ToolPinService, compute_tool_fingerprint

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")


@dataclass
class _DiscoveredTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if TEST_POSTGRES_URL is None:
        pytest.skip("KORTNY_TEST_POSTGRES_URL is required for pinning tests")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", normalize_database_url(TEST_POSTGRES_URL))
    command.upgrade(config, "head")
    engine = make_engine(TEST_POSTGRES_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        _cleanup(session)
        session.commit()
        yield session
        session.rollback()
        _cleanup(session)
        session.commit()


def _cleanup(session: Session) -> None:
    for model in (ToolPin, TaskEvent, McpServerTool, McpServer, Task, Installation):
        session.execute(delete(model))


def _installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation


def _server(
    session: Session, installation: Installation, *, trust_tier: str
) -> McpServer:
    server = add_mcp_server(
        session,
        installation_id=installation.id,
        name=f"srv{uuid.uuid4().hex[:8]}",
        transport="stdio",
        command="run-server",
        args=[],
        url=None,
        env_pairs=[],
        header_pairs=[],
        secret_pairs=[],
        created_by="admin",
        encryption_key=None,
    )
    if trust_tier != "untrusted":
        set_mcp_trust_tier(
            session,
            installation_id=installation.id,
            server_id=server.id,
            trust_tier=trust_tier,
        )
    return server


# --- ToolPinService -----------------------------------------------------------


def test_pin_on_first_sight_then_drift_then_repin(db_session: Session) -> None:
    installation = _installation(db_session)
    service = ToolPinService(db_session)
    fp1 = compute_tool_fingerprint(
        name="fetch", description="reads", input_schema={"properties": {}}
    )

    # First sight: pinned active.
    first = service.check_and_pin(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
        fingerprint=fp1,
    )
    assert first.pinned and not first.drifted
    assert service.is_clean(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
    )

    # Re-check unchanged: no-op, still clean.
    again = service.check_and_pin(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
        fingerprint=fp1,
    )
    assert not again.pinned and not again.drifted

    # Schema changes (rug pull): drift flagged, pin no longer clean.
    fp2 = compute_tool_fingerprint(
        name="fetch",
        description="reads",
        input_schema={"properties": {"exfil": {"type": "string"}}},
    )
    drift = service.check_and_pin(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
        fingerprint=fp2,
    )
    assert drift.drifted
    assert not service.is_clean(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
    )

    # Admin re-pin restores clean status.
    service.repin(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
        approved_by="admin",
    )
    assert service.is_clean(
        installation_id=installation.id,
        provider="mcp",
        server_ref="srv-1",
        tool_name="fetch",
    )


def test_is_clean_false_when_unpinned(db_session: Session) -> None:
    installation = _installation(db_session)
    service = ToolPinService(db_session)
    assert not service.is_clean(
        installation_id=installation.id,
        provider="mcp",
        server_ref="never-seen",
        tool_name="x",
    )


# --- MCP discovery hook (upsert_discovered_tools) -----------------------------


def test_discovery_pins_then_drift_on_schema_change(db_session: Session) -> None:
    installation = _installation(db_session)
    server = _server(db_session, installation, trust_tier="trusted")

    upsert_discovered_tools(
        db_session,
        server=server,
        discovered=[
            _DiscoveredTool(
                name="search",
                description="search the web",
                input_schema={"type": "object", "properties": {"q": {}}},
                read_only_hint=True,
            )
        ],
        error=None,
    )
    pin = db_session.scalar(
        select(ToolPin).where(
            ToolPin.installation_id == installation.id,
            ToolPin.provider == "mcp",
            ToolPin.tool_name == "search",
        )
    )
    assert pin is not None and pin.status == "active"

    # Re-discover with a mutated input schema -> drift.
    upsert_discovered_tools(
        db_session,
        server=server,
        discovered=[
            _DiscoveredTool(
                name="search",
                description="search the web",
                input_schema={
                    "type": "object",
                    "properties": {"q": {}, "callback": {"type": "string"}},
                },
                read_only_hint=True,
            )
        ],
        error=None,
    )
    db_session.refresh(pin)
    assert pin.status == "drifted"


# --- P0.2 McpExecuteTool read-only bypass gate --------------------------------


def _mcp_tool(
    session: Session,
    server: McpServer,
    *,
    read_only_bypass_allowed: bool,
) -> McpExecuteTool:
    tool = McpServerTool(
        server_id=server.id,
        name="read_thing",
        description="read-only",
        input_schema={"type": "object", "properties": {}},
        read_only_hint=True,
        destructive_hint=False,
        enabled=True,
    )
    session.add(tool)
    session.flush()
    return McpExecuteTool(
        session=session,
        task=None,
        server=server,
        tool=tool,
        encryption_key="k",
        timeout_seconds=10,
        read_only_bypass_allowed=read_only_bypass_allowed,
    )


def test_untrusted_server_read_only_requires_approval(db_session: Session) -> None:
    installation = _installation(db_session)
    server = _server(db_session, installation, trust_tier="untrusted")
    tool = _mcp_tool(db_session, server, read_only_bypass_allowed=False)
    policy = ToolApprovalPolicy()
    # Conservative makes the revoked bypass visible as a user-approval gate.
    requirement = policy.requirement_for(
        tool, {}, autonomy_level=AutonomyLevel.conservative
    )
    assert requirement.scope is ApprovalScope.user


def test_trusted_pinned_server_read_only_is_free(db_session: Session) -> None:
    installation = _installation(db_session)
    server = _server(db_session, installation, trust_tier="trusted")
    tool = _mcp_tool(db_session, server, read_only_bypass_allowed=True)
    policy = ToolApprovalPolicy()
    requirement = policy.requirement_for(
        tool, {}, autonomy_level=AutonomyLevel.conservative
    )
    assert requirement.scope is ApprovalScope.none


def test_repin_mcp_tool_action_clears_drift(db_session: Session) -> None:
    installation = _installation(db_session)
    server = _server(db_session, installation, trust_tier="trusted")
    upsert_discovered_tools(
        db_session,
        server=server,
        discovered=[
            _DiscoveredTool(name="t", description="d", input_schema={"properties": {}})
        ],
        error=None,
    )
    # Force drift.
    upsert_discovered_tools(
        db_session,
        server=server,
        discovered=[
            _DiscoveredTool(
                name="t",
                description="d",
                input_schema={"properties": {"y": {"type": "string"}}},
            )
        ],
        error=None,
    )
    tool = db_session.scalar(
        select(McpServerTool).where(McpServerTool.server_id == server.id)
    )
    assert tool is not None
    repin_mcp_tool(
        db_session,
        installation_id=installation.id,
        server_id=server.id,
        tool_id=tool.id,
        approved_by="admin",
    )
    assert ToolPinService(db_session).is_clean(
        installation_id=installation.id,
        provider="mcp",
        server_ref=str(server.id),
        tool_name="t",
    )
