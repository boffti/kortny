"""Read models for the operator dashboard."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from kortny.db.models import Artifact, LLMUsage, Task, TaskEvent

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class TaskListItem:
    task: Task
    models: tuple[str, ...]
    turn_count: int


@dataclass(frozen=True)
class TaskListPage:
    items: tuple[TaskListItem, ...]
    page: int
    page_size: int
    total_count: int

    @property
    def total_pages(self) -> int:
        if self.total_count == 0:
            return 1
        return math.ceil(self.total_count / self.page_size)

    @property
    def previous_page(self) -> int | None:
        if self.page <= 1:
            return None
        return self.page - 1

    @property
    def next_page(self) -> int | None:
        if self.page >= self.total_pages:
            return None
        return self.page + 1


@dataclass(frozen=True)
class TaskDetail:
    task: Task
    events: tuple[TaskEvent, ...]
    usage: tuple[LLMUsage, ...]
    artifacts: tuple[Artifact, ...]


@dataclass(frozen=True)
class AggregateRow:
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class DailyUsageRow:
    day: date
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class UsageAggregate:
    start: datetime | None
    end: datetime | None
    by_model: tuple[AggregateRow, ...]
    by_user: tuple[AggregateRow, ...]
    by_day: tuple[DailyUsageRow, ...]


def list_tasks(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> TaskListPage:
    """Return a paginated dashboard task list."""

    normalized_page = max(page, 1)
    normalized_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    offset = (normalized_page - 1) * normalized_size

    total_count = session.scalar(select(func.count()).select_from(Task)) or 0
    tasks = tuple(
        session.scalars(
            select(Task)
            .order_by(Task.created_at.desc(), Task.id.desc())
            .offset(offset)
            .limit(normalized_size)
        )
    )
    usage_by_task = _usage_by_task(session, [task.id for task in tasks])
    items = tuple(
        TaskListItem(
            task=task,
            models=tuple(sorted({usage.model for usage in usage_by_task[task.id]})),
            turn_count=len(usage_by_task[task.id]),
        )
        for task in tasks
    )
    return TaskListPage(
        items=items,
        page=normalized_page,
        page_size=normalized_size,
        total_count=total_count,
    )


def get_task_detail(session: Session, task_id: uuid.UUID) -> TaskDetail | None:
    """Return one task and its child rows."""

    task = session.get(Task, task_id)
    if task is None:
        return None
    events = tuple(
        session.scalars(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.seq.asc())
        )
    )
    usage = tuple(
        session.scalars(
            select(LLMUsage)
            .where(LLMUsage.task_id == task_id)
            .order_by(LLMUsage.created_at.asc(), LLMUsage.id.asc())
        )
    )
    artifacts = tuple(
        session.scalars(
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        )
    )
    return TaskDetail(task=task, events=events, usage=usage, artifacts=artifacts)


def get_usage_aggregate(
    session: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> UsageAggregate:
    """Return dashboard usage rollups."""

    usage_filter = _usage_filter(start=start, end=end)
    by_model_rows = session.execute(
        _aggregate_query(LLMUsage.model, usage_filter).order_by(
            func.sum(LLMUsage.cost_usd).desc()
        )
    ).all()
    by_user_rows = session.execute(
        select(
            Task.slack_user_id,
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.input_tokens), 0),
            func.coalesce(func.sum(LLMUsage.output_tokens), 0),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0),
        )
        .join(Task, Task.id == LLMUsage.task_id)
        .where(*usage_filter)
        .group_by(Task.slack_user_id)
        .order_by(func.sum(LLMUsage.cost_usd).desc())
    ).all()
    day_bucket = func.date_trunc("day", LLMUsage.created_at).label("day")
    by_day_rows = session.execute(
        select(
            day_bucket,
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.input_tokens), 0),
            func.coalesce(func.sum(LLMUsage.output_tokens), 0),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0),
        )
        .where(*usage_filter)
        .group_by(day_bucket)
        .order_by(day_bucket.desc())
    ).all()
    return UsageAggregate(
        start=start,
        end=end,
        by_model=tuple(_aggregate_row(row) for row in by_model_rows),
        by_user=tuple(_aggregate_row(row) for row in by_user_rows),
        by_day=tuple(_daily_row(row) for row in by_day_rows),
    )


def parse_date_bound(
    value: str | None, *, inclusive_end: bool = False
) -> datetime | None:
    """Parse dashboard date filters.

    Date-only upper bounds are treated as inclusive by moving to the next day.
    """

    if value is None or value.strip() == "":
        return None
    stripped = value.strip()
    parsed_date = date.fromisoformat(stripped)
    parsed = datetime.combine(parsed_date, time.min, tzinfo=UTC)
    if inclusive_end:
        return parsed + timedelta(days=1)
    return parsed


def _usage_by_task(
    session: Session, task_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LLMUsage]]:
    usage_by_task: dict[uuid.UUID, list[LLMUsage]] = defaultdict(list)
    if not task_ids:
        return usage_by_task
    usage_rows = session.scalars(
        select(LLMUsage)
        .where(LLMUsage.task_id.in_(task_ids))
        .order_by(LLMUsage.created_at.asc(), LLMUsage.id.asc())
    )
    for usage in usage_rows:
        usage_by_task[usage.task_id].append(usage)
    return usage_by_task


def _usage_filter(
    *, start: datetime | None, end: datetime | None
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    if start is not None:
        filters.append(LLMUsage.created_at >= start)
    if end is not None:
        filters.append(LLMUsage.created_at < end)
    return filters


def _aggregate_query(key: Any, filters: list[ColumnElement[bool]]) -> Select[Any]:
    return (
        select(
            key,
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.input_tokens), 0),
            func.coalesce(func.sum(LLMUsage.output_tokens), 0),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0),
        )
        .where(*filters)
        .group_by(key)
    )


def _aggregate_row(row: Row[Any]) -> AggregateRow:
    key, calls, input_tokens, output_tokens, cost_usd = row
    return AggregateRow(
        key=str(key),
        calls=int(calls),
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cost_usd=Decimal(cost_usd),
    )


def _daily_row(row: Row[Any]) -> DailyUsageRow:
    day_value, calls, input_tokens, output_tokens, cost_usd = row
    if isinstance(day_value, datetime):
        day = day_value.date()
    elif isinstance(day_value, date):
        day = day_value
    else:
        day = date.fromisoformat(str(day_value)[:10])
    return DailyUsageRow(
        day=day,
        calls=int(calls),
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        cost_usd=Decimal(cost_usd),
    )
