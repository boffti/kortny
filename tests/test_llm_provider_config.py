import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from kortny.config import Settings
from kortny.db.models import (
    EncryptedSecret,
    Installation,
    LLMBudgetPolicy,
    LLMConfigAudit,
    LLMModelCatalog,
    LLMModelPricing,
    LLMProviderAccount,
    LLMTierAssignment,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.llm.provider_config import bootstrap_llm_provider_config_from_env

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for provider config tests",
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
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        cleanup_database(session)
        session.commit()
        yield session
        session.rollback()
        cleanup_database(session)
        session.commit()


def test_env_bootstrap_seeds_provider_models_tiers_and_audit(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    settings = build_settings()

    result = bootstrap_llm_provider_config_from_env(
        db_session,
        installation_id=installation.id,
        settings=settings,
        actor_slack_user_id="UAdmin",
    )

    provider = db_session.scalar(select(LLMProviderAccount))
    models = db_session.scalars(select(LLMModelCatalog)).all()
    assignments = db_session.scalars(select(LLMTierAssignment)).all()
    audit = db_session.scalar(select(LLMConfigAudit))

    assert result.created is True
    assert result.skipped_reason is None
    assert result.provider_account_id is not None
    assert result.model_count == 5
    assert result.tier_assignment_count == 5
    assert provider is not None
    assert provider.provider_kind == "openrouter"
    assert provider.status == "active"
    assert provider.encrypted_secret_id is None
    assert provider.metadata_json["credential_source"] == "env"
    assert provider.metadata_json["seeded_from_env"] is True
    assert {model.model_identifier for model in models} == {
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-pro",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-opus-4.8",
        "openai/gpt-5.1",
    }
    assert all(model.source == "env_bootstrap" for model in models)
    assert all(model.is_enabled for model in models)

    model_by_id = {model.id: model.model_identifier for model in models}
    tiers = {item.tier: model_by_id[item.model_catalog_id] for item in assignments}
    assert tiers == {
        "cheap_fast": "deepseek/deepseek-v4-flash",
        "standard": "deepseek/deepseek-v4-pro",
        "analysis": "anthropic/claude-sonnet-4.6",
        "document": "openai/gpt-5.1",
        "high_reasoning": "anthropic/claude-opus-4.8",
    }
    assert audit is not None
    assert audit.action == "bootstrap"
    assert audit.actor_slack_user_id == "UAdmin"
    assert audit.new_value is not None
    assert audit.new_value["credential_source"] == "env"
    assert audit.new_value["tiers"]["analysis"] == "anthropic/claude-sonnet-4.6"
    assert "secret-llm-key" not in str(provider.metadata_json)
    assert "secret-llm-key" not in str(audit.new_value)


def test_env_bootstrap_skips_when_provider_config_exists(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    existing = LLMProviderAccount(
        installation_id=installation.id,
        provider_kind="openrouter",
        display_name="Existing provider",
        status="active",
        health_status="ok",
        metadata_json={"credential_source": "test"},
    )
    db_session.add(existing)
    db_session.flush()

    result = bootstrap_llm_provider_config_from_env(
        db_session,
        installation_id=installation.id,
        settings=build_settings(),
    )

    provider_count = db_session.scalar(
        select(func.count()).select_from(LLMProviderAccount)
    )
    model_count = db_session.scalar(select(func.count()).select_from(LLMModelCatalog))

    assert result.created is False
    assert result.skipped_reason == "existing_provider_config"
    assert result.provider_account_id == existing.id
    assert provider_count == 1
    assert model_count == 0


def test_env_bootstrap_respects_force_env_escape_hatch(db_session: Session) -> None:
    installation = create_installation(db_session)

    result = bootstrap_llm_provider_config_from_env(
        db_session,
        installation_id=installation.id,
        settings=build_settings(LLM_CONFIG_FORCE_ENV=True),
    )

    provider_count = db_session.scalar(
        select(func.count()).select_from(LLMProviderAccount)
    )

    assert result.created is False
    assert result.skipped_reason == "force_env_enabled"
    assert result.provider_account_id is None
    assert provider_count == 0


def cleanup_database(session: Session) -> None:
    for model in (
        LLMConfigAudit,
        LLMBudgetPolicy,
        LLMTierAssignment,
        LLMModelPricing,
        LLMModelCatalog,
        LLMProviderAccount,
        EncryptedSecret,
        Installation,
    ):
        session.execute(delete(model))


def create_installation(session: Session) -> Installation:
    installation = Installation(
        slack_team_id=f"T{uuid.uuid4().hex}",
        team_name="Highbrow",
        bot_user_id="UKortny",
    )
    session.add(installation)
    session.flush()
    return installation


def build_settings(**overrides: Any) -> Settings:
    assert TEST_POSTGRES_URL is not None
    values: dict[str, Any] = {
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_APP_TOKEN": "xapp-test-token",
        "SLACK_SIGNING_SECRET": "test-signing-secret",
        "LLM_PROVIDER": "openrouter",
        "LLM_API_KEY": "secret-llm-key",
        "LLM_MODEL": "fallback/model",
        "LLM_CHEAP_MODEL": "deepseek/deepseek-v4-flash",
        "LLM_STANDARD_MODEL": "deepseek/deepseek-v4-pro",
        "LLM_ANALYSIS_MODEL": "anthropic/claude-sonnet-4.6",
        "LLM_DOCUMENT_MODEL": "openai/gpt-5.1",
        "LLM_HIGH_REASONING_MODEL": "anthropic/claude-opus-4.8",
        "POSTGRES_URL": TEST_POSTGRES_URL,
    }
    values.update(overrides)
    return Settings(**values)
