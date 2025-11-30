"""Dagster implementation of Fork & Compare workflow.

This package provides Dagster-based orchestration for the Fork & Compare
workflow, enabling parallel execution with built-in observability.

## Quick Start

1. Install dependencies:
   uv add dagster dagster-webserver

2. Start Dagster dev server:
   cd orchestrators/dagster && uv run dagster dev

3. Access UI at http://localhost:3000

## Components

- definitions.py: Dagster definitions (assets, jobs, resources)
- assets.py: Asset definitions (data pipeline components)
- jobs.py: Job definitions (orchestration workflows)
- resources.py: Resource definitions (external services)
"""

from orchestrators.dagster.definitions import defs
from orchestrators.dagster.jobs import greeting_job

__all__ = [
    "defs",
    "greeting_job",
]
