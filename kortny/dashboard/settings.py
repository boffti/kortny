"""Settings for the read-only dashboard service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DashboardSettings(BaseSettings):
    """Dashboard-only settings.

    The dashboard intentionally avoids loading the full Slack/LLM runtime settings so
    it can stay a small read-only operational surface over the database.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    postgres_url: str = Field(validation_alias="POSTGRES_URL", min_length=1)
    username: str = Field(
        default="kortny", validation_alias="DASHBOARD_USERNAME", min_length=1
    )
    password: str = Field(
        default="change-me", validation_alias="DASHBOARD_PASSWORD", min_length=1
    )
    session_secret: str = Field(
        default="change-me-dashboard-session-secret",
        validation_alias="DASHBOARD_SESSION_SECRET",
        min_length=16,
    )
    secure_cookies: bool = Field(
        default=False, validation_alias="DASHBOARD_SECURE_COOKIES"
    )

    @field_validator("username", "password", "session_secret")
    @classmethod
    def _strip_required_string(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("cannot be blank")
        return stripped


class DashboardSettingsError(RuntimeError):
    """Raised when dashboard settings are missing or invalid."""


def load_dashboard_settings(
    env_file: str | Path | None = ".env",
) -> DashboardSettings:
    """Load dashboard settings with concise errors."""

    try:
        settings_kwargs: dict[str, Any] = {"_env_file": env_file}
        return DashboardSettings(**settings_kwargs)
    except ValidationError as exc:
        failed_fields = sorted({str(error["loc"][0]) for error in exc.errors()})
        message = "Missing or invalid dashboard configuration: " + ", ".join(
            failed_fields
        )
        raise DashboardSettingsError(message) from exc
