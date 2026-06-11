"""First-run setup wizard (HIG-209 onboarding compression).

The dashboard process is the one always-reachable Kortny surface even before
``.env`` is complete: the app/worker/ambient services refuse to boot without the
required Slack/LLM/Postgres config, but the dashboard can still render a wizard
that walks an operator through provider validation, Slack app creation via a
pre-filled manifest deep-link, and a copyable ``.env`` block.

Two entry points wire into the dashboard app factory:

* SETUP-ONLY mode — when the full runtime :class:`Settings` cannot load (a
  :class:`SettingsError` from a missing required field), every route serves the
  wizard so the operator is never stranded on a 500.
* ``/setup`` — once config is complete, the same wizard stays reachable to an
  admin for re-validation.

This module owns the pure pieces (manifest templating, deep-link generation,
``.env`` rendering, validation) so the app factory only does routing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from kortny.config import SettingsError, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "manifest.json"

# Fields the wizard collects, grouped by step. These mirror the required runtime
# Settings fields plus the optional integrations from step 3.
LLM_PROVIDER_CHOICES = ("openai", "anthropic", "openrouter")

# Env keys the wizard renders into the copyable .env block. Order is stable so
# the rendered block reads top-to-bottom like the wizard steps.
ENV_FIELD_ORDER = (
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "SLACK_SIGNING_SECRET",
    "SLACK_APP_NAME",
    "COMPOSIO_API_KEY",
    "OBSERVABILITY_ENABLED",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
)


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    """Result of a live validation call (LLM key probe or Slack auth.test)."""

    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def settings_are_complete() -> bool:
    """Whether the full runtime Settings load (i.e. ``.env`` is complete)."""

    try:
        load_settings()
    except SettingsError:
        return False
    return True


def settings_error_message() -> str | None:
    """Return the concise SettingsError message, or ``None`` when complete."""

    try:
        load_settings()
    except SettingsError as exc:
        return str(exc)
    return None


def load_app_manifest(
    *, app_name: str, manifest_path: Path | None = None
) -> dict[str, Any]:
    """Load ``manifest.json`` and template the app name into it.

    The repo manifest is the source of truth for scopes and event
    subscriptions; we only swap the display/bot name so the created app carries
    the operator's chosen name.
    """

    path = manifest_path or MANIFEST_PATH
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    name = (app_name or "").strip() or "Kortny"
    display = manifest.setdefault("display_information", {})
    if isinstance(display, dict):
        display["name"] = name
    features = manifest.get("features")
    if isinstance(features, dict):
        bot_user = features.get("bot_user")
        if isinstance(bot_user, dict):
            bot_user["display_name"] = name
    return manifest


def manifest_deep_link(manifest: dict[str, Any]) -> str:
    """Build the Slack ``api.slack.com/apps`` create-from-manifest deep link."""

    encoded = quote(
        json.dumps(manifest, separators=(",", ":"), sort_keys=False),
        safe="",
    )
    return f"https://api.slack.com/apps?new_app=1&manifest_json={encoded}"


def render_env_block(values: dict[str, str]) -> str:
    """Render a copyable ``.env`` block from collected wizard values.

    Only non-empty values are emitted. The order follows ``ENV_FIELD_ORDER``;
    any extra keys the caller passes are appended afterwards in sorted order.
    """

    lines: list[str] = []
    seen: set[str] = set()
    for key in ENV_FIELD_ORDER:
        value = values.get(key)
        seen.add(key)
        if value is None or value == "":
            continue
        lines.append(f"{key}={value}")
    for key in sorted(values):
        if key in seen:
            continue
        value = values[key]
        if value:
            lines.append(f"{key}={value}")
    return "\n".join(lines)


def validate_llm_key(
    *,
    provider: str,
    api_key: str,
    model: str,
) -> ValidationOutcome:
    """Run a live 1-token probe through LiteLLM for the given provider key.

    NOTE: this is the ONE place a direct LiteLLM call is acceptable — there is
    no task context during first-run setup, so the usual ``LLMService`` path
    (which records usage + cost against a task) cannot apply. Feature code
    elsewhere must keep going through ``LLMService``.
    """

    provider_kind = (provider or "").strip().lower()
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if provider_kind not in LLM_PROVIDER_CHOICES:
        return ValidationOutcome(
            ok=False,
            message=f"Unsupported provider '{provider}'.",
        )
    if not api_key:
        return ValidationOutcome(ok=False, message="API key is required.")
    if not model:
        return ValidationOutcome(ok=False, message="Model identifier is required.")

    from kortny.llm.litellm_catalog import check_litellm_provider_key

    try:
        ok = check_litellm_provider_key(
            provider_kind=provider_kind,
            api_key=api_key,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 - surface any probe failure to the UI
        return ValidationOutcome(
            ok=False,
            message=f"Validation failed: {type(exc).__name__}: {exc}",
        )
    if ok:
        return ValidationOutcome(
            ok=True,
            message=f"{provider_kind} key validated for model {model}.",
        )
    return ValidationOutcome(
        ok=False,
        message="The provider rejected the API key or model.",
    )


def validate_slack_token(
    *,
    bot_token: str,
    client_factory: Any | None = None,
) -> ValidationOutcome:
    """Run a live ``auth.test`` against Slack for the pasted bot token."""

    token = (bot_token or "").strip()
    if not token:
        return ValidationOutcome(ok=False, message="Bot token is required.")

    if client_factory is not None:
        client = client_factory(token)
    else:  # pragma: no cover - exercised only with a real Slack token
        from slack_sdk import WebClient

        client = WebClient(token=token)

    try:
        response = client.auth_test()
    except Exception as exc:  # noqa: BLE001 - surface any auth failure to the UI
        return ValidationOutcome(
            ok=False,
            message=f"auth.test failed: {type(exc).__name__}: {exc}",
        )

    payload = _response_mapping(response)
    if not payload.get("ok", False):
        error = payload.get("error") or "auth.test returned not-ok"
        return ValidationOutcome(ok=False, message=f"auth.test failed: {error}")
    team = payload.get("team") or payload.get("team_id") or "your workspace"
    user = payload.get("user") or payload.get("user_id") or "the bot user"
    return ValidationOutcome(
        ok=True,
        message=f"Connected to {team} as {user}.",
        details={
            "team": str(payload.get("team") or ""),
            "team_id": str(payload.get("team_id") or ""),
            "user": str(payload.get("user") or ""),
            "user_id": str(payload.get("user_id") or ""),
        },
    )


def _response_mapping(response: Any) -> dict[str, Any]:
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if isinstance(response, dict):
        return response
    return {}
