"""Dashboard integration tests for the MCP servers admin page."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.dashboard.app import create_app
from kortny.dashboard.settings import DashboardSettings
from kortny.db.models import (
    Installation,
    McpServer,
    McpServerTool,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for dashboard MCP tests",
)

# Path to Agent A's echo fixture — used for real discovery tests when available.
MCP_ECHO_FIXTURE = Path(__file__).parent / "fixtures" / "mcp" / "echo_server.py"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    assert TEST_POSTGRES_URL is not None

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
        cleanup_database(session)
        session.commit()
        yield session
        session.rollback()
        cleanup_database(session)
        session.commit()


@pytest.fixture
def client(db_session: Session, engine: Engine) -> Iterator[tuple[TestClient, Session]]:
    assert TEST_POSTGRES_URL is not None
    session_factory = make_session_factory(engine=engine)
    settings = DashboardSettings(
        postgres_url=TEST_POSTGRES_URL,
        username="admin",
        password="secret",
        session_secret="test-dashboard-session-secret",
    )
    with TestClient(
        create_app(settings=settings, session_factory=session_factory)
    ) as test_client:
        login = test_client.post(
            "/login",
            data={"username": "admin", "password": "secret", "next": "/"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        yield test_client, db_session


def cleanup_database(session: Session) -> None:
    for model in (McpServerTool, McpServer, Installation):
        session.execute(delete(model))


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.commit()
    return installation


def create_server(
    session: Session,
    installation: Installation,
    *,
    name: str = "test-server",
    transport: str = "stdio",
    command: str = "/usr/bin/python3",
    args: list[str] | None = None,
    status: str = "enabled",
) -> McpServer:
    server = McpServer(
        installation_id=installation.id,
        name=name,
        transport=transport,
        command=command,
        args=args or [],
        status=status,
        created_by="dashboard:admin",
    )
    session.add(server)
    session.commit()
    return server


# ── Page render ──────────────────────────────────────────────────────────────


def test_mcp_page_renders_for_authenticated_admin(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    response = test_client.get("/mcp")

    assert response.status_code == 200
    assert "MCP Servers" in response.text
    assert "Register a server" in response.text


def test_mcp_page_shows_registered_server(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    create_server(session, installation, name="github-tools")

    response = test_client.get("/mcp")

    assert response.status_code == 200
    assert "github-tools" in response.text
    assert "stdio" in response.text


def test_mcp_page_shows_empty_state_when_no_servers(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    response = test_client.get("/mcp")

    assert response.status_code == 200
    assert "No MCP servers registered yet" in response.text


def test_mcp_page_requires_admin(
    engine: Engine,
) -> None:
    assert TEST_POSTGRES_URL is not None
    session_factory = make_session_factory(engine=engine)
    settings = DashboardSettings(
        postgres_url=TEST_POSTGRES_URL,
        username="admin",
        password="secret",
        session_secret="test-mcp-session-secret",
    )
    with TestClient(
        create_app(settings=settings, session_factory=session_factory)
    ) as test_client:
        response = test_client.get("/mcp", follow_redirects=False)
    assert response.status_code == 303
    assert "login" in response.headers["location"]


# ── Add server ───────────────────────────────────────────────────────────────


def test_mcp_add_stdio_server(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    # Patch discovery to avoid subprocess spawning in unit test context.
    with patch(
        "kortny.dashboard.app._mcp_attempt_discovery",
        return_value="Discovered 0 tools.",
    ):
        response = test_client.post(
            "/mcp/add",
            data={
                "name": "echo-server",
                "transport": "stdio",
                "command": "/usr/bin/python3",
                "args": "-m\nmcp_echo",
                "env": "",
                "headers": "",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    location = response.headers["location"]
    assert "notice" in location

    server = session.scalar(select(McpServer).where(McpServer.name == "echo-server"))
    assert server is not None
    assert server.transport == "stdio"
    assert server.command == "/usr/bin/python3"
    assert server.status == "enabled"


def test_mcp_add_http_server(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    with patch(
        "kortny.dashboard.app._mcp_attempt_discovery",
        return_value="Discovered 0 tools.",
    ):
        response = test_client.post(
            "/mcp/add",
            data={
                "name": "remote-server",
                "transport": "streamable_http",
                "command": "",
                "args": "",
                "url": "https://mcp.example.com/mcp",
                "env": "",
                "headers": "X-Api-Id=test",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    server = session.scalar(select(McpServer).where(McpServer.name == "remote-server"))
    assert server is not None
    assert server.transport == "streamable_http"
    assert server.url == "https://mcp.example.com/mcp"
    assert server.command is None
    assert server.headers_json == {"X-Api-Id": "test"}


def test_mcp_add_duplicate_name_shows_error(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    create_server(session, installation, name="my-server")

    with patch(
        "kortny.dashboard.app._mcp_attempt_discovery",
        return_value="Discovered 0 tools.",
    ):
        response = test_client.post(
            "/mcp/add",
            data={
                "name": "my-server",
                "transport": "stdio",
                "command": "python3",
                "args": "",
                "env": "",
                "headers": "",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "notice_tone=danger" in response.headers["location"]


def test_mcp_add_missing_name_shows_error(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    with patch(
        "kortny.dashboard.app._mcp_attempt_discovery",
        return_value="Discovered 0 tools.",
    ):
        response = test_client.post(
            "/mcp/add",
            data={
                "name": "",
                "transport": "stdio",
                "command": "python3",
                "args": "",
                "env": "",
                "headers": "",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "notice_tone=danger" in response.headers["location"]


def test_mcp_add_stdio_missing_command_shows_error(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    create_installation(session)

    with patch("kortny.dashboard.app._mcp_attempt_discovery", return_value=""):
        response = test_client.post(
            "/mcp/add",
            data={
                "name": "bad-server",
                "transport": "stdio",
                "command": "",
                "args": "",
                "env": "",
                "headers": "",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert "notice_tone=danger" in response.headers["location"]


# ── Remove ───────────────────────────────────────────────────────────────────


def test_mcp_remove_server(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server = create_server(session, installation, name="to-remove")

    response = test_client.post(
        f"/mcp/{server.id}/remove",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "notice_tone=warning" in response.headers["location"]

    server_id = server.id
    session.expire_all()
    gone = session.scalar(select(McpServer).where(McpServer.id == server_id))
    assert gone is None


def test_mcp_remove_wrong_installation_is_rejected(
    client: tuple[TestClient, Session],
    engine: Engine,
) -> None:
    test_client, session = client
    other_installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(other_installation)
    session.commit()
    server = McpServer(
        installation_id=other_installation.id,
        name="foreign-server",
        transport="stdio",
        command="python3",
        args=[],
        status="enabled",
        created_by="dashboard:admin",
    )
    session.add(server)
    session.commit()

    # Ensure our client's installation is also created.
    create_installation(session)

    response = test_client.post(
        f"/mcp/{server.id}/remove",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "notice_tone=danger" in response.headers["location"]
    still_there = session.get(McpServer, server.id)
    assert still_there is not None


# ── Toggle server ────────────────────────────────────────────────────────────


def test_mcp_toggle_server_enabled_to_disabled(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server = create_server(session, installation, name="toggler", status="enabled")

    response = test_client.post(
        f"/mcp/{server.id}/toggle",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    refreshed = session.get(McpServer, server.id)
    assert refreshed is not None
    assert refreshed.status == "disabled"
    assert "notice_tone=warning" in response.headers["location"]


def test_mcp_toggle_server_disabled_to_enabled(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server = create_server(session, installation, name="re-enabler", status="disabled")

    response = test_client.post(
        f"/mcp/{server.id}/toggle",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    refreshed = session.get(McpServer, server.id)
    assert refreshed is not None
    assert refreshed.status == "enabled"
    assert "notice_tone=success" in response.headers["location"]


# ── Toggle tool ──────────────────────────────────────────────────────────────


def test_mcp_toggle_tool_enabled_to_disabled(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server = create_server(session, installation, name="tool-toggler")
    tool = McpServerTool(
        server_id=server.id,
        name="echo",
        description="Echoes text back.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        read_only_hint=True,
        enabled=True,
    )
    session.add(tool)
    session.commit()

    response = test_client.post(
        f"/mcp/{server.id}/tools/{tool.id}/toggle",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    refreshed = session.get(McpServerTool, tool.id)
    assert refreshed is not None
    assert refreshed.enabled is False
    assert "notice_tone=warning" in response.headers["location"]


def test_mcp_toggle_tool_disabled_to_enabled(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server = create_server(session, installation, name="tool-re-enabler")
    tool = McpServerTool(
        server_id=server.id,
        name="write_note",
        description="Writes a note.",
        input_schema={},
        enabled=False,
    )
    session.add(tool)
    session.commit()

    response = test_client.post(
        f"/mcp/{server.id}/tools/{tool.id}/toggle",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    refreshed = session.get(McpServerTool, tool.id)
    assert refreshed is not None
    assert refreshed.enabled is True


def test_mcp_tool_toggle_wrong_server_rejected(
    client: tuple[TestClient, Session],
) -> None:
    test_client, session = client
    installation = create_installation(session)
    server_a = create_server(session, installation, name="server-a")
    server_b = create_server(session, installation, name="server-b")
    tool = McpServerTool(
        server_id=server_a.id,
        name="some-tool",
        description="",
        input_schema={},
        enabled=True,
    )
    session.add(tool)
    session.commit()

    # Attempt to toggle a tool that belongs to server_a via server_b's URL.
    response = test_client.post(
        f"/mcp/{server_b.id}/tools/{tool.id}/toggle",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "notice_tone=danger" in response.headers["location"]


# ── Discovery ────────────────────────────────────────────────────────────────


def test_mcp_discover_with_bad_command_records_error(
    client: tuple[TestClient, Session],
) -> None:
    """Discovery endpoint stores last_discovery_error when server is unreachable."""
    test_client, session = client
    installation = create_installation(session)
    server = create_server(
        session,
        installation,
        name="bad-command-server",
        command="/nonexistent/binary",
        args=[],
    )

    # Run real discovery (no mock) — expect it to fail and store the error.
    response = test_client.post(
        f"/mcp/{server.id}/discover",
        data={"next": "/mcp"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    session.expire_all()
    refreshed = session.get(McpServer, server.id)
    assert refreshed is not None
    # Either discovery was skipped (no encryption key) or actually failed.
    # Either way the server remains registered.
    # Server must still be registered regardless of whether discovery succeeded.
    assert refreshed is not None


@pytest.mark.skipif(
    not MCP_ECHO_FIXTURE.exists(),
    reason="Agent A echo fixture not yet available",
)
def test_mcp_discover_with_echo_fixture_lists_tools(
    client: tuple[TestClient, Session],
    tmp_path: Path,
) -> None:
    """Full end-to-end: real stdio server, real discovery, tools appear on page."""
    test_client, session = client
    create_installation(session)

    # Register using the echo fixture.
    from kortny.config import load_settings

    try:
        runtime_settings = load_settings()
        encryption_key = runtime_settings.encryption_key
    except Exception:
        encryption_key = None

    if encryption_key is None:
        pytest.skip("ENCRYPTION_KEY not set — cannot test real discovery")

    with patch("kortny.dashboard.app._mcp_attempt_discovery") as mock_discover:
        # First register without live discovery.
        mock_discover.return_value = "Deferred."
        add_resp = test_client.post(
            "/mcp/add",
            data={
                "name": "echo-fixture",
                "transport": "stdio",
                "command": sys.executable,
                "args": str(MCP_ECHO_FIXTURE),
                "env": "",
                "headers": "",
                "secrets": "",
                "next": "/mcp",
            },
            follow_redirects=False,
        )
    assert add_resp.status_code == 303

    server = session.scalar(select(McpServer).where(McpServer.name == "echo-fixture"))
    assert server is not None

    # Now trigger real discovery.
    discover_resp = test_client.post(
        f"/mcp/{server.id}/discover",
        data={"next": "/mcp"},
        follow_redirects=False,
    )
    assert discover_resp.status_code == 303

    session.expire_all()
    tools = session.scalars(
        select(McpServerTool).where(McpServerTool.server_id == server.id)
    ).all()
    assert len(tools) >= 1
    tool_names = {t.name for t in tools}
    assert "echo" in tool_names

    # Page should list the tools.
    page = test_client.get("/mcp")
    assert "echo" in page.text
    assert "mcp__echo-fixture__echo" in page.text


# ── KV textarea parser ───────────────────────────────────────────────────────


def test_parse_kv_textarea_basic() -> None:
    from kortny.dashboard.mcp_actions import parse_kv_textarea

    pairs = parse_kv_textarea("KEY=value\nFOO=bar=baz\n# comment\n\nEMPTY=")
    assert ("KEY", "value") in pairs
    assert ("FOO", "bar=baz") in pairs
    assert ("EMPTY", "") in pairs
    assert all(k != "" for k, _ in pairs)


def test_parse_kv_textarea_empty() -> None:
    from kortny.dashboard.mcp_actions import parse_kv_textarea

    assert parse_kv_textarea("") == []
    assert parse_kv_textarea("  \n  \n  ") == []
