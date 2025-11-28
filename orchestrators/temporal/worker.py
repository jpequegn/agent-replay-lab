"""Temporal worker for Fork & Compare workflows.

The worker connects to the Temporal server and executes workflows and activities.
Run this before executing any workflows.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run the worker:
    uv run python -m orchestrators.temporal.worker
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    create_checkpoint_activity,
    execute_branch_activity,
    greet_activity,
    load_conversation_activity,
)
from .workflows import GreetingWorkflow

# Task queue name - all workflows and activities use this
TASK_QUEUE = "fork-compare-queue"


async def main():
    """Start the Temporal worker."""
    # Connect to local Temporal server
    client = await Client.connect("localhost:7233")

    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[GreetingWorkflow],
        activities=[
            greet_activity,
            load_conversation_activity,
            create_checkpoint_activity,
            execute_branch_activity,
        ],
    )

    print(f"Starting Temporal worker on task queue: {TASK_QUEUE}")
    print("Registered workflows: GreetingWorkflow")
    print("Press Ctrl+C to stop")

    # Run the worker
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
