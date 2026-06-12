"""Startup-time skill catalog seeding.

A fresh install has zero skills until something seeds the builtin + curated
catalog (HIG-239 ships a 45-skill curated pack). Previously this only happened
when an admin opened the dashboard ``/skills`` page, so fresh-install
correctness depended on a manual page view. ``seed_skills_at_startup`` runs the
same idempotent seeding once at worker and dashboard boot.

Every failure path logs a warning and returns: seeding must never prevent a
service from booting.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from kortny.config import Settings
from kortny.embeddings import embedding_index_from_settings
from kortny.skills.service import SkillRegistryService

logger = logging.getLogger(__name__)


def seed_skills_at_startup(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    """Idempotently seed builtin + curated skills at service startup.

    Takes a Postgres ``pg_try_advisory_lock`` (same approach as scheduler /
    witness leader election, with a dedicated key) so concurrent services don't
    race; if the lock is held another service is already seeding and this call
    skips without error. The embedding index is built failure-isolated from
    settings so skill cards embed on seed when configured.

    Fully failure-isolated: any exception logs a warning and returns.
    """

    lock_key = settings.skills_seed_advisory_lock_key
    try:
        with session_factory() as session:
            if not _try_advisory_lock(session, lock_key):
                logger.info(
                    "skill seeding skipped: advisory lock %s held by another "
                    "service (already seeding)",
                    lock_key,
                )
                return
            try:
                index = embedding_index_from_settings(session, settings)
                service = SkillRegistryService(session, embedding_index=index)
                service.ensure_builtin_skills()
                service.ensure_curated_skills()
                session.commit()
                logger.info("skill catalog seeded at startup")
            finally:
                _release_advisory_lock(session, lock_key)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        logger.warning("skill seeding at startup failed; continuing", exc_info=True)


def _try_advisory_lock(session: Session, lock_key: int) -> bool:
    return bool(session.scalar(select(func.pg_try_advisory_lock(lock_key))))


def _release_advisory_lock(session: Session, lock_key: int) -> None:
    session.execute(select(func.pg_advisory_unlock(lock_key)))
