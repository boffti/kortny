"""App Home console tests (HIG-232).

Real-Postgres tests in the style of ``tests/test_slack_ingress.py``: a fake
Slack client records ``views_publish`` / ``views_open`` calls, and the pure
``build_home_view`` builder is exercised against seeded rows.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from slack_bolt import App
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from kortny.config import Settings
from kortny.db.models import (
    DashboardUser,
    Installation,
    LLMProvider,
    LLMUsage,
    ProceduralSkill,
    ProceduralSkillInvocation,
    ProceduralSkillVersion,
    SkillEnablement,
    SkillFile,
    Task,
    TaskStatus,
    WitnessOpportunityCandidate,
)
from kortny.db.session import make_engine, make_session_factory, normalize_database_url
from kortny.skills.ingestion import IngestedSkill, SkillIngestionService
from kortny.slack import blockkit
from kortny.slack.app_home import (
    ADD_SKILL_ACTION,
    ADD_SKILL_MODAL_CALLBACK,
    DISABLE_SKILL_ACTION,
    ENABLE_SKILL_ACTION,
    MANAGE_MCP_ACTION,
    SKILL_MARKDOWN_ACTION_ID,
    SKILL_MARKDOWN_BLOCK_ID,
    SKILL_NAME_ACTION_ID,
    SKILL_NAME_BLOCK_ID,
    WITNESS_ACCEPT_ACTION,
    WITNESS_DISMISS_ACTION,
    build_home_view,
    register_app_home,
    resolve_dashboard_role,
)

TEST_POSTGRES_URL = os.environ.get("KORTNY_TEST_POSTGRES_URL")


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_APP_TOKEN": "xapp-test",
            "SLACK_SIGNING_SECRET": "secret",
            "LLM_PROVIDER": "openai",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "gpt-4o-mini",
            "POSTGRES_URL": "postgresql://kortny:kortny@localhost:5432/kortny",
            "COMPOSIO_API_KEY": "test-composio",
            "KORTNY_PUBLIC_BASE_URL": "https://kortny.example.com",
        }
    )


class FakeAppHomeClient:
    """Records views_publish / views_open the way Bolt's client would."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.opened: list[dict[str, Any]] = []

    def views_publish(self, *, user_id: str, view: dict[str, Any]) -> dict[str, Any]:
        self.published.append({"user_id": user_id, "view": view})
        return {"ok": True}

    def views_open(self, *, trigger_id: str, view: dict[str, Any]) -> dict[str, Any]:
        self.opened.append({"trigger_id": trigger_id, "view": view})
        return {"ok": True}


class FakeBoltApp:
    """Captures handlers registered by ``register_app_home``."""

    def __init__(self) -> None:
        self.event_handlers: dict[str, Any] = {}
        self.action_handlers: list[Any] = []
        self.view_handlers: list[Any] = []

    def event(self, name: str) -> Any:
        def decorator(func: Any) -> Any:
            self.event_handlers[name] = func
            return func

        return decorator

    def action(self, _matcher: Any) -> Any:
        def decorator(func: Any) -> Any:
            self.action_handlers.append(func)
            return func

        return decorator

    def view(self, _matcher: Any) -> Any:
        def decorator(func: Any) -> Any:
            self.view_handlers.append(func)
            return func

        return decorator


def _noop_ack() -> None:
    return None


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if TEST_POSTGRES_URL is None:
        pytest.skip("KORTNY_TEST_POSTGRES_URL is required for App Home tests")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", normalize_database_url(TEST_POSTGRES_URL))
    command.upgrade(config, "head")

    engine = make_engine(TEST_POSTGRES_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session_factory = make_session_factory(engine=engine)
    with session_factory() as session:
        cleanup_database(session)
        session.commit()
        yield session
        session.rollback()
        cleanup_database(session)
        session.commit()


def cleanup_database(session: Session) -> None:
    for model in (
        SkillEnablement,
        ProceduralSkillInvocation,
        SkillFile,
        ProceduralSkillVersion,
        ProceduralSkill,
        LLMUsage,
        Task,
        DashboardUser,
        Installation,
    ):
        session.execute(delete(model))


def create_installation(
    session: Session, *, slack_team_id: str = "T123"
) -> Installation:
    installation = Installation(slack_team_id=slack_team_id)
    session.add(installation)
    session.flush()
    return installation


def create_dashboard_user(
    session: Session,
    *,
    installation_id: uuid.UUID,
    slack_user_id: str,
    role: str,
) -> DashboardUser:
    user = DashboardUser(
        installation_id=installation_id,
        slack_user_id=slack_user_id,
        email=f"{slack_user_id}@example.com",
        display_name=slack_user_id,
        role=role,
        status="active",
    )
    session.add(user)
    session.flush()
    return user


def create_task(
    session: Session,
    *,
    installation_id: uuid.UUID,
    slack_user_id: str,
    input_text: str,
    status: TaskStatus,
    message_ts: str,
) -> Task:
    task = Task(
        installation_id=installation_id,
        slack_event_id=f"Ev{uuid.uuid4().hex}",
        slack_channel_id="C123",
        slack_thread_ts=message_ts,
        slack_message_ts=message_ts,
        slack_user_id=slack_user_id,
        input=input_text,
        status=status,
    )
    session.add(task)
    session.flush()
    return task


def seed_usage(
    session: Session,
    *,
    task: Task,
    model: str = "gpt-4o-mini",
    cost: str = "0.50",
) -> None:
    session.add(
        LLMUsage(
            task_id=task.id,
            provider=LLMProvider.openai,
            model=model,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=Decimal(cost),
        )
    )
    session.flush()


def seed_skill(
    session: Session,
    *,
    installation_id: uuid.UUID,
    name: str,
    description: str,
) -> IngestedSkill:
    content = (
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        "# Instructions\n\nDo the thing.\n"
    )
    ingested = SkillIngestionService(session).ingest_markdown(
        content,
        owner_type="workspace",
        owner_id=str(installation_id),
        provenance="test",
        trust_level="untrusted",
        created_by="test",
    )
    session.flush()
    return ingested


def _section_texts(view: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for block in view["blocks"]:
        if block["type"] == "section":
            if "text" in block:
                texts.append(block["text"]["text"])
            for field in block.get("fields", []):
                texts.append(field["text"])
        elif block["type"] == "card":
            for key in ("title", "subtitle", "body"):
                if key in block:
                    texts.append(block[key]["text"])
        elif block["type"] == "carousel":
            for element in block["elements"]:
                for key in ("title", "subtitle", "body"):
                    if key in element:
                        texts.append(element[key]["text"])
    return texts


def _all_buttons(view: dict[str, Any]) -> list[dict[str, Any]]:
    """Buttons from actions blocks, card actions, and section accessories."""

    buttons: list[dict[str, Any]] = []
    for block in view["blocks"]:
        if block["type"] == "actions":
            buttons.extend(block["elements"])
        elif block["type"] == "card":
            buttons.extend(block.get("actions", []))
        elif block["type"] == "carousel":
            for element in block["elements"]:
                buttons.extend(element.get("actions", []))
        accessory = block.get("accessory")
        if accessory and accessory.get("type") == "button":
            buttons.append(accessory)
    return buttons


def _header_texts(view: dict[str, Any]) -> list[str]:
    return [
        block["text"]["text"] for block in view["blocks"] if block["type"] == "header"
    ]


# --- build_home_view --------------------------------------------------------


def test_build_home_view_renders_all_panels_within_block_budget(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    task = create_task(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        input_text="research the pandas migration plan",
        status=TaskStatus.succeeded,
        message_ts="1716400000.000001",
    )
    seed_usage(db_session, task=task, model="gpt-4o-mini", cost="1.25")
    seed_skill(
        db_session,
        installation_id=installation.id,
        name="weekly-recap",
        description="Summarize the week for the team.",
    )
    db_session.flush()

    view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        settings=_settings(),
    )

    assert view["type"] == "home"
    assert len(view["blocks"]) <= blockkit.MAX_VIEW_BLOCKS
    # One page-title header; panel headers are bold sections with accessory
    # CTAs (Slack's own home-tab convention).
    assert _header_texts(view) == ["Your Kortny console"]
    texts = "\n".join(_section_texts(view))
    for panel in (
        "*Recent tasks*",
        "*Skills*",
        "*Connected accounts*",
        "*MCP servers*",
    ):
        assert panel in texts
    assert "Tasks run" in texts
    assert "$1.25" in texts
    assert "gpt-4o-mini" in texts
    assert "research the pandas migration plan" in texts
    assert "weekly-recap" in texts


def test_build_home_view_renders_empty_states(db_session: Session) -> None:
    installation = create_installation(db_session)

    view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="Unobody",
        settings=_settings(),
    )

    texts = "\n".join(_section_texts(view))
    assert "No tasks yet" in texts
    assert "No connected accounts yet" in texts
    assert "No MCP servers registered" in texts
    # Usage panel still renders zeroed numbers.
    assert "Tasks run" in texts


def test_build_home_view_skill_row_has_enable_button_when_disabled(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    seed_skill(
        db_session,
        installation_id=installation.id,
        name="weekly-recap",
        description="Summarize the week.",
    )
    db_session.flush()

    view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        settings=_settings(),
    )

    enable_buttons = [
        element
        for element in _all_buttons(view)
        if element.get("action_id") == ENABLE_SKILL_ACTION
    ]
    assert len(enable_buttons) == 1


def test_resolve_dashboard_role(db_session: Session) -> None:
    installation = create_installation(db_session)
    create_dashboard_user(
        db_session,
        installation_id=installation.id,
        slack_user_id="Uadmin",
        role="admin",
    )
    db_session.flush()

    assert resolve_dashboard_role(db_session, installation.id, "Uadmin") == "admin"
    assert resolve_dashboard_role(db_session, installation.id, "Umissing") is None


def test_build_home_view_admin_sees_manage_mcp_row(db_session: Session) -> None:
    installation = create_installation(db_session)
    create_dashboard_user(
        db_session,
        installation_id=installation.id,
        slack_user_id="Uadmin",
        role="admin",
    )
    create_dashboard_user(
        db_session,
        installation_id=installation.id,
        slack_user_id="Umember",
        role="member",
    )
    db_session.flush()

    admin_view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="Uadmin",
        settings=_settings(),
    )
    member_view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="Umember",
        settings=_settings(),
    )

    def has_manage_mcp(view: dict[str, Any]) -> bool:
        # The manage button rides as a section accessory on the panel header.
        for block in view["blocks"]:
            accessory = block.get("accessory")
            if accessory and accessory.get("action_id") == MANAGE_MCP_ACTION:
                return True
        return False

    assert has_manage_mcp(admin_view) is True
    assert has_manage_mcp(member_view) is False


# --- handlers ---------------------------------------------------------------


def test_app_home_opened_publishes_for_home_tab(db_session: Session) -> None:
    installation = create_installation(db_session)
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    app.event_handlers["app_home_opened"](
        ack=_noop_ack,
        event={"tab": "home", "user": "U123", "team": "T123"},
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    assert len(client.published) == 1
    assert client.published[0]["user_id"] == "U123"
    assert client.published[0]["view"]["type"] == "home"
    del installation


def test_app_home_opened_skips_messages_tab(db_session: Session) -> None:
    create_installation(db_session)
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    app.event_handlers["app_home_opened"](
        ack=_noop_ack,
        event={"tab": "messages", "user": "U123", "team": "T123"},
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    assert client.published == []


def test_enable_skill_action_creates_user_scope_enablement(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    ingested = seed_skill(
        db_session,
        installation_id=installation.id,
        name="weekly-recap",
        description="Summarize the week.",
    )
    skill_id = ingested.skill.id
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    app.action_handlers[0](
        ack=_noop_ack,
        body={"user": {"id": "U123"}, "team": {"id": "T123"}},
        action={"action_id": ENABLE_SKILL_ACTION, "value": str(skill_id)},
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    enablement = db_session.scalar(
        select(SkillEnablement).where(SkillEnablement.skill_id == skill_id)
    )
    assert enablement is not None
    assert enablement.scope_type == "user"
    assert enablement.scope_id == "U123"
    assert enablement.status == "enabled"
    assert enablement.added_by == "slack:U123"
    assert len(client.published) == 1


def test_add_skill_button_opens_modal(db_session: Session) -> None:
    create_installation(db_session)
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    app.action_handlers[0](
        ack=_noop_ack,
        body={
            "user": {"id": "U123"},
            "team": {"id": "T123"},
            "trigger_id": "trigger-123",
        },
        action={"action_id": ADD_SKILL_ACTION},
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    assert len(client.opened) == 1
    assert client.opened[0]["trigger_id"] == "trigger-123"
    assert client.opened[0]["view"]["callback_id"] == ADD_SKILL_MODAL_CALLBACK
    # No publish happens on modal open.
    assert client.published == []


def test_add_skill_view_submission_ingests_markdown_and_republishes(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    markdown = (
        "---\nname: from-modal\ndescription: Added from the App Home modal.\n---\n\n"
        "# Instructions\n\nGreet the team.\n"
    )
    app.view_handlers[0](
        ack=_noop_ack,
        body={"user": {"id": "U123"}},
        view={
            "callback_id": ADD_SKILL_MODAL_CALLBACK,
            "private_metadata": "U123|T123",
            "state": {
                "values": {
                    SKILL_NAME_BLOCK_ID: {
                        SKILL_NAME_ACTION_ID: {"value": "From Modal"}
                    },
                    SKILL_MARKDOWN_BLOCK_ID: {
                        SKILL_MARKDOWN_ACTION_ID: {"value": markdown}
                    },
                }
            },
        },
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    skill = db_session.scalar(
        select(ProceduralSkill).where(
            ProceduralSkill.owner_id == str(installation.id),
            ProceduralSkill.slug == "from-modal",
        )
    )
    assert skill is not None
    assert skill.status == "active"
    assert len(client.published) == 1
    assert client.published[0]["user_id"] == "U123"


def test_disable_skill_action_disables_enablement(db_session: Session) -> None:
    installation = create_installation(db_session)
    ingested = seed_skill(
        db_session,
        installation_id=installation.id,
        name="weekly-recap",
        description="Summarize the week.",
    )
    enablement = SkillEnablement(
        installation_id=installation.id,
        skill_id=ingested.skill.id,
        scope_type="user",
        scope_id="U123",
        status="enabled",
        added_by="slack:U123",
    )
    db_session.add(enablement)
    db_session.flush()
    enablement_id = enablement.id
    db_session.commit()

    app = FakeBoltApp()
    session_factory = make_session_factory(
        engine=db_session.get_bind()  # type: ignore[arg-type]
    )
    register_app_home(
        cast(App, app), settings=_settings(), session_factory=session_factory
    )
    client = FakeAppHomeClient()

    app.action_handlers[0](
        ack=_noop_ack,
        body={"user": {"id": "U123"}, "team": {"id": "T123"}},
        action={"action_id": DISABLE_SKILL_ACTION, "value": str(enablement_id)},
        client=client,
        logger=__import__("logging").getLogger("test"),
    )

    db_session.expire_all()
    refreshed = db_session.get(SkillEnablement, enablement_id)
    assert refreshed is not None
    assert refreshed.status == "disabled"
    assert len(client.published) == 1


def test_build_home_view_waiting_panel_shows_sent_candidates(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    candidate = WitnessOpportunityCandidate(
        installation_id=installation.id,
        channel_id="C123",
        target_slack_user_id=None,
        visibility_scope_type="channel",
        visibility_scope_id="C123",
        candidate_type="recurring_check",
        title="Daily trading summary",
        summary="The desk posts a manual summary every morning.",
        suggested_action="Automate the daily summary.",
        suggested_message="Want me to take this over?",
        evidence_json=[],
        source_type="channel_profile",
        source_id=None,
        source_task_id=None,
        source_profile_id=None,
        dedupe_key=uuid.uuid4().hex[:32],
        confidence_score=Decimal("0.9"),
        confidence_reason="test fixture",
        status="sent",
        feedback_json={},
        metadata_json={},
    )
    db_session.add(candidate)
    db_session.flush()

    view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        settings=_settings(),
    )

    texts = "\n".join(_section_texts(view))
    assert "*Waiting on you*" in texts
    assert "Daily trading summary" in texts
    buttons = _all_buttons(view)
    action_ids = [element.get("action_id") for element in buttons]
    assert WITNESS_ACCEPT_ACTION in action_ids
    assert WITNESS_DISMISS_ACTION in action_ids
    accept = next(
        element
        for element in buttons
        if element.get("action_id") == WITNESS_ACCEPT_ACTION
    )
    assert accept["value"] == str(candidate.id)


def test_build_home_view_omits_waiting_panel_when_empty(
    db_session: Session,
) -> None:
    installation = create_installation(db_session)
    db_session.flush()

    view = build_home_view(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        settings=_settings(),
    )

    assert "*Waiting on you*" not in "\n".join(_section_texts(view))


def test_composio_tool_call_counts_attributes_by_longest_slug(
    db_session: Session,
) -> None:
    from kortny.db.models import TaskEvent, TaskEventType
    from kortny.slack.app_home import _composio_tool_usage

    installation = create_installation(db_session)
    task = create_task(
        db_session,
        installation_id=installation.id,
        slack_user_id="U123",
        input_text="use some tools",
        status=TaskStatus.succeeded,
        message_ts="1716400003.000001",
    )
    for seq, tool in enumerate(
        (
            "composio_alpha_vantage_get_quote",
            "composio_alpha_vantage_get_quote",
            "composio_exa_search",
            "web_search",
        ),
        start=1,
    ):
        db_session.add(
            TaskEvent(
                task_id=task.id,
                seq=seq,
                type=TaskEventType.tool_call,
                payload={"tool": tool},
            )
        )
    db_session.flush()

    usage = _composio_tool_usage(
        db_session,
        installation_id=installation.id,
        toolkit_slugs=["exa", "alpha_vantage", "alpha"],
    )

    assert set(usage) == {"alpha_vantage", "exa"}
    assert usage["alpha_vantage"].calls == 2
    assert usage["alpha_vantage"].distinct_tools == 1
    assert usage["alpha_vantage"].last_used is not None
    assert usage["exa"].calls == 1
