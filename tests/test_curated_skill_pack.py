"""HIG-239 curated skill pack: selection hardening, tiering, dashboard provenance.

Agent E owns the Python/template changes for the pack: lexical fallback ranking,
richer embedding text, embed-on-ingest, the ranked-index K, default-pack
enablement seeding, and dashboard provenance/license surfacing.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.agent.context import (
    DEFAULT_SKILLS_CONTEXT_MAX_SKILLS,
    ContextAssembler,
)
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
from kortny.embeddings import EmbeddingIndex
from kortny.skills.embedding import SKILL_EMBEDDING_KIND, skill_embedding_text
from kortny.skills.ingestion import SkillIngestionService
from kortny.skills.service import (
    DEFAULT_PACK_ENABLEMENT_ADDED_BY,
    DEFAULT_PACK_SLUGS,
    PLAYBOOK_SKILL_SLUGS,
    SkillRegistryService,
)
from kortny.tasks import TaskService
from tests.fake_embeddings import FakeEmbeddingBackend, RaisingEmbeddingBackend

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="KORTNY_TEST_POSTGRES_URL is required for curated skill pack tests",
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


def cleanup_database(session: Session) -> None:
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


def create_installation(session: Session) -> Installation:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return installation


def create_task(
    session: Session,
    installation: Installation,
    *,
    input_text: str,
) -> Task:
    thread_ts = f"{uuid.uuid4().int % 10**6}.{uuid.uuid4().int % 10**6}"
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C123",
        slack_thread_ts=thread_ts,
        slack_message_ts=thread_ts,
        slack_user_id="U123",
        input=input_text,
    )


def write_skill_dir(
    root: Path,
    *,
    slug: str,
    description: str,
    tags: str,
    provenance: str | None = None,
    license_text: str | None = None,
) -> Path:
    directory = root / slug
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        "---\n"
        f"name: {slug}\n"
        f"description: {description}\n"
        "metadata:\n"
        "  version: 1.0.0\n"
        f"  display_name: {slug.replace('-', ' ').title()}\n"
        f"  tags: {tags}\n"
        "---\n\n"
        "## Steps\n\n1. Do the thing.\n",
        encoding="utf-8",
    )
    if provenance is not None:
        (directory / "PROVENANCE.md").write_text(provenance, encoding="utf-8")
    if license_text is not None:
        (directory / "LICENSE.txt").write_text(license_text, encoding="utf-8")
    return directory


# ---------------------------------------------------------------------------
# 1. Embedding text composition
# ---------------------------------------------------------------------------


def test_skill_embedding_text_includes_tags_and_triggers() -> None:
    text = skill_embedding_text(
        name="Thread Recap",
        description="Recap this thread.",
        intent_tags=("recap", "tldr"),
        trigger_phrases=("summarize the discussion",),
    )
    assert "Thread Recap. Recap this thread." in text
    assert "Tags: recap, tldr." in text
    assert "Triggers: summarize the discussion." in text


def test_skill_embedding_text_omits_empty_sections() -> None:
    text = skill_embedding_text(name="X", description="do x")
    assert text == "X. do x"


# ---------------------------------------------------------------------------
# 2. Lexical fallback ranking (no embedding index / failed rank)
# ---------------------------------------------------------------------------


def test_lexical_fallback_ranks_when_no_embedding_index(db_session: Session) -> None:
    installation = create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()
    task = create_task(
        db_session,
        installation,
        input_text="recap this thread with the decisions and action items",
    )

    # No embedding_index wired: ranking must fall back to lexical overlap and
    # still surface the thread-recap skill rather than returning nothing.
    package = ContextAssembler(session=db_session).build_for_task(task)

    assert package.skill_similarities
    slugs = [slug for slug, _ in package.skill_similarities]
    assert "thread-recap" in slugs
    assert slugs[0] == "thread-recap"
    assert package.selected_skills


def test_lexical_fallback_when_embedding_rank_fails(db_session: Session) -> None:
    installation = create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()
    task = create_task(
        db_session,
        installation,
        input_text="recap this thread please",
    )

    # A backend that raises makes EmbeddingIndex.rank return None; ranking must
    # fall back to lexical scoring rather than emptying the skill block.
    package = ContextAssembler(
        session=db_session,
        embedding_index=EmbeddingIndex(db_session, RaisingEmbeddingBackend()),
    ).build_for_task(task)

    assert package.skill_similarities
    assert package.selected_skills
    assert "thread-recap" in {s.slug for s in package.selected_skills}


# ---------------------------------------------------------------------------
# 3. Embed-on-ingest: a freshly ingested skill is embedded immediately
# ---------------------------------------------------------------------------


def test_ingest_embeds_skill_card_immediately(
    db_session: Session, tmp_path: Path
) -> None:
    backend = FakeEmbeddingBackend()
    index = EmbeddingIndex(db_session, backend)
    directory = write_skill_dir(
        tmp_path,
        slug="ingest-embed-demo",
        description="Use when running the ingest embed demo workflow.",
        tags="demo, ingest, embed",
    )

    SkillIngestionService(db_session, embedding_index=index).ingest_directory(
        directory,
        owner_type="system",
        owner_id=None,
        provenance="kortny",
        trust_level="trusted",
        created_by="test",
    )

    row = db_session.scalar(
        select(ToolEmbedding).where(
            ToolEmbedding.kind == SKILL_EMBEDDING_KIND,
            ToolEmbedding.ref_key == "ingest-embed-demo",
        )
    )
    assert row is not None
    # The embedded text drives the content sha; tags must be part of it.
    assert any("demo" in text for text in backend.passage_texts)


def test_ingest_without_index_is_backstopped_by_lazy_path(
    db_session: Session, tmp_path: Path
) -> None:
    directory = write_skill_dir(
        tmp_path,
        slug="no-index-demo",
        description="Use when no embedding index is wired at ingest.",
        tags="demo",
    )

    SkillIngestionService(db_session).ingest_directory(
        directory,
        owner_type="system",
        owner_id=None,
        provenance="kortny",
        trust_level="trusted",
        created_by="test",
    )

    # No index passed → no embedding row yet (the per-task ranker is the backstop).
    row = db_session.scalar(
        select(ToolEmbedding).where(ToolEmbedding.ref_key == "no-index-demo")
    )
    assert row is None


# ---------------------------------------------------------------------------
# 4. Ranked-index K and char budget
# ---------------------------------------------------------------------------


def test_ranked_index_capped_at_fifteen(db_session: Session, tmp_path: Path) -> None:
    assert DEFAULT_SKILLS_CONTEXT_MAX_SKILLS == 15
    installation = create_installation(db_session)
    registry = SkillRegistryService(db_session)
    # Seed and workspace-enable 20 distinct skills.
    for n in range(20):
        directory = write_skill_dir(
            tmp_path,
            slug=f"k-skill-{n:02d}",
            description=f"Use when handling scenario number {n} for the team.",
            tags="scenario, team",
        )
        ingested = SkillIngestionService(db_session).ingest_directory(
            directory,
            owner_type="system",
            owner_id=None,
            provenance="kortny",
            trust_level="trusted",
            created_by="test",
        )
        registry.enable_skill(
            installation_id=installation.id,
            skill_id=ingested.skill.id,
            scope_type="workspace",
            scope_id=None,
            added_by="test",
        )
    db_session.flush()
    task = create_task(db_session, installation, input_text="handle scenario for team")

    package = ContextAssembler(session=db_session).build_for_task(task)

    assert len(package.selected_skills) <= DEFAULT_SKILLS_CONTEXT_MAX_SKILLS
    # The 5 skills beyond K are recorded as an omission.
    assert any(
        omission.kind == "skills" and omission.reason == "skills_context_max_skills"
        for omission in package.omissions
    )


# ---------------------------------------------------------------------------
# 5. Similarity scores in the context_assembled event
# ---------------------------------------------------------------------------


def test_similarity_scores_recorded_in_context_event(db_session: Session) -> None:
    installation = create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()
    task = create_task(db_session, installation, input_text="recap this thread please")

    ContextAssembler(session=db_session).build_for_task(task)

    event = db_session.scalar(
        select(TaskEvent)
        .where(
            TaskEvent.task_id == task.id,
            TaskEvent.payload["message"].astext == "context_assembled",
        )
        .order_by(TaskEvent.created_at.desc())
    )
    assert event is not None
    similarities = event.payload.get("skill_similarities")
    assert isinstance(similarities, dict)
    assert similarities  # non-empty: scores were attached per slug


# ---------------------------------------------------------------------------
# 6. Default-pack tiering: playbook + default pack enabled, rest catalog-only
# ---------------------------------------------------------------------------


def test_default_pack_enabled_at_workspace_scope(db_session: Session) -> None:
    installation = create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()

    enabled_slugs = {
        slug
        for slug in db_session.scalars(
            select(ProceduralSkill.slug)
            .join(SkillEnablement, SkillEnablement.skill_id == ProceduralSkill.id)
            .where(
                SkillEnablement.installation_id == installation.id,
                SkillEnablement.scope_type == "workspace",
                SkillEnablement.status == "enabled",
            )
        )
    }
    # Every default-pack slug present in the tree is enabled.
    present_default = {
        slug
        for slug in DEFAULT_PACK_SLUGS
        if db_session.scalar(
            select(ProceduralSkill.id).where(ProceduralSkill.slug == slug)
        )
        is not None
    }
    assert present_default <= enabled_slugs
    assert set(PLAYBOOK_SKILL_SLUGS) <= enabled_slugs


def test_default_pack_enablement_uses_its_own_added_by(db_session: Session) -> None:
    create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()

    rows = list(
        db_session.scalars(
            select(SkillEnablement)
            .join(ProceduralSkill, ProceduralSkill.id == SkillEnablement.skill_id)
            .where(ProceduralSkill.slug.in_(DEFAULT_PACK_SLUGS))
        )
    )
    assert rows
    assert all(row.added_by == DEFAULT_PACK_ENABLEMENT_ADDED_BY for row in rows)


def test_non_default_curated_skill_is_catalog_only(db_session: Session) -> None:
    installation = create_installation(db_session)
    SkillRegistryService(db_session).ensure_curated_skills()

    # weekly-status-report is curated but neither playbook nor default-pack.
    catalog_slug = "weekly-status-report"
    skill_id = db_session.scalar(
        select(ProceduralSkill.id).where(ProceduralSkill.slug == catalog_slug)
    )
    assert skill_id is not None  # registered in the catalog
    enabled = db_session.scalar(
        select(SkillEnablement).where(
            SkillEnablement.installation_id == installation.id,
            SkillEnablement.skill_id == skill_id,
        )
    )
    assert enabled is None  # but not auto-enabled


def test_missing_default_pack_slug_is_skipped_not_crashed(
    db_session: Session,
) -> None:
    create_installation(db_session)
    service = SkillRegistryService(db_session)
    # Seed only a couple of skills; most DEFAULT_PACK_SLUGS will be absent.
    # ensure_curated_skills must warn-and-skip, never raise.
    service.ensure_curated_skills()  # idempotent; tolerates absent slugs
    # A second seed against the same DB stays a no-op and also never crashes.
    service.ensure_curated_skills()


# ---------------------------------------------------------------------------
# 7. Dashboard provenance + license surfacing
# ---------------------------------------------------------------------------


def test_ingest_captures_provenance_and_license_into_metadata(
    db_session: Session, tmp_path: Path
) -> None:
    directory = write_skill_dir(
        tmp_path,
        slug="prov-demo",
        description="Use when demonstrating provenance capture.",
        tags="demo",
        provenance="Source: github.com/acme/skills @ abc123 (2026-06-12)\nAdapted: Slack delivery.",
        license_text="MIT License\n\nPermission is hereby granted, free of charge...",
    )

    ingested = SkillIngestionService(db_session).ingest_directory(
        directory,
        owner_type="system",
        owner_id=None,
        provenance="kortny",
        trust_level="trusted",
        created_by="test",
    )

    metadata = ingested.version.metadata_json
    assert "github.com/acme/skills" in metadata.get("provenance_md", "")
    assert metadata.get("license_name") == "MIT"
    assert "Permission is hereby granted" in metadata.get("license_text", "")


def test_dashboard_entry_exposes_license_and_provenance(
    db_session: Session, tmp_path: Path
) -> None:
    from kortny.dashboard.skills_data import get_skills_dashboard

    installation = create_installation(db_session)
    directory = write_skill_dir(
        tmp_path,
        slug="dash-prov-demo",
        description="Use when checking dashboard provenance render.",
        tags="demo",
        provenance="Source: github.com/acme/x @ deadbee",
        license_text="Apache License\nVersion 2.0",
    )
    SkillIngestionService(db_session).ingest_directory(
        directory,
        owner_type="system",
        owner_id=None,
        provenance="kortny",
        trust_level="trusted",
        created_by="test",
    )
    db_session.flush()

    dashboard = get_skills_dashboard(db_session, installation.id)
    entry = next(e for e in dashboard.curated if e.slug == "dash-prov-demo")
    assert entry.license_name == "Apache-2.0"
    assert entry.provenance_md is not None
    assert "github.com/acme/x" in entry.provenance_md
