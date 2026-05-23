"""Runtime logging setup."""

from __future__ import annotations

import logging
import os

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure process logging for container-friendly stdout/stderr logs."""

    resolved_level = (level or os.environ.get("KORTNY_LOG_LEVEL") or "INFO").upper()
    numeric_level = getattr(logging, resolved_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=DEFAULT_LOG_FORMAT,
    )
