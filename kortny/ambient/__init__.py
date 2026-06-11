"""Ambient supervisor: one process hosting Kortny's near-idle poller loops.

Kortny ships three near-idle background pollers — the scheduler materializer,
the Witness runner, and the memory consolidator — each previously a separate
container at ~250MB RSS. The ambient supervisor (HIG-234) hosts all three as
supervised threads inside one ``python -m kortny.ambient`` process so the
default ``docker compose up`` is a leaner stack.

Multi-instance safety is unchanged: each loop already guards its mutating work
with a Postgres advisory lock (scheduler / witness / consolidator each hold a
distinct ``pg_try_advisory_lock`` key), so running several ambient processes —
or mixing the merged service with the split scale-out entrypoints — never
double-materializes or double-delivers. The supervisor adds no coordination of
its own; it only hosts the existing ``run_forever`` loops.
"""

from kortny.ambient.supervisor import (
    AmbientSupervisor,
    BackoffPolicy,
    LoopSpec,
    build_default_loops,
)

__all__ = [
    "AmbientSupervisor",
    "BackoffPolicy",
    "LoopSpec",
    "build_default_loops",
]
