"""Temporal client for executing workflows.

This module provides functions to start and query Fork & Compare workflows.

Usage:
    # Run a simple test workflow:
    uv run python -m orchestrators.temporal.client

    # Or import and use programmatically:
    from orchestrators.temporal.client import run_greeting_workflow
    result = await run_greeting_workflow("World")
"""

import asyncio
import uuid

from temporalio.client import Client

from .worker import TASK_QUEUE
from .workflows import GreetingWorkflow


async def get_client() -> Client:
    """Get a connected Temporal client."""
    return await Client.connect("localhost:7233")


async def run_greeting_workflow(name: str) -> str:
    """Run the greeting workflow.

    Args:
        name: Name to greet

    Returns:
        Greeting message
    """
    client = await get_client()

    # Start the workflow
    workflow_id = f"greeting-{uuid.uuid4()}"
    result = await client.execute_workflow(
        GreetingWorkflow.run,
        name,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return result


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
