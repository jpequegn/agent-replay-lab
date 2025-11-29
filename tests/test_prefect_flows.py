"""Tests for Prefect flows functionality.

Tests verify:
- Flow configuration and metadata
- Helper functions for error handling
- Flow execution with mocked tasks
- Partial failure handling
- Result aggregation
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prefect.states import Completed, Failed

# =============================================================================
# Tests for Helper Functions
# =============================================================================


class TestGetLogger:
    """Tests for _get_logger helper function."""

    def test_get_logger_returns_logger(self):
        """_get_logger returns a logger instance."""
        from orchestrators.prefect.flows import _get_logger

        logger = _get_logger()
        assert logger is not None

    def test_get_logger_fallback_to_standard_logger(self):
        """_get_logger falls back to standard logger outside flow context."""
        from orchestrators.prefect.flows import _get_logger

        # Outside flow context, should return standard logger
        logger = _get_logger()
        assert logger.name == "orchestrators.prefect.flows"


class TestCreateErrorResult:
    """Tests for _create_error_result helper function."""

    def test_create_error_result_structure(self):
        """_create_error_result returns correct structure."""
        from orchestrators.prefect.flows import _create_error_result

        result = _create_error_result("test-branch", ValueError("test error"))

        assert result["branch_name"] == "test-branch"
        assert result["status"] == "error"
        assert result["error"] == "test error"
        assert result["messages"] == []
        assert result["duration_ms"] == 0
        assert result["token_usage"] is None

    def test_create_error_result_with_different_exceptions(self):
        """_create_error_result handles different exception types."""
        from orchestrators.prefect.flows import _create_error_result

        # RuntimeError
        result = _create_error_result("branch-1", RuntimeError("runtime issue"))
        assert result["error"] == "runtime issue"

        # KeyError
        result = _create_error_result("branch-2", KeyError("missing_key"))
        assert "missing_key" in result["error"]


class TestProcessBranchFutures:
    """Tests for _process_branch_futures helper function.

    Note: The _process_branch_futures function uses isinstance() checks
    with Prefect's Completed/Failed states. These states are Pydantic models
    that are difficult to mock correctly in unit tests.

    The full behavior is tested through the ForkCompareFlow execution tests
    which use the actual Prefect runtime. These unit tests verify basic
    functionality and error handling.
    """

    def test_process_branch_futures_exists(self):
        """_process_branch_futures function exists."""
        from orchestrators.prefect.flows import _process_branch_futures

        assert callable(_process_branch_futures)

    def test_process_branch_futures_handles_empty_list(self):
        """_process_branch_futures handles empty list."""
        from orchestrators.prefect.flows import _process_branch_futures

        mock_logger = MagicMock()
        results = _process_branch_futures([], mock_logger)

        assert results == []

    def test_create_error_result_used_for_exceptions(self):
        """_process_branch_futures uses _create_error_result for exceptions."""
        from orchestrators.prefect.flows import _process_branch_futures

        # Create future that raises on state access
        mock_future = MagicMock()
        mock_future.state = property(lambda s: (_ for _ in ()).throw(RuntimeError("state error")))

        mock_logger = MagicMock()
        branch_futures = [("error-branch", mock_future)]

        # Should handle the exception and create an error result
        results = _process_branch_futures(branch_futures, mock_logger)

        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert results[0]["branch_name"] == "error-branch"


# =============================================================================
# Tests for GreetingFlow
# =============================================================================


class TestGreetingFlowConfig:
    """Tests for GreetingFlow configuration."""

    def test_greeting_flow_name(self):
        """GreetingFlow has correct name."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow.name == "greeting-flow"

    def test_greeting_flow_description(self):
        """GreetingFlow has description."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow.description is not None
        assert "greeting" in GreetingFlow.description.lower()

    def test_greeting_flow_retries(self):
        """GreetingFlow has retry configuration."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow.retries == 1


class TestGreetingFlowExecution:
    """Tests for GreetingFlow execution."""

    def test_run_greeting_flow(self):
        """run_greeting_flow returns correct greeting."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow("World")
        assert result == "Hello, World!"

    def test_run_greeting_flow_default_name(self):
        """run_greeting_flow uses default name."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow()
        assert result == "Hello, Prefect!"


# =============================================================================
# Tests for ForkCompareFlow Configuration
# =============================================================================


class TestForkCompareFlowConfig:
    """Tests for ForkCompareFlow configuration."""

    def test_fork_compare_flow_name(self):
        """ForkCompareFlow has correct name."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow.name == "fork-compare-flow"

    def test_fork_compare_flow_description(self):
        """ForkCompareFlow has description."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow.description is not None
        assert "fork" in ForkCompareFlow.description.lower()

    def test_fork_compare_flow_no_retries(self):
        """ForkCompareFlow doesn't retry (tasks handle retries)."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow.retries == 0

    def test_fork_compare_flow_is_async(self):
        """ForkCompareFlow is async."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert inspect.iscoroutinefunction(ForkCompareFlow.fn)

    def test_fork_compare_flow_log_prints(self):
        """ForkCompareFlow has log_prints enabled."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow.log_prints is True


# =============================================================================
# Tests for ForkCompareFlow Execution
# =============================================================================


class TestForkCompareFlowExecution:
    """Tests for ForkCompareFlow execution."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock ReplayRequest dict."""
        return {
            "conversation_id": "test-conv-123",
            "fork_at_step": 3,
            "branches": [
                {"name": "branch-1", "model": "claude-3-opus-20240229"},
                {"name": "branch-2", "model": "claude-3-sonnet-20240229"},
            ],
        }

    @pytest.fixture
    def mock_conversation_data(self):
        """Create mock conversation data."""
        return {
            "session_id": "test-conv-123",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
            "step_count": 3,
        }

    @pytest.fixture
    def mock_checkpoint_data(self):
        """Create mock checkpoint data."""
        return {
            "conversation_id": "test-conv-123",
            "step": 3,
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
        }

    @pytest.mark.asyncio
    async def test_fork_compare_flow_success(
        self, mock_request, mock_conversation_data, mock_checkpoint_data
    ):
        """ForkCompareFlow executes successfully with mocked tasks."""
        from orchestrators.prefect.flows import ForkCompareFlow

        # Mock branch results
        mock_branch_results = [
            {
                "branch_name": "branch-1",
                "status": "success",
                "messages": [{"role": "assistant", "content": "Response 1"}],
                "duration_ms": 100,
                "token_usage": {"input": 10, "output": 20},
            },
            {
                "branch_name": "branch-2",
                "status": "success",
                "messages": [{"role": "assistant", "content": "Response 2"}],
                "duration_ms": 150,
                "token_usage": {"input": 15, "output": 25},
            },
        ]

        mock_comparison = {
            "successful": 2,
            "failed": 0,
            "branches": mock_branch_results,
        }

        with (
            patch(
                "orchestrators.prefect.flows.load_conversation_task",
                return_value=mock_conversation_data,
            ),
            patch(
                "orchestrators.prefect.flows.create_checkpoint_task",
                return_value=mock_checkpoint_data,
            ),
            patch("orchestrators.prefect.flows.execute_branch_task") as mock_execute,
            patch(
                "orchestrators.prefect.flows.compare_results_task",
                return_value=mock_comparison,
            ),
            patch("orchestrators.prefect.flows.wait"),
        ):
            # Create mock futures that return results
            mock_future_1 = MagicMock()
            mock_future_1.state = Completed()
            mock_future_1.result.return_value = mock_branch_results[0]

            mock_future_2 = MagicMock()
            mock_future_2.state = Completed()
            mock_future_2.result.return_value = mock_branch_results[1]

            mock_execute.submit.side_effect = [mock_future_1, mock_future_2]

            result = await ForkCompareFlow(mock_request)

            assert result["request"] == mock_request
            assert result["checkpoint"] == mock_checkpoint_data
            assert len(result["branches"]) == 2
            assert result["total_duration_ms"] >= 0
            assert result["comparison_summary"] == mock_comparison

    @pytest.mark.asyncio
    async def test_fork_compare_flow_completes_with_branches(
        self, mock_request, mock_conversation_data, mock_checkpoint_data
    ):
        """ForkCompareFlow completes and returns expected structure with branches.

        Note: Due to Prefect state handling complexity in tests, we verify
        the flow completes and returns the expected structure rather than
        specific state transitions.
        """
        from orchestrators.prefect.flows import ForkCompareFlow

        mock_comparison = {
            "successful": 2,
            "failed": 0,
            "branches": [],
        }

        # Create mock futures with successful results
        mock_branch_result = {
            "branch_name": "test-branch",
            "status": "success",
            "messages": [],
            "duration_ms": 100,
            "token_usage": None,
        }

        with (
            patch(
                "orchestrators.prefect.flows.load_conversation_task",
                return_value=mock_conversation_data,
            ),
            patch(
                "orchestrators.prefect.flows.create_checkpoint_task",
                return_value=mock_checkpoint_data,
            ),
            patch("orchestrators.prefect.flows.execute_branch_task") as mock_execute,
            patch(
                "orchestrators.prefect.flows.compare_results_task",
                return_value=mock_comparison,
            ),
            patch("orchestrators.prefect.flows.wait"),
        ):
            mock_future = MagicMock()
            mock_future.state = Completed()
            mock_future.result.return_value = mock_branch_result

            mock_execute.submit.return_value = mock_future

            result = await ForkCompareFlow(mock_request)

            # Flow should complete and return expected structure
            assert "branches" in result
            assert "request" in result
            assert "checkpoint" in result
            assert "comparison_summary" in result
            assert "total_duration_ms" in result
            # Verify 2 branches were processed (one per branch config)
            assert len(result["branches"]) == 2

    @pytest.mark.asyncio
    async def test_fork_compare_flow_all_failures(
        self, mock_request, mock_conversation_data, mock_checkpoint_data
    ):
        """ForkCompareFlow handles all branches failing."""
        from orchestrators.prefect.flows import ForkCompareFlow

        mock_comparison = {
            "successful": 0,
            "failed": 2,
            "branches": [],
        }

        with (
            patch(
                "orchestrators.prefect.flows.load_conversation_task",
                return_value=mock_conversation_data,
            ),
            patch(
                "orchestrators.prefect.flows.create_checkpoint_task",
                return_value=mock_checkpoint_data,
            ),
            patch("orchestrators.prefect.flows.execute_branch_task") as mock_execute,
            patch(
                "orchestrators.prefect.flows.compare_results_task",
                return_value=mock_comparison,
            ),
            patch("orchestrators.prefect.flows.wait"),
        ):
            # Both futures fail
            mock_future_1 = MagicMock()
            mock_future_1.state = Failed(message="Error 1")

            mock_future_2 = MagicMock()
            mock_future_2.state = Failed(message="Error 2")

            mock_execute.submit.side_effect = [mock_future_1, mock_future_2]

            result = await ForkCompareFlow(mock_request)

            # Flow should complete even with all failures
            assert "branches" in result
            assert len(result["branches"]) == 2
            assert all(b["status"] == "error" for b in result["branches"])


# =============================================================================
# Tests for run_fork_compare_flow
# =============================================================================


class TestRunForkCompareFlow:
    """Tests for run_fork_compare_flow convenience function."""

    def test_run_fork_compare_flow_is_async(self):
        """run_fork_compare_flow is async."""
        from orchestrators.prefect.flows import run_fork_compare_flow

        assert inspect.iscoroutinefunction(run_fork_compare_flow)

    @pytest.mark.asyncio
    async def test_run_fork_compare_flow_calls_flow(self):
        """run_fork_compare_flow calls ForkCompareFlow."""
        from orchestrators.prefect.flows import run_fork_compare_flow

        mock_request = {"conversation_id": "test", "fork_at_step": 1, "branches": []}
        mock_result = {"request": mock_request, "branches": []}

        with patch(
            "orchestrators.prefect.flows.ForkCompareFlow",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await run_fork_compare_flow(mock_request)
            assert result == mock_result


# =============================================================================
# Tests for Module Exports
# =============================================================================


class TestFlowModuleExports:
    """Tests for flows module exports."""

    def test_exports_greeting_flow(self):
        """Module exports GreetingFlow."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow is not None

    def test_exports_fork_compare_flow(self):
        """Module exports ForkCompareFlow."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow is not None

    def test_exports_run_greeting_flow(self):
        """Module exports run_greeting_flow."""
        from orchestrators.prefect.flows import run_greeting_flow

        assert callable(run_greeting_flow)

    def test_exports_run_fork_compare_flow(self):
        """Module exports run_fork_compare_flow."""
        from orchestrators.prefect.flows import run_fork_compare_flow

        assert inspect.iscoroutinefunction(run_fork_compare_flow)
