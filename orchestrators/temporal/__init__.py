"""Temporal implementation of Fork & Compare workflow.

This package provides Temporal-based orchestration for the Fork & Compare
workflow, enabling durable, resumable execution with automatic retries.

## Quick Start

1. Install Temporal CLI:
   brew install temporal

2. Start local Temporal server:
   temporal server start-dev

3. Install dependencies:
   uv sync --extra temporal

4. Start the worker (in one terminal):
   uv run python -m orchestrators.temporal.worker

5. Run a test workflow (in another terminal):
   uv run python -m orchestrators.temporal.client

## Components

- activities.py: Activity implementations (actual work)
- workflows.py: Workflow definitions (orchestration logic)
- worker.py: Worker process that executes workflows/activities
- client.py: Client for starting and querying workflows
"""

from .activities import (
    create_checkpoint_activity,
    execute_branch_activity,
    greet_activity,
    load_conversation_activity,
)
from .client import get_client, run_greeting_workflow
from .worker import TASK_QUEUE
from .workflows import GreetingWorkflow

__all__ = [
    # Activities
    "greet_activity",
    "load_conversation_activity",
    "create_checkpoint_activity",
    "execute_branch_activity",
    # Workflows
    "GreetingWorkflow",
    # Client
    "get_client",
    "run_greeting_workflow",
    # Constants
    "TASK_QUEUE",
]
