"""Prefect tasks for Fork & Compare workflow.

Tasks are atomic units of work in Prefect. They can be retried,
cached, and run concurrently.

Prefect 3.x uses the @task decorator. Tasks:
- Are automatically retried on failure
- Can be cached based on inputs
- Run concurrently when called from flows
- Have built-in observability
"""

from prefect import task


@task(
    name="greet",
    description="Simple greeting task for testing Prefect setup",
    retries=3,
    retry_delay_seconds=1,
)
def greet_task(name: str) -> str:
    """Return a greeting message.

    This is a simple test task to verify the Prefect installation.

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    return f"Hello, {name}!"


@task(
    name="load_conversation",
    description="Load a conversation from episodic memory",
    retries=3,
    retry_delay_seconds=1,
)
def load_conversation_task(conversation_id: str) -> dict:
    """Load a conversation by ID.

    Args:
        conversation_id: The conversation ID to load

    Returns:
        Conversation data as a dict
    """
    from core.conversation import load_conversation

    conversation = load_conversation(conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation not found: {conversation_id}")
    return conversation.model_dump()


@task(
    name="create_checkpoint",
    description="Create a checkpoint at a specific step",
    retries=2,
    retry_delay_seconds=1,
)
def create_checkpoint_task(conversation_data: dict, step: int) -> dict:
    """Create a checkpoint from conversation at step.

    Args:
        conversation_data: Conversation data dict
        step: Step number to checkpoint at

    Returns:
        Checkpoint data as a dict
    """
    from core.checkpoint import create_checkpoint
    from core.models import Conversation

    conversation = Conversation.model_validate(conversation_data)
    checkpoint = create_checkpoint(conversation, step)
    return checkpoint.model_dump()


@task(
    name="execute_branch",
    description="Execute a conversation branch with Claude SDK",
    retries=2,
    retry_delay_seconds=5,
)
async def execute_branch_task(
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    Args:
        conversation_data: Conversation data dict
        branch_config: Branch configuration dict
        checkpoint_data: Checkpoint data dict

    Returns:
        Branch result as a dict
    """
    from core.executor import execute_branch
    from core.models import Checkpoint, Conversation, ForkConfig

    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    result = await execute_branch(conversation, config, checkpoint)
    return result.model_dump()


@task(
    name="compare_results",
    description="Compare results from multiple branches",
)
def compare_results_task(branch_results: list[dict]) -> dict:
    """Compare results from multiple branch executions.

    Args:
        branch_results: List of branch result dicts

    Returns:
        Comparison summary as a dict
    """
    from core.comparison import compare_branch_results

    from core.models import BranchResult

    results = [BranchResult.model_validate(r) for r in branch_results]
    comparison = compare_branch_results(results)
    return comparison.model_dump()
