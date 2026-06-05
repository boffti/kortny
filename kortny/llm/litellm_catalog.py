"""LiteLLM-backed provider and model catalog helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class LiteLLMProviderOption:
    kind: str
    label: str
    description: str
    default_probe_model: str
    default_base_url: str | None = None
    supports_endpoint_discovery: bool = False
    needs_base_url: bool = False


@dataclass(frozen=True, slots=True)
class LiteLLMModelCandidate:
    model_identifier: str
    display_name: str
    provider_kind: str
    source: str
    capabilities: dict[str, object]
    metadata: dict[str, object]
    input_price_per_mtok: Decimal | None
    output_price_per_mtok: Decimal | None


LITELLM_PROVIDER_OPTIONS: tuple[LiteLLMProviderOption, ...] = (
    LiteLLMProviderOption(
        kind="openrouter",
        label="OpenRouter",
        description="Multi-provider gateway with one API key.",
        default_probe_model="openrouter/openai/gpt-4o-mini",
    ),
    LiteLLMProviderOption(
        kind="openai",
        label="OpenAI",
        description="OpenAI models and OpenAI-compatible endpoints.",
        default_probe_model="gpt-4o-mini",
        supports_endpoint_discovery=True,
    ),
    LiteLLMProviderOption(
        kind="anthropic",
        label="Anthropic",
        description="Claude models through Anthropic's API.",
        default_probe_model="claude-3-5-haiku-20241022",
        supports_endpoint_discovery=True,
    ),
    LiteLLMProviderOption(
        kind="gemini",
        label="Google Gemini",
        description="Gemini API models.",
        default_probe_model="gemini/gemini-2.0-flash",
        supports_endpoint_discovery=True,
    ),
    LiteLLMProviderOption(
        kind="xai",
        label="xAI",
        description="Grok models through xAI.",
        default_probe_model="xai/grok-2-latest",
        supports_endpoint_discovery=True,
    ),
    LiteLLMProviderOption(
        kind="fireworks_ai",
        label="Fireworks AI",
        description="Hosted open model inference.",
        default_probe_model="fireworks_ai/accounts/fireworks/models/llama-v3p1-8b-instruct",
        supports_endpoint_discovery=True,
    ),
    LiteLLMProviderOption(
        kind="azure",
        label="Azure OpenAI",
        description="Azure-hosted OpenAI deployments.",
        default_probe_model="azure/gpt-4o-mini",
        needs_base_url=True,
    ),
    LiteLLMProviderOption(
        kind="bedrock",
        label="Amazon Bedrock",
        description="AWS Bedrock models. Usually needs AWS environment or role config.",
        default_probe_model="bedrock/anthropic.claude-3-5-haiku-20241022-v1:0",
    ),
    LiteLLMProviderOption(
        kind="ollama",
        label="Ollama",
        description="Self-hosted local models through Ollama.",
        default_probe_model="ollama/llama3.1",
        default_base_url="http://localhost:11434",
        needs_base_url=True,
    ),
)

_PROVIDER_BY_KIND = {option.kind: option for option in LITELLM_PROVIDER_OPTIONS}


def litellm_provider_options() -> tuple[LiteLLMProviderOption, ...]:
    """Return curated provider options for the dashboard."""

    return LITELLM_PROVIDER_OPTIONS


def litellm_provider_option(kind: str) -> LiteLLMProviderOption | None:
    """Return a provider option by LiteLLM provider kind."""

    return _PROVIDER_BY_KIND.get(kind)


def litellm_model_candidates(
    provider_kind: str,
    *,
    limit: int = 24,
) -> tuple[LiteLLMModelCandidate, ...]:
    """Return local LiteLLM model-cost-map candidates for a provider."""

    model_cost = _litellm_model_cost()
    candidates = [
        _candidate_from_model_cost(
            model_identifier=model_identifier,
            provider_kind=provider_kind,
            info=info,
            source="litellm_catalog",
        )
        for model_identifier, info in model_cost.items()
        if _model_cost_row_matches(provider_kind, model_identifier, info)
    ]
    return tuple(_rank_candidates(provider_kind, candidates)[:limit])


def litellm_endpoint_model_candidates(
    provider_kind: str,
    *,
    api_key: str,
    api_base: str | None = None,
    limit: int = 24,
) -> tuple[LiteLLMModelCandidate, ...]:
    """Ask LiteLLM/provider endpoint for valid models when supported."""

    option = litellm_provider_option(provider_kind)
    if option is None or not option.supports_endpoint_discovery:
        return ()
    import litellm

    models = litellm.get_valid_models(
        check_provider_endpoint=True,
        custom_llm_provider=provider_kind,
        api_key=api_key,
        api_base=api_base,
    )
    local_by_model = {
        candidate.model_identifier: candidate
        for candidate in litellm_model_candidates(provider_kind, limit=500)
    }
    candidates: list[LiteLLMModelCandidate] = []
    for model_identifier in _unique_strings(models):
        local = local_by_model.get(model_identifier)
        if local is not None:
            candidates.append(
                LiteLLMModelCandidate(
                    model_identifier=local.model_identifier,
                    display_name=local.display_name,
                    provider_kind=local.provider_kind,
                    source="provider_api",
                    capabilities=local.capabilities,
                    metadata=local.metadata,
                    input_price_per_mtok=local.input_price_per_mtok,
                    output_price_per_mtok=local.output_price_per_mtok,
                )
            )
        else:
            candidates.append(
                LiteLLMModelCandidate(
                    model_identifier=model_identifier,
                    display_name=_display_name(model_identifier),
                    provider_kind=provider_kind,
                    source="provider_api",
                    capabilities={},
                    metadata={"litellm_provider": provider_kind},
                    input_price_per_mtok=None,
                    output_price_per_mtok=None,
                )
            )
        if len(candidates) >= limit:
            break
    return tuple(candidates)


def check_litellm_provider_key(
    *,
    provider_kind: str,
    api_key: str,
    model: str,
    api_base: str | None = None,
) -> bool:
    """Validate a provider key through LiteLLM helpers."""

    import litellm

    option = litellm_provider_option(provider_kind)
    if api_base or (option is not None and option.supports_endpoint_discovery):
        models = litellm.get_valid_models(
            check_provider_endpoint=True,
            custom_llm_provider=provider_kind,
            api_key=api_key,
            api_base=api_base,
        )
        return bool(models)
    return bool(litellm.check_valid_key(model=model, api_key=api_key))


def default_probe_model(provider_kind: str, fallback: str | None = None) -> str:
    """Return a reasonable provider-specific model for credential tests."""

    option = litellm_provider_option(provider_kind)
    if option is not None:
        return option.default_probe_model
    if fallback:
        return fallback
    return provider_kind


def _litellm_model_cost() -> Mapping[str, Mapping[str, Any]]:
    import litellm

    return cast(Mapping[str, Mapping[str, Any]], litellm.model_cost)


def _model_cost_row_matches(
    provider_kind: str,
    model_identifier: str,
    info: Mapping[str, Any],
) -> bool:
    if model_identifier == "sample_spec":
        return False
    if info.get("litellm_provider") != provider_kind:
        return False
    return info.get("mode") in {None, "chat", "completion"}


def _candidate_from_model_cost(
    *,
    model_identifier: str,
    provider_kind: str,
    info: Mapping[str, Any],
    source: str,
) -> LiteLLMModelCandidate:
    return LiteLLMModelCandidate(
        model_identifier=model_identifier,
        display_name=_display_name(model_identifier),
        provider_kind=provider_kind,
        source=source,
        capabilities=_capabilities_from_model_cost(info),
        metadata={
            key: value
            for key, value in info.items()
            if key
            in {
                "litellm_provider",
                "max_input_tokens",
                "max_output_tokens",
                "max_tokens",
                "mode",
                "source",
                "supported_endpoints",
                "supported_modalities",
                "supported_output_modalities",
            }
        },
        input_price_per_mtok=_price_per_mtok(info.get("input_cost_per_token")),
        output_price_per_mtok=_price_per_mtok(info.get("output_cost_per_token")),
    )


def _capabilities_from_model_cost(info: Mapping[str, Any]) -> dict[str, object]:
    return {
        key: value
        for key, value in info.items()
        if key.startswith("supports_") and isinstance(value, bool)
    }


def _price_per_mtok(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return (Decimal(str(value)) * Decimal("1000000")).quantize(Decimal("0.000001"))
    except Exception:
        return None


def _rank_candidates(
    provider_kind: str,
    candidates: Iterable[LiteLLMModelCandidate],
) -> list[LiteLLMModelCandidate]:
    preferred = {
        "openrouter": (
            "openrouter/openai/gpt-4o-mini",
            "openrouter/anthropic/claude-sonnet-4",
            "openrouter/deepseek/deepseek-chat",
        ),
        "openai": ("gpt-4o-mini", "gpt-4o", "gpt-5.1"),
        "anthropic": (
            "claude-3-5-haiku-20241022",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
        ),
        "gemini": ("gemini/gemini-2.0-flash", "gemini/gemini-2.5-flash"),
        "xai": ("xai/grok-2-latest", "xai/grok-3"),
    }.get(provider_kind, ())
    preferred_rank = {model: index for index, model in enumerate(preferred)}
    return sorted(
        candidates,
        key=lambda candidate: (
            preferred_rank.get(candidate.model_identifier, len(preferred_rank) + 1),
            candidate.display_name.lower(),
            candidate.model_identifier.lower(),
        ),
    )


def _display_name(model_identifier: str) -> str:
    return model_identifier.removeprefix("openrouter/")


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
