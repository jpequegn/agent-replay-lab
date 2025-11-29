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

import logging
import time
from typing import Any

from prefect import flow
from prefect.futures import wait
from prefect.logging import get_run_logger
from prefect.states import Completed, Failed

from .tasks import (
    compare_results_task,
    create_checkpoint_task,
    execute_branch_task,
    greet_task,
    load_conversation_task,
)


def _get_logger() -> logging.Logger:
    """Get logger for flow execution.

    Returns Prefect run logger if in flow context,
    otherwise returns standard Python logger.
    """
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger("orchestrators.prefect.flows")


# =============================================================================
# Greeting Flow (Test Flow)
# =============================================================================


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
    logger = _get_logger()
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


# =============================================================================
# Fork & Compare Flow
# =============================================================================


def _create_error_result(branch_name: str, error: Exception) -> dict:
    """Create an error result dict for a failed branch.

    Args:
        branch_name: Name of the failed branch
        error: The exception that caused the failure

    Returns:
        BranchResult dict with error status
    """
    return {
        "branch_name": branch_name,
        "status": "error",
        "error": str(error),
        "messages": [],
        "duration_ms": 0,
        "token_usage": None,
    }


def _process_branch_futures(
    branch_futures: list[tuple[str, Any]],
    logger: logging.Logger,
) -> list[dict]:
    """Process branch task futures and collect results.

    Handles partial failures by converting exceptions to error results.

    Args:
        branch_futures: List of (branch_name, future) tuples
        logger: Logger instance

    Returns:
        List of BranchResult dicts
    """
    branch_results = []

    for branch_name, future in branch_futures:
        try:
            # Wait for the future to complete and get the state
            state = future.state

            if isinstance(state, Completed):
                result = future.result()
                branch_results.append(result)
                logger.info(f"  ✓ Branch '{branch_name}' completed successfully")
            elif isinstance(state, Failed):
                error = state.result(raise_on_failure=False)
                logger.error(f"  ✗ Branch '{branch_name}' failed: {error}")
                branch_results.append(_create_error_result(branch_name, error))
            else:
                # Handle other states (Pending, Running, etc.)
                logger.warning(f"  ? Branch '{branch_name}' in unexpected state: {state}")
                branch_results.append(
                    _create_error_result(branch_name, RuntimeError(f"Unexpected state: {state}"))
                )
        except Exception as e:
            logger.error(f"  ✗ Branch '{branch_name}' failed: {e}")
            branch_results.append(_create_error_result(branch_name, e))

    return branch_results


@flow(
    name="fork-compare-flow",
    description="Fork a conversation and compare different execution paths",
    retries=0,  # Don't retry the whole flow, let tasks handle retries
    log_prints=True,
)
async def ForkCompareFlow(request_dict: dict) -> dict:  # noqa: N802
    """Execute the Fork & Compare workflow.

    This flow orchestrates the complete Fork & Compare process:
    1. Load conversation from episodic memory
    2. Create checkpoint at the fork point
    3. Execute multiple branches in parallel using task mapping
    4. Aggregate and compare results

    The workflow is designed to be:
    - Parallel: Uses .submit() for concurrent branch execution
    - Fault-tolerant: Partial failures don't crash the entire workflow
    - Observable: Rich logging and Prefect UI integration

    Args:
        request_dict: ReplayRequest as a dict with:
            - conversation_id: ID of conversation to fork
            - fork_at_step: Step number to fork at
            - branches: List of branch configurations

    Returns:
        ComparisonResult as a dict containing:
            - request: Original request
            - checkpoint: Created checkpoint
            - branches: List of BranchResult dicts
            - total_duration_ms: Total execution time
            - comparison_summary: Analysis of results
    """
    from core.models import ReplayRequest

    logger = _get_logger()
    request = ReplayRequest.model_validate(request_dict)
    start_time = time.time()

    logger.info(
        f"Starting Fork & Compare for conversation {request.conversation_id} "
        f"at step {request.fork_at_step} with {len(request.branches)} branches"
    )

    # =========================================================================
    # Step 1: Load conversation from episodic memory
    # =========================================================================
    logger.info("Step 1: Loading conversation...")
    conversation_data = load_conversation_task(request.conversation_id)
    logger.info(f"  Loaded conversation with {conversation_data.get('step_count', '?')} steps")

    # =========================================================================
    # Step 2: Create checkpoint at specified step
    # =========================================================================
    logger.info(f"Step 2: Creating checkpoint at step {request.fork_at_step}...")
    checkpoint_data = create_checkpoint_task(conversation_data, request.fork_at_step)
    logger.info(f"  Checkpoint created with {len(checkpoint_data.get('messages', []))} messages")

    # =========================================================================
    # Step 3: Execute branches in parallel (fan-out)
    # =========================================================================
    logger.info(f"Step 3: Executing {len(request.branches)} branches in parallel...")

    # Submit all branch tasks for parallel execution
    branch_futures = []
    for branch_config in request.branches:
        logger.info(f"  → Submitting branch: {branch_config.name} (model: {branch_config.model})")
        future = execute_branch_task.submit(
            conversation_data,
            branch_config.model_dump(),
            checkpoint_data,
        )
        branch_futures.append((branch_config.name, future))

    # Wait for all futures to complete
    futures_only = [f for _, f in branch_futures]
    wait(futures_only)

    # Process results with partial failure handling
    logger.info("  Processing branch results...")
    branch_results = _process_branch_futures(branch_futures, logger)

    # Count successes and failures
    successful = sum(1 for r in branch_results if r.get("status") != "error")
    failed = len(branch_results) - successful
    logger.info(f"  Branch execution complete: {successful} successful, {failed} failed")

    # =========================================================================
    # Step 4: Compare and analyze results
    # =========================================================================
    logger.info("Step 4: Comparing branch results...")
    comparison_summary = compare_results_task(branch_results)

    # =========================================================================
    # Step 5: Build final result
    # =========================================================================
    total_duration_ms = int((time.time() - start_time) * 1000)

    logger.info(
        f"Fork & Compare completed in {total_duration_ms}ms "
        f"({successful}/{len(branch_results)} branches successful)"
    )

    return {
        "request": request_dict,
        "checkpoint": checkpoint_data,
        "branches": branch_results,
        "total_duration_ms": total_duration_ms,
        "comparison_summary": comparison_summary,
    }


async def run_fork_compare_flow(request: dict) -> dict:
    """Run the Fork & Compare flow.

    Args:
        request: ReplayRequest as a dict

    Returns:
        ComparisonResult as a dict
    """
    return await ForkCompareFlow(request)


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    # Test the setup by running the greeting flow
    print("Testing Prefect setup...\n")

    result = run_greeting_flow("Prefect")

    print("\n✓ Flow executed successfully!")
    print(f"   Result: {result}")
    print("\nPrefect setup is working correctly.")
