import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.db.models import (
    Artifact,
    EncryptedSecret,
    Installation,
    LLMUsage,
    ModelPricing,
    Task,
    TaskEvent,
    TaskEventType,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.execution import task_workspace
from kortny.tasks import TaskService
from kortny.tools import PdfGeneratorTool, ToolArtifact

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")


def test_pdf_generator_writes_valid_pdf(tmp_path: Path) -> None:
    result = PdfGeneratorTool(working_dir=tmp_path).invoke(report_args())
    output_path = Path(result.output["path"])

    assert output_path.exists()
    assert output_path.read_bytes().startswith(b"%PDF-")
    assert result.output["filename"] == "kortny-report.pdf"
    assert result.output["mime_type"] == "application/pdf"
    assert result.output["size_bytes"] == output_path.stat().st_size
    assert result.output["artifact_id"] is None
    assert result.artifacts == (
        ToolArtifact(
            filename="kortny-report.pdf",
            path=str(output_path),
            mime_type="application/pdf",
            size_bytes=output_path.stat().st_size,
        ),
    )


def test_pdf_generator_sanitizes_filename(tmp_path: Path) -> None:
    args = report_args(filename="../My Unsafe Report")

    result = PdfGeneratorTool(working_dir=tmp_path).invoke(args)

    assert result.output["filename"] == "My_Unsafe_Report.pdf"
    assert Path(result.output["path"]).parent == tmp_path


def test_pdf_generator_rejects_empty_sections(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sections"):
        PdfGeneratorTool(working_dir=tmp_path).invoke(
            {
                "title": "Empty report",
                "sections": [],
            }
        )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if TEST_POSTGRES_URL is None:
        pytest.skip("KORTNY_TEST_POSTGRES_URL is required for PDF artifact tests")

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


def test_pdf_generator_creates_artifact_row(
    db_session: Session,
    tmp_path: Path,
) -> None:
    task = create_task(db_session)
    task_service = TaskService(db_session)

    with task_workspace(task.id, base_dir=tmp_path) as workspace:
        result = PdfGeneratorTool(
            working_dir=workspace.path,
            session=db_session,
            task_id=task.id,
            task_service=task_service,
        ).invoke(report_args())
        output_path = Path(result.output["path"])

        artifact = db_session.scalar(
            select(Artifact).where(Artifact.task_id == task.id)
        )
        artifact_event = db_session.scalar(
            select(TaskEvent)
            .where(
                TaskEvent.task_id == task.id,
                TaskEvent.type == TaskEventType.artifact_created,
            )
            .order_by(TaskEvent.seq.desc())
            .limit(1)
        )

        assert artifact is not None
        assert artifact.filename == "kortny-report.pdf"
        assert artifact.mime_type == "application/pdf"
        assert artifact.size_bytes == output_path.stat().st_size
        assert artifact.storage_path == str(output_path)
        assert result.output["artifact_id"] == str(artifact.id)
        assert artifact_event is not None
        assert artifact_event.payload["artifact_id"] == str(artifact.id)
        assert artifact_event.payload["storage_path"] == str(output_path)


def report_args(filename: str = "kortny-report.pdf") -> dict[str, Any]:
    return {
        "title": "Kortny Research Report",
        "filename": filename,
        "sections": [
            {
                "heading": "Summary",
                "body": "Kortny generated this PDF from structured content.",
                "bullets": [
                    "The PDF is written into the task workspace.",
                    "The artifact metadata is returned to the caller.",
                ],
            },
            {
                "heading": "Details",
                "body": "Paragraph one.\n\nParagraph two.",
            },
        ],
    }


def cleanup_database(session: Session) -> None:
    for model in (
        Artifact,
        LLMUsage,
        TaskEvent,
        Task,
        ModelPricing,
        EncryptedSecret,
        Installation,
    ):
        session.execute(delete(model))


def create_task(session: Session) -> Task:
    installation = Installation(slack_team_id=f"T{uuid.uuid4().hex}")
    session.add(installation)
    session.flush()
    return TaskService(session).create_task(
        installation_id=installation.id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C123",
        slack_thread_ts="1716400000.000001",
        slack_message_ts="1716400000.000001",
        slack_user_id="U123",
        input="make a PDF",
    )
