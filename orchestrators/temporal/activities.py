"""Temporal activities for Fork & Compare workflow.

Activities are the building blocks of workflows - they perform the actual work
like loading conversations, creating checkpoints, and executing branches.

This module provides:
- Core activities wrapping library functions
- Retry policies appropriate for each activity type
- Timeout configurations for reliable execution
"""

from datetime import timedelta

from temporalio import activity
from temporalio.common import RetryPolicy

from core.checkpoint import create_checkpoint
from core.comparator import compare_branches
from core.conversation import load_conversation
from core.executor import execute_branch
from core.models import BranchResult, Checkpoint, ForkConfig

# =============================================================================
# Retry Policies
# =============================================================================

# For Claude API calls: exponential backoff with longer intervals
# Claude API can have transient errors, rate limits
CLAUDE_API_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=5,
    non_retryable_error_types=["ValueError", "InvalidRequestError"],
)

# For local operations: quick retries for transient issues
LOCAL_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=100),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=3,
)

# For comparison/analysis: minimal retries (pure computation)
COMPUTE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=100),
    maximum_attempts=2,
)


# =============================================================================
# Timeout Configurations
# =============================================================================

class ActivityTimeouts:
    """Timeout configurations for different activity types."""

    # Local operations (file I/O, memory access)
    LOCAL_START_TO_CLOSE = timedelta(seconds=30)
    LOCAL_SCHEDULE_TO_CLOSE = timedelta(minutes=1)

    # Claude API operations (can take several minutes per turn)
    CLAUDE_START_TO_CLOSE = timedelta(minutes=5)
    CLAUDE_SCHEDULE_TO_CLOSE = timedelta(minutes=10)

    # Pure computation (comparison, analysis)
    COMPUTE_START_TO_CLOSE = timedelta(seconds=30)
    COMPUTE_SCHEDULE_TO_CLOSE = timedelta(minutes=1)


# =============================================================================
# Activity Options Helpers
# =============================================================================

def get_local_activity_options() -> dict:
    """Get activity options for local operations.

    Use for: load_conversation, create_checkpoint

    Returns:
        Dict with start_to_close_timeout and retry_policy
    """
    return {
        "start_to_close_timeout": ActivityTimeouts.LOCAL_START_TO_CLOSE,
        "retry_policy": LOCAL_RETRY_POLICY,
    }


def get_claude_activity_options() -> dict:
    """Get activity options for Claude API operations.

    Use for: execute_branch (calls Claude SDK)

    Returns:
        Dict with start_to_close_timeout and retry_policy
    """
    return {
        "start_to_close_timeout": ActivityTimeouts.CLAUDE_START_TO_CLOSE,
        "retry_policy": CLAUDE_API_RETRY_POLICY,
    }


def get_compute_activity_options() -> dict:
    """Get activity options for pure computation.

    Use for: compare_results (no I/O, just data processing)

    Returns:
        Dict with start_to_close_timeout and retry_policy
    """
    return {
        "start_to_close_timeout": ActivityTimeouts.COMPUTE_START_TO_CLOSE,
        "retry_policy": COMPUTE_RETRY_POLICY,
    }


# =============================================================================
# Activities
# =============================================================================

@activity.defn
async def load_conversation_activity(session_id: str) -> dict | None:
    """Load a conversation from episodic memory.

    This is a local operation that reads from the episodic memory store.

    Args:
        session_id: The session ID to load

    Returns:
        Serialized conversation dict or None if not found

    Recommended options: get_local_activity_options()
    """
    activity.logger.info(f"Loading conversation: {session_id}")
    conv = load_conversation(session_id)
    if conv is None:
        activity.logger.warning(f"Conversation not found: {session_id}")
        return None
    activity.logger.info(f"Loaded conversation with {conv.step_count} messages")
    return conv.model_dump()


@activity.defn
async def create_checkpoint_activity(conversation_dict: dict, step: int) -> dict:
    """Create a checkpoint at a specific step.

    This is a local operation that processes conversation data.

    Args:
        conversation_dict: Serialized conversation
        step: Step number to checkpoint at

    Returns:
        Serialized checkpoint dict

    Recommended options: get_local_activity_options()
    """
    from core.models import Conversation

    activity.logger.info(f"Creating checkpoint at step {step}")
    conv = Conversation.model_validate(conversation_dict)
    checkpoint = create_checkpoint(conv, step)
    activity.logger.info(
        f"Created checkpoint: {checkpoint.conversation_id} at step {checkpoint.step}"
    )
    return checkpoint.model_dump()


@activity.defn
async def execute_branch_activity(checkpoint_dict: dict, config_dict: dict) -> dict:
    """Execute a single branch from a checkpoint.

    This activity calls the Claude API and may take several minutes.
    Use appropriate timeout and retry policies for API operations.

    Args:
        checkpoint_dict: Serialized checkpoint
        config_dict: Serialized ForkConfig

    Returns:
        Serialized BranchResult dict

    Recommended options: get_claude_activity_options()
    """
    checkpoint = Checkpoint.model_validate(checkpoint_dict)
    config = ForkConfig.model_validate(config_dict)

    activity.logger.info(
        f"Executing branch '{config.name}' with model {config.model}"
    )

    # Heartbeat to indicate activity is still running during long API calls
    activity.heartbeat(f"Starting branch execution: {config.name}")

    result = execute_branch(checkpoint, config)

    if result.status == "success":
        activity.logger.info(
            f"Branch '{config.name}' completed: "
            f"{len(result.messages)} messages, {result.duration_ms}ms"
        )
    else:
        activity.logger.warning(
            f"Branch '{config.name}' {result.status}: {result.error}"
        )

    return result.model_dump()


@activity.defn
async def compare_results_activity(branch_results: list[dict]) -> dict:
    """Compare results from multiple branch executions.

    This is a pure computation activity that analyzes branch results
    and generates comparison metrics.

    Args:
        branch_results: List of serialized BranchResult dicts

    Returns:
        Comparison summary dict

    Recommended options: get_compute_activity_options()
    """
    activity.logger.info(f"Comparing {len(branch_results)} branch results")

    # Deserialize branch results
    results = [BranchResult.model_validate(r) for r in branch_results]

    # Generate comparison
    summary = compare_branches(results)

    successful = summary.get("successful", 0)
    failed = summary.get("failed", 0)
    activity.logger.info(
        f"Comparison complete: {successful} successful, {failed} failed"
    )

    return summary


# Simple test activity for verifying Temporal setup
@activity.defn
async def greet_activity(name: str) -> str:
    """Simple greeting activity for testing.

    Args:
        name: Name to greet

    Returns:
        Greeting message
    """
    return f"Hello, {name}!"
