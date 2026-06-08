"""Minimal Docker API client for sandbox-runner smoke checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class DockerApiProbe:
    """Result of a safe Docker API reachability probe."""

    ok: bool
    configured: bool
    endpoint: str = "GET /version"
    api_version: str | None = None
    docker_version: str | None = None
    platform_name: str | None = None
    status_code: int | None = None
    error_type: str | None = None
    error: str | None = None

    def to_payload(self) -> JsonObject:
        return {
            "ok": self.ok,
            "configured": self.configured,
            "endpoint": self.endpoint,
            "api_version": self.api_version,
            "docker_version": self.docker_version,
            "platform_name": self.platform_name,
            "status_code": self.status_code,
            "error_type": self.error_type,
            "error": self.error,
        }


class DockerApiProbeClient(Protocol):
    """Shape used by the runner app to probe Docker safely."""

    def version(self) -> DockerApiProbe:
        """Probe Docker Engine `/version`."""
        ...


@dataclass(frozen=True, slots=True)
class DockerApiClient:
    """Tiny Docker Engine API client for safe control-plane checks."""

    docker_host: str
    timeout_seconds: float = 2.0

    def version(self) -> DockerApiProbe:
        """Return Docker Engine version metadata through the configured endpoint."""

        if not self.docker_host.strip():
            return DockerApiProbe(
                ok=False,
                configured=False,
                error_type="DockerHostMissing",
                error="DOCKER_HOST is not configured.",
            )

        try:
            base_url = _docker_host_base_url(self.docker_host)
            response = httpx.get(
                f"{base_url}/version",
                timeout=self.timeout_seconds,
            )
            payload = response.json() if response.content else {}
            if not isinstance(payload, dict):
                payload = {}
            return DockerApiProbe(
                ok=response.is_success,
                configured=True,
                api_version=_optional_str(payload.get("ApiVersion")),
                docker_version=_optional_str(payload.get("Version")),
                platform_name=_platform_name(payload),
                status_code=response.status_code,
                error=None if response.is_success else response.text[:500],
            )
        except Exception as exc:
            return DockerApiProbe(
                ok=False,
                configured=True,
                error_type=type(exc).__name__,
                error=str(exc),
            )


def _docker_host_base_url(docker_host: str) -> str:
    value = docker_host.strip().rstrip("/")
    if value.startswith("tcp://"):
        return f"http://{value.removeprefix('tcp://')}"
    if value.startswith(("http://", "https://")):
        return value
    raise ValueError(
        "Only tcp://, http://, and https:// Docker hosts are supported by "
        "the sandbox-runner smoke client."
    )


def _platform_name(payload: JsonObject) -> str | None:
    platform = payload.get("Platform")
    if not isinstance(platform, dict):
        return None
    return _optional_str(platform.get("Name"))


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
