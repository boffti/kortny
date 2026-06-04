"""Dashboard read and action helpers for scheduled tasks."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kortny.db.models import Schedule, SlackIdentity

SCHEDULE_PAGE_SIZE = 25
SCHEDULE_STATUSES = {"all", "proposed", "active", "paused", "completed", "cancelled"}
SCHEDULE_VIEWS = {"all", "my", "system"}
SCHEDULE_ACTIONS = {"activate", "pause", "resume", "cancel"}


@dataclass(frozen=True)
class ScheduleMetric:
    label: str
    value: str
    detail: str
    tone: str = "neutral"


@dataclass(frozen=True)
class ScheduleRow:
    schedule: Schedule
    cadence: str
    owner: str
    delivery: str
    next_run: str
    last_run: str
    budget: str
    tone: str
    can_activate: bool
    can_pause: bool
    can_resume: bool
    can_cancel: bool


@dataclass(frozen=True)
class SchedulePage:
    rows: tuple[ScheduleRow, ...]
    metrics: tuple[ScheduleMetric, ...]
    active_view: str
    status_filter: str
    page: int
    page_size: int
    total_count: int
    base_path: str
    previous_page_url: str | None
    next_page_url: str | None

    @property
    def total_pages(self) -> int:
        if self.total_count == 0:
            return 1
        return math.ceil(self.total_count / self.page_size)

    @property
    def first_item(self) -> int:
        if self.total_count == 0:
            return 0
        return ((self.page - 1) * self.page_size) + 1

    @property
    def last_item(self) -> int:
        return min(self.page * self.page_size, self.total_count)


def get_schedule_dashboard(
    session: Session,
    *,
    installation_id: uuid.UUID | None,
    slack_user_id: str | None,
    is_admin: bool,
    view: str = "all",
    status: str = "all",
    page: int = 1,
    base_path: str = "/schedules",
) -> SchedulePage:
    """Return a paginated schedule dashboard scoped to the current principal."""

    active_view = _normalize_view(view=view, is_admin=is_admin)
    status_filter = status if status in SCHEDULE_STATUSES else "all"
    normalized_page = max(page, 1)
    filters = _schedule_filters(
        installation_id=installation_id,
        slack_user_id=slack_user_id,
        is_admin=is_admin,
        view=active_view,
        status=status_filter,
    )
    total_count = (
        session.scalar(select(func.count()).select_from(Schedule).where(*filters)) or 0
    )
    schedules = tuple(
        session.scalars(
            select(Schedule)
            .where(*filters)
            .order_by(
                Schedule.next_run_at.asc().nulls_last(),
                Schedule.updated_at.desc(),
                Schedule.id.desc(),
            )
            .offset((normalized_page - 1) * SCHEDULE_PAGE_SIZE)
            .limit(SCHEDULE_PAGE_SIZE)
        )
    )
    identities = _owner_identity_map(session, schedules)
    page_model = SchedulePage(
        rows=tuple(_schedule_row(schedule, identities=identities) for schedule in schedules),
        metrics=_schedule_metrics(
            session,
            installation_id=installation_id,
            slack_user_id=slack_user_id,
            is_admin=is_admin,
            view=active_view,
        ),
        active_view=active_view,
        status_filter=status_filter,
        page=normalized_page,
        page_size=SCHEDULE_PAGE_SIZE,
        total_count=total_count,
        base_path=base_path,
        previous_page_url=None,
        next_page_url=None,
    )
    return SchedulePage(
        **{
            **page_model.__dict__,
            "previous_page_url": _schedule_page_url(
                base_path=base_path,
                view=active_view,
                status=status_filter,
                page=normalized_page - 1,
            )
            if normalized_page > 1
            else None,
            "next_page_url": _schedule_page_url(
                base_path=base_path,
                view=active_view,
                status=status_filter,
                page=normalized_page + 1,
            )
            if normalized_page < page_model.total_pages
            else None,
        }
    )


def apply_schedule_action(
    session: Session,
    *,
    schedule_id: uuid.UUID,
    action: str,
    installation_id: uuid.UUID | None,
    slack_user_id: str | None,
    is_admin: bool,
    now: datetime | None = None,
) -> str:
    """Apply a dashboard schedule action and return a human notice."""

    if action not in SCHEDULE_ACTIONS:
        raise ValueError("Unsupported schedule action.")
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        raise ValueError("Scheduled task was not found.")
    if not _can_access_schedule(
        schedule,
        installation_id=installation_id,
        slack_user_id=slack_user_id,
        is_admin=is_admin,
    ):
        raise ValueError("You do not have access to this scheduled task.")

    if action == "activate":
        if schedule.status != "proposed":
            raise ValueError("Only proposed schedules can be activated.")
        schedule.status = "active"
        notice = "Scheduled task activated."
    elif action == "pause":
        if schedule.status != "active":
            raise ValueError("Only active schedules can be paused.")
        schedule.status = "paused"
        notice = "Scheduled task paused."
    elif action == "resume":
        if schedule.status != "paused":
            raise ValueError("Only paused schedules can be resumed.")
        schedule.status = "active"
        notice = "Scheduled task resumed."
    else:
        if schedule.status not in {"proposed", "active", "paused"}:
            raise ValueError("Only proposed, active, or paused schedules can be cancelled.")
        schedule.status = "cancelled"
        schedule.next_run_at = None
        notice = "Scheduled task cancelled."

    metadata = dict(schedule.metadata_json or {})
    metadata["dashboard_last_action"] = action
    metadata["dashboard_last_action_at"] = (now or datetime.now(UTC)).isoformat()
    schedule.metadata_json = metadata
    schedule.updated_at = now or datetime.now(UTC)
    session.add(schedule)
    session.commit()
    return notice


def _schedule_filters(
    *,
    installation_id: uuid.UUID | None,
    slack_user_id: str | None,
    is_admin: bool,
    view: str,
    status: str,
) -> list[Any]:
    filters: list[Any] = []
    if installation_id is not None:
        filters.append(Schedule.installation_id == installation_id)
    if not is_admin or view == "my":
        filters.extend(
            [
                Schedule.owner_type == "user",
                Schedule.owner_slack_user_id == slack_user_id,
            ]
        )
    elif view == "system":
        filters.append(Schedule.owner_type == "system")
    if status != "all":
        filters.append(Schedule.status == status)
    return filters


def _schedule_metrics(
    session: Session,
    *,
    installation_id: uuid.UUID | None,
    slack_user_id: str | None,
    is_admin: bool,
    view: str,
) -> tuple[ScheduleMetric, ...]:
    filters = _schedule_filters(
        installation_id=installation_id,
        slack_user_id=slack_user_id,
        is_admin=is_admin,
        view=view,
        status="all",
    )

    def count(status: str | None = None) -> int:
        status_filters = [*filters]
        if status is not None:
            status_filters.append(Schedule.status == status)
        return int(
            session.scalar(
                select(func.count()).select_from(Schedule).where(*status_filters)
            )
            or 0
        )

    return (
        ScheduleMetric("Active", f"{count('active'):,}", "Running on schedule", "success"),
        ScheduleMetric("Paused", f"{count('paused'):,}", "Waiting to resume", "warning"),
        ScheduleMetric("Proposed", f"{count('proposed'):,}", "Drafts not yet active", "neutral"),
        ScheduleMetric("Total", f"{count():,}", "All visible schedules", "neutral"),
    )


def _schedule_row(
    schedule: Schedule,
    *,
    identities: dict[tuple[uuid.UUID, str], str],
) -> ScheduleRow:
    return ScheduleRow(
        schedule=schedule,
        cadence=_cadence_label(schedule),
        owner=_owner_label(schedule, identities=identities),
        delivery=_delivery_label(schedule),
        next_run=_datetime_label(schedule.next_run_at),
        last_run=_datetime_label(schedule.last_run_at),
        budget=_budget_label(schedule.planned_cost_ceiling_usd),
        tone=_status_tone(schedule.status),
        can_activate=schedule.status == "proposed",
        can_pause=schedule.status == "active",
        can_resume=schedule.status == "paused",
        can_cancel=schedule.status in {"proposed", "active", "paused"},
    )


def _can_access_schedule(
    schedule: Schedule,
    *,
    installation_id: uuid.UUID | None,
    slack_user_id: str | None,
    is_admin: bool,
) -> bool:
    if installation_id is not None and schedule.installation_id != installation_id:
        return False
    if is_admin:
        return True
    return schedule.owner_type == "user" and schedule.owner_slack_user_id == slack_user_id


def _normalize_view(*, view: str, is_admin: bool) -> str:
    if not is_admin:
        return "my"
    return view if view in SCHEDULE_VIEWS else "all"


def _cadence_label(schedule: Schedule) -> str:
    metadata = schedule.metadata_json if isinstance(schedule.metadata_json, dict) else {}
    label = metadata.get("cadence_label")
    if isinstance(label, str) and label.strip():
        return label
    if schedule.spec_kind == "oneoff":
        return "One-time"
    if schedule.spec_kind == "interval" and schedule.interval_seconds is not None:
        return f"Every {schedule.interval_seconds:,} seconds"
    if schedule.cron_expr:
        return schedule.cron_expr
    return schedule.spec_kind


def _owner_identity_map(
    session: Session,
    schedules: tuple[Schedule, ...],
) -> dict[tuple[uuid.UUID, str], str]:
    owner_pairs = {
        (schedule.installation_id, schedule.owner_slack_user_id)
        for schedule in schedules
        if schedule.owner_type == "user" and schedule.owner_slack_user_id
    }
    if not owner_pairs:
        return {}
    installation_ids = {installation_id for installation_id, _slack_id in owner_pairs}
    slack_ids = {slack_id for _installation_id, slack_id in owner_pairs}
    identities = session.scalars(
        select(SlackIdentity).where(
            SlackIdentity.kind == "user",
            SlackIdentity.installation_id.in_(installation_ids),
            SlackIdentity.slack_id.in_(slack_ids),
        )
    )
    return {
        (identity.installation_id, identity.slack_id): identity.display_name
        for identity in identities
    }


def _owner_label(
    schedule: Schedule,
    *,
    identities: dict[tuple[uuid.UUID, str], str],
) -> str:
    if schedule.owner_type == "system":
        return "System"
    if not schedule.owner_slack_user_id:
        return "User"
    return (
        identities.get((schedule.installation_id, schedule.owner_slack_user_id))
        or schedule.owner_slack_user_id
    )


def _delivery_label(schedule: Schedule) -> str:
    delivery_kind = getattr(schedule, "delivery_kind", None)
    if delivery_kind == "slack_dm":
        return _delivery_with_artifact_policy("DM", schedule)
    if delivery_kind == "slack_channel":
        return _delivery_with_artifact_policy("Channel", schedule)
    if delivery_kind == "slack_thread":
        return _delivery_with_artifact_policy("Thread", schedule)
    if delivery_kind == "dashboard_only":
        return _delivery_with_artifact_policy("Dashboard", schedule)
    template = schedule.task_template if isinstance(schedule.task_template, dict) else {}
    surface = template.get("delivery_surface")
    if surface == "dm":
        return _delivery_with_artifact_policy("DM", schedule)
    if surface == "channel":
        return _delivery_with_artifact_policy("Channel", schedule)
    if surface == "thread":
        return _delivery_with_artifact_policy("Thread", schedule)
    channel = template.get("slack_channel_id")
    return str(channel) if channel else "Unknown"


def _delivery_with_artifact_policy(label: str, schedule: Schedule) -> str:
    template = schedule.task_template if isinstance(schedule.task_template, dict) else {}
    policy = (
        getattr(schedule, "artifact_delivery_policy", None)
        or template.get("artifact_delivery_policy")
        or "message_only"
    )
    if policy == "attach_files":
        return f"{label} + files"
    if policy == "link_artifacts":
        return f"{label} + links"
    return label


def _datetime_label(value: datetime | None) -> str:
    if value is None:
        return "Not scheduled"
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _budget_label(value: Decimal | None) -> str:
    if value is None:
        return "No cap"
    return f"${value:,.4f}"


def _status_tone(status: str) -> str:
    return {
        "active": "success",
        "paused": "warning",
        "proposed": "neutral",
        "completed": "accent",
        "cancelled": "danger",
    }.get(status, "neutral")


def _schedule_page_url(
    *,
    base_path: str,
    view: str,
    status: str,
    page: int,
) -> str:
    params = {"view": view, "status": status, "page": str(page)}
    return f"{base_path}?{_query(params)}"


def _query(params: dict[str, str]) -> str:
    from urllib.parse import urlencode

    return urlencode({key: value for key, value in params.items() if value})
