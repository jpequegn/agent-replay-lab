"""Prefect client for executing flows.

This module provides functions to run Fork & Compare flows using Prefect.

Prefect 3.x supports ephemeral execution (no server required) by default.
For persistence and UI, start the Prefect server: prefect server start

Usage:
    # Run a simple test flow:
    uv run python -m orchestrators.prefect.client

    # Or import and use programmatically:
    from orchestrators.prefect.client import run_fork_compare_flow
    result = await run_fork_compare_flow(request_dict)
"""

import asyncio
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .flows import ForkCompareFlow, GreetingFlow, run_greeting_flow

# =============================================================================
# Status Types
# =============================================================================


class FlowRunStatus(str, Enum):
    """Flow run execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"
    PAUSED = "paused"
    SCHEDULED = "scheduled"


@dataclass
class FlowRunInfo:
    """Information about a flow run execution."""

    flow_run_id: str
    flow_name: str
    status: FlowRunStatus
    result: Any | None = None
    error: str | None = None


# =============================================================================
# Client Functions
# =============================================================================


async def run_fork_compare_flow(
    request_dict: dict,
    flow_run_id: str | None = None,
) -> dict:
    """Run the Fork & Compare flow.

    This runs the flow in ephemeral mode (no Prefect server required).
    The flow executes locally and returns the result directly.

    Args:
        request_dict: Serialized ReplayRequest with:
            - conversation_id: ID of conversation to load
            - fork_at_step: Step number to create checkpoint at
            - branches: List of ForkConfig dicts
        flow_run_id: Optional custom flow run ID (for tracking)

    Returns:
        Serialized ComparisonResult dict
    """
    # Generate flow run ID if not provided
    if flow_run_id is None:
        conversation_id = request_dict.get("conversation_id", "unknown")
        flow_run_id = f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"

    # Execute flow directly (ephemeral mode)
    result = await ForkCompareFlow(request_dict)

    return result


async def run_greeting_flow_async(name: str) -> str:
    """Run the greeting flow asynchronously.

    Args:
        name: Name to greet

    Returns:
        Greeting message
    """
    return GreetingFlow(name)


def generate_flow_run_id(conversation_id: str) -> str:
    """Generate a unique flow run ID.

    Args:
        conversation_id: Conversation ID to include in the ID

    Returns:
        Unique flow run ID string
    """
    return f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"


# =============================================================================
# Status Functions (for future Prefect server integration)
# =============================================================================


async def get_flow_run_status(flow_run_id: str) -> FlowRunInfo:
    """Get the status of a flow run.

    Note: In ephemeral mode, flows run synchronously so status tracking
    is limited. This function is provided for future Prefect server integration.

    Args:
        flow_run_id: The flow run ID to check

    Returns:
        FlowRunInfo with status
    """
    # In ephemeral mode, we don't have access to flow run history
    # This is a placeholder for future Prefect server integration
    return FlowRunInfo(
        flow_run_id=flow_run_id,
        flow_name="fork-compare-flow",
        status=FlowRunStatus.COMPLETED,
        error="Status tracking requires Prefect server",
    )


# =============================================================================
# Health Check
# =============================================================================


async def check_prefect_health() -> dict:
    """Check Prefect health by running a simple test flow.

    Returns:
        Dict with health status:
            - healthy: bool
            - mode: "ephemeral" or "server"
            - message: Status message
    """
    try:
        result = run_greeting_flow("health-check")
        return {
            "healthy": True,
            "mode": "ephemeral",
            "message": f"Prefect is healthy. Test result: {result}",
        }
    except Exception as e:
        return {
            "healthy": False,
            "mode": "unknown",
            "message": f"Prefect health check failed: {e}",
        }


# =============================================================================
# CLI Main
# =============================================================================


async def main():
    """Test the Prefect setup with a simple flow."""
    print("Testing Prefect setup...")
    print()

    try:
        # Test greeting flow
        result = run_greeting_flow("Prefect")
        print(" Greeting flow executed successfully!")
        print(f"   Result: {result}")
        print()

        # Health check
        health = await check_prefect_health()
        print(f" Health check: {health['message']}")
        print(f"   Mode: {health['mode']}")
        print()

        print("Prefect setup is working correctly.")
        print("Note: Running in ephemeral mode (no server required).")

    except Exception as e:
        print(f"L Flow failed: {e}")
        print()
        print("Make sure Prefect is installed: uv add prefect")
        raise


if __name__ == "__main__":
    asyncio.run(main())
