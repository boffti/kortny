from pathlib import Path

import pytest

from kortny.execution import (
    SandboxArtifact,
    SandboxLifecycleEvent,
    SandboxResourceLimits,
    SandboxResult,
    SandboxSpec,
    ToolSandboxPolicy,
)


def test_tool_sandbox_policy_defaults_to_no_sandbox() -> None:
    policy = ToolSandboxPolicy()

    assert policy.requires_sandbox is False
    assert policy.network == "none"
    assert policy.to_payload() == {
        "requires_sandbox": False,
        "profile": "default",
        "network": "none",
        "egress_allowlist": [],
        "resource_limits": {
            "cpus": 1.0,
            "memory_mb": 512,
            "pids_limit": 128,
            "timeout_seconds": 60,
        },
        "reason": "",
    }


def test_allowlist_network_requires_explicit_hosts() -> None:
    with pytest.raises(ValueError, match="allowlist network requires egress hosts"):
        ToolSandboxPolicy(network="allowlist")

    with pytest.raises(ValueError, match="allowlist network requires egress hosts"):
        SandboxSpec(
            image="kortny/sandbox-python:latest",
            command=("python", "-c", "print('ok')"),
            workspace_path=Path("/tmp/task"),
            network="allowlist",
        )


def test_resource_limits_reject_non_positive_values() -> None:
    with pytest.raises(ValueError, match="CPU limit"):
        SandboxResourceLimits(cpus=0)
    with pytest.raises(ValueError, match="memory limit"):
        SandboxResourceLimits(memory_mb=0)
    with pytest.raises(ValueError, match="PID limit"):
        SandboxResourceLimits(pids_limit=0)
    with pytest.raises(ValueError, match="timeout"):
        SandboxResourceLimits(timeout_seconds=0)


def test_sandbox_spec_payload_redacts_env_values() -> None:
    spec = SandboxSpec(
        image="kortny/sandbox-python:latest",
        command=("python", "-c", "print('ok')"),
        workspace_path=Path("/tmp/task"),
        artifacts_path=Path("/tmp/task/artifacts"),
        env={"SAFE_FLAG": "1", "SECRET_TOKEN": "do-not-log"},
    )

    payload = spec.to_payload()

    assert payload["image"] == "kortny/sandbox-python:latest"
    assert payload["command"] == ["python", "-c", "print('ok')"]
    assert payload["workspace_path"] == "/tmp/task"
    assert payload["artifacts_path"] == "/tmp/task/artifacts"
    assert payload["network"] == "none"
    assert payload["env_keys"] == ["SAFE_FLAG", "SECRET_TOKEN"]
    assert "do-not-log" not in str(payload)


def test_sandbox_result_payload_preserves_artifact_and_lifecycle_summary() -> None:
    result = SandboxResult(
        exit_code=0,
        stdout="done",
        artifacts=(
            SandboxArtifact(
                filename="report.pdf",
                path="/tmp/task/artifacts/report.pdf",
                mime_type="application/pdf",
                size_bytes=42,
            ),
        ),
        usage={"wall_ms": 123},
        events=(
            SandboxLifecycleEvent(
                phase="started",
                message="sandbox started",
                details={"container_id": "abc123"},
            ),
        ),
    )

    payload = result.to_payload()

    assert payload["exit_code"] == 0
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["filename"] == "report.pdf"
    assert payload["usage"] == {"wall_ms": 123}
    assert payload["events"] == [
        {
            "phase": "started",
            "message": "sandbox started",
            "details": {"container_id": "abc123"},
        }
    ]
