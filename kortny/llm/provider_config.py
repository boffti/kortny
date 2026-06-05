"""DB-backed LLM provider configuration helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.config import Settings
from kortny.db.models import (
    LLMConfigAudit,
    LLMModelCatalog,
    LLMProviderAccount,
    LLMTierAssignment,
)
from kortny.llm.routing import ModelRouter, ModelRouteTier

ENV_BOOTSTRAP_SOURCE = "env_bootstrap"
ENV_CREDENTIAL_SOURCE = "env"
CONFIG_TIERS: tuple[ModelRouteTier, ...] = (
    ModelRouteTier.cheap_fast,
    ModelRouteTier.standard,
    ModelRouteTier.analysis,
    ModelRouteTier.document,
    ModelRouteTier.high_reasoning,
)


@dataclass(frozen=True, slots=True)
class LLMProviderBootstrapResult:
    """Result from an env-to-DB provider configuration bootstrap attempt."""

    created: bool
    skipped_reason: str | None
    provider_account_id: uuid.UUID | None
    model_count: int
    tier_assignment_count: int


def bootstrap_llm_provider_config_from_env(
    session: Session,
    *,
    installation_id: uuid.UUID,
    settings: Settings,
    actor_slack_user_id: str | None = None,
) -> LLMProviderBootstrapResult:
    """Seed provider/model/tier config from env when no DB config exists.

    This intentionally records only that credentials come from env. It does not
    copy the API key into the database; dashboard-managed secrets need the
    dedicated secret service planned for the next slice.
    """

    if settings.llm_config_force_env:
        return LLMProviderBootstrapResult(
            created=False,
            skipped_reason="force_env_enabled",
            provider_account_id=None,
            model_count=0,
            tier_assignment_count=0,
        )

    existing = session.scalar(
        select(LLMProviderAccount.id)
        .where(LLMProviderAccount.installation_id == installation_id)
        .limit(1)
    )
    if existing is not None:
        return LLMProviderBootstrapResult(
            created=False,
            skipped_reason="existing_provider_config",
            provider_account_id=existing,
            model_count=0,
            tier_assignment_count=0,
        )

    provider_kind = settings.llm_provider.value
    seeded_at = datetime.now(UTC).isoformat()
    routes = [
        ModelRouter(settings).route_for_tier(tier, reason="env_bootstrap")
        for tier in CONFIG_TIERS
    ]
    model_tiers: dict[str, list[str]] = {}
    for route in routes:
        model_tiers.setdefault(route.model, []).append(route.tier.value)

    provider = LLMProviderAccount(
        installation_id=installation_id,
        provider_kind=provider_kind,
        display_name=f"{provider_kind.title()} env provider",
        status="active",
        health_status="unknown",
        encrypted_secret_id=None,
        metadata_json={
            "credential_source": ENV_CREDENTIAL_SOURCE,
            "seeded_from_env": True,
            "seeded_at": seeded_at,
        },
    )
    session.add(provider)
    session.flush()

    catalog_by_model: dict[str, LLMModelCatalog] = {}
    for model_identifier, tiers in model_tiers.items():
        catalog = LLMModelCatalog(
            provider_account_id=provider.id,
            model_identifier=model_identifier,
            display_name=model_identifier,
            is_enabled=True,
            capabilities_json={},
            source=ENV_BOOTSTRAP_SOURCE,
            metadata_json={
                "credential_source": ENV_CREDENTIAL_SOURCE,
                "env_tiers": tiers,
                "seeded_from_env": True,
            },
        )
        session.add(catalog)
        catalog_by_model[model_identifier] = catalog
    session.flush()

    assignments: list[LLMTierAssignment] = []
    for route in routes:
        assignment = LLMTierAssignment(
            installation_id=installation_id,
            tier=route.tier.value,
            model_catalog_id=catalog_by_model[route.model].id,
            priority=1,
            is_active=True,
            routing_json={
                "source": ENV_BOOTSTRAP_SOURCE,
                "reason": route.reason,
            },
        )
        session.add(assignment)
        assignments.append(assignment)

    audit = LLMConfigAudit(
        installation_id=installation_id,
        actor_slack_user_id=actor_slack_user_id,
        action="bootstrap",
        entity_type="llm_provider_config",
        entity_id=str(provider.id),
        previous_value=None,
        new_value={
            "provider_account_id": str(provider.id),
            "provider_kind": provider.provider_kind,
            "credential_source": ENV_CREDENTIAL_SOURCE,
            "tiers": {route.tier.value: route.model for route in routes},
        },
    )
    session.add(audit)
    session.flush()

    return LLMProviderBootstrapResult(
        created=True,
        skipped_reason=None,
        provider_account_id=provider.id,
        model_count=len(catalog_by_model),
        tier_assignment_count=len(assignments),
    )
