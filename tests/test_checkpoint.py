"""Tests for checkpoint creation and serialization."""

import json
from pathlib import Path

import pytest

from core.checkpoint import (
    _message_to_api_format,
    checkpoint_to_messages,
    create_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from core.models import Conversation, Message, ToolCall, ToolResult


# Test fixtures
@pytest.fixture
def simple_messages():
    """Simple text-only messages."""
    return [
        Message(role="user", content="Hello", timestamp="2025-01-01T00:00:00Z"),
        Message(role="assistant", content="Hi there!", timestamp="2025-01-01T00:00:01Z"),
        Message(role="user", content="How are you?", timestamp="2025-01-01T00:00:02Z"),
        Message(role="assistant", content="I'm doing well!", timestamp="2025-01-01T00:00:03Z"),
    ]


@pytest.fixture
def messages_with_tools():
    """Messages including tool calls and results."""
    return [
        Message(role="user", content="Read the file", timestamp="2025-01-01T00:00:00Z"),
        Message(
            role="assistant",
            content="Let me read that file.",
            timestamp="2025-01-01T00:00:01Z",
            tool_calls=[
                ToolCall(id="tool_123", name="Read", input={"path": "/test.txt"})
            ],
        ),
        Message(
            role="user",
            content="",
            timestamp="2025-01-01T00:00:02Z",
            tool_results=[
                ToolResult(tool_call_id="tool_123", output="File contents here", is_error=False)
            ],
        ),
        Message(
            role="assistant",
            content="The file contains: File contents here",
            timestamp="2025-01-01T00:00:03Z",
        ),
    ]


@pytest.fixture
def conversation(simple_messages):
    """A simple conversation."""
    return Conversation(
        session_id="test-session",
        project_path="test-project",
        messages=simple_messages,
    )


@pytest.fixture
def conversation_with_tools(messages_with_tools):
    """Conversation with tool usage."""
    return Conversation(
        session_id="tool-session",
        project_path="test-project",
        messages=messages_with_tools,
    )


class TestCreateCheckpoint:
    """Tests for create_checkpoint function."""

    def test_creates_checkpoint_at_step(self, conversation):
        """Creates checkpoint at specified step."""
        checkpoint = create_checkpoint(conversation, step=2)

        assert checkpoint.conversation_id == "test-session"
        assert checkpoint.step == 2
        assert len(checkpoint.messages) == 2
        assert checkpoint.project_path == "test-project"
        assert checkpoint.created_at is not None

    def test_checkpoint_truncates_messages(self, conversation):
        """Checkpoint only includes messages up to step."""
        checkpoint = create_checkpoint(conversation, step=3)

        assert len(checkpoint.messages) == 3
        assert checkpoint.messages[0].content == "Hello"
        assert checkpoint.messages[2].content == "How are you?"

    def test_checkpoint_at_first_step(self, conversation):
        """Can create checkpoint at step 1."""
        checkpoint = create_checkpoint(conversation, step=1)

        assert checkpoint.step == 1
        assert len(checkpoint.messages) == 1
        assert checkpoint.messages[0].content == "Hello"

    def test_checkpoint_at_last_step(self, conversation):
        """Can create checkpoint at last step."""
        checkpoint = create_checkpoint(conversation, step=4)

        assert checkpoint.step == 4
        assert len(checkpoint.messages) == 4

    def test_step_zero_raises_error(self, conversation):
        """Step 0 raises ValueError."""
        with pytest.raises(ValueError, match="out of bounds"):
            create_checkpoint(conversation, step=0)

    def test_step_beyond_conversation_raises_error(self, conversation):
        """Step beyond conversation length raises ValueError."""
        with pytest.raises(ValueError, match="out of bounds"):
            create_checkpoint(conversation, step=10)

    def test_checkpoint_preserves_tool_calls(self, conversation_with_tools):
        """Tool calls are preserved in checkpoint."""
        checkpoint = create_checkpoint(conversation_with_tools, step=2)

        assert checkpoint.messages[1].tool_calls is not None
        assert len(checkpoint.messages[1].tool_calls) == 1
        assert checkpoint.messages[1].tool_calls[0].name == "Read"


class TestCheckpointToMessages:
    """Tests for checkpoint_to_messages function."""

    def test_simple_messages_format(self, conversation):
        """Simple messages produce simple format."""
        checkpoint = create_checkpoint(conversation, step=2)
        messages = checkpoint_to_messages(checkpoint)

        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "Hello"}
        assert messages[1] == {"role": "assistant", "content": "Hi there!"}

    def test_messages_with_tool_calls(self, conversation_with_tools):
        """Tool calls produce content block arrays."""
        checkpoint = create_checkpoint(conversation_with_tools, step=2)
        messages = checkpoint_to_messages(checkpoint)

        # First message is simple
        assert messages[0] == {"role": "user", "content": "Read the file"}

        # Second message has tool use
        assert messages[1]["role"] == "assistant"
        content = messages[1]["content"]
        assert isinstance(content, list)
        assert len(content) == 2

        # Text block
        assert content[0] == {"type": "text", "text": "Let me read that file."}

        # Tool use block
        assert content[1]["type"] == "tool_use"
        assert content[1]["id"] == "tool_123"
        assert content[1]["name"] == "Read"
        assert content[1]["input"] == {"path": "/test.txt"}

    def test_messages_with_tool_results(self, conversation_with_tools):
        """Tool results produce content block arrays."""
        checkpoint = create_checkpoint(conversation_with_tools, step=3)
        messages = checkpoint_to_messages(checkpoint)

        # Third message has tool result
        assert messages[2]["role"] == "user"
        content = messages[2]["content"]
        assert isinstance(content, list)

        # Tool result block (no text since content was empty)
        assert content[0]["type"] == "tool_result"
        assert content[0]["tool_use_id"] == "tool_123"
        assert content[0]["content"] == "File contents here"
        assert content[0]["is_error"] is False


class TestMessageToApiFormat:
    """Tests for _message_to_api_format function."""

    def test_simple_user_message(self):
        """Simple user message returns string content."""
        msg = Message(role="user", content="Hello", timestamp="")
        result = _message_to_api_format(msg)

        assert result == {"role": "user", "content": "Hello"}

    def test_simple_assistant_message(self):
        """Simple assistant message returns string content."""
        msg = Message(role="assistant", content="Hi!", timestamp="")
        result = _message_to_api_format(msg)

        assert result == {"role": "assistant", "content": "Hi!"}

    def test_message_with_tool_call(self):
        """Message with tool call returns content blocks."""
        msg = Message(
            role="assistant",
            content="Reading file...",
            timestamp="",
            tool_calls=[ToolCall(id="abc", name="Read", input={"path": "/x"})],
        )
        result = _message_to_api_format(msg)

        assert result["role"] == "assistant"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 2
        assert result["content"][0] == {"type": "text", "text": "Reading file..."}
        assert result["content"][1] == {
            "type": "tool_use",
            "id": "abc",
            "name": "Read",
            "input": {"path": "/x"},
        }

    def test_message_with_multiple_tool_calls(self):
        """Message with multiple tool calls includes all."""
        msg = Message(
            role="assistant",
            content="Let me check both.",
            timestamp="",
            tool_calls=[
                ToolCall(id="1", name="Read", input={"path": "/a"}),
                ToolCall(id="2", name="Grep", input={"pattern": "test"}),
            ],
        )
        result = _message_to_api_format(msg)

        assert len(result["content"]) == 3  # 1 text + 2 tool uses
        assert result["content"][1]["id"] == "1"
        assert result["content"][2]["id"] == "2"

    def test_message_with_tool_result(self):
        """Message with tool result returns content blocks."""
        msg = Message(
            role="user",
            content="",
            timestamp="",
            tool_results=[
                ToolResult(tool_call_id="abc", output="Result text", is_error=False)
            ],
        )
        result = _message_to_api_format(msg)

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1  # No text, just result
        assert result["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "abc",
            "content": "Result text",
            "is_error": False,
        }

    def test_tool_result_with_error(self):
        """Tool result with error flag is preserved."""
        msg = Message(
            role="user",
            content="",
            timestamp="",
            tool_results=[
                ToolResult(tool_call_id="xyz", output="Error occurred", is_error=True)
            ],
        )
        result = _message_to_api_format(msg)

        assert result["content"][0]["is_error"] is True

    def test_empty_tool_calls_list_treated_as_simple(self):
        """Empty tool_calls list is treated as simple message."""
        msg = Message(role="assistant", content="Hello", timestamp="", tool_calls=[])
        result = _message_to_api_format(msg)

        assert result == {"role": "assistant", "content": "Hello"}


class TestSaveAndLoadCheckpoint:
    """Tests for save_checkpoint and load_checkpoint functions."""

    def test_save_and_load_roundtrip(self, conversation, tmp_path):
        """Checkpoint can be saved and loaded."""
        checkpoint = create_checkpoint(conversation, step=2)
        file_path = tmp_path / "checkpoint.json"

        save_checkpoint(checkpoint, file_path)
        loaded = load_checkpoint(file_path)

        assert loaded is not None
        assert loaded.conversation_id == checkpoint.conversation_id
        assert loaded.step == checkpoint.step
        assert len(loaded.messages) == len(checkpoint.messages)
        assert loaded.created_at == checkpoint.created_at

    def test_save_creates_parent_directories(self, conversation, tmp_path):
        """Save creates parent directories if needed."""
        checkpoint = create_checkpoint(conversation, step=1)
        file_path = tmp_path / "nested" / "dirs" / "checkpoint.json"

        save_checkpoint(checkpoint, file_path)

        assert file_path.exists()

    def test_load_nonexistent_returns_none(self, tmp_path):
        """Loading nonexistent file returns None."""
        result = load_checkpoint(tmp_path / "nonexistent.json")
        assert result is None

    def test_save_produces_valid_json(self, conversation, tmp_path):
        """Saved file is valid JSON."""
        checkpoint = create_checkpoint(conversation, step=2)
        file_path = tmp_path / "checkpoint.json"

        save_checkpoint(checkpoint, file_path)

        with open(file_path) as f:
            data = json.load(f)

        assert data["conversation_id"] == "test-session"
        assert data["step"] == 2
        assert len(data["messages"]) == 2

    def test_preserves_tool_calls_through_roundtrip(self, conversation_with_tools, tmp_path):
        """Tool calls survive save/load roundtrip."""
        checkpoint = create_checkpoint(conversation_with_tools, step=2)
        file_path = tmp_path / "checkpoint.json"

        save_checkpoint(checkpoint, file_path)
        loaded = load_checkpoint(file_path)

        assert loaded.messages[1].tool_calls is not None
        assert len(loaded.messages[1].tool_calls) == 1
        assert loaded.messages[1].tool_calls[0].name == "Read"
        assert loaded.messages[1].tool_calls[0].input == {"path": "/test.txt"}

    def test_preserves_tool_results_through_roundtrip(self, conversation_with_tools, tmp_path):
        """Tool results survive save/load roundtrip."""
        checkpoint = create_checkpoint(conversation_with_tools, step=3)
        file_path = tmp_path / "checkpoint.json"

        save_checkpoint(checkpoint, file_path)
        loaded = load_checkpoint(file_path)

        assert loaded.messages[2].tool_results is not None
        assert len(loaded.messages[2].tool_results) == 1
        assert loaded.messages[2].tool_results[0].tool_call_id == "tool_123"
        assert loaded.messages[2].tool_results[0].is_error is False


class TestIntegrationWithConversationLoading:
    """Integration tests combining conversation loading with checkpoints."""

    @pytest.fixture
    def real_archive_path(self):
        """Get the real archive path, skip if not available."""
        path = Path.home() / ".config/superpowers/conversation-archive"
        if not path.exists():
            pytest.skip("Episodic memory archive not found")
        return path

    def test_checkpoint_from_real_conversation(self, real_archive_path, tmp_path):
        """Can create checkpoint from real conversation."""
        from core.conversation import list_conversations, load_conversation

        convos = list_conversations(archive_path=real_archive_path, limit=1)
        if not convos:
            pytest.skip("No conversations in archive")

        conv = load_conversation(convos[0]["session_id"], archive_path=real_archive_path)
        if conv is None or conv.step_count < 2:
            pytest.skip("Conversation too short")

        # Create checkpoint
        checkpoint = create_checkpoint(conv, step=2)
        assert checkpoint.step == 2

        # Save and reload
        file_path = tmp_path / "real_checkpoint.json"
        save_checkpoint(checkpoint, file_path)
        loaded = load_checkpoint(file_path)

        assert loaded is not None
        assert loaded.step == 2

        # Convert to API format
        messages = checkpoint_to_messages(loaded)
        assert len(messages) == 2
        for msg in messages:
            assert msg["role"] in ("user", "assistant")
            assert "content" in msg
