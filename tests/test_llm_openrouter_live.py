import os
from collections.abc import Mapping

import pytest
from dotenv import dotenv_values

from kortny.llm import ChatMessage, OpenRouterProvider

LIVE_TESTS_ENABLED = os.environ.get("KORTNY_RUN_LIVE_OPENROUTER_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE_TESTS_ENABLED,
    reason="set KORTNY_RUN_LIVE_OPENROUTER_TESTS=1 to run live OpenRouter tests",
)


def test_openrouter_live_chat_completion() -> None:
    provider = make_live_openrouter_provider()

    completion = provider.complete(
        [
            ChatMessage(
                role="user",
                content="Reply with exactly: kortny-openrouter-live-ok",
            )
        ]
    )

    assert completion.content is not None
    assert "kortny-openrouter-live-ok" in completion.content.lower()
    assert completion.usage.input_tokens > 0
    assert completion.usage.output_tokens > 0


def test_openrouter_live_accepts_tool_declarations() -> None:
    provider = make_live_openrouter_provider()

    completion = provider.complete(
        [
            ChatMessage(
                role="system",
                content=(
                    "When a provided tool can satisfy the user request, call the "
                    "tool instead of answering directly."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "Use the kortny_echo tool to echo the word live-ping. "
                    "Do not answer directly."
                ),
            ),
        ],
        [
            {
                "name": "kortny_echo",
                "description": "Echoes a short input string.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to echo.",
                        }
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            }
        ],
    )

    assert completion.usage.input_tokens > 0
    assert completion.usage.output_tokens >= 0
    assert completion.tool_calls
    assert completion.tool_calls[0].name == "kortny_echo"
    assert "live-ping" in str(completion.tool_calls[0].arguments).lower()


def make_live_openrouter_provider() -> OpenRouterProvider:
    env = load_test_env()
    provider = env.get("LLM_PROVIDER", "openrouter")
    if provider != "openrouter":
        pytest.skip("LLM_PROVIDER must be openrouter for live OpenRouter tests")

    api_key = env.get("LLM_API_KEY")
    model = env.get("LLM_MODEL")
    if not api_key or not model:
        pytest.skip("LLM_API_KEY and LLM_MODEL are required for live OpenRouter tests")

    return OpenRouterProvider(api_key=api_key, model=model)


def load_test_env() -> Mapping[str, str]:
    env_file_values = {
        key: value for key, value in dotenv_values(".env").items() if value is not None
    }
    return {**env_file_values, **os.environ}
