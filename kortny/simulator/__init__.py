"""Workspace simulator: backdated synthetic team history for ambient testing.

See ``kortny/simulator/__main__.py`` for the CLI and ``docs/simulator.md``
for the quickstart.
"""

from kortny.simulator.fixtures import (
    DEFAULT_SIM_DAYS,
    PERSONAS,
    SIM_EVENT_ID_PREFIX,
    SIM_MARKER_KEY,
    SIM_SOURCE,
    SIM_TASK_IDENTITY_PREFIX,
    SimMessage,
    SimPersona,
    build_story,
)
from kortny.simulator.seeder import (
    SIM_TASK_SPECS,
    CleanReport,
    SeedReport,
    SimulatorError,
    StatusReport,
    clean_simulation,
    seed_simulation,
    simulation_status,
)

__all__ = [
    "DEFAULT_SIM_DAYS",
    "PERSONAS",
    "SIM_EVENT_ID_PREFIX",
    "SIM_MARKER_KEY",
    "SIM_SOURCE",
    "SIM_TASK_IDENTITY_PREFIX",
    "SIM_TASK_SPECS",
    "CleanReport",
    "SeedReport",
    "SimMessage",
    "SimPersona",
    "SimulatorError",
    "StatusReport",
    "build_story",
    "clean_simulation",
    "seed_simulation",
    "simulation_status",
]
