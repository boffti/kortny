"""Tests for the skill directory: models, ingestion, scoped enablement."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kortny.db.models import (
    Installation,
    ProceduralSkill,
    ProceduralSkillInvocation,
    ProceduralSkillVersion,
    SkillEnablement,
    SkillFile,
    Task,
    TaskEvent,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.tasks import TaskService

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for skill directory tests",
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


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation


def create_task(
    session: Session,
    installation: Installation | None = None,
    *,
    channel_id: str = "C123",
    user_id: str = "U123",
) -> Task:
    installation = installation or create_installation(session)
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id=channel_id,
        slack_thread_ts="123.456",
        slack_message_ts="123.456",
        slack_user_id=user_id,
        input="summarize the meeting notes from today",
    )


def create_skill(
    session: Session,
    *,
    slug: str = "demo-skill",
    owner_type: str = "system",
    owner_id: str | None = None,
    trust_level: str = "trusted",
    provenance: str = "kortny",
) -> tuple[ProceduralSkill, ProceduralSkillVersion]:
    skill = ProceduralSkill(
        slug=slug,
        owner_type=owner_type,
        owner_id=owner_id,
        status="active",
        trust_level=trust_level,
        visibility="catalog",
        provenance=provenance,
    )
    session.add(skill)
    session.flush()
    version = ProceduralSkillVersion(
        skill_id=skill.id,
        version="1.0.0",
        status="active",
        name=slug.replace("-", " ").title(),
        description=f"Use when the task involves {slug}.",
        instructions_md="## Steps\n1. Do the thing.",
        content_sha256="0" * 64,
        created_by="test",
    )
    session.add(version)
    session.flush()
    return skill, version


def cleanup_database(session: Session) -> None:
    for model in (
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


class TestSkillDirectoryModels:
    def test_skill_files_and_enablement_round_trip(self, db_session: Session) -> None:
        installation = create_installation(db_session)
        skill, version = create_skill(db_session)

        db_session.add(
            SkillFile(
                skill_version_id=version.id,
                path="references/notes.md",
                kind="reference",
                content_text="# Notes",
                size_bytes=7,
                sha256="a" * 64,
            )
        )
        db_session.add(
            SkillEnablement(
                installation_id=installation.id,
                skill_id=skill.id,
                scope_type="channel",
                scope_id="C42",
                added_by="dashboard:tester",
            )
        )
        db_session.flush()

        stored_file = db_session.scalar(select(SkillFile))
        assert stored_file is not None
        assert stored_file.kind == "reference"
        stored_enablement = db_session.scalar(select(SkillEnablement))
        assert stored_enablement is not None
        assert stored_enablement.status == "enabled"
        assert db_session.scalar(
            select(ProceduralSkill.provenance).where(ProceduralSkill.id == skill.id)
        ) == "kortny"

    def test_workspace_enablement_rejects_scope_id(self, db_session: Session) -> None:
        installation = create_installation(db_session)
        skill, _ = create_skill(db_session)

        db_session.add(
            SkillEnablement(
                installation_id=installation.id,
                skill_id=skill.id,
                scope_type="workspace",
                scope_id="C42",
                added_by="dashboard:tester",
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_duplicate_enablement_rejected(self, db_session: Session) -> None:
        installation = create_installation(db_session)
        skill, _ = create_skill(db_session)

        for _ in range(2):
            db_session.add(
                SkillEnablement(
                    installation_id=installation.id,
                    skill_id=skill.id,
                    scope_type="workspace",
                    scope_id=None,
                    added_by="dashboard:tester",
                )
            )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_legacy_trust_levels_rejected(self, db_session: Session) -> None:
        with pytest.raises(IntegrityError):
            create_skill(db_session, slug="legacy", trust_level="reviewed")
        db_session.rollback()
