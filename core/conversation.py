"""Load and parse conversations from episodic memory archives."""

import json
from pathlib import Path

from .models import Conversation, Message, ToolCall, ToolResult


DEFAULT_ARCHIVE_PATH = Path.home() / ".config/superpowers/conversation-archive"


def list_conversations(
    archive_path: Path = DEFAULT_ARCHIVE_PATH,
    project_filter: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List available conversations from episodic memory.

    Args:
        archive_path: Path to conversation archive directory
        project_filter: Optional project path to filter by
        limit: Maximum number of conversations to return

    Returns:
        List of conversation metadata dicts
    """
    conversations = []

    if not archive_path.exists():
        return conversations

    for project_dir in archive_path.iterdir():
        if not project_dir.is_dir():
            continue

        if project_filter and project_filter not in str(project_dir):
            continue

        for jsonl_file in project_dir.glob("*.jsonl"):
            try:
                # Read first few lines to get metadata
                with open(jsonl_file, "r") as f:
                    first_line = f.readline()
                    if first_line:
                        data = json.loads(first_line)
                        conversations.append({
                            "session_id": jsonl_file.stem,
                            "project_path": str(project_dir.name),
                            "file_path": str(jsonl_file),
                            "modified": jsonl_file.stat().st_mtime,
                        })
            except (json.JSONDecodeError, IOError):
                continue

        if len(conversations) >= limit:
            break

    # Sort by modification time, most recent first
    conversations.sort(key=lambda x: x["modified"], reverse=True)
    return conversations[:limit]


def load_conversation(
    session_id: str,
    archive_path: Path = DEFAULT_ARCHIVE_PATH,
) -> Conversation | None:
    """Load a conversation by session ID.

    Args:
        session_id: The session ID (filename without extension)
        archive_path: Path to conversation archive directory

    Returns:
        Conversation object or None if not found
    """
    if not archive_path.exists():
        return None

    # Search for the session file
    for project_dir in archive_path.iterdir():
        if not project_dir.is_dir():
            continue

        jsonl_file = project_dir / f"{session_id}.jsonl"
        if jsonl_file.exists():
            return _parse_conversation_file(jsonl_file, project_dir.name)

    return None


def load_conversation_from_path(file_path: Path) -> Conversation | None:
    """Load a conversation from a specific file path.

    Args:
        file_path: Path to the JSONL conversation file

    Returns:
        Conversation object or None if not found
    """
    if not file_path.exists():
        return None

    project_path = file_path.parent.name
    return _parse_conversation_file(file_path, project_path)


def _parse_conversation_file(file_path: Path, project_path: str) -> Conversation:
    """Parse a JSONL conversation file into a Conversation object.

    Args:
        file_path: Path to the JSONL file
        project_path: Project directory name

    Returns:
        Parsed Conversation object
    """
    messages = []

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                message = _parse_message(data)
                if message:
                    messages.append(message)
            except json.JSONDecodeError:
                continue

    return Conversation(
        session_id=file_path.stem,
        project_path=project_path,
        messages=messages,
    )


def _parse_message(data: dict) -> Message | None:
    """Parse a single message from JSONL data.

    The episodic memory format varies - this handles common patterns.
    """
    # Handle different message formats
    role = data.get("role")
    if role not in ("user", "assistant"):
        return None

    content = data.get("content", "")
    if isinstance(content, list):
        # Handle content blocks
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        content = "\n".join(text_parts)

    timestamp = data.get("timestamp", "")

    # Parse tool calls if present
    tool_calls = None
    if "tool_calls" in data:
        tool_calls = [
            ToolCall(
                id=tc.get("id", ""),
                name=tc.get("name", ""),
                input=tc.get("input", {}),
            )
            for tc in data["tool_calls"]
        ]

    # Parse tool results if present
    tool_results = None
    if "tool_results" in data:
        tool_results = [
            ToolResult(
                tool_call_id=tr.get("tool_call_id", ""),
                output=tr.get("output", ""),
                is_error=tr.get("is_error", False),
            )
            for tr in data["tool_results"]
        ]

    return Message(
        role=role,
        content=content,
        timestamp=timestamp,
        tool_calls=tool_calls,
        tool_results=tool_results,
    )
