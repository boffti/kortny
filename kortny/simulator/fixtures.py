"""Deterministic "Acme Robotics" fixture story for the workspace simulator.

The story spans a configurable backdated window and is generated from the
current time at seed time — no LLM, no network, no randomness. Four personas
talk in one channel and exhibit the patterns the ambient stack (observe →
witness → automation) must discover:

1. A daily manual end-of-day trading summary, posted every weekday at ~17:00
   (recurring automation bait).
2. A weekly status report compiled by hand every Friday (recurring bait).
3. A one-shot verification ask that is never resolved (one_shot bait).
4. A vendor decision thread that trails off (unresolved_decision bait).
5. Greetings, meme references, and ops chatter as noise the extractor has to
   discriminate against.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from datetime import date as date_cls

SIM_MARKER_KEY = "sim"
SIM_SOURCE = "workspace_simulator"
SIM_TASK_IDENTITY_SOURCE = "sim"
SIM_TASK_IDENTITY_PREFIX = "synthetic:sim:"
SIM_EVENT_ID_PREFIX = "sim:"

DEFAULT_SIM_DAYS = 21


@dataclass(frozen=True, slots=True)
class SimPersona:
    """A fake team member; the user id is intentionally non-real."""

    user_id: str
    display_name: str
    role: str


@dataclass(frozen=True, slots=True)
class SimMessage:
    """One deterministic channel message in the fixture story."""

    slug: str
    persona: SimPersona
    sent_at: datetime
    text: str
    pattern: str
    thread_slug: str | None = None

    @property
    def message_ts(self) -> str:
        """Slack-style message timestamp derived from the send time."""

        return f"{self.sent_at.timestamp():.6f}"


PRIYA = SimPersona("USIM01", "Priya Raman", "trading operations lead")
MARCO = SimPersona("USIM02", "Marco Diaz", "quant developer")
JEN = SimPersona("USIM03", "Jen Park", "program manager")
SAM = SimPersona("USIM04", "Sam Okafor", "infrastructure engineer")

PERSONAS: tuple[SimPersona, ...] = (PRIYA, MARCO, JEN, SAM)

_GREETERS: tuple[SimPersona, ...] = (MARCO, JEN, SAM, PRIYA)
_GREETINGS: tuple[str, ...] = (
    "morning all, coffee acquired",
    "good morning team",
    "hey folks, happy {weekday}",
    "morning! desk is up and running",
)
_OPS_CHATTER: tuple[str, ...] = (
    "heads up: rotating the staging API keys this afternoon, expect a blip",
    "deploy of the risk service went out clean, no alerts so far",
    "anyone else seeing slow CI on the data repo? re-running the flaky job",
    "reminder: change freeze starts Friday 16:00 as usual",
)
_MEMES: tuple[str, ...] = (
    "that spreadsheet is held together by hopes and vlookups, send the meme",
    "this is fine (it is not fine) — the dashboard gif goes here",
    "obligatory friday robot-dance gif before the status scramble",
)

_TRADING_LINES: tuple[str, ...] = (
    "EOD trading summary for {date}: desk PnL {pnl}k, {fills} fills, "
    "top book ACME-{book}. Compiled by hand from the blotter as usual.",
    "EOD trading summary {date} — PnL {pnl}k, volume {fills} lots, "
    "no breaks. Copy-pasted the numbers from the blotter export again.",
    "EOD trading summary, {date}: {pnl}k on the day across {fills} tickets. "
    "Manual roll-up of the blotter; shout if a number looks off.",
)

_STATUS_REPLIES: tuple[tuple[SimPersona, str], ...] = (
    (
        MARCO,
        "signals backtest at 80%, refactoring the order-router config this week",
    ),
    (
        SAM,
        "rack migration done, telemetry collectors for the fleet still pending",
    ),
)


def build_story(*, now: datetime, days: int) -> tuple[SimMessage, ...]:
    """Build the deterministic message history for a backdated window.

    Messages are ordered by send time and every send time is strictly within
    ``[now - days, now]``. The schedule is calendar-aware so the "every
    weekday at 17:00" pattern is real for any window.
    """

    if days < 1:
        raise ValueError("days must be >= 1")
    now = now.astimezone(UTC)
    window_start = now - timedelta(days=days)

    messages: list[SimMessage] = []
    day_count = days + 1
    for day_index in range(day_count):
        date = (window_start + timedelta(days=day_index)).date()
        weekday = date.weekday()
        day_messages: list[SimMessage] = []

        if weekday in (0, 2):  # Monday / Wednesday greeting noise
            persona = _GREETERS[day_index % len(_GREETERS)]
            greeting = _GREETINGS[day_index % len(_GREETINGS)].format(
                weekday=date.strftime("%A")
            )
            day_messages.append(
                SimMessage(
                    slug=f"noise-greeting-{date.isoformat()}",
                    persona=persona,
                    sent_at=_at(date, 9, 5),
                    text=greeting,
                    pattern="noise",
                )
            )
        if weekday in (1, 3):  # Tuesday / Thursday ops chatter noise
            day_messages.append(
                SimMessage(
                    slug=f"noise-ops-{date.isoformat()}",
                    persona=SAM,
                    sent_at=_at(date, 14, 20),
                    text=_OPS_CHATTER[day_index % len(_OPS_CHATTER)],
                    pattern="noise",
                )
            )

        if weekday == 4:  # Friday: manual weekly status compilation
            day_messages.extend(_friday_status_messages(date))
            day_messages.append(
                SimMessage(
                    slug=f"noise-meme-{date.isoformat()}",
                    persona=MARCO,
                    sent_at=_at(date, 15, 45),
                    text=_MEMES[day_index % len(_MEMES)],
                    pattern="noise",
                )
            )

        if weekday < 5:  # Every weekday: manual EOD trading summary at 17:00
            line = _TRADING_LINES[day_index % len(_TRADING_LINES)]
            day_messages.append(
                SimMessage(
                    slug=f"trading-summary-{date.isoformat()}",
                    persona=PRIYA,
                    sent_at=_at(date, 17, 0),
                    text=line.format(
                        date=date.isoformat(),
                        pnl=((day_index * 137) % 480) - 90,
                        fills=120 + (day_index * 23) % 240,
                        book=chr(ord("A") + day_index % 4),
                    ),
                    pattern="trading_summary",
                )
            )

        messages.extend(
            message
            for message in day_messages
            if window_start <= message.sent_at <= now
        )

    messages.extend(
        message
        for message in _one_shot_messages(window_start, days)
        if window_start <= message.sent_at <= now
    )
    messages.extend(
        message
        for message in _vendor_decision_messages(window_start, days)
        if window_start <= message.sent_at <= now
    )

    messages.sort(key=lambda message: (message.sent_at, message.slug))
    return tuple(messages)


def _friday_status_messages(date: date_cls) -> list[SimMessage]:
    ask_slug = f"status-ask-{date.isoformat()}"
    messages = [
        SimMessage(
            slug=ask_slug,
            persona=JEN,
            sent_at=_at(date, 10, 0),
            text=(
                "It's Friday — please drop your status updates in this thread "
                "by noon so I can compile the weekly report for leadership."
            ),
            pattern="weekly_status",
        )
    ]
    for offset_minutes, (persona, update) in zip(
        (30, 55), _STATUS_REPLIES, strict=True
    ):
        messages.append(
            SimMessage(
                slug=f"status-reply-{persona.user_id.lower()}-{date.isoformat()}",
                persona=persona,
                sent_at=_at(date, 10, offset_minutes),
                text=update,
                pattern="weekly_status",
                thread_slug=ask_slug,
            )
        )
    messages.append(
        SimMessage(
            slug=f"status-report-{date.isoformat()}",
            persona=JEN,
            sent_at=_at(date, 12, 0),
            text=(
                f"Weekly status report, week of {date.isoformat()} (compiled "
                "by hand again): trading desk steady, signals backtest "
                "progressing, infra migration on track. Full doc pasted into "
                "the leadership email as usual."
            ),
            pattern="weekly_status",
        )
    )
    return messages


def _one_shot_messages(
    window_start: datetime,
    days: int,
) -> tuple[SimMessage, ...]:
    """A verification ask in the middle of the window that nobody resolves."""

    date = (window_start + timedelta(days=max(days // 2, 1))).date()
    return (
        SimMessage(
            slug=f"oneshot-q2-verify-{date.isoformat()}",
            persona=MARCO,
            sent_at=_at(date, 11, 15),
            text=(
                "Someone needs to double-check the Q2 pipeline numbers doc "
                "before Thursday — I haven't had time and finance is waiting "
                "on it."
            ),
            pattern="one_shot",
        ),
    )


def _vendor_decision_messages(
    window_start: datetime,
    days: int,
) -> tuple[SimMessage, ...]:
    """A two-day vendor debate thread that trails off unresolved."""

    first = (window_start + timedelta(days=max(days // 3, 1))).date()
    second = first + timedelta(days=1)
    root_slug = f"vendor-decision-{first.isoformat()}"
    return (
        SimMessage(
            slug=root_slug,
            persona=SAM,
            sent_at=_at(first, 13, 0),
            text=(
                "We still need to pick a fleet telemetry vendor: TelemetryHub "
                "is cheaper but GridWatch has the better alerting story. "
                "Thoughts before I draft the contract request?"
            ),
            pattern="unresolved_decision",
        ),
        SimMessage(
            slug=f"vendor-decision-reply1-{first.isoformat()}",
            persona=MARCO,
            sent_at=_at(first, 13, 25),
            text=(
                "GridWatch's API rate limits worry me; TelemetryHub publishes "
                "theirs at least."
            ),
            pattern="unresolved_decision",
            thread_slug=root_slug,
        ),
        SimMessage(
            slug=f"vendor-decision-reply2-{second.isoformat()}",
            persona=JEN,
            sent_at=_at(second, 9, 40),
            text=(
                "Budget-wise either works this quarter. Do we have a "
                "decision owner for this?"
            ),
            pattern="unresolved_decision",
            thread_slug=root_slug,
        ),
        SimMessage(
            slug=f"vendor-decision-reply3-{second.isoformat()}",
            persona=SAM,
            sent_at=_at(second, 16, 10),
            text="Let's revisit next week, swamped with the rack move.",
            pattern="unresolved_decision",
            thread_slug=root_slug,
        ),
    )


def _at(date: date_cls, hour: int, minute: int) -> datetime:
    return datetime.combine(date, time(hour=hour, minute=minute), tzinfo=UTC)
