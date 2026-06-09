"""Worker-side HTTP client for sandbox-runner sessions.

The workbench tools use this client to drive one long-lived sandbox
container per task: run commands, move files, and export artifacts.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from kortny.config import Settings
from kortny.execution.sandbox import SandboxUnavailableError

JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class SandboxSessionInfo:
    """One open sandbox session for a task."""

    session_id: str
    task_id: str
    container_id: str
    profile: str
    reused: bool


@dataclass(frozen=True, slots=True)
class SandboxExecResult:
    """Result of one command executed in a sandbox session."""

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int | None = None
    timed_out: bool = False
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class SandboxSessionError(RuntimeError):
    """Raised when the runner rejects a session operation."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SandboxSessionClient(Protocol):
    """Session operations the workbench tools depend on."""

    def open_session(
        self, task_id: str, profile: str = "workbench"
    ) -> SandboxSessionInfo:
        """Open or reuse the sandbox session for a task."""
        ...

    def exec(
        self,
        session_id: str,
        command: str,
        *,
        workdir: str = "/workspace",
        timeout_seconds: int = 120,
    ) -> SandboxExecResult:
        """Run one shell command in the session."""
        ...

    def write_file(self, session_id: str, path: str, content: bytes) -> int:
        """Write one file into the session workspace."""
        ...

    def read_file(self, session_id: str, path: str) -> bytes:
        """Read one file from the session workspace."""
        ...

    def export_archive(self, session_id: str, path: str) -> bytes:
        """Return a tar archive of one workspace path."""
        ...

    def close_session(self, session_id: str) -> None:
        """Close the session and remove its container."""
        ...


@dataclass(frozen=True, slots=True)
class HttpSandboxSessionClient(SandboxSessionClient):
    """Drive sandbox-runner sessions over the internal HTTP API."""

    base_url: str
    timeout_seconds: float = 70.0
    http_client: httpx.Client | None = None

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("Sandbox runner URL is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Sandbox runner timeout must be positive")
        object.__setattr__(self, "base_url", base_url)

    def open_session(
        self, task_id: str, profile: str = "workbench"
    ) -> SandboxSessionInfo:
        payload = self._request(
            "POST",
            "/sessions",
            json={"task_id": task_id, "profile": profile},
        )
        return SandboxSessionInfo(
            session_id=_required_str(payload, "session_id"),
            task_id=_required_str(payload, "task_id"),
            container_id=_required_str(payload, "container_id"),
            profile=str(payload.get("profile") or profile),
            reused=bool(payload.get("reused")),
        )

    def exec(
        self,
        session_id: str,
        command: str,
        *,
        workdir: str = "/workspace",
        timeout_seconds: int = 120,
    ) -> SandboxExecResult:
        payload = self._request(
            "POST",
            f"/sessions/{session_id}/exec",
            json={
                "command": command,
                "workdir": workdir,
                "timeout_seconds": timeout_seconds,
            },
            read_timeout=timeout_seconds + 30,
        )
        exit_code = payload.get("exit_code")
        if not isinstance(exit_code, int):
            exit_code = 124 if payload.get("timed_out") else 1
        return SandboxExecResult(
            exit_code=exit_code,
            stdout=str(payload.get("stdout") or ""),
            stderr=str(payload.get("stderr") or ""),
            duration_ms=payload.get("duration_ms")
            if isinstance(payload.get("duration_ms"), int)
            else None,
            timed_out=bool(payload.get("timed_out")),
            truncated=bool(payload.get("truncated")),
        )

    def write_file(self, session_id: str, path: str, content: bytes) -> int:
        payload = self._request(
            "PUT",
            f"/sessions/{session_id}/files",
            json={
                "path": path,
                "content_b64": base64.b64encode(content).decode("ascii"),
            },
        )
        size = payload.get("size_bytes")
        return size if isinstance(size, int) else len(content)

    def read_file(self, session_id: str, path: str) -> bytes:
        payload = self._request(
            "GET",
            f"/sessions/{session_id}/files",
            params={"path": path},
        )
        content_b64 = payload.get("content_b64")
        if not isinstance(content_b64, str):
            raise SandboxSessionError("Sandbox runner returned no file content.")
        return base64.b64decode(content_b64)

    def export_archive(self, session_id: str, path: str) -> bytes:
        response = self._raw_request(
            "GET",
            f"/sessions/{session_id}/archive",
            params={"path": path},
        )
        return response.content

    def close_session(self, session_id: str) -> None:
        self._request("DELETE", f"/sessions/{session_id}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: JsonObject | None = None,
        params: dict[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> dict[str, Any]:
        response = self._raw_request(
            method, path, json=json, params=params, read_timeout=read_timeout
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SandboxUnavailableError(
                "Sandbox runner returned invalid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise SandboxUnavailableError(
                "Sandbox runner returned a non-object payload."
            )
        return payload

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json: JsonObject | None = None,
        params: dict[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> httpx.Response:
        client = self.http_client or httpx.Client(timeout=self.timeout_seconds)
        timeout = max(self.timeout_seconds, read_timeout or 0)
        try:
            response = client.request(
                method,
                f"{self.base_url}{path}",
                json=json,
                params=params,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            raise SandboxUnavailableError(
                f"Sandbox runner request failed: {type(exc).__name__}: {exc}"
            ) from exc
        if response.status_code == 503:
            raise SandboxUnavailableError(_error_detail(response))
        if not response.is_success:
            raise SandboxSessionError(
                _error_detail(response), status_code=response.status_code
            )
        return response


def create_sandbox_session_client_from_settings(
    settings: Settings,
) -> SandboxSessionClient | None:
    """Return the configured session client, if enabled for this process."""

    if settings.sandbox_runner_url is None:
        return None
    return HttpSandboxSessionClient(
        base_url=settings.sandbox_runner_url,
        timeout_seconds=settings.sandbox_runner_timeout_seconds,
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        return f"Sandbox runner error ({response.status_code}): {payload['detail']}"
    return f"Sandbox runner error ({response.status_code}): {response.text[:300]}"


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SandboxUnavailableError(
            f"Sandbox runner session response missing '{key}'."
        )
    return value
