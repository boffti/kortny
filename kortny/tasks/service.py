"""Task domain service.

For the MVP this is intentionally a thin SQLAlchemy-backed service. Keeping this
as a named service gives Slack ingress, workers, and the future agent loop a
stable import path even if the repository internals split later.
"""

from __future__ import annotations

from kortny.tasks.repository import TaskRepository


class TaskService(TaskRepository):
    """Application service over task persistence."""
