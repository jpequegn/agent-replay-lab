"""Prefect tasks for Fork & Compare workflow.

Tasks are atomic units of work in Prefect. They can be retried,
cached, and run concurrently.

This module provides:
- Core tasks wrapping library functions
- Retry configuration appropriate for each task type
- Timeout configurations for reliable execution
- Error handling with proper logging

Prefect 3.x uses the @task decorator. Tasks:
- Are automatically retried on failure
- Can be cached based on inputs
- Run concurrently when called from flows
- Have built-in observability
"""

import logging
from dataclasses import dataclass

from prefect import task
from prefect.logging import get_run_logger


def _get_logger() -> logging.Logger:
    """Get logger for task execution.

    Returns Prefect run logger if in flow/task context,
    otherwise returns standard Python logger.
    """
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger("orchestrators.prefect.tasks")


# =============================================================================
# Retry Configuration
# =============================================================================


@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for different task types."""

    # For Claude API calls: exponential backoff with longer intervals
    # Claude API can have transient errors, rate limits
    CLAUDE_API_RETRIES = 5
    CLAUDE_API_RETRY_DELAY = 1  # Initial delay in seconds
    CLAUDE_API_RETRY_JITTER = 1.0  # Random jitter factor
    CLAUDE_API_EXPONENTIAL_BACKOFF = 2  # Backoff coefficient

    # For local operations: quick retries for transient issues
    LOCAL_RETRIES = 3
    LOCAL_RETRY_DELAY = 0.1  # 100ms
    LOCAL_RETRY_JITTER = 0.5

    # For comparison/analysis: minimal retries (pure computation)
    COMPUTE_RETRIES = 2
    COMPUTE_RETRY_DELAY = 0.1


@dataclass(frozen=True)
class TaskTimeouts:
    """Timeout configurations for different task types."""

    # Local operations (file I/O, memory access)
    LOCAL_TIMEOUT = 30  # seconds

    # Claude API operations (can take several minutes per turn)
    CLAUDE_API_TIMEOUT = 300  # 5 minutes

    # Pure computation (comparison, analysis)
    COMPUTE_TIMEOUT = 30  # seconds


# =============================================================================
# Non-Retryable Errors
# =============================================================================

# Errors that should not trigger retries (permanent failures)
NON_RETRYABLE_ERRORS = (
    ValueError,  # Bad input won't fix itself
    TypeError,  # Type errors are programming bugs
    KeyError,  # Missing keys indicate data issues
)


def should_retry(exc: Exception, retries: int) -> bool:
    """Determine if an exception should trigger a retry.

    Args:
        exc: The exception that was raised
        retries: Number of retries remaining

    Returns:
        True if should retry, False otherwise
    """
    if isinstance(exc, NON_RETRYABLE_ERRORS):
        return False
    return retries > 0


# =============================================================================
# Test Task
# =============================================================================


@task(
    name="greet",
    description="Simple greeting task for testing Prefect setup",
    retries=RetryConfig.LOCAL_RETRIES,
    retry_delay_seconds=RetryConfig.LOCAL_RETRY_DELAY,
    timeout_seconds=TaskTimeouts.LOCAL_TIMEOUT,
)
def greet_task(name: str) -> str:
    """Return a greeting message.

    This is a simple test task to verify the Prefect installation.

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    logger = _get_logger()
    logger.debug(f"Greeting: {name}")
    return f"Hello, {name}!"


# =============================================================================
# Core Tasks
# =============================================================================


@task(
    name="load_conversation",
    description="Load a conversation from episodic memory",
    retries=RetryConfig.LOCAL_RETRIES,
    retry_delay_seconds=RetryConfig.LOCAL_RETRY_DELAY,
    retry_jitter_factor=RetryConfig.LOCAL_RETRY_JITTER,
    timeout_seconds=TaskTimeouts.LOCAL_TIMEOUT,
)
def load_conversation_task(conversation_id: str) -> dict:
    """Load a conversation by ID.

    Args:
        conversation_id: The conversation ID to load

    Returns:
        Conversation data as a dict

    Raises:
        ValueError: If conversation not found (non-retryable)
    """
    logger = _get_logger()
    logger.info(f"Loading conversation: {conversation_id}")

    from core.conversation import load_conversation

    conversation = load_conversation(conversation_id)
    if conversation is None:
        logger.error(f"Conversation not found: {conversation_id}")
        raise ValueError(f"Conversation not found: {conversation_id}")

    logger.info(f"Loaded conversation with {conversation.step_count} steps")
    return conversation.model_dump()


@task(
    name="create_checkpoint",
    description="Create a checkpoint at a specific step",
    retries=RetryConfig.LOCAL_RETRIES,
    retry_delay_seconds=RetryConfig.LOCAL_RETRY_DELAY,
    retry_jitter_factor=RetryConfig.LOCAL_RETRY_JITTER,
    timeout_seconds=TaskTimeouts.LOCAL_TIMEOUT,
)
def create_checkpoint_task(conversation_data: dict, step: int) -> dict:
    """Create a checkpoint from conversation at step.

    Args:
        conversation_data: Conversation data dict
        step: Step number to checkpoint at

    Returns:
        Checkpoint data as a dict

    Raises:
        ValueError: If step is out of range (non-retryable)
    """
    logger = _get_logger()
    logger.info(f"Creating checkpoint at step {step}")

    from core.checkpoint import create_checkpoint
    from core.models import Conversation

    conversation = Conversation.model_validate(conversation_data)

    # Validate step range
    if step < 1 or step > conversation.step_count:
        logger.error(f"Step {step} out of range (1-{conversation.step_count})")
        raise ValueError(f"Step {step} out of range (1-{conversation.step_count})")

    checkpoint = create_checkpoint(conversation, step)
    logger.info(f"Created checkpoint with {len(checkpoint.messages)} messages")
    return checkpoint.model_dump()


@task(
    name="execute_branch",
    description="Execute a conversation branch with Claude SDK",
    retries=RetryConfig.CLAUDE_API_RETRIES,
    retry_delay_seconds=RetryConfig.CLAUDE_API_RETRY_DELAY,
    retry_jitter_factor=RetryConfig.CLAUDE_API_RETRY_JITTER,
    retry_condition_fn=should_retry,
    timeout_seconds=TaskTimeouts.CLAUDE_API_TIMEOUT,
)
async def execute_branch_task(
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    This task calls the Claude API and may take several minutes.
    It uses exponential backoff for retries on transient failures.

    Args:
        conversation_data: Conversation data dict
        branch_config: Branch configuration dict
        checkpoint_data: Checkpoint data dict

    Returns:
        Branch result as a dict with:
        - branch_name: Name of the branch
        - status: "success" or "error"
        - messages: List of conversation messages
        - duration_ms: Execution time
        - token_usage: Token usage statistics
        - error: Error message (if status is "error")
    """
    logger = _get_logger()

    from core.executor import execute_branch
    from core.models import Checkpoint, Conversation, ForkConfig

    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    logger.info(f"Executing branch '{config.name}' with model {config.model}")

    try:
        result = await execute_branch(conversation, config, checkpoint)
        logger.info(
            f"Branch '{config.name}' completed in {result.duration_ms}ms "
            f"with {len(result.messages)} messages"
        )
        return result.model_dump()
    except Exception as e:
        logger.error(f"Branch '{config.name}' failed: {e}")
        raise


@task(
    name="compare_results",
    description="Compare results from multiple branches",
    retries=RetryConfig.COMPUTE_RETRIES,
    retry_delay_seconds=RetryConfig.COMPUTE_RETRY_DELAY,
    timeout_seconds=TaskTimeouts.COMPUTE_TIMEOUT,
)
def compare_results_task(branch_results: list[dict]) -> dict:
    """Compare results from multiple branch executions.

    Args:
        branch_results: List of branch result dicts

    Returns:
        Comparison summary as a dict with:
        - successful: Count of successful branches
        - failed: Count of failed branches
        - branches: Detailed results per branch
    """
    logger = _get_logger()
    logger.info(f"Comparing {len(branch_results)} branch results")

    from core.comparator import compare_branches
    from core.models import BranchResult

    results = [BranchResult.model_validate(r) for r in branch_results]
    comparison = compare_branches(results)

    successful = sum(1 for r in results if r.status == "success")
    failed = len(results) - successful
    logger.info(f"Comparison complete: {successful} successful, {failed} failed")

    return comparison.model_dump()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Configuration
    "RetryConfig",
    "TaskTimeouts",
    "NON_RETRYABLE_ERRORS",
    "should_retry",
    # Tasks
    "greet_task",
    "load_conversation_task",
    "create_checkpoint_task",
    "execute_branch_task",
    "compare_results_task",
]
