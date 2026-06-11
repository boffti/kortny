"""Tests for the HIG-209 first-run setup wizard (dashboard)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from kortny.dashboard import setup as dashboard_setup
from kortny.dashboard.app import create_app
from kortny.dashboard.settings import DashboardSettings
from kortny.dashboard.setup import (
    load_app_manifest,
    manifest_deep_link,
    render_env_block,
    validate_llm_key,
    validate_slack_token,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for dashboard setup tests",
)


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
def session_factory(engine: Engine) -> sessionmaker:
    return make_session_factory(engine=engine)


def _dashboard_settings() -> DashboardSettings:
    assert TEST_POSTGRES_URL is not None
    return DashboardSettings(
        postgres_url=TEST_POSTGRES_URL,
        username="admin",
        password="secret",
        session_secret="test-dashboard-session-secret",
    )


class FakeSlackAuthClient:
    """Fake Slack WebClient exposing only auth.test."""

    def __init__(self, token: str, *, ok: bool = True) -> None:
        self.token = token
        self._ok = ok
        self.auth_test_calls = 0

    def auth_test(self) -> dict[str, Any]:
        self.auth_test_calls += 1
        if not self._ok:
            return {"ok": False, "error": "invalid_auth"}
        return {
            "ok": True,
            "team": "Acme",
            "team_id": "T1",
            "user": "kortny",
            "user_id": "U1",
        }


# --- Pure helpers -----------------------------------------------------------


def test_manifest_deep_link_contains_urlencoded_manifest_with_scopes() -> None:
    manifest = load_app_manifest(app_name="Acme Bot")
    link = manifest_deep_link(manifest)

    parsed = urlsplit(link)
    assert parsed.netloc == "api.slack.com"
    assert parsed.path == "/apps"
    params = parse_qs(parsed.query)
    assert params["new_app"] == ["1"]
    decoded = json.loads(params["manifest_json"][0])
    # App name templated into the manifest.
    assert decoded["display_information"]["name"] == "Acme Bot"
    assert decoded["features"]["bot_user"]["display_name"] == "Acme Bot"
    # Real scopes preserved from manifest.json.
    bot_scopes = decoded["oauth_config"]["scopes"]["bot"]
    assert "app_mentions:read" in bot_scopes
    assert "chat:write" in bot_scopes
    assert "reactions:write" in bot_scopes
    assert decoded["settings"]["socket_mode_enabled"] is True


def test_render_env_block_emits_only_filled_values_in_order() -> None:
    block = render_env_block(
        {
            "LLM_PROVIDER": "openai",
            "LLM_API_KEY": "sk-test",
            "LLM_MODEL": "gpt-4o",
            "SLACK_BOT_TOKEN": "xoxb-1",
            "SLACK_APP_TOKEN": "",
            "SLACK_SIGNING_SECRET": "sign",
            "COMPOSIO_API_KEY": "",
            "OBSERVABILITY_ENABLED": "true",
        }
    )
    lines = block.splitlines()
    assert "LLM_PROVIDER=openai" in lines
    assert "LLM_API_KEY=sk-test" in lines
    assert "OBSERVABILITY_ENABLED=true" in lines
    # Blank values dropped.
    assert not any(line.startswith("SLACK_APP_TOKEN") for line in lines)
    assert not any(line.startswith("COMPOSIO_API_KEY") for line in lines)
    # Order follows ENV_FIELD_ORDER: provider before bot token.
    assert lines.index("LLM_PROVIDER=openai") < lines.index("SLACK_BOT_TOKEN=xoxb-1")


def test_validate_llm_key_probes_litellm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_check(**kwargs: Any) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(
        "kortny.llm.litellm_catalog.check_litellm_provider_key", fake_check
    )
    outcome = validate_llm_key(provider="openai", api_key="sk-test", model="gpt-4o")
    assert outcome.ok is True
    assert calls == [
        {"provider_kind": "openai", "api_key": "sk-test", "model": "gpt-4o"}
    ]


def test_validate_llm_key_rejects_blank_key() -> None:
    outcome = validate_llm_key(provider="openai", api_key="", model="gpt-4o")
    assert outcome.ok is False


def test_validate_slack_token_calls_auth_test() -> None:
    captured: list[FakeSlackAuthClient] = []

    def factory(token: str) -> FakeSlackAuthClient:
        client = FakeSlackAuthClient(token)
        captured.append(client)
        return client

    outcome = validate_slack_token(bot_token="xoxb-1", client_factory=factory)
    assert outcome.ok is True
    assert captured[0].auth_test_calls == 1
    assert "Acme" in outcome.message


def test_validate_slack_token_reports_auth_failure() -> None:
    outcome = validate_slack_token(
        bot_token="xoxb-bad",
        client_factory=lambda token: FakeSlackAuthClient(token, ok=False),
    )
    assert outcome.ok is False
    assert "invalid_auth" in outcome.message


# --- App-factory wiring -----------------------------------------------------


def test_setup_mode_funnels_all_routes_to_wizard(
    session_factory: sessionmaker,
) -> None:
    app = create_app(
        settings=_dashboard_settings(),
        session_factory=session_factory,
        setup_mode=True,
    )
    with TestClient(app) as test_client:
        # /setup renders the wizard with the manifest deep-link.
        wizard = test_client.get("/setup")
        assert wizard.status_code == 200
        assert "First-run setup" in wizard.text
        assert "api.slack.com/apps?new_app=1" in wizard.text

        # An arbitrary normal route is funnelled to the wizard.
        redirected = test_client.get("/tasks", follow_redirects=False)
        assert redirected.status_code == 303
        assert redirected.headers["location"] == "/setup"


def test_full_settings_serves_normal_app_and_setup_for_admin(
    session_factory: sessionmaker,
) -> None:
    app = create_app(
        settings=_dashboard_settings(),
        session_factory=session_factory,
        setup_mode=False,
    )
    with TestClient(app) as test_client:
        # Normal app: unauthenticated home redirects to login (not the wizard).
        home = test_client.get("/", follow_redirects=False)
        assert home.status_code == 303
        assert home.headers["location"].startswith("/login")

        # /setup is admin-gated in normal mode.
        anon = test_client.get("/setup", follow_redirects=False)
        assert anon.status_code == 303
        assert anon.headers["location"].startswith("/login")

        # After admin login, /setup is reachable for re-validation.
        test_client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=False,
        )
        wizard = test_client.get("/setup")
        assert wizard.status_code == 200
        assert "First-run setup" in wizard.text


def test_setup_validate_slack_handler_calls_auth_test_on_fake_client(
    session_factory: sessionmaker,
) -> None:
    app = create_app(
        settings=_dashboard_settings(),
        session_factory=session_factory,
        setup_mode=True,
    )
    captured: list[FakeSlackAuthClient] = []

    def factory(token: str) -> FakeSlackAuthClient:
        client = FakeSlackAuthClient(token)
        captured.append(client)
        return client

    app.state.setup_slack_client_factory = factory
    with TestClient(app) as test_client:
        response = test_client.post(
            "/setup/validate-slack",
            data={
                "app_name": "Kortny",
                "slack_bot_token": "xoxb-test",
                "slack_app_token": "xapp-test",
                "slack_signing_secret": "sign",
            },
        )
    assert response.status_code == 200
    assert captured and captured[0].auth_test_calls == 1
    assert "Connected to Acme" in response.text


def test_setup_validate_llm_handler_probes_and_render_env(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "kortny.dashboard.app.validate_llm_key",
        lambda **kwargs: dashboard_setup.ValidationOutcome(ok=True, message="ok!"),
    )
    app = create_app(
        settings=_dashboard_settings(),
        session_factory=session_factory,
        setup_mode=True,
    )
    with TestClient(app) as test_client:
        llm = test_client.post(
            "/setup/validate-llm",
            data={
                "llm_provider": "openai",
                "llm_api_key": "sk-x",
                "llm_model": "gpt-4o",
            },
        )
        assert llm.status_code == 200
        assert "ok!" in llm.text

        env = test_client.post(
            "/setup/render-env",
            data={
                "llm_provider": "openai",
                "llm_api_key": "sk-x",
                "llm_model": "gpt-4o",
                "app_name": "Kortny",
                "slack_bot_token": "xoxb-1",
                "slack_app_token": "xapp-1",
                "slack_signing_secret": "sign",
                "composio_api_key": "comp-1",
                "observability_enabled": "1",
            },
        )
        assert env.status_code == 200
        assert "LLM_API_KEY=sk-x" in env.text
        assert "SLACK_BOT_TOKEN=xoxb-1" in env.text
        assert "OBSERVABILITY_ENABLED=true" in env.text
