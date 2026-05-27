"""Context engine contract for agent runtime context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kortny.agent.context import ContextAssembler, ContextPackage
from kortny.db.models import Task


@dataclass(frozen=True, slots=True)
class ContextEngineInfo:
    """Stable metadata for a context engine implementation."""

    id: str
    name: str
    version: str = "1"
    owns_compaction: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("context engine id must be non-empty")
        if not self.name:
            raise ValueError("context engine name must be non-empty")
        if not self.version:
            raise ValueError("context engine version must be non-empty")


class ContextEngine(Protocol):
    """Lifecycle-managed context provider for agent runs.

    This boundary is intentionally small. It mirrors the useful parts of
    OpenClaw/Hermes-style context engines without replacing Kortny's existing
    coordinator, planner, memory, or tool system.
    """

    @property
    def info(self) -> ContextEngineInfo:
        """Return engine metadata for tracing and diagnostics."""

    def ingest(self, task: Task) -> None:
        """Ingest a task before context assembly."""

    def assemble(self, task: Task) -> ContextPackage:
        """Build model messages and structured context metadata."""

    def compact(self, task: Task, *, force: bool = False) -> ContextPackage | None:
        """Compact or summarize context if the engine owns compaction."""

    def after_turn(
        self,
        task: Task,
        package: ContextPackage,
        *,
        outcome: str,
    ) -> None:
        """Persist post-run context state or trigger background maintenance."""


DEFAULT_CONTEXT_ENGINE_INFO = ContextEngineInfo(
    id="kortny.default_context_engine",
    name="Default Context Engine",
)


class DefaultContextEngine:
    """Context engine that delegates to the current ContextAssembler."""

    def __init__(
        self,
        assembler: ContextAssembler,
        *,
        info: ContextEngineInfo = DEFAULT_CONTEXT_ENGINE_INFO,
    ) -> None:
        self._assembler = assembler
        self._info = info

    @property
    def info(self) -> ContextEngineInfo:
        return self._info

    def ingest(self, task: Task) -> None:
        del task

    def assemble(self, task: Task) -> ContextPackage:
        return self._assembler.build_for_task(task)

    def compact(self, task: Task, *, force: bool = False) -> ContextPackage | None:
        del task, force
        return None

    def after_turn(
        self,
        task: Task,
        package: ContextPackage,
        *,
        outcome: str,
    ) -> None:
        del task, package, outcome
