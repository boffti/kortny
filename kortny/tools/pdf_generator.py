"""ReportLab-backed PDF generation tool."""

from __future__ import annotations

import html
import re
import uuid
from pathlib import Path
from typing import Any, Protocol

from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib.styles import getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from sqlalchemy.orm import Session

from kortny.db.models import Artifact, TaskEventType
from kortny.tools.types import JsonObject, JsonSchema, ToolArtifact, ToolResult

PDF_MIME_TYPE = "application/pdf"
DEFAULT_FILENAME = "report.pdf"
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class TaskEventSink(Protocol):
    """Subset of TaskService needed for artifact event emission."""

    def append_event(
        self,
        task: uuid.UUID,
        event_type: TaskEventType | str,
        payload: dict[str, Any] | None = None,
    ) -> object:
        """Append an event for a task."""


class PdfGeneratorTool:
    """Generate a structured report PDF in a task working directory."""

    name = "pdf_generator"
    description = "Generates a PDF report from structured title and section content."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The report title.",
            },
            "sections": {
                "type": "array",
                "description": "Ordered report sections.",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {
                            "type": "string",
                            "description": "Section heading.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Section body text.",
                        },
                        "bullets": {
                            "type": "array",
                            "description": "Optional bullet points for the section.",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["heading"],
                    "additionalProperties": False,
                },
            },
            "filename": {
                "type": "string",
                "description": "Optional output filename. The .pdf suffix is enforced.",
                "default": DEFAULT_FILENAME,
            },
        },
        "required": ["title", "sections"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        *,
        working_dir: str | Path,
        session: Session | None = None,
        task_id: uuid.UUID | None = None,
        task_service: TaskEventSink | None = None,
    ) -> None:
        if (session is None) != (task_id is None):
            raise ValueError("session and task_id must be provided together")

        self.working_dir = Path(working_dir)
        self.session = session
        self.task_id = task_id
        self.task_service = task_service

    def invoke(self, args: JsonObject) -> ToolResult:
        """Generate a PDF and return artifact metadata."""

        title = _required_string(args, "title")
        sections = _parse_sections(args.get("sections"))
        filename = _safe_pdf_filename(args.get("filename"))
        self.working_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.working_dir / filename

        _build_pdf(output_path, title=title, sections=sections)
        size_bytes = output_path.stat().st_size
        artifact = ToolArtifact(
            filename=filename,
            path=str(output_path),
            mime_type=PDF_MIME_TYPE,
            size_bytes=size_bytes,
        )

        artifact_id: str | None = None
        if self.session is not None and self.task_id is not None:
            artifact_id = str(
                self._record_artifact(
                    filename=filename,
                    path=output_path,
                    size_bytes=size_bytes,
                ).id
            )

        return ToolResult(
            output={
                "filename": filename,
                "path": str(output_path),
                "mime_type": PDF_MIME_TYPE,
                "size_bytes": size_bytes,
                "artifact_id": artifact_id,
            },
            artifacts=(artifact,),
        )

    def _record_artifact(
        self,
        *,
        filename: str,
        path: Path,
        size_bytes: int,
    ) -> Artifact:
        assert self.session is not None
        assert self.task_id is not None

        artifact = Artifact(
            task_id=self.task_id,
            filename=filename,
            mime_type=PDF_MIME_TYPE,
            size_bytes=size_bytes,
            storage_path=str(path),
        )
        self.session.add(artifact)
        self.session.flush()

        if self.task_service is not None:
            self.task_service.append_event(
                self.task_id,
                TaskEventType.artifact_created,
                {
                    "artifact_id": str(artifact.id),
                    "filename": filename,
                    "mime_type": PDF_MIME_TYPE,
                    "size_bytes": size_bytes,
                    "storage_path": str(path),
                },
            )

        return artifact


def _build_pdf(
    output_path: Path,
    *,
    title: str,
    sections: list[dict[str, Any]],
) -> None:
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(_paragraph_text(title), styles["Title"]),
        Spacer(1, 0.25 * inch),
    ]

    for section in sections:
        story.append(Paragraph(_paragraph_text(section["heading"]), styles["Heading2"]))
        body = section.get("body")
        if isinstance(body, str) and body.strip():
            for paragraph in _split_paragraphs(body):
                story.append(Paragraph(_paragraph_text(paragraph), styles["BodyText"]))
                story.append(Spacer(1, 0.12 * inch))

        bullets = section.get("bullets")
        if isinstance(bullets, list):
            for bullet in bullets:
                if isinstance(bullet, str) and bullet.strip():
                    story.append(
                        Paragraph(f"- {_paragraph_text(bullet)}", styles["BodyText"])
                    )
                    story.append(Spacer(1, 0.08 * inch))

        story.append(Spacer(1, 0.18 * inch))

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title,
    )
    document.build(story)


def _parse_sections(raw_sections: object) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("pdf_generator requires a non-empty 'sections' array")

    sections: list[dict[str, Any]] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise ValueError("Each PDF section must be an object")
        heading = raw_section.get("heading")
        if not isinstance(heading, str) or not heading.strip():
            raise ValueError("Each PDF section requires a non-empty heading")
        body = raw_section.get("body")
        if body is not None and not isinstance(body, str):
            raise ValueError("PDF section body must be a string when provided")
        bullets = raw_section.get("bullets")
        if bullets is not None and (
            not isinstance(bullets, list)
            or not all(isinstance(bullet, str) for bullet in bullets)
        ):
            raise ValueError("PDF section bullets must be an array of strings")

        sections.append(
            {
                "heading": heading.strip(),
                "body": body,
                "bullets": bullets,
            }
        )

    return sections


def _required_string(args: JsonObject, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pdf_generator requires a non-empty {key!r} argument")
    return value.strip()


def _safe_pdf_filename(raw_filename: object) -> str:
    filename = raw_filename if isinstance(raw_filename, str) else DEFAULT_FILENAME
    safe_name = SAFE_FILENAME_RE.sub("_", Path(filename).name.strip())
    if safe_name in ("", ".", ".."):
        safe_name = DEFAULT_FILENAME
    if not safe_name.lower().endswith(".pdf"):
        safe_name = f"{safe_name}.pdf"
    return safe_name


def _split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]


def _paragraph_text(text: str) -> str:
    return html.escape(text).replace("\n", "<br/>")
