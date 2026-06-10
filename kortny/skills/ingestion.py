"""SKILL.md ingestion: parse skill directories/zips/markdown into the registry.

Format validation delegates to ADK's skill models
(``google.adk.skills.models``: ``Frontmatter``/``Skill``) so community
Claude/Codex/ADK skills import verbatim. The directory walk is our own rather
than ADK's ``load_skill_from_dir`` because ADK requires the directory name to
match the frontmatter name — uploaded zips rarely satisfy that. Storage is
kortny's multi-tenant ``ProceduralSkill`` registry; bundled resources land in
``skill_files``. Scripts are stored but never executed here (trust-gated
sandbox execution is a later slice).
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from google.adk.skills.models import Frontmatter, Resources, Script, Skill
from sqlalchemy import select
from sqlalchemy.orm import Session

from kortny.db.models import ProceduralSkill, ProceduralSkillVersion, SkillFile

MAX_SKILL_ARCHIVE_BYTES = 16 * 1024 * 1024
DEFAULT_SKILL_VERSION = "1.0.0"
RESOURCE_KINDS = ("reference", "asset", "script")
_RESOURCE_DIRS = {"references": "reference", "assets": "asset", "scripts": "script"}


class SkillIngestionError(ValueError):
    """Raised when a skill directory, archive, or markdown cannot be ingested."""


@dataclass(frozen=True, slots=True)
class IngestedSkill:
    """Result of ingesting one skill into the registry."""

    skill: ProceduralSkill
    version: ProceduralSkillVersion
    files: list[SkillFile]
    created_new_version: bool


class SkillIngestionService:
    """Parses SKILL.md content via ADK and upserts the skill registry."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest_directory(
        self,
        directory: Path,
        *,
        owner_type: str,
        owner_id: str | None,
        provenance: str,
        trust_level: str,
        created_by: str,
    ) -> IngestedSkill:
        """Load a skill directory (SKILL.md + references/assets/scripts)."""

        parsed = _load_skill_dir(Path(directory))
        binary_files = _collect_binary_files(Path(directory))
        return self._persist(
            parsed,
            binary_files=binary_files,
            owner_type=owner_type,
            owner_id=owner_id,
            provenance=provenance,
            trust_level=trust_level,
            created_by=created_by,
        )

    def ingest_zip(
        self,
        data: bytes,
        *,
        owner_type: str,
        owner_id: str | None,
        provenance: str,
        trust_level: str,
        created_by: str,
    ) -> IngestedSkill:
        """Extract an uploaded skill zip safely and ingest it as a directory."""

        if len(data) > MAX_SKILL_ARCHIVE_BYTES:
            raise SkillIngestionError(
                f"Skill archive exceeds {MAX_SKILL_ARCHIVE_BYTES // (1024 * 1024)}MB."
            )
        with tempfile.TemporaryDirectory(prefix="kortny-skill-") as tmp:
            extract_root = Path(tmp) / "extracted"
            _safe_extract_zip(data, extract_root)
            skill_root = _find_skill_root(extract_root)
            return self.ingest_directory(
                skill_root,
                owner_type=owner_type,
                owner_id=owner_id,
                provenance=provenance,
                trust_level=trust_level,
                created_by=created_by,
            )

    def ingest_markdown(
        self,
        content: str,
        *,
        owner_type: str,
        owner_id: str | None,
        provenance: str,
        trust_level: str,
        created_by: str,
        fallback_name: str | None = None,
        fallback_description: str | None = None,
    ) -> IngestedSkill:
        """Ingest a pasted SKILL.md; synthesize frontmatter when missing."""

        content = content.strip()
        if not content:
            raise SkillIngestionError("Skill markdown content is empty.")
        if content.startswith("---"):
            frontmatter, body = _parse_skill_markdown(content)
        else:
            if not fallback_name:
                raise SkillIngestionError(
                    "Markdown has no YAML frontmatter; a skill name is required."
                )
            description = fallback_description or _first_text_line(content)
            try:
                frontmatter = Frontmatter(
                    name=_slugify(fallback_name),
                    description=description[:1024],
                )
            except ValueError as exc:
                raise SkillIngestionError(str(exc)) from exc
            body = content
        parsed = Skill(frontmatter=frontmatter, instructions=body)
        return self._persist(
            parsed,
            binary_files={},
            owner_type=owner_type,
            owner_id=owner_id,
            provenance=provenance,
            trust_level=trust_level,
            created_by=created_by,
        )

    def _persist(
        self,
        parsed: Skill,
        *,
        binary_files: dict[str, bytes],
        owner_type: str,
        owner_id: str | None,
        provenance: str,
        trust_level: str,
        created_by: str,
    ) -> IngestedSkill:
        slug = parsed.frontmatter.name
        skill = self.session.scalar(
            select(ProceduralSkill).where(
                ProceduralSkill.owner_type == owner_type,
                ProceduralSkill.owner_id == owner_id
                if owner_id is not None
                else ProceduralSkill.owner_id.is_(None),
                ProceduralSkill.slug == slug,
            )
        )
        if skill is None:
            skill = ProceduralSkill(
                slug=slug,
                owner_type=owner_type,
                owner_id=owner_id,
                status="active",
                trust_level=trust_level,
                visibility="catalog",
                provenance=provenance,
            )
            self.session.add(skill)
            self.session.flush()
        else:
            skill.status = "active"
            skill.provenance = provenance

        text_files = _resource_text_files(parsed)
        content_hash = _content_sha256(parsed, text_files, binary_files)

        latest = self.session.scalar(
            select(ProceduralSkillVersion)
            .where(
                ProceduralSkillVersion.skill_id == skill.id,
                ProceduralSkillVersion.status == "active",
            )
            .order_by(ProceduralSkillVersion.created_at.desc())
        )
        if latest is not None and latest.content_sha256 == content_hash:
            files = list(
                self.session.scalars(
                    select(SkillFile).where(SkillFile.skill_version_id == latest.id)
                )
            )
            return IngestedSkill(
                skill=skill, version=latest, files=files, created_new_version=False
            )

        declared_version = str(parsed.frontmatter.metadata.get("version") or "").strip()
        if latest is None:
            version_str = declared_version or DEFAULT_SKILL_VERSION
        else:
            latest.status = "deprecated"
            if declared_version and declared_version != latest.version:
                version_str = declared_version
            else:
                version_str = _bump_patch(latest.version)

        allowed_tools = (parsed.frontmatter.allowed_tools or "").split()
        version = ProceduralSkillVersion(
            skill_id=skill.id,
            version=version_str,
            status="active",
            name=parsed.frontmatter.metadata.get("display_name") or slug,
            description=parsed.frontmatter.description,
            instructions_md=parsed.instructions,
            intent_tags=[],
            response_modes=[],
            trigger_phrases=[],
            allowed_tools=allowed_tools,
            metadata_json={
                "format": "skill_md",
                **{
                    key: value
                    for key, value in parsed.frontmatter.metadata.items()
                    if isinstance(value, str | int | float | bool)
                },
            },
            content_sha256=content_hash,
            created_by=created_by,
            published_at=datetime.now(UTC),
        )
        self.session.add(version)
        self.session.flush()

        files = []
        for path, text in sorted(text_files.items()):
            encoded = text.encode("utf-8")
            files.append(
                SkillFile(
                    skill_version_id=version.id,
                    path=path,
                    kind=_kind_for_path(path),
                    content_text=text,
                    size_bytes=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                )
            )
        for path, blob in sorted(binary_files.items()):
            files.append(
                SkillFile(
                    skill_version_id=version.id,
                    path=path,
                    kind=_kind_for_path(path),
                    content_bytes=blob,
                    size_bytes=len(blob),
                    sha256=hashlib.sha256(blob).hexdigest(),
                )
            )
        self.session.add_all(files)
        self.session.flush()
        return IngestedSkill(
            skill=skill, version=version, files=files, created_new_version=True
        )


def _parse_skill_markdown(content: str) -> tuple[Frontmatter, str]:
    """Split YAML frontmatter from body and validate via ADK's Frontmatter."""

    import yaml  # type: ignore[import-untyped]

    if not content.startswith("---"):
        raise SkillIngestionError("SKILL.md must start with YAML frontmatter (---).")
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise SkillIngestionError("SKILL.md frontmatter is not closed with ---.")
    try:
        raw = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise SkillIngestionError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(raw, dict):
        raise SkillIngestionError("SKILL.md frontmatter must be a YAML mapping.")
    try:
        frontmatter = Frontmatter.model_validate(raw)
    except ValueError as exc:
        raise SkillIngestionError(f"Invalid skill frontmatter: {exc}") from exc
    return frontmatter, parts[2].strip()


def _load_skill_dir(directory: Path) -> Skill:
    """Load SKILL.md + text resources from a skill directory into ADK models."""

    if not directory.is_dir():
        raise SkillIngestionError(f"Skill directory '{directory}' not found.")
    skill_md = None
    for name in ("SKILL.md", "skill.md"):
        if (directory / name).is_file():
            skill_md = directory / name
            break
    if skill_md is None:
        raise SkillIngestionError(f"SKILL.md not found in '{directory}'.")
    frontmatter, body = _parse_skill_markdown(skill_md.read_text(encoding="utf-8"))
    references: dict[str, str | bytes] = dict(_load_text_dir(directory / "references"))
    assets: dict[str, str | bytes] = dict(_load_text_dir(directory / "assets"))
    scripts = {
        name: Script(src=content)
        for name, content in _load_text_dir(directory / "scripts").items()
    }
    return Skill(
        frontmatter=frontmatter,
        instructions=body,
        resources=Resources(references=references, assets=assets, scripts=scripts),
    )


def _load_text_dir(directory: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    if not directory.is_dir():
        return files
    for file_path in directory.rglob("*"):
        if not file_path.is_file() or "__pycache__" in file_path.parts:
            continue
        try:
            files[str(file_path.relative_to(directory))] = file_path.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            continue  # binary files are captured separately
    return files


def _safe_extract_zip(data: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillIngestionError("Upload is not a valid zip archive.") from exc
    with archive:
        total = 0
        for member in archive.infolist():
            name = member.filename
            if name.startswith("/") or ".." in Path(name).parts:
                raise SkillIngestionError(f"Unsafe path in archive: {name}")
            total += member.file_size
            if total > MAX_SKILL_ARCHIVE_BYTES:
                raise SkillIngestionError("Skill archive contents exceed 16MB.")
        archive.extractall(destination)


def _find_skill_root(extract_root: Path) -> Path:
    """Locate the directory containing SKILL.md (root or one level down)."""

    candidates = [
        extract_root,
        *sorted(p for p in extract_root.iterdir() if p.is_dir()),
    ]
    for candidate in candidates:
        for name in ("SKILL.md", "skill.md"):
            if (candidate / name).is_file():
                return candidate
    raise SkillIngestionError("No SKILL.md found in the uploaded archive.")


def _collect_binary_files(directory: Path) -> dict[str, bytes]:
    """Capture non-UTF-8 resource files that ADK's text loader skips."""

    binary: dict[str, bytes] = {}
    for sub, _kind in _RESOURCE_DIRS.items():
        base = directory / sub
        if not base.is_dir():
            continue
        for file_path in base.rglob("*"):
            if not file_path.is_file() or "__pycache__" in file_path.parts:
                continue
            raw = file_path.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                binary[f"{sub}/{file_path.relative_to(base)}"] = raw
    return binary


def _resource_text_files(parsed: Skill) -> dict[str, str]:
    files: dict[str, str] = {}
    for name, content in parsed.resources.references.items():
        if isinstance(content, str):
            files[f"references/{name}"] = content
    for name, content in parsed.resources.assets.items():
        if isinstance(content, str):
            files[f"assets/{name}"] = content
    for name, script in parsed.resources.scripts.items():
        files[f"scripts/{name}"] = script.src
    return files


def _kind_for_path(path: str) -> str:
    prefix = path.split("/", 1)[0]
    return _RESOURCE_DIRS.get(prefix, "asset")


def _content_sha256(
    parsed: Skill,
    text_files: dict[str, str],
    binary_files: dict[str, bytes],
) -> str:
    payload = {
        "name": parsed.frontmatter.name,
        "description": parsed.frontmatter.description,
        "allowed_tools": parsed.frontmatter.allowed_tools,
        "instructions": parsed.instructions,
        "files": {
            **{
                path: hashlib.sha256(text.encode("utf-8")).hexdigest()
                for path, text in text_files.items()
            },
            **{
                path: hashlib.sha256(blob).hexdigest()
                for path, blob in binary_files.items()
            },
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _bump_patch(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return f"{version}.1"
    major, minor, patch = match.groups()
    return f"{major}.{minor}.{int(patch) + 1}"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise SkillIngestionError(f"Cannot derive a skill name from {value!r}.")
    return slug


def _first_text_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return "Custom skill."
