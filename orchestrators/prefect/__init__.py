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

from .flows import ForkCompareFlow, GreetingFlow, run_fork_compare_flow, run_greeting_flow
from .tasks import (
    NON_RETRYABLE_ERRORS,
    RetryConfig,
    TaskTimeouts,
    compare_results_task,
    create_checkpoint_task,
    execute_branch_task,
    greet_task,
    load_conversation_task,
    should_retry,
)

__all__ = [
    # Retry Configuration
    "RetryConfig",
    "TaskTimeouts",
    "NON_RETRYABLE_ERRORS",
    "should_retry",
    # Tasks
    "greet_task",
    "load_conversation_task",
    "create_checkpoint_task",
    "execute_branch_task",
    "compare_results_task",
    # Flows
    "GreetingFlow",
    "ForkCompareFlow",
    "run_greeting_flow",
    "run_fork_compare_flow",
]
