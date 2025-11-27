"""Checkpoint creation and management."""

from datetime import datetime, timezone

from .models import Checkpoint, Conversation


def create_checkpoint(conversation: Conversation, step: int) -> Checkpoint:
    """Create a checkpoint at a specific step in the conversation.

    Args:
        conversation: The full conversation
        step: Step number to checkpoint at (1-indexed)

    Returns:
        Checkpoint object with conversation state at that step

    Raises:
        ValueError: If step is out of bounds
    """
    if step < 1 or step > conversation.step_count:
        raise ValueError(
            f"Step {step} is out of bounds. "
            f"Conversation has {conversation.step_count} steps."
        )

    truncated = conversation.at_step(step)

    return Checkpoint(
        conversation_id=conversation.session_id,
        step=step,
        messages=truncated.messages,
        project_path=conversation.project_path,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def checkpoint_to_messages(checkpoint: Checkpoint) -> list[dict]:
    """Convert checkpoint to Claude API message format.

    Args:
        checkpoint: The checkpoint to convert

    Returns:
        List of messages in Claude API format
    """
    messages = []

    for msg in checkpoint.messages:
        message = {
            "role": msg.role,
            "content": msg.content,
        }
        messages.append(message)

    return messages
