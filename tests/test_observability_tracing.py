from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

import kortny.observability.tracing as tracing_module
from kortny.config import Settings
from kortny.observability.events import observability_payload
from kortny.observability.tracing import (
    configure_tracing,
    sanitize_span_attributes,
    start_span,
    tracing_enabled,
)


def test_tracing_is_noop_without_otlp_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tracing_module, "_CONFIGURED", False)
    monkeypatch.setattr(tracing_module, "_TRACING_ENABLED", False)

    configure_tracing(_settings(OTEL_EXPORTER_OTLP_ENDPOINT=""))

    assert tracing_enabled() is False
    with start_span("test.noop") as span:
        assert span is None


def test_sanitize_span_attributes_converts_non_otel_values() -> None:
    identifier = UUID("11111111-1111-4111-8111-111111111111")

    attributes = sanitize_span_attributes(
        {
            "uuid": identifier,
            "decimal": Decimal("1.25"),
            "mapping": {"identifier": identifier},
            "list": ["ok", identifier],
            "none": None,
        }
    )

    assert attributes == {
        "uuid": str(identifier),
        "decimal": "1.25",
        "mapping": f'{{"identifier":"{identifier}"}}',
        "list": f'["ok","{identifier}"]',
    }


def test_observability_payload_includes_active_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tracing_module,
        "current_trace_context",
        lambda: {"trace_id": "abc", "span_id": "def"},
    )

    assert observability_payload("event") == {
        "message": "event",
        "trace_id": "abc",
        "span_id": "def",
    }


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_APP_TOKEN": "xapp-test",
        "SLACK_SIGNING_SECRET": "secret",
        "LLM_PROVIDER": "openrouter",
        "LLM_API_KEY": "llm-key",
        "LLM_MODEL": "openai/gpt-4o",
        "POSTGRES_URL": "postgresql://kortny:kortny@localhost/kortny",
    }
    values.update(overrides)
    return Settings(**values)
