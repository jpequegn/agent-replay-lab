"""Temporal workflows for Fork & Compare.

Workflows are the orchestration layer - they coordinate activities,
handle failures, and maintain durable state.
"""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from .activities import greet_activity


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


# The ForkCompareWorkflow will be implemented in issue #8
# For now, we just verify the basic setup works
