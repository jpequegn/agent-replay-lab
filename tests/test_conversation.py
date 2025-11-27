"""Tests for conversation loading from episodic memory."""

import json
from pathlib import Path

import pytest

from core.conversation import (
    _extract_content,
    _extract_tool_calls,
    _extract_tool_results,
    _parse_entry,
    list_conversations,
    load_conversation,
    load_conversation_from_path,
)


class TestExtractContent:
    """Tests for _extract_content function."""

    def test_string_content(self):
        """Simple string content is returned as-is."""
        assert _extract_content("Hello world") == "Hello world"

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _extract_content("") == ""

    def test_list_with_text_block(self):
        """List with text block extracts text."""
        content = [{"type": "text", "text": "Hello"}]
        assert _extract_content(content) == "Hello"

    def test_list_with_multiple_text_blocks(self):
        """Multiple text blocks are joined with newlines."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        assert _extract_content(content) == "Hello\nWorld"

    def test_list_with_mixed_blocks(self):
        """Non-text blocks are ignored."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "thinking", "thinking": "Some thinking..."},
            {"type": "tool_use", "id": "123", "name": "test"},
            {"type": "text", "text": "World"},
        ]
        assert _extract_content(content) == "Hello\nWorld"

    def test_list_with_string_items(self):
        """String items in list are included."""
        content = ["Hello", "World"]
        assert _extract_content(content) == "Hello\nWorld"

    def test_none_returns_empty(self):
        """None returns empty string."""
        assert _extract_content(None) == ""

    def test_other_type_returns_empty(self):
        """Other types return empty string."""
        assert _extract_content(123) == ""


class TestExtractToolCalls:
    """Tests for _extract_tool_calls function."""

    def test_no_tool_calls(self):
        """Returns empty list when no tool calls."""
        assert _extract_tool_calls([{"type": "text", "text": "Hello"}]) == []

    def test_single_tool_call(self):
        """Extracts single tool call."""
        content = [
            {"type": "tool_use", "id": "123", "name": "Read", "input": {"path": "/test"}}
        ]
        calls = _extract_tool_calls(content)
        assert len(calls) == 1
        assert calls[0].id == "123"
        assert calls[0].name == "Read"
        assert calls[0].input == {"path": "/test"}

    def test_multiple_tool_calls(self):
        """Extracts multiple tool calls."""
        content = [
            {"type": "tool_use", "id": "1", "name": "Read", "input": {}},
            {"type": "text", "text": "Some text"},
            {"type": "tool_use", "id": "2", "name": "Write", "input": {}},
        ]
        calls = _extract_tool_calls(content)
        assert len(calls) == 2
        assert calls[0].name == "Read"
        assert calls[1].name == "Write"

    def test_string_content(self):
        """String content returns empty list."""
        assert _extract_tool_calls("Hello") == []


class TestExtractToolResults:
    """Tests for _extract_tool_results function."""

    def test_no_tool_results(self):
        """Returns empty list when no tool results."""
        assert _extract_tool_results([{"type": "text", "text": "Hello"}]) == []

    def test_single_tool_result(self):
        """Extracts single tool result."""
        content = [
            {"type": "tool_result", "tool_use_id": "123", "content": "Result text"}
        ]
        results = _extract_tool_results(content)
        assert len(results) == 1
        assert results[0].tool_call_id == "123"
        assert results[0].output == "Result text"
        assert results[0].is_error is False

    def test_tool_result_with_error(self):
        """Extracts tool result with error flag."""
        content = [
            {"type": "tool_result", "tool_use_id": "123", "content": "Error!", "is_error": True}
        ]
        results = _extract_tool_results(content)
        assert len(results) == 1
        assert results[0].is_error is True

    def test_tool_result_with_list_content(self):
        """Extracts tool result with list content."""
        content = [
            {
                "type": "tool_result",
                "tool_use_id": "123",
                "content": [{"type": "text", "text": "Part 1"}, {"type": "text", "text": "Part 2"}],
            }
        ]
        results = _extract_tool_results(content)
        assert len(results) == 1
        assert results[0].output == "Part 1\nPart 2"


class TestParseEntry:
    """Tests for _parse_entry function."""

    def test_user_message(self):
        """Parses user message entry."""
        entry = {
            "type": "user",
            "message": {"role": "user", "content": "Hello"},
            "timestamp": "2025-01-01T00:00:00Z",
        }
        msg = _parse_entry(entry)
        assert msg is not None
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp == "2025-01-01T00:00:00Z"

    def test_assistant_message(self):
        """Parses assistant message entry."""
        entry = {
            "type": "assistant",
            "message": {"role": "assistant", "content": "Hi there"},
            "timestamp": "2025-01-01T00:00:01Z",
        }
        msg = _parse_entry(entry)
        assert msg is not None
        assert msg.role == "assistant"
        assert msg.content == "Hi there"

    def test_system_entry_ignored(self):
        """System entries are ignored."""
        entry = {"type": "system", "message": {}}
        assert _parse_entry(entry) is None

    def test_file_history_snapshot_ignored(self):
        """File history snapshots are ignored."""
        entry = {"type": "file-history-snapshot", "snapshot": {}}
        assert _parse_entry(entry) is None

    def test_empty_content_ignored(self):
        """Messages with empty content are ignored."""
        entry = {
            "type": "user",
            "message": {"role": "user", "content": "   "},
            "timestamp": "",
        }
        assert _parse_entry(entry) is None

    def test_message_with_tool_calls(self):
        """Parses message with tool calls."""
        entry = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read that file."},
                    {"type": "tool_use", "id": "123", "name": "Read", "input": {"path": "/test"}},
                ],
            },
            "timestamp": "",
        }
        msg = _parse_entry(entry)
        assert msg is not None
        assert msg.content == "Let me read that file."
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "Read"


class TestListConversations:
    """Tests for list_conversations function."""

    def test_empty_directory(self, tmp_path):
        """Returns empty list for empty directory."""
        result = list_conversations(archive_path=tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """Returns empty list for nonexistent directory."""
        result = list_conversations(archive_path=tmp_path / "nonexistent")
        assert result == []

    def test_finds_conversations(self, tmp_path):
        """Finds conversation files in archive."""
        # Create a project directory with a conversation file
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create a valid conversation file
        conv_file = project_dir / "session-123.jsonl"
        entries = [
            {
                "type": "user",
                "sessionId": "session-123",
                "message": {"role": "user", "content": "Hello"},
                "timestamp": "2025-01-01T00:00:00Z",
            },
            {
                "type": "assistant",
                "sessionId": "session-123",
                "message": {"role": "assistant", "content": "Hi"},
                "timestamp": "2025-01-01T00:00:01Z",
            },
        ]
        with open(conv_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = list_conversations(archive_path=tmp_path)
        assert len(result) == 1
        assert result[0]["session_id"] == "session-123"
        assert result[0]["message_count"] == 2

    def test_project_filter(self, tmp_path):
        """Filters by project path."""
        # Create two project directories
        project1 = tmp_path / "project-one"
        project1.mkdir()
        project2 = tmp_path / "project-two"
        project2.mkdir()

        # Create conversation in each
        for proj in [project1, project2]:
            conv_file = proj / "session.jsonl"
            entry = {"type": "user", "message": {"role": "user", "content": "Hi"}, "timestamp": ""}
            with open(conv_file, "w") as f:
                f.write(json.dumps(entry) + "\n")

        # Filter for project-one
        result = list_conversations(archive_path=tmp_path, project_filter="project-one")
        assert len(result) == 1
        assert "project-one" in result[0]["project_path"]


class TestLoadConversation:
    """Tests for load_conversation function."""

    def test_loads_by_session_id(self, tmp_path):
        """Loads conversation by session ID."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        conv_file = project_dir / "my-session.jsonl"
        entries = [
            {
                "type": "user",
                "sessionId": "my-session",
                "message": {"role": "user", "content": "Hello"},
                "timestamp": "",
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Hi there"},
                "timestamp": "",
            },
        ]
        with open(conv_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        conv = load_conversation("my-session", archive_path=tmp_path)
        assert conv is not None
        assert conv.session_id == "my-session"
        assert len(conv.messages) == 2

    def test_returns_none_for_missing(self, tmp_path):
        """Returns None for missing session ID."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        conv = load_conversation("nonexistent", archive_path=tmp_path)
        assert conv is None


class TestLoadConversationFromPath:
    """Tests for load_conversation_from_path function."""

    def test_loads_from_path(self, tmp_path):
        """Loads conversation from file path."""
        conv_file = tmp_path / "session.jsonl"
        entries = [
            {
                "type": "user",
                "sessionId": "test-session",
                "message": {"role": "user", "content": "Hello"},
                "timestamp": "",
            },
        ]
        with open(conv_file, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        conv = load_conversation_from_path(conv_file)
        assert conv is not None
        assert conv.session_id == "test-session"

    def test_returns_none_for_missing_file(self, tmp_path):
        """Returns None for missing file."""
        conv = load_conversation_from_path(tmp_path / "nonexistent.jsonl")
        assert conv is None


class TestIntegrationWithRealArchive:
    """Integration tests with the real episodic memory archive.

    These tests require the actual archive to exist.
    """

    @pytest.fixture
    def real_archive_path(self):
        """Get the real archive path, skip if not available."""
        path = Path.home() / ".config/superpowers/conversation-archive"
        if not path.exists():
            pytest.skip("Episodic memory archive not found")
        return path

    def test_list_real_conversations(self, real_archive_path):
        """Can list conversations from real archive."""
        convos = list_conversations(archive_path=real_archive_path, limit=5)
        assert isinstance(convos, list)
        # Should find at least some conversations if archive exists
        if convos:
            assert "session_id" in convos[0]
            assert "project_path" in convos[0]
            assert "message_count" in convos[0]

    def test_load_real_conversation(self, real_archive_path):
        """Can load a real conversation."""
        convos = list_conversations(archive_path=real_archive_path, limit=1)
        if not convos:
            pytest.skip("No conversations in archive")

        conv = load_conversation(convos[0]["session_id"], archive_path=real_archive_path)
        assert conv is not None
        assert conv.session_id is not None
        assert len(conv.messages) > 0

        # Verify message structure
        for msg in conv.messages:
            assert msg.role in ("user", "assistant")
            assert isinstance(msg.content, str)
