"""Tests for Temporal activities.

Tests activity functions directly (without running Temporal worker)
to verify they correctly wrap core library functions.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from core.models import (
    BranchResult,
    Checkpoint,
    Conversation,
    ForkConfig,
    Message,
    TokenUsage,
)
from orchestrators.temporal.activities import (
    # Retry policies
    CLAUDE_API_RETRY_POLICY,
    COMPUTE_RETRY_POLICY,
    LOCAL_RETRY_POLICY,
    # Timeout configurations
    ActivityTimeouts,
    # Activities
    compare_results_activity,
    create_checkpoint_activity,
    execute_branch_activity,
    # Activity option helpers
    get_claude_activity_options,
    get_compute_activity_options,
    get_local_activity_options,
    greet_activity,
    load_conversation_activity,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_conversation():
    """Sample conversation for testing."""
    return Conversation(
        session_id="test-session-123",
        project_path="/path/to/project",
        messages=[
            Message(role="user", content="Hello", timestamp="2025-01-01T00:00:00Z"),
            Message(role="assistant", content="Hi there!", timestamp="2025-01-01T00:00:01Z"),
            Message(role="user", content="How are you?", timestamp="2025-01-01T00:00:02Z"),
        ],
    )


@pytest.fixture
def sample_checkpoint():
    """Sample checkpoint for testing."""
    return Checkpoint(
        conversation_id="test-session-123",
        step=2,
        messages=[
            Message(role="user", content="Hello", timestamp="2025-01-01T00:00:00Z"),
            Message(role="assistant", content="Hi there!", timestamp="2025-01-01T00:00:01Z"),
        ],
        project_path="/path/to/project",
        created_at="2025-01-01T00:00:02Z",
    )


@pytest.fixture
def sample_config():
    """Sample fork configuration."""
    return ForkConfig(
        name="test-branch",
        model="claude-sonnet-4-20250514",
        max_turns=1,
    )


@pytest.fixture
def sample_branch_results():
    """Sample branch results for comparison testing."""
    return [
        BranchResult(
            branch_name="branch-a",
            config=ForkConfig(name="branch-a", model="claude-sonnet-4-20250514"),
            messages=[
                Message(role="assistant", content="Response A", timestamp=""),
            ],
            duration_ms=1000,
            token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            status="success",
        ),
        BranchResult(
            branch_name="branch-b",
            config=ForkConfig(name="branch-b", model="claude-haiku-4-20250514"),
            messages=[
                Message(role="assistant", content="Response B", timestamp=""),
            ],
            duration_ms=500,
            token_usage=TokenUsage(input_tokens=80, output_tokens=40, total_tokens=120),
            status="success",
        ),
    ]


# =============================================================================
# Tests for Retry Policies
# =============================================================================


class TestRetryPolicies:
    """Tests for retry policy configurations."""

    def test_claude_api_retry_policy_config(self):
        """Claude API retry policy has appropriate settings."""
        assert CLAUDE_API_RETRY_POLICY.initial_interval == timedelta(seconds=1)
        assert CLAUDE_API_RETRY_POLICY.backoff_coefficient == 2.0
        assert CLAUDE_API_RETRY_POLICY.maximum_interval == timedelta(seconds=60)
        assert CLAUDE_API_RETRY_POLICY.maximum_attempts == 5
        # Non-retryable errors for validation failures
        assert "ValueError" in CLAUDE_API_RETRY_POLICY.non_retryable_error_types
        assert "InvalidRequestError" in CLAUDE_API_RETRY_POLICY.non_retryable_error_types

    def test_local_retry_policy_config(self):
        """Local retry policy has quick retry settings."""
        assert LOCAL_RETRY_POLICY.initial_interval == timedelta(milliseconds=100)
        assert LOCAL_RETRY_POLICY.backoff_coefficient == 2.0
        assert LOCAL_RETRY_POLICY.maximum_interval == timedelta(seconds=5)
        assert LOCAL_RETRY_POLICY.maximum_attempts == 3

    def test_compute_retry_policy_config(self):
        """Compute retry policy has minimal retries."""
        assert COMPUTE_RETRY_POLICY.initial_interval == timedelta(milliseconds=100)
        assert COMPUTE_RETRY_POLICY.maximum_attempts == 2


# =============================================================================
# Tests for Timeout Configurations
# =============================================================================


class TestTimeoutConfigurations:
    """Tests for timeout configurations."""

    def test_local_timeouts(self):
        """Local operation timeouts are reasonable."""
        assert ActivityTimeouts.LOCAL_START_TO_CLOSE == timedelta(seconds=30)
        assert ActivityTimeouts.LOCAL_SCHEDULE_TO_CLOSE == timedelta(minutes=1)

    def test_claude_api_timeouts(self):
        """Claude API timeouts are long enough for multi-turn conversations."""
        assert ActivityTimeouts.CLAUDE_START_TO_CLOSE == timedelta(minutes=5)
        assert ActivityTimeouts.CLAUDE_SCHEDULE_TO_CLOSE == timedelta(minutes=10)

    def test_compute_timeouts(self):
        """Compute timeouts are reasonable for processing."""
        assert ActivityTimeouts.COMPUTE_START_TO_CLOSE == timedelta(seconds=30)
        assert ActivityTimeouts.COMPUTE_SCHEDULE_TO_CLOSE == timedelta(minutes=1)


# =============================================================================
# Tests for Activity Option Helpers
# =============================================================================


class TestActivityOptionHelpers:
    """Tests for activity option helper functions."""

    def test_get_local_activity_options(self):
        """Local activity options return correct config."""
        options = get_local_activity_options()

        assert "start_to_close_timeout" in options
        assert "retry_policy" in options
        assert options["start_to_close_timeout"] == ActivityTimeouts.LOCAL_START_TO_CLOSE
        assert options["retry_policy"] == LOCAL_RETRY_POLICY

    def test_get_claude_activity_options(self):
        """Claude activity options return correct config."""
        options = get_claude_activity_options()

        assert "start_to_close_timeout" in options
        assert "retry_policy" in options
        assert options["start_to_close_timeout"] == ActivityTimeouts.CLAUDE_START_TO_CLOSE
        assert options["retry_policy"] == CLAUDE_API_RETRY_POLICY

    def test_get_compute_activity_options(self):
        """Compute activity options return correct config."""
        options = get_compute_activity_options()

        assert "start_to_close_timeout" in options
        assert "retry_policy" in options
        assert options["start_to_close_timeout"] == ActivityTimeouts.COMPUTE_START_TO_CLOSE
        assert options["retry_policy"] == COMPUTE_RETRY_POLICY


# =============================================================================
# Tests for greet_activity
# =============================================================================


class TestGreetActivity:
    """Tests for the simple greeting activity."""

    @pytest.mark.asyncio
    async def test_greet_returns_greeting(self):
        """Greet activity returns formatted greeting."""
        result = await greet_activity("World")
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_greet_with_different_names(self):
        """Greet activity works with various names."""
        assert await greet_activity("Temporal") == "Hello, Temporal!"
        assert await greet_activity("Claude") == "Hello, Claude!"
        assert await greet_activity("") == "Hello, !"


# =============================================================================
# Tests for load_conversation_activity
# =============================================================================


class TestLoadConversationActivity:
    """Tests for the load conversation activity."""

    @pytest.mark.asyncio
    async def test_load_existing_conversation(self, sample_conversation):
        """Loading existing conversation returns serialized dict."""
        with patch("orchestrators.temporal.activities.load_conversation") as mock_load:
            mock_load.return_value = sample_conversation

            with patch("orchestrators.temporal.activities.activity"):
                result = await load_conversation_activity("test-session-123")

        assert result is not None
        assert result["session_id"] == "test-session-123"
        assert result["project_path"] == "/path/to/project"
        assert len(result["messages"]) == 3

    @pytest.mark.asyncio
    async def test_load_nonexistent_conversation(self):
        """Loading nonexistent conversation returns None."""
        with patch("orchestrators.temporal.activities.load_conversation") as mock_load:
            mock_load.return_value = None

            with patch("orchestrators.temporal.activities.activity"):
                result = await load_conversation_activity("nonexistent")

        assert result is None


# =============================================================================
# Tests for create_checkpoint_activity
# =============================================================================


class TestCreateCheckpointActivity:
    """Tests for the create checkpoint activity."""

    @pytest.mark.asyncio
    async def test_create_checkpoint_from_conversation(self, sample_conversation):
        """Creating checkpoint returns serialized checkpoint dict."""
        conv_dict = sample_conversation.model_dump()

        with patch("orchestrators.temporal.activities.create_checkpoint") as mock_create:
            mock_checkpoint = Checkpoint(
                conversation_id="test-session-123",
                step=2,
                messages=sample_conversation.messages[:2],
                project_path="/path/to/project",
                created_at="2025-01-01T00:00:02Z",
            )
            mock_create.return_value = mock_checkpoint

            with patch("orchestrators.temporal.activities.activity"):
                result = await create_checkpoint_activity(conv_dict, step=2)

        assert result["conversation_id"] == "test-session-123"
        assert result["step"] == 2
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_create_checkpoint_calls_core_function(self, sample_conversation):
        """Checkpoint activity calls core create_checkpoint function."""
        conv_dict = sample_conversation.model_dump()

        with patch("orchestrators.temporal.activities.create_checkpoint") as mock_create:
            mock_checkpoint = MagicMock()
            mock_checkpoint.model_dump.return_value = {"step": 2}
            mock_create.return_value = mock_checkpoint

            with patch("orchestrators.temporal.activities.activity"):
                await create_checkpoint_activity(conv_dict, step=2)

        # Verify create_checkpoint was called with correct args
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][1] == 2  # step argument


# =============================================================================
# Tests for execute_branch_activity
# =============================================================================


class TestExecuteBranchActivity:
    """Tests for the execute branch activity."""

    @pytest.mark.asyncio
    async def test_execute_branch_success(self, sample_checkpoint, sample_config):
        """Successful branch execution returns serialized result."""
        checkpoint_dict = sample_checkpoint.model_dump()
        config_dict = sample_config.model_dump()

        mock_result = BranchResult(
            branch_name="test-branch",
            config=sample_config,
            messages=[Message(role="assistant", content="Response", timestamp="")],
            duration_ms=1000,
            token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            status="success",
        )

        with patch("orchestrators.temporal.activities.execute_branch") as mock_exec:
            mock_exec.return_value = mock_result

            with patch("orchestrators.temporal.activities.activity"):
                result = await execute_branch_activity(checkpoint_dict, config_dict)

        assert result["status"] == "success"
        assert result["branch_name"] == "test-branch"
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_execute_branch_error_handling(self, sample_checkpoint, sample_config):
        """Branch execution with error returns error status."""
        checkpoint_dict = sample_checkpoint.model_dump()
        config_dict = sample_config.model_dump()

        mock_result = BranchResult(
            branch_name="test-branch",
            config=sample_config,
            messages=[],
            duration_ms=500,
            status="error",
            error="API rate limit exceeded",
        )

        with patch("orchestrators.temporal.activities.execute_branch") as mock_exec:
            mock_exec.return_value = mock_result

            with patch("orchestrators.temporal.activities.activity"):
                result = await execute_branch_activity(checkpoint_dict, config_dict)

        assert result["status"] == "error"
        assert "rate limit" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_branch_timeout(self, sample_checkpoint, sample_config):
        """Branch execution timeout returns timeout status."""
        checkpoint_dict = sample_checkpoint.model_dump()
        config_dict = sample_config.model_dump()

        mock_result = BranchResult(
            branch_name="test-branch",
            config=sample_config,
            messages=[],
            duration_ms=300000,
            status="timeout",
            error="Execution timed out",
        )

        with patch("orchestrators.temporal.activities.execute_branch") as mock_exec:
            mock_exec.return_value = mock_result

            with patch("orchestrators.temporal.activities.activity"):
                result = await execute_branch_activity(checkpoint_dict, config_dict)

        assert result["status"] == "timeout"


# =============================================================================
# Tests for compare_results_activity
# =============================================================================


class TestCompareResultsActivity:
    """Tests for the compare results activity."""

    @pytest.mark.asyncio
    async def test_compare_results_success(self, sample_branch_results):
        """Comparing successful results returns summary."""
        results_dicts = [r.model_dump() for r in sample_branch_results]

        with patch("orchestrators.temporal.activities.activity"):
            result = await compare_results_activity(results_dicts)

        assert result["total_branches"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0
        assert "branch-a" in result["branches"]
        assert "branch-b" in result["branches"]

    @pytest.mark.asyncio
    async def test_compare_results_with_failure(self, sample_branch_results):
        """Comparing mixed results counts failures."""
        # Add a failed branch
        failed = BranchResult(
            branch_name="branch-c",
            config=ForkConfig(name="branch-c", model="claude-opus-4-20250514"),
            messages=[],
            duration_ms=100,
            status="error",
            error="API error",
        )
        all_results = sample_branch_results + [failed]
        results_dicts = [r.model_dump() for r in all_results]

        with patch("orchestrators.temporal.activities.activity"):
            result = await compare_results_activity(results_dicts)

        assert result["total_branches"] == 3
        assert result["successful"] == 2
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_compare_results_metrics(self, sample_branch_results):
        """Comparison includes aggregate metrics."""
        results_dicts = [r.model_dump() for r in sample_branch_results]

        with patch("orchestrators.temporal.activities.activity"):
            result = await compare_results_activity(results_dicts)

        assert "metrics" in result
        # Average of 1000ms and 500ms
        assert result["metrics"]["avg_duration_ms"] == 750
        assert result["metrics"]["min_duration_ms"] == 500
        assert result["metrics"]["max_duration_ms"] == 1000
        # Average of 150 and 120 tokens
        assert result["metrics"]["avg_tokens"] == 135

    @pytest.mark.asyncio
    async def test_compare_empty_results(self):
        """Comparing empty results handles gracefully."""
        with patch("orchestrators.temporal.activities.activity"):
            result = await compare_results_activity([])

        assert result["total_branches"] == 0
        assert result["successful"] == 0
        assert result["failed"] == 0


# =============================================================================
# Tests for Activity Serialization
# =============================================================================


class TestActivitySerialization:
    """Tests to verify activities correctly serialize/deserialize Pydantic models."""

    @pytest.mark.asyncio
    async def test_conversation_roundtrip(self, sample_conversation):
        """Conversation survives serialization through activity."""
        conv_dict = sample_conversation.model_dump()

        # Verify we can reconstruct
        reconstructed = Conversation.model_validate(conv_dict)
        assert reconstructed.session_id == sample_conversation.session_id
        assert len(reconstructed.messages) == len(sample_conversation.messages)

    @pytest.mark.asyncio
    async def test_checkpoint_roundtrip(self, sample_checkpoint):
        """Checkpoint survives serialization through activity."""
        checkpoint_dict = sample_checkpoint.model_dump()

        reconstructed = Checkpoint.model_validate(checkpoint_dict)
        assert reconstructed.conversation_id == sample_checkpoint.conversation_id
        assert reconstructed.step == sample_checkpoint.step

    @pytest.mark.asyncio
    async def test_config_roundtrip(self, sample_config):
        """ForkConfig survives serialization through activity."""
        config_dict = sample_config.model_dump()

        reconstructed = ForkConfig.model_validate(config_dict)
        assert reconstructed.name == sample_config.name
        assert reconstructed.model == sample_config.model

    @pytest.mark.asyncio
    async def test_branch_result_roundtrip(self, sample_branch_results):
        """BranchResult survives serialization through activity."""
        result = sample_branch_results[0]
        result_dict = result.model_dump()

        reconstructed = BranchResult.model_validate(result_dict)
        assert reconstructed.branch_name == result.branch_name
        assert reconstructed.status == result.status
        assert reconstructed.token_usage.total_tokens == result.token_usage.total_tokens
