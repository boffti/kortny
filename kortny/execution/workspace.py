"""Per-task temporary working directories."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TaskWorkspace:
    """Filesystem scratch space for a single task execution."""

    task_id: uuid.UUID
    path: Path


@contextmanager
def task_workspace(
    task_id: uuid.UUID,
    *,
    base_dir: Path | str | None = None,
) -> Iterator[TaskWorkspace]:
    """Create an isolated temporary directory for a task and clean it up."""

    resolved_base_dir = _resolve_base_dir(base_dir)
    prefix = f"kortny-task-{task_id.hex}-"
    with tempfile.TemporaryDirectory(prefix=prefix, dir=resolved_base_dir) as dirname:
        yield TaskWorkspace(task_id=task_id, path=Path(dirname))


def _resolve_base_dir(base_dir: Path | str | None) -> str | None:
    if base_dir is None:
        return None

    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
