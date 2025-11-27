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
                metadata = _extract_conversation_metadata(jsonl_file, project_dir.name)
                if metadata:
                    conversations.append(metadata)
            except (json.JSONDecodeError, IOError):
                continue

    # Sort by modification time, most recent first
    conversations.sort(key=lambda x: x["modified"], reverse=True)
    return conversations[:limit]


def _extract_conversation_metadata(jsonl_file: Path, project_name: str) -> dict | None:
    """Extract metadata from a conversation file.

    Reads the file to find session info and message count.
    """
    session_id = None
    message_count = 0
    first_timestamp = None
    last_timestamp = None

    with open(jsonl_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                # Get session ID from first entry that has it
                if not session_id and "sessionId" in data:
                    session_id = data["sessionId"]

                # Count user/assistant messages
                entry_type = data.get("type")
                if entry_type in ("user", "assistant"):
                    message_count += 1

                    # Track timestamps
                    timestamp = data.get("timestamp")
                    if timestamp:
                        if not first_timestamp:
                            first_timestamp = timestamp
                        last_timestamp = timestamp

            except json.JSONDecodeError:
                continue

    if message_count == 0:
        return None

    return {
        "session_id": session_id or jsonl_file.stem,
        "project_path": project_name,
        "file_path": str(jsonl_file),
        "modified": jsonl_file.stat().st_mtime,
        "message_count": message_count,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
    }


def load_conversation(
    session_id: str,
    archive_path: Path = DEFAULT_ARCHIVE_PATH,
) -> Conversation | None:
    """Load a conversation by session ID.

    Args:
        session_id: The session ID (filename without extension or actual sessionId)
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

        # Try exact filename match first
        jsonl_file = project_dir / f"{session_id}.jsonl"
        if jsonl_file.exists():
            return _parse_conversation_file(jsonl_file, project_dir.name)

        # Also search by sessionId in file content (for partial matches)
        for jsonl_file in project_dir.glob("*.jsonl"):
            if session_id in jsonl_file.stem:
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

    The episodic memory JSONL format has entries with:
    - type: "user" | "assistant" | "system" | "file-history-snapshot"
    - message: { role, content } for user/assistant entries
    - timestamp: ISO timestamp
    - sessionId: session identifier

    Args:
        file_path: Path to the JSONL file
        project_path: Project directory name

    Returns:
        Parsed Conversation object
    """
    messages = []
    session_id = file_path.stem

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)

                # Update session_id if found in data
                if "sessionId" in data and data["sessionId"]:
                    session_id = data["sessionId"]

                message = _parse_entry(data)
                if message:
                    messages.append(message)
            except json.JSONDecodeError:
                continue

    return Conversation(
        session_id=session_id,
        project_path=project_path,
        messages=messages,
    )


def _parse_entry(data: dict) -> Message | None:
    """Parse a single JSONL entry into a Message.

    Handles the episodic memory format where:
    - Top level has 'type': 'user' | 'assistant'
    - Actual message content is in 'message' field
    - 'message' contains 'role' and 'content'

    Args:
        data: Parsed JSON entry

    Returns:
        Message object or None if not a valid message entry
    """
    # Only process user and assistant entries
    entry_type = data.get("type")
    if entry_type not in ("user", "assistant"):
        return None

    # Get the nested message object
    message_data = data.get("message", {})
    if not message_data:
        return None

    role = message_data.get("role")
    if role not in ("user", "assistant"):
        return None

    # Get timestamp from top level
    timestamp = data.get("timestamp", "")

    # Parse content - can be string or list of content blocks
    content = _extract_content(message_data.get("content", ""))

    # Skip empty messages (often just tool use markers)
    if not content.strip():
        return None

    # Parse tool calls from content blocks
    tool_calls = _extract_tool_calls(message_data.get("content", []))

    # Parse tool results from content (for user messages with tool results)
    tool_results = _extract_tool_results(message_data.get("content", []))

    return Message(
        role=role,
        content=content,
        timestamp=timestamp,
        tool_calls=tool_calls if tool_calls else None,
        tool_results=tool_results if tool_results else None,
    )


def _extract_content(content) -> str:
    """Extract text content from various content formats.

    Content can be:
    - A plain string
    - A list of content blocks (text, tool_use, tool_result, thinking, etc.)

    Args:
        content: The content field from a message

    Returns:
        Extracted text content as a string
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                # Skip thinking, tool_use, tool_result blocks for main content
        return "\n".join(filter(None, text_parts))

    return ""


def _extract_tool_calls(content) -> list[ToolCall]:
    """Extract tool calls from content blocks.

    Args:
        content: The content field (should be a list for tool calls)

    Returns:
        List of ToolCall objects
    """
    tool_calls = []

    if not isinstance(content, list):
        return tool_calls

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_calls.append(ToolCall(
                id=block.get("id", ""),
                name=block.get("name", ""),
                input=block.get("input", {}),
            ))

    return tool_calls


def _extract_tool_results(content) -> list[ToolResult]:
    """Extract tool results from content blocks.

    Args:
        content: The content field (should be a list for tool results)

    Returns:
        List of ToolResult objects
    """
    tool_results = []

    if not isinstance(content, list):
        return tool_results

    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            # Tool result content can be string or list
            output = block.get("content", "")
            if isinstance(output, list):
                output_parts = []
                for part in output:
                    if isinstance(part, dict) and part.get("type") == "text":
                        output_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        output_parts.append(part)
                output = "\n".join(output_parts)

            tool_results.append(ToolResult(
                tool_call_id=block.get("tool_use_id", ""),
                output=output,
                is_error=block.get("is_error", False),
            ))

    return tool_results
