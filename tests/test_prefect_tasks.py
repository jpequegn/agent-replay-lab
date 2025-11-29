"""Tests for Prefect tasks configuration and behavior.

Tests verify:
- Retry configuration classes
- Timeout configuration classes
- Task retry behavior
- Error handling
- Task execution
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Tests for Retry Configuration
# =============================================================================


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_retry_config_is_frozen(self):
        """RetryConfig is immutable."""
        from orchestrators.prefect.tasks import RetryConfig

        config = RetryConfig()
        with pytest.raises(AttributeError):
            config.LOCAL_RETRIES = 10

    def test_claude_api_retries(self):
        """Claude API has 5 retries configured."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.CLAUDE_API_RETRIES == 5

    def test_local_retries(self):
        """Local operations have 3 retries configured."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.LOCAL_RETRIES == 3

    def test_compute_retries(self):
        """Compute operations have 2 retries configured."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.COMPUTE_RETRIES == 2

    def test_claude_api_retry_delay(self):
        """Claude API retry delay is 1 second."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.CLAUDE_API_RETRY_DELAY == 1

    def test_local_retry_delay(self):
        """Local retry delay is 100ms."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.LOCAL_RETRY_DELAY == 0.1

    def test_claude_api_jitter(self):
        """Claude API has jitter factor of 1.0."""
        from orchestrators.prefect.tasks import RetryConfig

        assert RetryConfig.CLAUDE_API_RETRY_JITTER == 1.0


# =============================================================================
# Tests for Timeout Configuration
# =============================================================================


class TestTaskTimeouts:
    """Tests for TaskTimeouts dataclass."""

    def test_timeout_config_is_frozen(self):
        """TaskTimeouts is immutable."""
        from orchestrators.prefect.tasks import TaskTimeouts

        config = TaskTimeouts()
        with pytest.raises(AttributeError):
            config.LOCAL_TIMEOUT = 100

    def test_local_timeout(self):
        """Local operations timeout is 30 seconds."""
        from orchestrators.prefect.tasks import TaskTimeouts

        assert TaskTimeouts.LOCAL_TIMEOUT == 30

    def test_claude_api_timeout(self):
        """Claude API timeout is 5 minutes."""
        from orchestrators.prefect.tasks import TaskTimeouts

        assert TaskTimeouts.CLAUDE_API_TIMEOUT == 300

    def test_compute_timeout(self):
        """Compute operations timeout is 30 seconds."""
        from orchestrators.prefect.tasks import TaskTimeouts

        assert TaskTimeouts.COMPUTE_TIMEOUT == 30


# =============================================================================
# Tests for Non-Retryable Errors
# =============================================================================


class TestNonRetryableErrors:
    """Tests for non-retryable error configuration."""

    def test_value_error_not_retryable(self):
        """ValueError is non-retryable."""
        from orchestrators.prefect.tasks import NON_RETRYABLE_ERRORS

        assert ValueError in NON_RETRYABLE_ERRORS

    def test_type_error_not_retryable(self):
        """TypeError is non-retryable."""
        from orchestrators.prefect.tasks import NON_RETRYABLE_ERRORS

        assert TypeError in NON_RETRYABLE_ERRORS

    def test_key_error_not_retryable(self):
        """KeyError is non-retryable."""
        from orchestrators.prefect.tasks import NON_RETRYABLE_ERRORS

        assert KeyError in NON_RETRYABLE_ERRORS


# =============================================================================
# Tests for should_retry Function
# =============================================================================


class TestShouldRetry:
    """Tests for should_retry function."""

    def test_should_retry_value_error(self):
        """ValueError should not trigger retry."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(ValueError("test"), 3) is False

    def test_should_retry_type_error(self):
        """TypeError should not trigger retry."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(TypeError("test"), 3) is False

    def test_should_retry_key_error(self):
        """KeyError should not trigger retry."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(KeyError("test"), 3) is False

    def test_should_retry_runtime_error(self):
        """RuntimeError should trigger retry if retries remaining."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(RuntimeError("test"), 3) is True

    def test_should_retry_no_retries_left(self):
        """Should not retry if no retries remaining."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(RuntimeError("test"), 0) is False

    def test_should_retry_connection_error(self):
        """ConnectionError should trigger retry."""
        from orchestrators.prefect.tasks import should_retry

        assert should_retry(ConnectionError("test"), 2) is True


# =============================================================================
# Tests for Task Configuration
# =============================================================================


class TestGreetTaskConfig:
    """Tests for greet_task configuration."""

    def test_greet_task_retries(self):
        """greet_task has correct retry count."""
        from orchestrators.prefect.tasks import RetryConfig, greet_task

        assert greet_task.retries == RetryConfig.LOCAL_RETRIES

    def test_greet_task_timeout(self):
        """greet_task has correct timeout."""
        from orchestrators.prefect.tasks import TaskTimeouts, greet_task

        assert greet_task.timeout_seconds == TaskTimeouts.LOCAL_TIMEOUT


class TestLoadConversationTaskConfig:
    """Tests for load_conversation_task configuration."""

    def test_load_conversation_retries(self):
        """load_conversation_task has correct retry count."""
        from orchestrators.prefect.tasks import RetryConfig, load_conversation_task

        assert load_conversation_task.retries == RetryConfig.LOCAL_RETRIES

    def test_load_conversation_timeout(self):
        """load_conversation_task has correct timeout."""
        from orchestrators.prefect.tasks import TaskTimeouts, load_conversation_task

        assert load_conversation_task.timeout_seconds == TaskTimeouts.LOCAL_TIMEOUT

    def test_load_conversation_jitter(self):
        """load_conversation_task has retry jitter."""
        from orchestrators.prefect.tasks import RetryConfig, load_conversation_task

        assert load_conversation_task.retry_jitter_factor == RetryConfig.LOCAL_RETRY_JITTER


class TestCreateCheckpointTaskConfig:
    """Tests for create_checkpoint_task configuration."""

    def test_create_checkpoint_retries(self):
        """create_checkpoint_task has correct retry count."""
        from orchestrators.prefect.tasks import RetryConfig, create_checkpoint_task

        assert create_checkpoint_task.retries == RetryConfig.LOCAL_RETRIES

    def test_create_checkpoint_timeout(self):
        """create_checkpoint_task has correct timeout."""
        from orchestrators.prefect.tasks import TaskTimeouts, create_checkpoint_task

        assert create_checkpoint_task.timeout_seconds == TaskTimeouts.LOCAL_TIMEOUT


class TestExecuteBranchTaskConfig:
    """Tests for execute_branch_task configuration."""

    def test_execute_branch_retries(self):
        """execute_branch_task has correct retry count."""
        from orchestrators.prefect.tasks import RetryConfig, execute_branch_task

        assert execute_branch_task.retries == RetryConfig.CLAUDE_API_RETRIES

    def test_execute_branch_timeout(self):
        """execute_branch_task has correct timeout."""
        from orchestrators.prefect.tasks import TaskTimeouts, execute_branch_task

        assert execute_branch_task.timeout_seconds == TaskTimeouts.CLAUDE_API_TIMEOUT

    def test_execute_branch_is_async(self):
        """execute_branch_task is async."""
        from orchestrators.prefect.tasks import execute_branch_task

        assert inspect.iscoroutinefunction(execute_branch_task.fn)

    def test_execute_branch_has_retry_condition(self):
        """execute_branch_task has custom retry condition."""
        from orchestrators.prefect.tasks import execute_branch_task, should_retry

        assert execute_branch_task.retry_condition_fn == should_retry


class TestCompareResultsTaskConfig:
    """Tests for compare_results_task configuration."""

    def test_compare_results_retries(self):
        """compare_results_task has correct retry count."""
        from orchestrators.prefect.tasks import RetryConfig, compare_results_task

        assert compare_results_task.retries == RetryConfig.COMPUTE_RETRIES

    def test_compare_results_timeout(self):
        """compare_results_task has correct timeout."""
        from orchestrators.prefect.tasks import TaskTimeouts, compare_results_task

        assert compare_results_task.timeout_seconds == TaskTimeouts.COMPUTE_TIMEOUT


# =============================================================================
# Tests for Task Execution
# =============================================================================


class TestGreetTaskExecution:
    """Tests for greet_task execution."""

    def test_greet_task_returns_greeting(self):
        """greet_task returns correct greeting."""
        from orchestrators.prefect.tasks import greet_task

        result = greet_task.fn("World")
        assert result == "Hello, World!"

    def test_greet_task_empty_name(self):
        """greet_task handles empty name."""
        from orchestrators.prefect.tasks import greet_task

        result = greet_task.fn("")
        assert result == "Hello, !"


class TestLoadConversationTaskExecution:
    """Tests for load_conversation_task execution."""

    def test_load_conversation_not_found(self):
        """load_conversation_task raises ValueError for missing conversation."""
        from orchestrators.prefect.tasks import load_conversation_task

        with patch("core.conversation.load_conversation", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                load_conversation_task.fn("nonexistent-id")

    def test_load_conversation_success(self):
        """load_conversation_task returns conversation dict."""
        from orchestrators.prefect.tasks import load_conversation_task

        mock_conv = MagicMock()
        mock_conv.step_count = 5
        mock_conv.model_dump.return_value = {"session_id": "test", "messages": []}

        with patch("core.conversation.load_conversation", return_value=mock_conv):
            result = load_conversation_task.fn("test-id")
            assert result == {"session_id": "test", "messages": []}


class TestCreateCheckpointTaskExecution:
    """Tests for create_checkpoint_task execution."""

    def test_create_checkpoint_invalid_step_low(self):
        """create_checkpoint_task raises ValueError for step < 1."""
        from orchestrators.prefect.tasks import create_checkpoint_task

        conv_data = {"session_id": "test", "messages": [], "step_count": 5}

        with patch("core.models.Conversation.model_validate") as mock_validate:
            mock_conv = MagicMock()
            mock_conv.step_count = 5
            mock_validate.return_value = mock_conv

            with pytest.raises(ValueError, match="out of range"):
                create_checkpoint_task.fn(conv_data, 0)

    def test_create_checkpoint_invalid_step_high(self):
        """create_checkpoint_task raises ValueError for step > step_count."""
        from orchestrators.prefect.tasks import create_checkpoint_task

        conv_data = {"session_id": "test", "messages": [], "step_count": 5}

        with patch("core.models.Conversation.model_validate") as mock_validate:
            mock_conv = MagicMock()
            mock_conv.step_count = 5
            mock_validate.return_value = mock_conv

            with pytest.raises(ValueError, match="out of range"):
                create_checkpoint_task.fn(conv_data, 10)


class TestCompareResultsTaskExecution:
    """Tests for compare_results_task execution."""

    def test_compare_results_empty_list(self):
        """compare_results_task handles empty list."""
        from orchestrators.prefect.tasks import compare_results_task

        mock_comparison = MagicMock()
        mock_comparison.model_dump.return_value = {"successful": 0, "failed": 0}

        with (
            patch("core.comparator.compare_branches", return_value=mock_comparison),
            patch("core.models.BranchResult.model_validate", return_value=MagicMock()),
        ):
            result = compare_results_task.fn([])
            assert result == {"successful": 0, "failed": 0}


# =============================================================================
# Tests for Module Exports
# =============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_exports_retry_config(self):
        """Module exports RetryConfig."""
        from orchestrators.prefect import RetryConfig

        assert RetryConfig is not None

    def test_exports_task_timeouts(self):
        """Module exports TaskTimeouts."""
        from orchestrators.prefect import TaskTimeouts

        assert TaskTimeouts is not None

    def test_exports_non_retryable_errors(self):
        """Module exports NON_RETRYABLE_ERRORS."""
        from orchestrators.prefect import NON_RETRYABLE_ERRORS

        assert NON_RETRYABLE_ERRORS is not None

    def test_exports_should_retry(self):
        """Module exports should_retry."""
        from orchestrators.prefect import should_retry

        assert callable(should_retry)

    def test_exports_all_tasks(self):
        """Module exports all task functions."""
        from orchestrators.prefect import (
            compare_results_task,
            create_checkpoint_task,
            execute_branch_task,
            greet_task,
            load_conversation_task,
        )

        assert all(
            [
                greet_task,
                load_conversation_task,
                create_checkpoint_task,
                execute_branch_task,
                compare_results_task,
            ]
        )

    def test_exports_all_flows(self):
        """Module exports all flow functions."""
        from orchestrators.prefect import (
            ForkCompareFlow,
            GreetingFlow,
            run_fork_compare_flow,
            run_greeting_flow,
        )

        assert all([GreetingFlow, ForkCompareFlow, run_greeting_flow, run_fork_compare_flow])
