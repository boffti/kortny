from __future__ import annotations

import pytest

from kortny.scheduler import service


def test_scheduler_help_does_not_require_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_load_settings() -> None:
        raise AssertionError("settings should not load for --help")

    monkeypatch.setattr(service, "load_settings", fail_load_settings)

    with pytest.raises(SystemExit) as exc_info:
        service.main(["--help"])

    assert exc_info.value.code == 0
    assert "Run the Kortny scheduler" in capsys.readouterr().out
