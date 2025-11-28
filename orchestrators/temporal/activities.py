"""Temporal activities for Fork & Compare workflow.

Activities are the building blocks of workflows - they perform the actual work
like loading conversations, creating checkpoints, and executing branches.
"""

from temporalio import activity

from core.checkpoint import create_checkpoint
from core.conversation import load_conversation
from core.executor import execute_branch
from core.models import Checkpoint, ForkConfig


@activity.defn
async def load_conversation_activity(session_id: str) -> dict:
    """Load a conversation from episodic memory.

    Args:
        session_id: The session ID to load

    Returns:
        Serialized conversation dict or None if not found
    """
    conv = load_conversation(session_id)
    if conv is None:
        return None
    return conv.model_dump()


@activity.defn
async def create_checkpoint_activity(conversation_dict: dict, step: int) -> dict:
    """Create a checkpoint at a specific step.

    Args:
        conversation_dict: Serialized conversation
        step: Step number to checkpoint at

    Returns:
        Serialized checkpoint dict
    """
    from core.models import Conversation

    conv = Conversation.model_validate(conversation_dict)
    checkpoint = create_checkpoint(conv, step)
    return checkpoint.model_dump()


@activity.defn
async def execute_branch_activity(checkpoint_dict: dict, config_dict: dict) -> dict:
    """Execute a single branch from a checkpoint.

    Args:
        checkpoint_dict: Serialized checkpoint
        config_dict: Serialized ForkConfig

    Returns:
        Serialized BranchResult dict
    """
    checkpoint = Checkpoint.model_validate(checkpoint_dict)
    config = ForkConfig.model_validate(config_dict)
    result = execute_branch(checkpoint, config)
    return result.model_dump()


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
