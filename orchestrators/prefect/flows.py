"""Prefect flows for Fork & Compare workflow.

Flows are the main orchestration unit in Prefect. They:
- Coordinate multiple tasks
- Handle errors and retries
- Provide observability and logging
- Can run tasks concurrently

Prefect 3.x uses the @flow decorator. Flows can be run:
- Locally (ephemeral mode)
- With Prefect server for persistence and UI
- On Prefect Cloud for production
"""

import asyncio

from prefect import flow, get_run_logger

from .tasks import (
    compare_results_task,
    create_checkpoint_task,
    execute_branch_task,
    greet_task,
    load_conversation_task,
)


@flow(
    name="greeting-flow",
    description="Simple greeting flow for testing Prefect setup",
    retries=1,
)
def GreetingFlow(name: str = "Prefect") -> str:  # noqa: N802
    """Run a simple greeting flow.

    This flow tests basic Prefect functionality:
    - Task execution
    - Logging
    - Return values

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    logger = get_run_logger()
    logger.info(f"Starting greeting flow for: {name}")

    result = greet_task(name)

    logger.info(f"Greeting complete: {result}")
    return result


def run_greeting_flow(name: str = "Prefect") -> str:
    """Run the greeting flow and return the result.

    This is a convenience function for running the flow from Python code.

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    return GreetingFlow(name)


@flow(
    name="fork-compare-flow",
    description="Fork a conversation and compare different execution paths",
    retries=0,  # Don't retry the whole flow, let tasks handle retries
)
async def ForkCompareFlow(request_dict: dict) -> dict:  # noqa: N802
    """Execute the Fork & Compare workflow.

    This flow:
    1. Loads a conversation from episodic memory
    2. Creates a checkpoint at the fork point
    3. Executes multiple branches in parallel
    4. Compares the results

    Args:
        request_dict: ReplayRequest as a dict with:
            - conversation_id: ID of conversation to fork
            - fork_at_step: Step number to fork at
            - branches: List of branch configurations

    Returns:
        ComparisonResult as a dict
    """
    import time

    from core.models import ReplayRequest

    logger = get_run_logger()
    request = ReplayRequest.model_validate(request_dict)
    start_time = time.time()

    logger.info(
        f"Starting Fork & Compare for conversation {request.conversation_id} "
        f"at step {request.fork_at_step} with {len(request.branches)} branches"
    )

    # Step 1: Load conversation
    logger.info("Step 1: Loading conversation...")
    conversation_data = load_conversation_task(request.conversation_id)

    # Step 2: Create checkpoint
    logger.info(f"Step 2: Creating checkpoint at step {request.fork_at_step}...")
    checkpoint_data = create_checkpoint_task(conversation_data, request.fork_at_step)

    # Step 3: Execute branches in parallel
    logger.info(f"Step 3: Executing {len(request.branches)} branches in parallel...")
    branch_tasks = []
    for branch_config in request.branches:
        logger.info(f"  - Starting branch: {branch_config.name}")
        task = execute_branch_task.submit(
            conversation_data,
            branch_config.model_dump(),
            checkpoint_data,
        )
        branch_tasks.append((branch_config.name, task))

    # Wait for all branches and collect results
    branch_results = []
    for branch_name, task in branch_tasks:
        try:
            result = await asyncio.to_thread(task.result)
            branch_results.append(result)
            logger.info(f"  - Branch {branch_name} completed successfully")
        except Exception as e:
            logger.error(f"  - Branch {branch_name} failed: {e}")
            branch_results.append(
                {
                    "branch_name": branch_name,
                    "status": "error",
                    "error": str(e),
                    "messages": [],
                    "duration_ms": 0,
                    "token_usage": None,
                }
            )

    # Step 4: Compare results
    logger.info("Step 4: Comparing branch results...")
    comparison = compare_results_task(branch_results)

    total_duration_ms = int((time.time() - start_time) * 1000)
    logger.info(f"Fork & Compare completed in {total_duration_ms}ms")

    return {
        "total_duration_ms": total_duration_ms,
        "branches": branch_results,
        "comparison_summary": comparison,
    }


async def run_fork_compare_flow(request: dict) -> dict:
    """Run the Fork & Compare flow.

    Args:
        request: ReplayRequest as a dict

    Returns:
        ComparisonResult as a dict
    """
    return await ForkCompareFlow(request)


if __name__ == "__main__":
    # Test the setup by running the greeting flow
    print("Testing Prefect setup...\n")

    result = run_greeting_flow("Prefect")

    print("\n Flow executed successfully!")
    print(f"   Result: {result}")
    print("\nPrefect setup is working correctly.")
