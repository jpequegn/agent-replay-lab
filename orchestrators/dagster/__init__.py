"""Dagster implementation of Fork & Compare workflow.

This package provides Dagster-based orchestration for the Fork & Compare
workflow, enabling parallel execution with built-in observability.

## Quick Start

1. Install dependencies:
   uv add dagster dagster-webserver

2. Start Dagster dev server:
   uv run dagster dev -m orchestrators.dagster.definitions

3. Access UI at http://localhost:3000

## Components

- definitions.py: Dagster definitions (assets, jobs, resources)
- ops.py: Op definitions (atomic computation units)
- graph.py: Graph and job definitions for Fork & Compare
- jobs.py: Test job definitions
- client.py: Client functions for programmatic execution
"""

from orchestrators.dagster.client import (
    JobRunInfo,
    JobRunStatus,
    check_dagster_health,
    generate_job_run_id,
    run_fork_compare_job,
    run_greeting_job,
)
from orchestrators.dagster.definitions import checkpoint_job, defs, greet_op_job
from orchestrators.dagster.graph import (
    ForkCompareConfig,
    fork_compare_graph,
    fork_compare_job,
    fork_compare_parallel_job,
    fork_compare_simple_graph,
)
from orchestrators.dagster.jobs import greeting_graph_job, greeting_job
from orchestrators.dagster.ops import (
    CLAUDE_API_RETRY_POLICY,
    COMPUTE_RETRY_POLICY,
    LOCAL_RETRY_POLICY,
    RetryConfig,
    compare_results_op,
    create_checkpoint_op,
    execute_branch_op,
    greet_op,
    load_conversation_op,
)

__all__ = [
    # Definitions
    "defs",
    # Client Functions
    "run_fork_compare_job",
    "run_greeting_job",
    "generate_job_run_id",
    "check_dagster_health",
    "JobRunStatus",
    "JobRunInfo",
    # Retry Configuration
    "RetryConfig",
    "LOCAL_RETRY_POLICY",
    "CLAUDE_API_RETRY_POLICY",
    "COMPUTE_RETRY_POLICY",
    # Ops
    "greet_op",
    "load_conversation_op",
    "create_checkpoint_op",
    "execute_branch_op",
    "compare_results_op",
    # Graphs
    "fork_compare_graph",
    "fork_compare_simple_graph",
    # Jobs
    "greeting_job",
    "greeting_graph_job",
    "greet_op_job",
    "checkpoint_job",
    "fork_compare_job",
    "fork_compare_parallel_job",
    # Config
    "ForkCompareConfig",
]
