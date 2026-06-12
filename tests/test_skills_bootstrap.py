"""HIG-239 startup skill seeding (``kortny.skills.bootstrap``).

A fresh install must have the builtin + curated skill catalog (plus default
workspace enablements) before the first task runs, without waiting for an admin
to open the dashboard ``/skills`` page. These tests exercise the startup seeder
end to end against real Postgres: fresh-seed correctness, idempotency, the
None-embedding-backend path, and the advisory-lock-held skip.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from kortny.config import Settings
from kortny.config.settings import LLMProvider
from kortny.db.models import (
    Installation,
    ProceduralSkill,
    ProceduralSkillInvocation,
    ProceduralSkillVersion,
    SkillEnablement,
    SkillFile,
    Task,
    TaskEvent,
    ToolEmbedding,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.skills.bootstrap import seed_skills_at_startup
from kortny.skills.builtins import BUILTIN_SKILLS
from kortny.skills.service import DEFAULT_ENABLED_SLUGS

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for skill bootstrap tests",
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
def clean_db(engine: Engine) -> Iterator[Engine]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        _cleanup_database(session)
        session.commit()
    yield engine
    with session_factory() as session:
        _cleanup_database(session)
        session.commit()


def _cleanup_database(session: Session) -> None:
    for model in (
        ToolEmbedding,
        SkillEnablement,
        SkillFile,
        ProceduralSkillInvocation,
        ProceduralSkillVersion,
        ProceduralSkill,
        TaskEvent,
        Task,
        Installation,
    ):
        session.execute(delete(model))


def _make_settings(*, embeddings_backend: str = "disabled") -> Settings:
    assert TEST_POSTGRES_URL is not None
    return Settings.model_validate(
        {
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_APP_TOKEN": "xapp-test",
            "SLACK_SIGNING_SECRET": "signing-secret",
            "LLM_PROVIDER": LLMProvider.openrouter,
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "openai/gpt-test",
            "COMPOSIO_API_KEY": "composio-key",
            "POSTGRES_URL": TEST_POSTGRES_URL,
            "KORTNY_EMBEDDINGS_BACKEND": embeddings_backend,
        }
    )


def _create_installation(session: Session) -> uuid.UUID:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation.id


def _count_system_skills(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(ProceduralSkill)
            .where(ProceduralSkill.owner_type == "system")
        )
        or 0
    )


def test_seed_at_startup_creates_skills_and_default_enablements(
    clean_db: Engine,
) -> None:
    session_factory = make_session_factory(engine=clean_db)
    # An installation must exist for default workspace enablements to be seeded.
    with session_factory() as session:
        installation_id = _create_installation(session)
        session.commit()

    seed_skills_at_startup(session_factory, _make_settings())

    with session_factory() as session:
        assert _count_system_skills(session) > 0
        # Builtin skills (system-owned, seeded by ensure_builtin_skills) present.
        builtin_slugs = {definition.slug for definition in BUILTIN_SKILLS}
        seeded_builtins = set(
            session.scalars(
                select(ProceduralSkill.slug).where(
                    ProceduralSkill.owner_type == "system",
                    ProceduralSkill.slug.in_(builtin_slugs),
                )
            )
        )
        assert seeded_builtins == builtin_slugs
        # Default-enabled curated skills produced workspace enablements.
        enablement_count = int(
            session.scalar(
                select(func.count())
                .select_from(SkillEnablement)
                .where(
                    SkillEnablement.installation_id == installation_id,
                    SkillEnablement.scope_type == "workspace",
                    SkillEnablement.status == "enabled",
                )
            )
            or 0
        )
        assert enablement_count > 0
        assert enablement_count <= len(DEFAULT_ENABLED_SLUGS)


def test_seed_at_startup_is_idempotent(clean_db: Engine) -> None:
    session_factory = make_session_factory(engine=clean_db)
    with session_factory() as session:
        installation_id = _create_installation(session)
        session.commit()

    settings = _make_settings()
    seed_skills_at_startup(session_factory, settings)
    with session_factory() as session:
        first_skills = _count_system_skills(session)
        first_enablements = int(
            session.scalar(
                select(func.count())
                .select_from(SkillEnablement)
                .where(SkillEnablement.installation_id == installation_id)
            )
            or 0
        )

    seed_skills_at_startup(session_factory, settings)
    with session_factory() as session:
        assert _count_system_skills(session) == first_skills
        second_enablements = int(
            session.scalar(
                select(func.count())
                .select_from(SkillEnablement)
                .where(SkillEnablement.installation_id == installation_id)
            )
            or 0
        )
        assert second_enablements == first_enablements


def test_seed_at_startup_with_no_embedding_backend(clean_db: Engine) -> None:
    # "disabled" makes create_embedding_backend return None — seeding must still
    # populate the catalog (the lazy per-task ranker backstops embeddings).
    session_factory = make_session_factory(engine=clean_db)
    seed_skills_at_startup(
        session_factory, _make_settings(embeddings_backend="disabled")
    )

    with session_factory() as session:
        assert _count_system_skills(session) > 0


def test_seed_at_startup_skips_when_lock_held(clean_db: Engine) -> None:
    settings = _make_settings()
    lock_key = settings.skills_seed_advisory_lock_key
    session_factory = make_session_factory(engine=clean_db)

    # Hold the advisory lock on a dedicated session for the duration of the
    # seed call; the seeder must skip cleanly without writing any skills.
    holder = session_factory()
    try:
        acquired = bool(holder.scalar(select(func.pg_try_advisory_lock(lock_key))))
        assert acquired

        seed_skills_at_startup(session_factory, settings)

        with session_factory() as session:
            assert _count_system_skills(session) == 0
    finally:
        holder.execute(select(func.pg_advisory_unlock(lock_key)))
        holder.commit()
        holder.close()
