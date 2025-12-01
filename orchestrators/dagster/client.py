"""Dagster client for executing jobs.

This module provides functions to run Fork & Compare jobs using Dagster.

Dagster can run jobs in two modes:
1. In-process: Direct execution without a server (default)
2. With server: Start `dagster dev` for UI and persistence

Usage:
    # Run a simple test job:
    uv run python -m orchestrators.dagster.client

    # Or import and use programmatically:
    from orchestrators.dagster.client import run_fork_compare_job
    result = await run_fork_compare_job(request_dict)

    # With Dagster UI:
    uv run dagster dev -m orchestrators.dagster.definitions
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from dagster import DagsterRunStatus

from .graph import fork_compare_job

# =============================================================================
# Status Types
# =============================================================================


class JobRunStatus(str, Enum):
    """Job run execution status."""

    QUEUED = "queued"
    NOT_STARTED = "not_started"
    STARTING = "starting"
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELING = "canceling"
    CANCELED = "canceled"


@dataclass
class JobRunInfo:
    """Information about a job run execution."""

    run_id: str
    job_name: str
    status: JobRunStatus
    result: Any | None = None
    error: str | None = None


# =============================================================================
# Status Mapping
# =============================================================================


def _map_dagster_status(status: DagsterRunStatus) -> JobRunStatus:
    """Map Dagster run status to our JobRunStatus enum.

    Args:
        status: Dagster run status

    Returns:
        Mapped JobRunStatus
    """
    mapping = {
        DagsterRunStatus.QUEUED: JobRunStatus.QUEUED,
        DagsterRunStatus.NOT_STARTED: JobRunStatus.NOT_STARTED,
        DagsterRunStatus.STARTING: JobRunStatus.STARTING,
        DagsterRunStatus.STARTED: JobRunStatus.STARTED,
        DagsterRunStatus.SUCCESS: JobRunStatus.SUCCESS,
        DagsterRunStatus.FAILURE: JobRunStatus.FAILURE,
        DagsterRunStatus.CANCELING: JobRunStatus.CANCELING,
        DagsterRunStatus.CANCELED: JobRunStatus.CANCELED,
    }
    return mapping.get(status, JobRunStatus.FAILURE)


# =============================================================================
# Client Functions
# =============================================================================


async def run_fork_compare_job(
    request_dict: dict,
    run_id: str | None = None,
) -> dict:
    """Run the Fork & Compare job.

    This runs the job in-process without requiring a Dagster server.
    The job executes locally and returns the result directly.

    Args:
        request_dict: Serialized ReplayRequest with:
            - conversation_id: ID of conversation to load
            - fork_at_step: Step number to create checkpoint at
            - branches: List of ForkConfig dicts
        run_id: Optional custom run ID (for tracking)

    Returns:
        Serialized ComparisonResult dict

    Raises:
        RuntimeError: If job execution fails
    """
    # Generate run ID if not provided
    if run_id is None:
        conversation_id = request_dict.get("conversation_id", "unknown")
        run_id = f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"

    # Build run config for Dagster job
    run_config = {
        "ops": {
            "fork_compare_all_in_one": {
                "config": {
                    "conversation_id": request_dict["conversation_id"],
                    "fork_at_step": request_dict["fork_at_step"],
                    "branches_json": json.dumps(
                        [
                            b if isinstance(b, dict) else b.model_dump()
                            for b in request_dict.get("branches", [])
                        ]
                    ),
                }
            }
        }
    }

    # Execute job in-process
    # Run in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _execute_job_sync(run_config, run_id),
    )

    return result


def _execute_job_sync(run_config: dict, run_id: str) -> dict:
    """Execute job synchronously (for use in executor).

    Args:
        run_config: Dagster run configuration
        run_id: Run ID for tracking

    Returns:
        Job result as dict

    Raises:
        RuntimeError: If job fails
    """
    # Execute job in-process
    result = fork_compare_job.execute_in_process(
        run_config=run_config,
        raise_on_error=False,
    )

    if not result.success:
        # Collect error messages
        errors = []
        for event in result.all_events:
            if event.is_failure:
                errors.append(str(event.event_specific_data))

        error_msg = "; ".join(errors) if errors else "Job execution failed"
        raise RuntimeError(error_msg)

    # Get output from the job
    output = result.output_for_node("fork_compare_all_in_one")
    return output


def generate_job_run_id(conversation_id: str) -> str:
    """Generate a unique job run ID.

    Args:
        conversation_id: Conversation ID to include in the ID

    Returns:
        Unique job run ID string
    """
    return f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"


# =============================================================================
# Greeting Job (for testing)
# =============================================================================


async def run_greeting_job(name: str) -> str:
    """Run the greeting job for testing.

    Args:
        name: Name to greet

    Returns:
        Greeting message
    """
    from .jobs import greeting_job

    run_config = {
        "ops": {
            "greet": {
                "inputs": {"name": name},
            }
        }
    }

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: greeting_job.execute_in_process(run_config=run_config),
    )

    if not result.success:
        raise RuntimeError("Greeting job failed")

    return result.output_for_node("log_greeting")


# =============================================================================
# Health Check
# =============================================================================


async def check_dagster_health() -> dict:
    """Check Dagster health by running a simple test job.

    Returns:
        Dict with health status:
            - healthy: bool
            - mode: "in-process" or "server"
            - message: Status message
    """
    try:
        result = await run_greeting_job("health-check")
        return {
            "healthy": True,
            "mode": "in-process",
            "message": f"Dagster is healthy. Test result: {result}",
        }
    except Exception as e:
        return {
            "healthy": False,
            "mode": "unknown",
            "message": f"Dagster health check failed: {e}",
        }


# =============================================================================
# CLI Main
# =============================================================================


async def main():
    """Test the Dagster setup with a simple job."""
    print("Testing Dagster setup...")
    print()

    try:
        # Test greeting job
        result = await run_greeting_job("Dagster")
        print("Greeting job executed successfully!")
        print(f"   Result: {result}")
        print()

        # Health check
        health = await check_dagster_health()
        print(f"Health check: {health['message']}")
        print(f"   Mode: {health['mode']}")
        print()

        print("Dagster setup is working correctly.")
        print("Note: Running in-process mode (no server required).")

    except Exception as e:
        print(f"Job failed: {e}")
        print()
        print("Make sure Dagster is installed: uv add dagster dagster-webserver")
        raise


if __name__ == "__main__":
    asyncio.run(main())
