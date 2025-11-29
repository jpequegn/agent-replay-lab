"""Prefect implementation of Fork & Compare workflow.

This package provides Prefect-based orchestration for the Fork & Compare
workflow, enabling parallel execution with built-in observability.

## Quick Start

1. Install dependencies:
   uv add prefect

2. Run ephemeral mode (no server needed):
   uv run python -m orchestrators.prefect.flows

3. (Optional) Start Prefect server for UI:
   uv run prefect server start
   # Access UI at http://localhost:4200

## Components

- tasks.py: Task implementations (atomic work units)
- flows.py: Flow definitions (orchestration logic)
"""

from .flows import GreetingFlow, run_greeting_flow
from .tasks import greet_task

__all__ = [
    # Tasks
    "greet_task",
    # Flows
    "GreetingFlow",
    "run_greeting_flow",
]
