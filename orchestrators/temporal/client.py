"""Temporal client for executing workflows.

This module provides functions to start, query, and manage Fork & Compare workflows.

Usage:
    # Run a simple test workflow:
    uv run python -m orchestrators.temporal.client

    # Or import and use programmatically:
    from orchestrators.temporal.client import run_fork_compare_workflow
    result = await run_fork_compare_workflow(request_dict)

    # Check workflow status:
    status = await get_workflow_status(workflow_id)
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

from temporalio.client import Client, WorkflowHandle
from temporalio.service import RPCError

from .worker import TASK_QUEUE
from .workflows import ForkCompareWorkflow, GreetingWorkflow

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"
DEFAULT_NAMESPACE = "default"

# Workflow execution timeouts
FORK_COMPARE_EXECUTION_TIMEOUT = timedelta(minutes=30)
GREETING_EXECUTION_TIMEOUT = timedelta(minutes=1)


# =============================================================================
# Status Types
# =============================================================================


class WorkflowStatus(str, Enum):
    """Workflow execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    TIMED_OUT = "timed_out"
    UNKNOWN = "unknown"


@dataclass
class WorkflowInfo:
    """Information about a workflow execution."""

    workflow_id: str
    run_id: str | None
    status: WorkflowStatus
    result: Any | None = None
    error: str | None = None


# =============================================================================
# Client Functions
# =============================================================================


async def get_client(
    address: str = DEFAULT_TEMPORAL_ADDRESS,
    namespace: str = DEFAULT_NAMESPACE,
) -> Client:
    """Get a connected Temporal client.

    Args:
        address: Temporal server address (default: localhost:7233)
        namespace: Temporal namespace (default: default)

    Returns:
        Connected Temporal client
    """
    return await Client.connect(address, namespace=namespace)


async def run_greeting_workflow(
    name: str,
    client: Client | None = None,
    workflow_id: str | None = None,
) -> str:
    """Run the greeting workflow.

    Args:
        name: Name to greet
        client: Optional pre-connected client
        workflow_id: Optional custom workflow ID

    Returns:
        Greeting message
    """
    if client is None:
        client = await get_client()

    if workflow_id is None:
        workflow_id = f"greeting-{uuid.uuid4()}"

    result = await client.execute_workflow(
        GreetingWorkflow.run,
        name,
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=GREETING_EXECUTION_TIMEOUT,
    )

    return result


async def run_fork_compare_workflow(
    request_dict: dict,
    client: Client | None = None,
    workflow_id: str | None = None,
    wait_for_result: bool = True,
) -> dict | WorkflowHandle:
    """Run the Fork & Compare workflow.

    Args:
        request_dict: Serialized ReplayRequest with:
            - conversation_id: ID of conversation to load
            - fork_at_step: Step number to create checkpoint at
            - branches: List of ForkConfig dicts
        client: Optional pre-connected client
        workflow_id: Optional custom workflow ID
        wait_for_result: If True, wait for completion. If False, return handle.

    Returns:
        If wait_for_result=True: Serialized ComparisonResult dict
        If wait_for_result=False: WorkflowHandle for async tracking
    """
    if client is None:
        client = await get_client()

    if workflow_id is None:
        conversation_id = request_dict.get("conversation_id", "unknown")
        workflow_id = f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"

    if wait_for_result:
        # Execute and wait for result
        result = await client.execute_workflow(
            ForkCompareWorkflow.run,
            request_dict,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            execution_timeout=FORK_COMPARE_EXECUTION_TIMEOUT,
        )
        return result
    else:
        # Start workflow and return handle for async tracking
        handle = await client.start_workflow(
            ForkCompareWorkflow.run,
            request_dict,
            id=workflow_id,
            task_queue=TASK_QUEUE,
            execution_timeout=FORK_COMPARE_EXECUTION_TIMEOUT,
        )
        return handle


async def start_fork_compare_workflow(
    request_dict: dict,
    client: Client | None = None,
    workflow_id: str | None = None,
) -> WorkflowHandle:
    """Start Fork & Compare workflow without waiting for completion.

    This is useful for long-running workflows where you want to
    track progress or get results later.

    Args:
        request_dict: Serialized ReplayRequest
        client: Optional pre-connected client
        workflow_id: Optional custom workflow ID

    Returns:
        WorkflowHandle for tracking and retrieving results
    """
    return await run_fork_compare_workflow(
        request_dict,
        client=client,
        workflow_id=workflow_id,
        wait_for_result=False,
    )


async def get_workflow_status(
    workflow_id: str,
    client: Client | None = None,
) -> WorkflowInfo:
    """Get the status of a workflow execution.

    Args:
        workflow_id: The workflow ID to check
        client: Optional pre-connected client

    Returns:
        WorkflowInfo with status and optionally result/error
    """
    if client is None:
        client = await get_client()

    try:
        handle = client.get_workflow_handle(workflow_id)
        describe = await handle.describe()

        # Map Temporal status to our enum
        status_map = {
            1: WorkflowStatus.RUNNING,      # RUNNING
            2: WorkflowStatus.COMPLETED,    # COMPLETED
            3: WorkflowStatus.FAILED,       # FAILED
            4: WorkflowStatus.CANCELLED,    # CANCELLED
            5: WorkflowStatus.TERMINATED,   # TERMINATED
            6: WorkflowStatus.TIMED_OUT,    # TIMED_OUT
        }
        status = status_map.get(describe.status, WorkflowStatus.UNKNOWN)

        info = WorkflowInfo(
            workflow_id=workflow_id,
            run_id=describe.run_id,
            status=status,
        )

        # If completed, try to get result
        if status == WorkflowStatus.COMPLETED:
            try:
                result = await handle.result()
                info.result = result
            except Exception as e:
                info.error = f"Failed to get result: {e}"

        # If failed, try to get error
        elif status == WorkflowStatus.FAILED:
            info.error = "Workflow failed (check Temporal UI for details)"

        return info

    except RPCError as e:
        if "not found" in str(e).lower():
            return WorkflowInfo(
                workflow_id=workflow_id,
                run_id=None,
                status=WorkflowStatus.UNKNOWN,
                error=f"Workflow not found: {workflow_id}",
            )
        raise


async def get_workflow_result(
    workflow_id: str,
    client: Client | None = None,
    timeout: timedelta | None = None,
) -> Any:
    """Get the result of a completed workflow.

    Args:
        workflow_id: The workflow ID
        client: Optional pre-connected client
        timeout: Optional timeout for waiting

    Returns:
        Workflow result

    Raises:
        Exception if workflow failed or timed out
    """
    if client is None:
        client = await get_client()

    handle = client.get_workflow_handle(workflow_id)

    if timeout:
        return await asyncio.wait_for(handle.result(), timeout=timeout.total_seconds())
    else:
        return await handle.result()


async def cancel_workflow(
    workflow_id: str,
    client: Client | None = None,
) -> bool:
    """Request cancellation of a running workflow.

    Args:
        workflow_id: The workflow ID to cancel
        client: Optional pre-connected client

    Returns:
        True if cancellation was requested successfully
    """
    if client is None:
        client = await get_client()

    try:
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
        return True
    except RPCError as e:
        if "not found" in str(e).lower():
            return False
        raise


async def list_workflows(
    client: Client | None = None,
    query: str | None = None,
) -> list[WorkflowInfo]:
    """List workflows matching a query.

    Args:
        client: Optional pre-connected client
        query: Optional query string (e.g., 'WorkflowType="ForkCompareWorkflow"')

    Returns:
        List of WorkflowInfo for matching workflows
    """
    if client is None:
        client = await get_client()

    workflows = []
    async for workflow in client.list_workflows(query=query):
        status_map = {
            1: WorkflowStatus.RUNNING,
            2: WorkflowStatus.COMPLETED,
            3: WorkflowStatus.FAILED,
            4: WorkflowStatus.CANCELLED,
            5: WorkflowStatus.TERMINATED,
            6: WorkflowStatus.TIMED_OUT,
        }
        status = status_map.get(workflow.status, WorkflowStatus.UNKNOWN)

        workflows.append(WorkflowInfo(
            workflow_id=workflow.id,
            run_id=workflow.run_id,
            status=status,
        ))

    return workflows


# =============================================================================
# CLI Main
# =============================================================================


async def main():
    """Test the Temporal setup with a simple workflow."""
    print("Testing Temporal setup...")
    print()

    try:
        result = await run_greeting_workflow("Temporal")
        print("✅ Workflow executed successfully!")
        print(f"   Result: {result}")
        print()
        print("Temporal setup is working correctly.")
    except Exception as e:
        print(f"❌ Workflow failed: {e}")
        print()
        print("Make sure:")
        print("  1. Temporal server is running: temporal server start-dev")
        print("  2. Worker is running: uv run python -m orchestrators.temporal.worker")
        raise


if __name__ == "__main__":
    asyncio.run(main())
