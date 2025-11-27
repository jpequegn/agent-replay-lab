"""Checkpoint creation and management."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Checkpoint, Conversation, Message


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

    The Claude API accepts messages with:
    - Simple string content for text-only messages
    - Array of content blocks for messages with tool calls/results

    Args:
        checkpoint: The checkpoint to convert

    Returns:
        List of messages in Claude API format
    """
    messages = []

    for msg in checkpoint.messages:
        message = _message_to_api_format(msg)
        messages.append(message)

    return messages


def _message_to_api_format(msg: Message) -> dict:
    """Convert a single message to Claude API format.

    Handles text content, tool calls (tool_use), and tool results.

    Args:
        msg: The message to convert

    Returns:
        Message dict in Claude API format
    """
    # Build content blocks if we have tool calls or results
    has_tool_calls = msg.tool_calls and len(msg.tool_calls) > 0
    has_tool_results = msg.tool_results and len(msg.tool_results) > 0

    if not has_tool_calls and not has_tool_results:
        # Simple text-only message
        return {"role": msg.role, "content": msg.content}

    # Build content block array
    content_blocks = []

    # Add text content if present
    if msg.content.strip():
        content_blocks.append({"type": "text", "text": msg.content})

    # Add tool use blocks for assistant messages
    if has_tool_calls and msg.role == "assistant":
        for tool_call in msg.tool_calls:
            content_blocks.append({
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.name,
                "input": tool_call.input,
            })

    # Add tool result blocks for user messages
    if has_tool_results and msg.role == "user":
        for result in msg.tool_results:
            content_blocks.append({
                "type": "tool_result",
                "tool_use_id": result.tool_call_id,
                "content": result.output,
                "is_error": result.is_error,
            })

    return {"role": msg.role, "content": content_blocks}


def save_checkpoint(checkpoint: Checkpoint, path: Path) -> None:
    """Save a checkpoint to a JSON file.

    Args:
        checkpoint: The checkpoint to save
        path: File path to save to (will be created if needed)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(checkpoint.model_dump(), f, indent=2)


def load_checkpoint(path: Path) -> Checkpoint | None:
    """Load a checkpoint from a JSON file.

    Args:
        path: Path to the checkpoint JSON file

    Returns:
        Checkpoint object or None if file doesn't exist
    """
    if not path.exists():
        return None

    with open(path, "r") as f:
        data = json.load(f)

    return Checkpoint.model_validate(data)
