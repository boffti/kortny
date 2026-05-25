"""FastAPI app for the read-only Kortny cost dashboard."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from kortny.dashboard.data import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    get_task_detail,
    get_usage_aggregate,
    list_tasks,
    parse_date_bound,
)
from kortny.dashboard.settings import DashboardSettings, load_dashboard_settings
from kortny.db.session import make_session_factory

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

security = HTTPBasic()
templates = Jinja2Templates(directory=TEMPLATE_DIR)


def create_app(
    settings: DashboardSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Create the dashboard app."""

    resolved_settings = settings or load_dashboard_settings()
    resolved_session_factory = session_factory or make_session_factory(
        database_url=resolved_settings.postgres_url
    )
    app = FastAPI(title="Kortny Dashboard", docs_url=None, redoc_url=None)
    app.state.dashboard_settings = resolved_settings
    app.state.session_factory = resolved_session_factory

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    templates.env.filters["money"] = _money
    templates.env.filters["datetime"] = _datetime
    templates.env.filters["json"] = _json

    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    """Register dashboard routes."""

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        _username: Annotated[str, Depends(require_user)],
        session: Annotated[Session, Depends(get_session)],
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    ) -> Response:
        task_page = list_tasks(session, page=page, page_size=page_size)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"task_page": task_page, "page_size": page_size},
        )

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    def task_detail(
        request: Request,
        task_id: UUID,
        _username: Annotated[str, Depends(require_user)],
        session: Annotated[Session, Depends(get_session)],
    ) -> Response:
        detail = get_task_detail(session, task_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return templates.TemplateResponse(
            request=request,
            name="task_detail.html",
            context={"detail": detail},
        )

    @app.get("/usage", response_class=HTMLResponse)
    def usage(
        request: Request,
        _username: Annotated[str, Depends(require_user)],
        session: Annotated[Session, Depends(get_session)],
        from_date: Annotated[str | None, Query(alias="from")] = None,
        to_date: Annotated[str | None, Query(alias="to")] = None,
    ) -> Response:
        start = parse_date_bound(from_date)
        end = parse_date_bound(to_date, inclusive_end=True)
        aggregate = get_usage_aggregate(session, start=start, end=end)
        return templates.TemplateResponse(
            request=request,
            name="usage.html",
            context={
                "aggregate": aggregate,
                "from_date": from_date or "",
                "to_date": to_date or "",
            },
        )

    @app.get("/tasks", include_in_schema=False)
    def tasks_redirect(
        _username: Annotated[str, Depends(require_user)],
    ) -> RedirectResponse:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


def require_user(
    request: Request,
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    """Require dashboard HTTP Basic Auth."""

    settings = cast(DashboardSettings, request.app.state.dashboard_settings)
    username_ok = secrets.compare_digest(credentials.username, settings.username)
    password_ok = secrets.compare_digest(credentials.password, settings.password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_session(request: Request) -> Iterator[Session]:
    """Yield a database session for dashboard requests."""

    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    with factory() as session:
        yield session


def _money(value: Decimal | int | float | str | None) -> str:
    if value is None:
        return "$0.000000"
    return f"${Decimal(value):,.6f}"


def _datetime(value: object) -> str:
    if value is None:
        return "-"
    return str(value).replace("+00:00", " UTC")


def _json(value: object) -> str:
    if value is None:
        return "{}"
    return str(value)
