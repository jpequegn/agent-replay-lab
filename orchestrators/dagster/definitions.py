"""Dagster definitions for Fork & Compare workflow.

This module serves as the entry point for Dagster. The Definitions object
collects all assets, jobs, schedules, and sensors for the project.

Usage:
    cd orchestrators/dagster && uv run dagster dev

This will start the Dagster UI at http://localhost:3000
"""

from dagster import Definitions

from orchestrators.dagster.jobs import greeting_graph_job, greeting_job

# =============================================================================
# Dagster Definitions
# =============================================================================

defs = Definitions(
    jobs=[
        greeting_job,
        greeting_graph_job,
    ],
    # Future: Add assets, schedules, sensors, resources
    # assets=[...],
    # schedules=[...],
    # sensors=[...],
    # resources={...},
)
