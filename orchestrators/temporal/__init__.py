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
    # Retry policies
    CLAUDE_API_RETRY_POLICY,
    COMPUTE_RETRY_POLICY,
    LOCAL_RETRY_POLICY,
    # Timeout configurations
    ActivityTimeouts,
    # Activities
    compare_results_activity,
    create_checkpoint_activity,
    execute_branch_activity,
    # Activity option helpers
    get_claude_activity_options,
    get_compute_activity_options,
    get_local_activity_options,
    greet_activity,
    load_conversation_activity,
)
from .client import (
    # Configuration
    DEFAULT_NAMESPACE,
    DEFAULT_TEMPORAL_ADDRESS,
    FORK_COMPARE_EXECUTION_TIMEOUT,
    GREETING_EXECUTION_TIMEOUT,
    # Status types
    WorkflowInfo,
    WorkflowStatus,
    # Client functions
    cancel_workflow,
    get_client,
    get_workflow_result,
    get_workflow_status,
    list_workflows,
    run_fork_compare_workflow,
    run_greeting_workflow,
    start_fork_compare_workflow,
)
from .worker import (
    ACTIVITIES,
    TASK_QUEUE,
    WORKFLOWS,
    WorkerShutdownError,
    create_worker,
    run_worker,
)
from .workflows import ForkCompareWorkflow, GreetingWorkflow

__all__ = [
    # Retry Policies
    "CLAUDE_API_RETRY_POLICY",
    "LOCAL_RETRY_POLICY",
    "COMPUTE_RETRY_POLICY",
    # Timeout Configurations
    "ActivityTimeouts",
    # Activity Option Helpers
    "get_local_activity_options",
    "get_claude_activity_options",
    "get_compute_activity_options",
    # Activities
    "greet_activity",
    "load_conversation_activity",
    "create_checkpoint_activity",
    "execute_branch_activity",
    "compare_results_activity",
    # Workflows
    "GreetingWorkflow",
    "ForkCompareWorkflow",
    # Client Configuration
    "DEFAULT_TEMPORAL_ADDRESS",
    "DEFAULT_NAMESPACE",
    "FORK_COMPARE_EXECUTION_TIMEOUT",
    "GREETING_EXECUTION_TIMEOUT",
    # Client Status Types
    "WorkflowStatus",
    "WorkflowInfo",
    # Client Functions
    "get_client",
    "run_greeting_workflow",
    "run_fork_compare_workflow",
    "start_fork_compare_workflow",
    "get_workflow_status",
    "get_workflow_result",
    "cancel_workflow",
    "list_workflows",
    # Worker
    "TASK_QUEUE",
    "WORKFLOWS",
    "ACTIVITIES",
    "WorkerShutdownError",
    "create_worker",
    "run_worker",
]
