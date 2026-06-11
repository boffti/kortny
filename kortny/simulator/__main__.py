"""Workspace simulator CLI.

Seeds, inspects, and removes a deterministic backdated "Acme Robotics" team
history directly in the database so the ambient stack (witness extraction,
candidate lifecycle, accept-to-automation) can be exercised and demoed
without waiting weeks of real time.

Canonical invocation (against the live dev database inside compose):

    docker compose exec worker uv run python -m kortny.simulator \
        seed --channel C0123456789 --days 21
    docker compose exec worker uv run python -m kortny.simulator status
    docker compose exec worker uv run python -m kortny.simulator clean

``seed`` requires an explicit ``--channel`` (use a real test channel ID so
post-accept confirmations land somewhere visible) and refuses to run when no
installation exists. Nothing is posted to Slack and no LLM is called.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from kortny.config import load_settings
from kortny.db.session import make_session_factory, session_scope
from kortny.simulator.fixtures import DEFAULT_SIM_DAYS
from kortny.simulator.seeder import (
    CleanReport,
    SeedReport,
    SimulatorError,
    StatusReport,
    clean_simulation,
    seed_simulation,
    simulation_status,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the simulator argument parser."""

    parser = argparse.ArgumentParser(
        prog="python -m kortny.simulator",
        description="Seed, inspect, or remove backdated synthetic history.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser(
        "seed",
        help="Inject the backdated fixture story for one channel.",
    )
    seed_parser.add_argument(
        "--channel",
        required=True,
        help="Slack channel ID the history attaches to (e.g. C0123456789).",
    )
    seed_parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_SIM_DAYS,
        help=f"Backdated window length in days (default {DEFAULT_SIM_DAYS}).",
    )

    subparsers.add_parser("clean", help="Delete all simulator-seeded rows.")
    subparsers.add_parser("status", help="Print current simulator row counts.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint; returns a process exit code."""

    args = build_parser().parse_args(argv)
    settings = load_settings()
    session_factory = make_session_factory(database_url=settings.postgres_url)

    try:
        with session_scope(session_factory) as session:
            if args.command == "seed":
                _print_seed_report(
                    seed_simulation(
                        session,
                        channel_id=args.channel,
                        days=args.days,
                    )
                )
            elif args.command == "clean":
                _print_clean_report(clean_simulation(session))
            else:
                _print_status_report(simulation_status(session))
    except SimulatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _print_seed_report(report: SeedReport) -> None:
    print(f"seeded channel {report.channel_id} ({report.days} days)")
    print(f"  installation: {report.installation_team_id}")
    print(
        "  observation events: "
        f"{report.observation_events_created} created, "
        f"{report.observation_events_existing} already present"
    )
    print(f"  distinct message days: {report.distinct_message_days}")
    print(f"  observation policy observable: {report.policy_observable}")
    print(
        "  channel membership: "
        + ("created by simulator" if report.membership_created else "existing")
        + ("" if report.membership_active else " (warning: not active)")
    )
    print(
        "  channel profile: "
        + ("created" if report.profile_created else "updated")
        + f" (version {report.profile_version}, scan-due for witness)"
    )
    print(
        f"  synthetic tasks: {report.tasks_created} created, "
        f"{report.tasks_existing} already present"
    )
    print(f"  episodes recorded: {report.episodes_recorded}")


def _print_clean_report(report: CleanReport) -> None:
    print("cleaned simulator rows")
    print(f"  witness candidates deleted: {report.candidates_deleted}")
    for note in report.automated_candidate_notes:
        print(f"    note: {note}")
    print(f"  episodes deleted: {report.episodes_deleted}")
    print(f"  channel profiles deleted: {report.profiles_deleted}")
    print(f"  task events deleted: {report.task_events_deleted}")
    print(f"  tasks deleted: {report.tasks_deleted}")
    print(f"  observation events deleted: {report.observation_events_deleted}")
    print(f"  sim-created memberships deleted: {report.memberships_deleted}")


def _print_status_report(report: StatusReport) -> None:
    print("simulator status")
    print(f"  observation events: {report.observation_events}")
    print(f"  distinct message days: {report.distinct_message_days}")
    versions = ", ".join(str(version) for version in report.profile_versions)
    print(
        f"  channel profiles: {report.profiles}"
        + (f" (versions: {versions})" if versions else "")
    )
    print(f"  synthetic tasks: {report.tasks}")
    print(f"  task events: {report.task_events}")
    print(f"  episodes: {report.episodes}")
    if report.candidates_by_status:
        breakdown = ", ".join(
            f"{status}={count}"
            for status, count in sorted(report.candidates_by_status.items())
        )
        print(f"  derived witness candidates: {breakdown}")
    else:
        print("  derived witness candidates: none")
    print(f"  sim-created memberships: {report.memberships}")


if __name__ == "__main__":
    raise SystemExit(main())
