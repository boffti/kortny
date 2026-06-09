"""Sandbox execution contracts and task-event helpers.

The worker uses these contracts to call the internal sandbox-runner service for
tools that execute untrusted code. Fixed in-process tools can still stay outside
the sandbox when their metadata does not require sandboxing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

JsonObject = dict[str, object]

SandboxNetworkMode = Literal["none", "allowlist"]
SandboxLifecyclePhase = Literal["created", "started", "exited", "killed"]
SANDBOX_LIFECYCLE_MESSAGE = "sandbox_lifecycle"
SANDBOX_RESULT_MESSAGE = "sandbox_result"
SANDBOX_EVENT_SOURCE = "execution.sandbox"
DEFAULT_SANDBOX_OUTPUT_PREVIEW_CHARS = 2_000


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


class SandboxEventSink(Protocol):
    """Minimal event sink required for sandbox task-event recording."""

    def append_event(
        self,
        task: Any,
        event_type: str,
        payload: JsonObject | None = None,
    ) -> Any:
        """Append an event to a task timeline."""
        ...


@dataclass(frozen=True, slots=True)
class SandboxEventRecorder:
    """Records sandbox lifecycle and result summaries into a task event sink."""

    event_sink: SandboxEventSink
    runner: str = "local"
    output_preview_chars: int = DEFAULT_SANDBOX_OUTPUT_PREVIEW_CHARS

    def __post_init__(self) -> None:
        if self.output_preview_chars < 0:
            raise ValueError("Sandbox output preview length cannot be negative")

    def record_lifecycle(
        self,
        task: Any,
        event: SandboxLifecycleEvent,
        *,
        spec: SandboxSpec | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> Any:
        """Append a sandbox lifecycle event to the task timeline."""

        return self.event_sink.append_event(
            task,
            "log",
            sandbox_lifecycle_event_payload(
                event,
                spec=spec,
                runner=self.runner,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            ),
        )

    def record_result(
        self,
        task: Any,
        result: SandboxResult,
        *,
        spec: SandboxSpec | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> Any:
        """Append a sandbox result summary to the task timeline."""

        return self.event_sink.append_event(
            task,
            "log",
            sandbox_result_event_payload(
                result,
                spec=spec,
                runner=self.runner,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                output_preview_chars=self.output_preview_chars,
            ),
        )


def sandbox_lifecycle_event_payload(
    event: SandboxLifecycleEvent,
    *,
    spec: SandboxSpec | None = None,
    runner: str = "local",
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> JsonObject:
    """Return the task-event payload for one sandbox lifecycle transition."""

    payload: JsonObject = {
        "message": SANDBOX_LIFECYCLE_MESSAGE,
        "source": SANDBOX_EVENT_SOURCE,
        "runner": runner,
        "phase": event.phase,
        "event": event.to_payload(),
    }
    if spec is not None:
        payload["spec"] = spec.to_payload()
    if tool_name:
        payload["tool"] = tool_name
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id
    return payload


def sandbox_result_event_payload(
    result: SandboxResult,
    *,
    spec: SandboxSpec | None = None,
    runner: str = "local",
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    output_preview_chars: int = DEFAULT_SANDBOX_OUTPUT_PREVIEW_CHARS,
) -> JsonObject:
    """Return a bounded task-event payload for sandbox execution results."""

    if output_preview_chars < 0:
        raise ValueError("Sandbox output preview length cannot be negative")

    payload: JsonObject = {
        "message": SANDBOX_RESULT_MESSAGE,
        "source": SANDBOX_EVENT_SOURCE,
        "runner": runner,
        "status": "succeeded" if result.exit_code == 0 else "failed",
        "exit_code": result.exit_code,
        "stdout_chars": len(result.stdout),
        "stderr_chars": len(result.stderr),
        "stdout_preview": _preview_text(result.stdout, output_preview_chars),
        "stderr_preview": _preview_text(result.stderr, output_preview_chars),
        "artifact_count": len(result.artifacts),
        "artifacts": [artifact.to_payload() for artifact in result.artifacts],
        "usage": result.usage,
        "lifecycle_event_count": len(result.events),
        "lifecycle_events": [event.to_payload() for event in result.events],
    }
    if spec is not None:
        payload["spec"] = spec.to_payload()
    if tool_name:
        payload["tool"] = tool_name
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id
    return payload


def _preview_text(value: str, max_chars: int) -> str:
    if max_chars == 0 or not value:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars]
