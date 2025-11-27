"""Tests for the Claude SDK executor."""

import os
from unittest.mock import MagicMock

import pytest

from core.executor import execute_branch
from core.models import Checkpoint, ForkConfig, Message, ToolCall, ToolResult


# Test fixtures
@pytest.fixture
def simple_checkpoint():
    """A simple checkpoint with text-only messages."""
    return Checkpoint(
        conversation_id="test-session",
        step=2,
        messages=[
            Message(role="user", content="Hello!", timestamp="2025-01-01T00:00:00Z"),
            Message(role="assistant", content="Hi there!", timestamp="2025-01-01T00:00:01Z"),
        ],
        project_path="test-project",
        created_at="2025-01-01T00:00:02Z",
    )


@pytest.fixture
def checkpoint_with_tools():
    """Checkpoint with tool calls/results."""
    return Checkpoint(
        conversation_id="tool-session",
        step=3,
        messages=[
            Message(role="user", content="Read file.txt", timestamp=""),
            Message(
                role="assistant",
                content="Let me read that file.",
                timestamp="",
                tool_calls=[
                    ToolCall(id="tool_1", name="Read", input={"path": "/file.txt"})
                ],
            ),
            Message(
                role="user",
                content="",
                timestamp="",
                tool_results=[
                    ToolResult(tool_call_id="tool_1", output="file contents", is_error=False)
                ],
            ),
        ],
        project_path="test-project",
        created_at="2025-01-01T00:00:00Z",
    )


@pytest.fixture
def default_config():
    """Default fork configuration."""
    return ForkConfig(
        name="test-branch",
        model="claude-sonnet-4-20250514",
        max_turns=1,
    )


@pytest.fixture
def mock_response():
    """Create a mock Claude API response."""
    response = MagicMock()
    response.content = [MagicMock(text="This is the response.")]
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    response.stop_reason = "end_turn"
    return response


class TestExecuteBranchWithMock:
    """Tests for execute_branch using mocked Claude SDK."""

    def test_basic_execution(self, simple_checkpoint, default_config, mock_response):
        """Basic execution returns success."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.status == "success"
        assert result.branch_name == "test-branch"
        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert result.messages[0].content == "This is the response."

    def test_token_usage_captured(self, simple_checkpoint, default_config, mock_response):
        """Token usage is correctly captured."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.token_usage is not None
        assert result.token_usage.input_tokens == 100
        assert result.token_usage.output_tokens == 50
        assert result.token_usage.total_tokens == 150

    def test_duration_tracked(self, simple_checkpoint, default_config, mock_response):
        """Duration is tracked in milliseconds."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.duration_ms >= 0

    def test_inject_message(self, simple_checkpoint, mock_response):
        """Inject message is added to conversation."""
        config = ForkConfig(
            name="inject-branch",
            model="claude-sonnet-4-20250514",
            max_turns=1,
            inject_message="What about a different approach?",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        # Should have user message + assistant response
        assert len(result.messages) == 2
        assert result.messages[0].role == "user"
        assert result.messages[0].content == "What about a different approach?"
        assert result.messages[1].role == "assistant"

        # Verify the inject message was included in API call
        # The messages list has: checkpoint messages + inject message
        # After response, the assistant response is appended, so we check the 3rd message (index 2)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Checkpoint has 2 messages, inject_message adds 1 more = 3 messages sent to API
        assert len(messages) >= 3
        assert messages[2]["content"] == "What about a different approach?"

    def test_model_override(self, simple_checkpoint, mock_response):
        """Different model can be specified."""
        config = ForkConfig(
            name="opus-branch",
            model="claude-opus-4-20250514",
            max_turns=1,
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-20250514"
        assert result.status == "success"

    def test_system_prompt_override(self, simple_checkpoint, mock_response):
        """System prompt can be specified."""
        config = ForkConfig(
            name="system-branch",
            model="claude-sonnet-4-20250514",
            max_turns=1,
            system_prompt="You are a helpful coding assistant.",
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a helpful coding assistant."
        assert result.status == "success"

    def test_multiple_turns(self, simple_checkpoint):
        """Multiple turns are executed until end_turn."""
        config = ForkConfig(
            name="multi-turn",
            model="claude-sonnet-4-20250514",
            max_turns=5,
            inject_message="Start conversation",
        )

        # First response doesn't end
        response1 = MagicMock()
        response1.content = [MagicMock(text="Response 1")]
        response1.usage.input_tokens = 50
        response1.usage.output_tokens = 25
        response1.stop_reason = "max_tokens"

        # Second response ends
        response2 = MagicMock()
        response2.content = [MagicMock(text="Response 2")]
        response2.usage.input_tokens = 75
        response2.usage.output_tokens = 30
        response2.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [response1, response2]

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        # 1 inject + 2 assistant responses
        assert len(result.messages) == 3
        assert result.messages[1].content == "Response 1"
        assert result.messages[2].content == "Response 2"

        # Token usage accumulated
        assert result.token_usage.input_tokens == 125  # 50 + 75
        assert result.token_usage.output_tokens == 55  # 25 + 30

    def test_max_turns_limit(self, simple_checkpoint):
        """Execution stops at max_turns even without end_turn."""
        config = ForkConfig(
            name="limited",
            model="claude-sonnet-4-20250514",
            max_turns=2,
            inject_message="Go",
        )

        # Never ends
        response = MagicMock()
        response.content = [MagicMock(text="Still going...")]
        response.usage.input_tokens = 50
        response.usage.output_tokens = 25
        response.stop_reason = "max_tokens"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = response

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        # Called exactly max_turns times
        assert mock_client.messages.create.call_count == 2
        # 1 inject + 2 assistant messages
        assert len(result.messages) == 3


class TestExecuteBranchErrorHandling:
    """Tests for error handling in execute_branch."""

    def test_api_error_returns_error_result(self, simple_checkpoint, default_config):
        """API errors are caught and returned in result."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API rate limit exceeded")

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.status == "error"
        assert "API rate limit exceeded" in result.error
        assert result.branch_name == "test-branch"

    def test_timeout_error_returns_timeout_result(self, simple_checkpoint, default_config):
        """TimeoutError is caught and returns timeout status."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = TimeoutError("Request timed out")

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.status == "timeout"
        assert result.error == "Execution timed out"

    def test_error_preserves_partial_messages(self, simple_checkpoint):
        """Error after some turns preserves collected messages."""
        config = ForkConfig(
            name="partial",
            model="claude-sonnet-4-20250514",
            max_turns=5,
            inject_message="Start",
        )

        # First call succeeds
        response1 = MagicMock()
        response1.content = [MagicMock(text="First response")]
        response1.usage.input_tokens = 50
        response1.usage.output_tokens = 25
        response1.stop_reason = "max_tokens"

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            response1,
            Exception("Connection lost"),
        ]

        result = execute_branch(simple_checkpoint, config, client=mock_client)

        assert result.status == "error"
        # Should have inject message + first response
        assert len(result.messages) == 2
        assert result.messages[0].content == "Start"
        assert result.messages[1].content == "First response"

    def test_duration_tracked_on_error(self, simple_checkpoint, default_config):
        """Duration is tracked even on error."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Error")

        result = execute_branch(simple_checkpoint, default_config, client=mock_client)

        assert result.duration_ms >= 0


class TestExecuteBranchWithToolMessages:
    """Tests for execute_branch with tool call/result messages."""

    def test_checkpoint_with_tools_converts_correctly(
        self, checkpoint_with_tools, default_config, mock_response
    ):
        """Checkpoint with tools is converted to API format."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        result = execute_branch(checkpoint_with_tools, default_config, client=mock_client)

        # Verify messages were passed correctly
        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # First message is simple
        assert messages[0]["content"] == "Read file.txt"

        # Second has tool_use blocks
        assert isinstance(messages[1]["content"], list)
        tool_use_block = next(
            b for b in messages[1]["content"] if b.get("type") == "tool_use"
        )
        assert tool_use_block["name"] == "Read"

        # Third has tool_result
        assert isinstance(messages[2]["content"], list)
        tool_result_block = next(
            b for b in messages[2]["content"] if b.get("type") == "tool_result"
        )
        assert tool_result_block["content"] == "file contents"

        assert result.status == "success"


class TestIntegrationWithRealAPI:
    """Integration tests with real Claude API.

    These tests require ANTHROPIC_API_KEY to be set.
    """

    @pytest.fixture
    def has_api_key(self):
        """Check if API key is available."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

    def test_real_api_call(self, simple_checkpoint, has_api_key):
        """Test with real Claude API."""
        config = ForkConfig(
            name="real-test",
            model="claude-sonnet-4-20250514",
            max_turns=1,
            inject_message="Say 'Hello test!' and nothing else.",
        )

        result = execute_branch(simple_checkpoint, config)

        assert result.status == "success", (
            f"Expected success but got {result.status}: {result.error}"
        )
        assert result.token_usage is not None
        assert result.token_usage.input_tokens > 0
        assert result.token_usage.output_tokens > 0
        assert len(result.messages) >= 1
        assert result.duration_ms > 0

    def test_real_api_with_haiku(self, simple_checkpoint, has_api_key):
        """Test with Haiku model."""
        config = ForkConfig(
            name="haiku-test",
            model="claude-haiku-4-20250514",
            max_turns=1,
            inject_message="Respond with just the word 'test'.",
        )

        result = execute_branch(simple_checkpoint, config)

        assert result.status == "success"
        assert len(result.messages) >= 1
