"""Temporal worker for Fork & Compare workflows.

The worker connects to the Temporal server and executes workflows and activities.
Run this before executing any workflows.

Usage:
    # Start Temporal server first:
    temporal server start-dev

    # Then run the worker:
    uv run python -m orchestrators.temporal.worker

Features:
    - Registers all Fork & Compare workflows and activities
    - Graceful shutdown on SIGINT/SIGTERM
    - Configurable Temporal server address
"""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    compare_results_activity,
    create_checkpoint_activity,
    execute_branch_activity,
    greet_activity,
    load_conversation_activity,
)
from .workflows import ForkCompareWorkflow, GreetingWorkflow

# Task queue name - all workflows and activities use this
TASK_QUEUE = "fork-compare-queue"

# Default configuration
DEFAULT_TEMPORAL_ADDRESS = "localhost:7233"
DEFAULT_NAMESPACE = "default"

# All workflows to register
WORKFLOWS = [
    GreetingWorkflow,
    ForkCompareWorkflow,
]

# All activities to register
ACTIVITIES = [
    greet_activity,
    load_conversation_activity,
    create_checkpoint_activity,
    execute_branch_activity,
    compare_results_activity,
]


class WorkerShutdownError(Exception):
    """Raised when worker receives shutdown signal."""

    pass


@asynccontextmanager
async def create_worker(
    address: str = DEFAULT_TEMPORAL_ADDRESS,
    namespace: str = DEFAULT_NAMESPACE,
    task_queue: str = TASK_QUEUE,
):
    """Create and manage a Temporal worker with proper lifecycle.

    Args:
        address: Temporal server address
        namespace: Temporal namespace
        task_queue: Task queue name

    Yields:
        Configured Worker instance
    """
    # Connect to Temporal server
    client = await Client.connect(address, namespace=namespace)

    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
    )

    try:
        yield worker
    finally:
        # Worker cleanup happens automatically
        pass


async def run_worker(
    address: str = DEFAULT_TEMPORAL_ADDRESS,
    namespace: str = DEFAULT_NAMESPACE,
    task_queue: str = TASK_QUEUE,
    graceful_shutdown: bool = True,
):
    """Run the Temporal worker with optional graceful shutdown handling.

    Args:
        address: Temporal server address
        namespace: Temporal namespace
        task_queue: Task queue name
        graceful_shutdown: Whether to handle SIGINT/SIGTERM gracefully
    """
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        """Handle shutdown signals."""
        print(f"\nReceived signal {sig}, initiating graceful shutdown...")
        shutdown_event.set()

    # Set up signal handlers for graceful shutdown
    if graceful_shutdown:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async with create_worker(address, namespace, task_queue) as worker:
        print(f"Starting Temporal worker on task queue: {task_queue}")
        print(f"Connected to: {address}")
        print(f"Namespace: {namespace}")
        print()
        print("Registered workflows:")
        for wf in WORKFLOWS:
            print(f"  - {wf.__name__}")
        print()
        print("Registered activities:")
        for act in ACTIVITIES:
            print(f"  - {act.__name__}")
        print()
        print("Worker is ready. Press Ctrl+C to stop.")
        print()

        if graceful_shutdown:
            # Run worker with shutdown handling
            worker_task = asyncio.create_task(worker.run())
            shutdown_task = asyncio.create_task(shutdown_event.wait())

            try:
                # Wait for either worker to complete or shutdown signal
                done, pending = await asyncio.wait(
                    [worker_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # If shutdown was requested, cancel worker
                if shutdown_task in done:
                    print("Shutting down worker...")
                    worker_task.cancel()
                    try:
                        await worker_task
                    except asyncio.CancelledError:
                        pass
                    print("Worker stopped gracefully.")

            except asyncio.CancelledError:
                print("Worker cancelled.")
        else:
            # Run worker without shutdown handling
            await worker.run()


async def main():
    """Start the Temporal worker."""
    await run_worker()


def cli_main():
    """Entry point for CLI usage."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Already handled by signal handler
        pass
    sys.exit(0)


if __name__ == "__main__":
    cli_main()
