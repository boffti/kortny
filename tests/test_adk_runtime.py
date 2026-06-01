import os
import uuid
from typing import Any, cast

import pytest

from kortny.agent.adk_runtime import AdkAgentRuntime, adk_litellm_model_name
from kortny.config import load_settings
from kortny.db.models import Task
from kortny.tools import ToolRegistry
from kortny.tools.types import JsonObject, ToolResult


def test_adk_model_mapping_prefixes_openrouter_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-sonnet-test")

    settings = load_settings(env_file=None)

    assert adk_litellm_model_name(settings) == (
        "openrouter/anthropic/claude-sonnet-test"
    )


def test_adk_model_mapping_preserves_existing_openrouter_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/openai/gpt-test")

    settings = load_settings(env_file=None)

    assert adk_litellm_model_name(settings) == "openrouter/openai/gpt-test"


def test_adk_model_mapping_preserves_direct_provider_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-test")

    settings = load_settings(env_file=None)

    assert adk_litellm_model_name(settings) == "openai/gpt-test"


def test_adk_runtime_builds_root_agent_in_chat_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    settings = load_settings(env_file=None)

    runtime = AdkAgentRuntime(
        settings=settings,
        session=cast(Any, None),
        task_service=cast(Any, None),
    )

    agent = runtime._build_agent()

    assert agent.mode == "chat"


def test_adk_runtime_default_prompt_is_text_only_and_not_tool_claiming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    settings = load_settings(env_file=None)

    runtime = AdkAgentRuntime(
        settings=settings,
        session=cast(Any, None),
        task_service=cast(Any, None),
    )

    instruction = runtime._instruction()

    assert "Do not introduce yourself unless the user asks" in instruction
    assert "no tools are connected yet" in instruction
    assert "live integrations" in instruction
    assert "Use the available tools" not in instruction


def test_adk_runtime_prompt_switches_when_tools_are_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    settings = load_settings(env_file=None)

    runtime = AdkAgentRuntime(
        settings=settings,
        session=cast(Any, None),
        task_service=cast(Any, None),
        registry=ToolRegistry([_EchoTool()]),
    )

    instruction = runtime._instruction()

    assert "ADK tool-enabled migration" in instruction
    assert "no tools are connected yet" not in instruction


def test_adk_runtime_builds_agent_with_registry_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_settings_env(monkeypatch)
    settings = load_settings(env_file=None)
    task = Task(
        id=uuid.UUID("2c53f4e1-9d72-468d-ab18-5021d9e15dad"),
        installation_id=uuid.UUID("1c53f4e1-9d72-468d-ab18-5021d9e15dad"),
        slack_channel_id="C123",
        slack_thread_ts="123.456",
        slack_user_id="U123",
        input="echo this",
    )
    runtime = AdkAgentRuntime(
        settings=settings,
        session=cast(Any, None),
        task_service=cast(Any, None),
        registry=ToolRegistry([_EchoTool()]),
    )

    agent = runtime._build_agent(task=task)

    assert [getattr(tool, "name", None) for tool in agent.tools] == ["echo_tool"]


class _EchoTool:
    name = "echo_tool"
    description = "Echoes provided text."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def invoke(self, args: JsonObject) -> ToolResult:
        return ToolResult(output={"echo": args})


def set_required_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
        "SLACK_SIGNING_SECRET",
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_MODEL",
        "POSTGRES_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://kortny:kortny@localhost/kortny")
    os.environ.pop("OPENROUTER_API_KEY", None)
