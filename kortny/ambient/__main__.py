"""Run Kortny's merged ambient poller service with ``python -m kortny.ambient``.

Hosts the scheduler, witness, and consolidator loops as supervised threads in
one process (HIG-234). The three split entrypoints (``python -m
kortny.scheduler`` / ``kortny.witness`` / ``kortny.consolidator``) keep working
unchanged as the documented scale-out path; advisory locks make running both
forms simultaneously safe.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from kortny.ambient.supervisor import AmbientSupervisor, build_default_loops
from kortny.config import Settings, load_settings
from kortny.logging_config import configure_logging
from kortny.observability import configure_tracing

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for the ambient supervisor."""

    configure_logging()
    parser = argparse.ArgumentParser(description="Run the Kortny ambient service")
    parser.add_argument(
        "--list-loops",
        action="store_true",
        help="Print which loops would run, then exit without starting threads",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_tracing(settings)

    loops = build_default_loops(settings)
    if args.list_loops:
        for spec in loops:
            state = "enabled" if spec.enabled else "disabled"
            print(f"{spec.name}: {state}")
        return

    _seed_system_drives(settings)

    supervisor = AmbientSupervisor(loops)
    supervisor.install_signal_handlers()
    live = supervisor.start()
    logger.info("ambient supervisor started loops=%s", ", ".join(live) or "(none)")
    if not live:
        logger.warning("ambient supervisor has no enabled loops; exiting")
        return
    supervisor.join()
    logger.info("ambient supervisor stopped")


def _seed_system_drives(settings: Settings) -> None:
    """Idempotently seed the user-visible system drive rows at boot (HIG-233)."""

    from kortny.ambient.system_drives import seed_system_drives_for_all_installations
    from kortny.db.session import make_session_factory

    try:
        ensured = seed_system_drives_for_all_installations(
            make_session_factory(), settings=settings
        )
        logger.info("ambient system drives seeded rows=%s", ensured)
    except Exception:
        # Seeding is a visibility convenience; a failure must not stop the loops.
        logger.exception("ambient system drive seeding failed; continuing")


if __name__ == "__main__":
    main()
