"""Dagster ops for Fork & Compare workflow.

Ops are atomic units of computation in Dagster. They can be composed
into graphs and jobs, with configurable retry behavior.

This module provides:
- Core ops wrapping library functions
- Retry policies for different operation types
- Proper Dagster typing for inputs/outputs
- Error handling with proper logging

Dagster uses the @op decorator. Ops:
- Can be retried on failure via RetryPolicy
- Accept configuration via Config objects
- Have strong typing for inputs and outputs
- Integrate with Dagster's logging and observability
"""

import logging
from dataclasses import dataclass

from dagster import (
    Config,
    In,
    OpExecutionContext,
    Out,
    RetryPolicy,
    op,
)

# =============================================================================
# Retry Configuration
# =============================================================================


@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration mirroring Prefect patterns for consistency."""

    # For Claude API calls: exponential backoff with longer intervals
    CLAUDE_API_MAX_RETRIES = 5
    CLAUDE_API_DELAY = 1.0  # Initial delay in seconds

    # For local operations: quick retries for transient issues
    LOCAL_MAX_RETRIES = 3
    LOCAL_DELAY = 0.1  # 100ms

    # For comparison/analysis: minimal retries (pure computation)
    COMPUTE_MAX_RETRIES = 2
    COMPUTE_DELAY = 0.1


# Dagster retry policies for different operation types
LOCAL_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.LOCAL_MAX_RETRIES,
    delay=RetryConfig.LOCAL_DELAY,
)

CLAUDE_API_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.CLAUDE_API_MAX_RETRIES,
    delay=RetryConfig.CLAUDE_API_DELAY,
    backoff=None,  # Dagster backoff is configured differently
)

COMPUTE_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.COMPUTE_MAX_RETRIES,
    delay=RetryConfig.COMPUTE_DELAY,
)


# =============================================================================
# Op Configurations
# =============================================================================


class LoadConversationConfig(Config):
    """Configuration for load_conversation op."""

    conversation_id: str


class CreateCheckpointConfig(Config):
    """Configuration for create_checkpoint op."""

    step: int


class ExecuteBranchConfig(Config):
    """Configuration for execute_branch op."""

    name: str
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 1.0
    system_prompt: str | None = None
    inject_message: str | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _get_logger(context: OpExecutionContext | None = None) -> logging.Logger:
    """Get logger for op execution.

    Args:
        context: Dagster op context (provides Dagster logging)

    Returns:
        Logger instance
    """
    if context is not None:
        return context.log
    return logging.getLogger("orchestrators.dagster.ops")


# =============================================================================
# Test Op
# =============================================================================


@op(
    name="greet",
    description="Simple greeting op for testing Dagster setup",
    retry_policy=LOCAL_RETRY_POLICY,
    out=Out(str, description="Greeting message"),
)
def greet_op(context: OpExecutionContext, name: str) -> str:
    """Return a greeting message.

    Args:
        context: Dagster op context
        name: The name to greet

    Returns:
        A greeting message
    """
    context.log.debug(f"Greeting: {name}")
    return f"Hello, {name}!"


# =============================================================================
# Core Ops
# =============================================================================


@op(
    name="load_conversation",
    description="Load a conversation from episodic memory",
    retry_policy=LOCAL_RETRY_POLICY,
    ins={"conversation_id": In(str, description="Conversation ID to load")},
    out=Out(dict, description="Conversation data dictionary"),
)
def load_conversation_op(context: OpExecutionContext, conversation_id: str) -> dict:
    """Load a conversation by ID.

    Args:
        context: Dagster op context
        conversation_id: The conversation ID to load

    Returns:
        Conversation data as a dict

    Raises:
        ValueError: If conversation not found (non-retryable)
    """
    context.log.info(f"Loading conversation: {conversation_id}")

    from core.conversation import load_conversation

    conversation = load_conversation(conversation_id)
    if conversation is None:
        context.log.error(f"Conversation not found: {conversation_id}")
        raise ValueError(f"Conversation not found: {conversation_id}")

    context.log.info(f"Loaded conversation with {conversation.step_count} steps")
    return conversation.model_dump()


@op(
    name="create_checkpoint",
    description="Create a checkpoint at a specific step",
    retry_policy=LOCAL_RETRY_POLICY,
    ins={
        "conversation_data": In(dict, description="Conversation data dict"),
        "step": In(int, description="Step number to checkpoint at"),
    },
    out=Out(dict, description="Checkpoint data dictionary"),
)
def create_checkpoint_op(
    context: OpExecutionContext,
    conversation_data: dict,
    step: int,
) -> dict:
    """Create a checkpoint from conversation at step.

    Args:
        context: Dagster op context
        conversation_data: Conversation data dict
        step: Step number to checkpoint at

    Returns:
        Checkpoint data as a dict

    Raises:
        ValueError: If step is out of range (non-retryable)
    """
    context.log.info(f"Creating checkpoint at step {step}")

    from core.checkpoint import create_checkpoint
    from core.models import Conversation

    conversation = Conversation.model_validate(conversation_data)

    # Validate step range
    if step < 1 or step > conversation.step_count:
        context.log.error(f"Step {step} out of range (1-{conversation.step_count})")
        raise ValueError(f"Step {step} out of range (1-{conversation.step_count})")

    checkpoint = create_checkpoint(conversation, step)
    context.log.info(f"Created checkpoint with {len(checkpoint.messages)} messages")
    return checkpoint.model_dump()


@op(
    name="execute_branch",
    description="Execute a conversation branch with Claude SDK",
    retry_policy=CLAUDE_API_RETRY_POLICY,
    ins={
        "conversation_data": In(dict, description="Conversation data dict"),
        "branch_config": In(dict, description="Branch configuration dict"),
        "checkpoint_data": In(dict, description="Checkpoint data dict"),
    },
    out=Out(dict, description="Branch result dictionary"),
)
def execute_branch_op(
    context: OpExecutionContext,
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    This op calls the Claude API and may take several minutes.
    It uses retry policy for transient failures.

    Note: This is a synchronous wrapper around the async execute_branch.
    For production use, consider using Dagster's async support.

    Args:
        context: Dagster op context
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
    import asyncio

    from core.executor import execute_branch
    from core.models import Checkpoint, Conversation, ForkConfig

    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    context.log.info(f"Executing branch '{config.name}' with model {config.model}")

    try:
        # Run async function synchronously
        result = asyncio.run(execute_branch(conversation, config, checkpoint))
        context.log.info(
            f"Branch '{config.name}' completed in {result.duration_ms}ms "
            f"with {len(result.messages)} messages"
        )
        return result.model_dump()
    except Exception as e:
        context.log.error(f"Branch '{config.name}' failed: {e}")
        raise


@op(
    name="compare_results",
    description="Compare results from multiple branches",
    retry_policy=COMPUTE_RETRY_POLICY,
    ins={"branch_results": In(list, description="List of branch result dicts")},
    out=Out(dict, description="Comparison summary dictionary"),
)
def compare_results_op(
    context: OpExecutionContext,
    branch_results: list[dict],
) -> dict:
    """Compare results from multiple branch executions.

    Args:
        context: Dagster op context
        branch_results: List of branch result dicts

    Returns:
        Comparison summary as a dict with:
        - successful: Count of successful branches
        - failed: Count of failed branches
        - branches: Detailed results per branch
    """
    context.log.info(f"Comparing {len(branch_results)} branch results")

    from core.comparator import compare_branches
    from core.models import BranchResult

    results = [BranchResult.model_validate(r) for r in branch_results]
    comparison = compare_branches(results)

    successful = sum(1 for r in results if r.status == "success")
    failed = len(results) - successful
    context.log.info(f"Comparison complete: {successful} successful, {failed} failed")

    return comparison.model_dump()


# =============================================================================
# Graph-Composable Versions
# =============================================================================

# These ops are designed to be composed into graphs where
# inputs flow from one op to the next automatically.


@op(
    name="load_conversation_with_config",
    description="Load a conversation using config",
    retry_policy=LOCAL_RETRY_POLICY,
    out=Out(dict, description="Conversation data dictionary"),
)
def load_conversation_with_config_op(
    context: OpExecutionContext,
    config: LoadConversationConfig,
) -> dict:
    """Load a conversation using configuration.

    Args:
        context: Dagster op context
        config: Configuration with conversation_id

    Returns:
        Conversation data as a dict
    """
    return load_conversation_op(context, config.conversation_id)


@op(
    name="create_checkpoint_with_config",
    description="Create a checkpoint using config for step",
    retry_policy=LOCAL_RETRY_POLICY,
    ins={"conversation_data": In(dict, description="Conversation data dict")},
    out=Out(dict, description="Checkpoint data dictionary"),
)
def create_checkpoint_with_config_op(
    context: OpExecutionContext,
    config: CreateCheckpointConfig,
    conversation_data: dict,
) -> dict:
    """Create a checkpoint using configuration.

    Args:
        context: Dagster op context
        config: Configuration with step number
        conversation_data: Conversation data dict

    Returns:
        Checkpoint data as a dict
    """
    return create_checkpoint_op(context, conversation_data, config.step)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Configuration
    "RetryConfig",
    "LOCAL_RETRY_POLICY",
    "CLAUDE_API_RETRY_POLICY",
    "COMPUTE_RETRY_POLICY",
    "LoadConversationConfig",
    "CreateCheckpointConfig",
    "ExecuteBranchConfig",
    # Test op
    "greet_op",
    # Core ops
    "load_conversation_op",
    "create_checkpoint_op",
    "execute_branch_op",
    "compare_results_op",
    # Config-based ops
    "load_conversation_with_config_op",
    "create_checkpoint_with_config_op",
]
