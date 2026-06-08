"""Sandbox execution contracts.

This module intentionally defines contracts only. The Docker-backed runner lands
in a later slice so current tools keep their in-process behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

JsonObject = dict[str, object]

SandboxNetworkMode = Literal["none", "allowlist"]
SandboxLifecyclePhase = Literal["created", "started", "exited", "killed"]


@dataclass(frozen=True, slots=True)
class SandboxResourceLimits:
    """Resource caps for one sandboxed tool execution."""

    cpus: float = 1.0
    memory_mb: int = 512
    pids_limit: int = 128
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        if self.cpus <= 0:
            raise ValueError("Sandbox CPU limit must be positive")
        if self.memory_mb <= 0:
            raise ValueError("Sandbox memory limit must be positive")
        if self.pids_limit <= 0:
            raise ValueError("Sandbox PID limit must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("Sandbox timeout must be positive")

    def to_payload(self) -> JsonObject:
        """Return a JSON-safe representation for task events and dashboard use."""

        return {
            "cpus": self.cpus,
            "memory_mb": self.memory_mb,
            "pids_limit": self.pids_limit,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class ToolSandboxPolicy:
    """Static sandbox policy advertised by a tool."""

    requires_sandbox: bool = False
    profile: str = "default"
    network: SandboxNetworkMode = "none"
    egress_allowlist: tuple[str, ...] = ()
    resource_limits: SandboxResourceLimits = field(
        default_factory=SandboxResourceLimits
    )
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.profile.strip():
            raise ValueError("Sandbox profile is required")
        if self.network == "allowlist" and not self.egress_allowlist:
            raise ValueError("Sandbox allowlist network requires egress hosts")

    def to_payload(self) -> JsonObject:
        """Return a JSON-safe representation for descriptors and task events."""

        return {
            "requires_sandbox": self.requires_sandbox,
            "profile": self.profile,
            "network": self.network,
            "egress_allowlist": list(self.egress_allowlist),
            "resource_limits": self.resource_limits.to_payload(),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SandboxArtifact:
    """File-like artifact produced by sandboxed execution."""

    filename: str
    path: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None

    def to_payload(self) -> JsonObject:
        return {
            "filename": self.filename,
            "path": self.path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """One concrete sandbox execution request."""

    image: str
    command: tuple[str, ...]
    workspace_path: Path
    artifacts_path: Path | None = None
    network: SandboxNetworkMode = "none"
    egress_allowlist: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    resource_limits: SandboxResourceLimits = field(
        default_factory=SandboxResourceLimits
    )

    def __post_init__(self) -> None:
        if not self.image.strip():
            raise ValueError("Sandbox image is required")
        if not self.command:
            raise ValueError("Sandbox command is required")
        if self.network == "allowlist" and not self.egress_allowlist:
            raise ValueError("Sandbox allowlist network requires egress hosts")

    def to_payload(self) -> JsonObject:
        """Return non-secret execution metadata for logs and traces."""

        return {
            "image": self.image,
            "command": list(self.command),
            "workspace_path": str(self.workspace_path),
            "artifacts_path": str(self.artifacts_path) if self.artifacts_path else None,
            "network": self.network,
            "egress_allowlist": list(self.egress_allowlist),
            "env_keys": sorted(self.env),
            "resource_limits": self.resource_limits.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class SandboxLifecycleEvent:
    """Lifecycle event emitted by a sandbox runner."""

    phase: SandboxLifecyclePhase
    message: str
    details: JsonObject = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        return {
            "phase": self.phase,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Result returned by a sandbox runner."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    artifacts: tuple[SandboxArtifact, ...] = ()
    usage: JsonObject = field(default_factory=dict)
    events: tuple[SandboxLifecycleEvent, ...] = ()

    def to_payload(self) -> JsonObject:
        """Return a JSON-safe execution summary."""

        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifact_count": len(self.artifacts),
            "artifacts": [artifact.to_payload() for artifact in self.artifacts],
            "usage": self.usage,
            "events": [event.to_payload() for event in self.events],
        }


class SandboxRunner(Protocol):
    """Runs a single sandboxed execution request."""

    def run(self, spec: SandboxSpec) -> SandboxResult:
        """Execute the sandbox request and return captured output."""
        ...


class SandboxUnavailableError(RuntimeError):
    """Raised when a sandboxed tool is invoked without a configured runner."""
