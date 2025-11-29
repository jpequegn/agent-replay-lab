"""Temporal workflows for Fork & Compare.

Workflows are the orchestration layer - they coordinate activities,
handle failures, and maintain durable state.
"""

import asyncio
import time
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from .activities import (
        CLAUDE_API_RETRY_POLICY,
        COMPUTE_RETRY_POLICY,
        LOCAL_RETRY_POLICY,
        ActivityTimeouts,
        compare_results_activity,
        create_checkpoint_activity,
        execute_branch_activity,
        greet_activity,
        load_conversation_activity,
    )


@workflow.defn
class GreetingWorkflow:
    """Simple test workflow to verify Temporal setup.

    This workflow demonstrates the basic structure and can be used
    to test that the Temporal server and worker are running correctly.
    """

    @workflow.run
    async def run(self, name: str) -> str:
        """Execute the greeting workflow.

        Args:
            name: Name to greet

        Returns:
            Greeting message from the activity
        """
        return await workflow.execute_activity(
            greet_activity,
            name,
            start_to_close_timeout=timedelta(seconds=10),
        )


@workflow.defn
class ForkCompareWorkflow:
    """Main workflow for Fork & Compare operations.

    This workflow orchestrates the complete Fork & Compare process:
    1. Load conversation from episodic memory
    2. Create checkpoint at specified step
    3. Execute branches in parallel (fan-out)
    4. Aggregate results
    5. Compare and analyze results

    The workflow is designed to be:
    - Durable: can resume after crashes
    - Parallel: executes branches concurrently
    - Fault-tolerant: partial failures don't crash the entire workflow
    - Deterministic: can replay from history
    """

    @workflow.run
    async def run(self, request_dict: dict) -> dict:
        """Execute the Fork & Compare workflow.

        Args:
            request_dict: Serialized ReplayRequest with:
                - conversation_id: ID of conversation to load
                - fork_at_step: Step number to create checkpoint at
                - branches: List of ForkConfig dicts

        Returns:
            Serialized ComparisonResult dict containing:
                - request: Original request
                - checkpoint: Created checkpoint
                - branches: List of BranchResult
                - total_duration_ms: Total execution time
                - comparison_summary: Analysis of results
        """
        start_time = time.time()

        workflow.logger.info(
            f"Starting ForkCompareWorkflow for conversation: {request_dict['conversation_id']}"
        )

        # Step 1: Load conversation from episodic memory
        workflow.logger.info("Step 1: Loading conversation")
        conversation_dict = await workflow.execute_activity(
            load_conversation_activity,
            request_dict["conversation_id"],
            start_to_close_timeout=ActivityTimeouts.LOCAL_START_TO_CLOSE,
            retry_policy=LOCAL_RETRY_POLICY,
        )

        if conversation_dict is None:
            raise ValueError(
                f"Conversation not found: {request_dict['conversation_id']}"
            )

        # Step 2: Create checkpoint at specified step
        workflow.logger.info(f"Step 2: Creating checkpoint at step {request_dict['fork_at_step']}")
        checkpoint_dict = await workflow.execute_activity(
            create_checkpoint_activity,
            args=[conversation_dict, request_dict["fork_at_step"]],
            start_to_close_timeout=ActivityTimeouts.LOCAL_START_TO_CLOSE,
            retry_policy=LOCAL_RETRY_POLICY,
        )

        # Step 3: Execute branches in parallel (fan-out)
        workflow.logger.info(
            f"Step 3: Executing {len(request_dict['branches'])} branches in parallel"
        )
        branch_results = await self._execute_branches_parallel(
            checkpoint_dict, request_dict["branches"]
        )

        # Step 4: Compare and analyze results
        workflow.logger.info("Step 4: Comparing results")
        comparison_summary = await workflow.execute_activity(
            compare_results_activity,
            branch_results,
            start_to_close_timeout=ActivityTimeouts.COMPUTE_START_TO_CLOSE,
            retry_policy=COMPUTE_RETRY_POLICY,
        )

        # Step 5: Build and return final result
        total_duration_ms = int((time.time() - start_time) * 1000)
        workflow.logger.info(
            f"Workflow complete in {total_duration_ms}ms. "
            f"Successful: {comparison_summary.get('successful', 0)}, "
            f"Failed: {comparison_summary.get('failed', 0)}"
        )

        # Build ComparisonResult
        return {
            "request": request_dict,
            "checkpoint": checkpoint_dict,
            "branches": branch_results,
            "total_duration_ms": total_duration_ms,
            "comparison_summary": comparison_summary,
        }

    async def _execute_branches_parallel(
        self, checkpoint_dict: dict, branches: list[dict]
    ) -> list[dict]:
        """Execute multiple branches in parallel.

        Uses asyncio.gather with return_exceptions=True to ensure
        partial failures don't crash the entire workflow.

        Args:
            checkpoint_dict: Serialized checkpoint to fork from
            branches: List of serialized ForkConfig dicts

        Returns:
            List of serialized BranchResult dicts
        """
        # Create coroutines for each branch
        branch_coros = [
            self._execute_single_branch(checkpoint_dict, branch_config)
            for branch_config in branches
        ]

        # Execute all branches in parallel
        # return_exceptions=True ensures one failure doesn't cancel others
        results = await asyncio.gather(*branch_coros, return_exceptions=True)

        # Process results, converting exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Convert exception to error BranchResult
                branch_name = branches[i].get("name", f"branch-{i}")
                workflow.logger.warning(
                    f"Branch '{branch_name}' failed with exception: {result}"
                )
                error_result = {
                    "branch_name": branch_name,
                    "config": branches[i],
                    "messages": [],
                    "duration_ms": 0,
                    "token_usage": None,
                    "status": "error",
                    "error": str(result),
                }
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_single_branch(
        self, checkpoint_dict: dict, branch_config: dict
    ) -> dict:
        """Execute a single branch with appropriate error handling.

        Args:
            checkpoint_dict: Serialized checkpoint
            branch_config: Serialized ForkConfig

        Returns:
            Serialized BranchResult dict
        """
        branch_name = branch_config.get("name", "unknown")
        workflow.logger.info(f"Starting branch: {branch_name}")

        try:
            result = await workflow.execute_activity(
                execute_branch_activity,
                args=[checkpoint_dict, branch_config],
                start_to_close_timeout=ActivityTimeouts.CLAUDE_START_TO_CLOSE,
                retry_policy=CLAUDE_API_RETRY_POLICY,
                heartbeat_timeout=timedelta(minutes=2),
            )
            return result
        except ActivityError as e:
            # Activity failed after all retries
            workflow.logger.error(f"Branch '{branch_name}' activity failed: {e}")
            raise
