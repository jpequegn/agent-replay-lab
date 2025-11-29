"""End-to-end tests for Prefect workflow implementation.

Tests the complete workflow from CLI through Prefect to tasks,
using mocked Claude API responses.

This mirrors test_temporal_e2e.py for fair comparison between orchestrators.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.models import (
    BranchResult,
    Checkpoint,
    Conversation,
    ForkConfig,
    Message,
    ReplayRequest,
    TokenUsage,
)

# =============================================================================
# Test Fixtures (Same as Temporal E2E for fair comparison)
# =============================================================================


@pytest.fixture
def sample_conversation():
    """Sample conversation with 6+ steps for testing."""
    return Conversation(
        session_id="test-e2e-session",
        project_path="/test/project",
        messages=[
            Message(
                role="user",
                content="Hello, I need help with Python",
                timestamp="2025-01-01T10:00:00Z",
            ),
            Message(
                role="assistant",
                content="Hello! I'd be happy to help with Python.",
                timestamp="2025-01-01T10:00:01Z",
            ),
            Message(
                role="user",
                content="How do I read a file?",
                timestamp="2025-01-01T10:00:02Z",
            ),
            Message(
                role="assistant",
                content="You can use open() or pathlib",
                timestamp="2025-01-01T10:00:03Z",
            ),
            Message(
                role="user",
                content="Show me pathlib example",
                timestamp="2025-01-01T10:00:04Z",
            ),
            Message(
                role="assistant",
                content="Here's an example: Path('file.txt').read_text()",
                timestamp="2025-01-01T10:00:05Z",
            ),
        ],
    )


@pytest.fixture
def sample_checkpoint(sample_conversation):
    """Checkpoint at step 5 (fork point)."""
    return Checkpoint(
        conversation_id=sample_conversation.session_id,
        step=5,
        messages=sample_conversation.messages[:5],
        project_path=sample_conversation.project_path,
        created_at="2025-01-01T10:00:04Z",
    )


@pytest.fixture
def sample_request():
    """Sample replay request with 3 branches (same as Temporal test)."""
    return ReplayRequest(
        conversation_id="test-e2e-session",
        fork_at_step=5,
        branches=[
            ForkConfig(
                name="sonnet-baseline",
                model="claude-sonnet-4-20250514",
                max_turns=1,
            ),
            ForkConfig(
                name="haiku-speed",
                model="claude-haiku-4-20250514",
                max_turns=1,
            ),
            ForkConfig(
                name="alternative",
                model="claude-sonnet-4-20250514",
                inject_message="Give me a different approach",
                max_turns=1,
            ),
        ],
    )


@pytest.fixture
def mock_branch_result():
    """Mock successful branch result."""
    return BranchResult(
        branch_name="test-branch",
        config=ForkConfig(name="test-branch", model="claude-sonnet-4-20250514"),
        messages=[
            Message(
                role="assistant",
                content="Here's the response",
                timestamp="2025-01-01T10:00:06Z",
            ),
        ],
        duration_ms=500,
        token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        status="success",
    )


# =============================================================================
# Tests for GreetingFlow (Simple E2E)
# =============================================================================


class TestGreetingFlowE2E:
    """End-to-end tests for the Prefect greeting flow."""

    def test_greeting_flow_executes(self):
        """Test greeting flow executes in ephemeral mode."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow("TestUser")

        assert result == "Hello, TestUser!"

    def test_greeting_flow_default_name(self):
        """Test greeting flow with default name."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow()

        assert result == "Hello, Prefect!"


# =============================================================================
# Tests for ForkCompareFlow (Full E2E with Mocked Tasks)
# =============================================================================


class TestForkCompareFlowE2E:
    """End-to-end tests for the Prefect Fork & Compare flow.

    These tests mock at the flow level (task functions and state handling)
    to properly test the flow logic without running actual Claude API calls.
    """

    @pytest.fixture
    def mock_request(self):
        """Create a mock ReplayRequest dict."""
        return {
            "conversation_id": "test-e2e-session",
            "fork_at_step": 5,
            "branches": [
                {
                    "name": "sonnet-baseline",
                    "model": "claude-sonnet-4-20250514",
                    "max_turns": 1,
                },
                {
                    "name": "haiku-speed",
                    "model": "claude-haiku-4-20250514",
                    "max_turns": 1,
                },
                {
                    "name": "alternative",
                    "model": "claude-sonnet-4-20250514",
                    "max_turns": 1,
                    "inject_message": "Give me a different approach",
                },
            ],
        }

    @pytest.fixture
    def mock_conversation_data(self):
        """Mock conversation data as dict."""
        return {
            "session_id": "test-e2e-session",
            "project_path": "/test/project",
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2025-01-01T10:00:00Z"},
                {"role": "assistant", "content": "Hi!", "timestamp": "2025-01-01T10:00:01Z"},
                {"role": "user", "content": "How are you?", "timestamp": "2025-01-01T10:00:02Z"},
                {"role": "assistant", "content": "Good!", "timestamp": "2025-01-01T10:00:03Z"},
                {"role": "user", "content": "Question", "timestamp": "2025-01-01T10:00:04Z"},
            ],
            "step_count": 5,
        }

    @pytest.fixture
    def mock_checkpoint_data(self):
        """Mock checkpoint data as dict."""
        return {
            "conversation_id": "test-e2e-session",
            "step": 5,
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2025-01-01T10:00:00Z"},
                {"role": "assistant", "content": "Hi!", "timestamp": "2025-01-01T10:00:01Z"},
                {"role": "user", "content": "How are you?", "timestamp": "2025-01-01T10:00:02Z"},
                {"role": "assistant", "content": "Good!", "timestamp": "2025-01-01T10:00:03Z"},
                {"role": "user", "content": "Question", "timestamp": "2025-01-01T10:00:04Z"},
            ],
            "project_path": "/test/project",
            "created_at": "2025-01-01T10:00:04Z",
        }

    @pytest.mark.asyncio
    async def test_complete_flow_with_mocked_tasks(
        self, mock_request, mock_conversation_data, mock_checkpoint_data
    ):
        """Test complete Prefect flow with mocked task implementations."""
        from orchestrators.prefect.flows import ForkCompareFlow

        # Create mock branch results
        mock_branch_results = [
            {
                "branch_name": "sonnet-baseline",
                "status": "success",
                "messages": [{"role": "assistant", "content": "Response 1"}],
                "duration_ms": 500,
                "token_usage": {"input_tokens": 100, "output_tokens": 50},
            },
            {
                "branch_name": "haiku-speed",
                "status": "success",
                "messages": [{"role": "assistant", "content": "Response 2"}],
                "duration_ms": 300,
                "token_usage": {"input_tokens": 80, "output_tokens": 40},
            },
            {
                "branch_name": "alternative",
                "status": "success",
                "messages": [{"role": "assistant", "content": "Response 3"}],
                "duration_ms": 500,
                "token_usage": {"input_tokens": 100, "output_tokens": 50},
            },
        ]

        mock_comparison = {
            "successful": 3,
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
            # Mock state with is_completed/is_failed methods (Prefect 3.x API)
            mock_futures = []
            for result in mock_branch_results:
                mock_future = MagicMock()
                mock_future.state.is_completed.return_value = True
                mock_future.state.is_failed.return_value = False
                mock_future.result.return_value = result
                mock_futures.append(mock_future)

            mock_execute.submit.side_effect = mock_futures

            result = await ForkCompareFlow(mock_request)

            # Verify result structure (same as Temporal test)
            assert "request" in result
            assert "checkpoint" in result
            assert "branches" in result
            assert "total_duration_ms" in result
            assert "comparison_summary" in result

            # Verify all 3 branches executed
            assert len(result["branches"]) == 3

            # Verify branch names
            branch_names = [b["branch_name"] for b in result["branches"]]
            assert "sonnet-baseline" in branch_names
            assert "haiku-speed" in branch_names
            assert "alternative" in branch_names

            # Verify all succeeded
            assert all(b["status"] == "success" for b in result["branches"])

            # Verify comparison summary
            assert result["comparison_summary"]["successful"] == 3
            assert result["comparison_summary"]["failed"] == 0

    @pytest.mark.asyncio
    async def test_flow_with_partial_failure(self, mock_conversation_data, mock_checkpoint_data):
        """Test Prefect flow handles partial branch failures correctly."""
        from orchestrators.prefect.flows import ForkCompareFlow

        request = {
            "conversation_id": "test-partial-failure",
            "fork_at_step": 3,
            "branches": [
                {"name": "success-branch", "model": "claude-sonnet-4-20250514"},
                {"name": "failure-branch", "model": "claude-sonnet-4-20250514"},
            ],
        }

        mock_success_result = {
            "branch_name": "success-branch",
            "status": "success",
            "messages": [{"role": "assistant", "content": "Success"}],
            "duration_ms": 500,
            "token_usage": {"input_tokens": 100, "output_tokens": 50},
        }

        mock_failure_result = {
            "branch_name": "failure-branch",
            "status": "error",
            "messages": [],
            "duration_ms": 100,
            "token_usage": None,
            "error": "Simulated API error",
        }

        mock_comparison = {
            "successful": 1,
            "failed": 1,
            "branches": [mock_success_result, mock_failure_result],
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
            # Success future - mock state with is_completed/is_failed methods
            mock_future_success = MagicMock()
            mock_future_success.state.is_completed.return_value = True
            mock_future_success.state.is_failed.return_value = False
            mock_future_success.result.return_value = mock_success_result

            # Failure future - task completed but returned error status
            mock_future_failure = MagicMock()
            mock_future_failure.state.is_completed.return_value = True
            mock_future_failure.state.is_failed.return_value = False
            mock_future_failure.result.return_value = mock_failure_result

            mock_execute.submit.side_effect = [mock_future_success, mock_future_failure]

            result = await ForkCompareFlow(request)

            # Both branches should have results
            assert len(result["branches"]) == 2

            # Check success branch
            success_branch = next(
                b for b in result["branches"] if b["branch_name"] == "success-branch"
            )
            assert success_branch["status"] == "success"

            # Check failure branch
            failure_branch = next(
                b for b in result["branches"] if b["branch_name"] == "failure-branch"
            )
            assert failure_branch["status"] == "error"

            # Verify comparison summary
            assert result["comparison_summary"]["successful"] == 1
            assert result["comparison_summary"]["failed"] == 1


# =============================================================================
# Tests for Parallel Execution
# =============================================================================


class TestPrefectParallelExecution:
    """Tests for Prefect parallel branch execution."""

    @pytest.mark.asyncio
    async def test_branches_submitted_in_parallel(self):
        """Test that Prefect uses .submit() for parallel execution."""
        from orchestrators.prefect.flows import ForkCompareFlow

        request = {
            "conversation_id": "test-parallel",
            "fork_at_step": 3,
            "branches": [
                {"name": "branch-1", "model": "claude-sonnet-4-20250514"},
                {"name": "branch-2", "model": "claude-sonnet-4-20250514"},
                {"name": "branch-3", "model": "claude-sonnet-4-20250514"},
            ],
        }

        mock_conversation_data = {
            "session_id": "test-parallel",
            "project_path": "/test/project",
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2025-01-01T10:00:00Z"},
                {"role": "assistant", "content": "Hi!", "timestamp": "2025-01-01T10:00:01Z"},
                {"role": "user", "content": "Question", "timestamp": "2025-01-01T10:00:02Z"},
            ],
            "step_count": 3,
        }

        mock_checkpoint_data = {
            "conversation_id": "test-parallel",
            "step": 3,
            "messages": mock_conversation_data["messages"],
            "project_path": "/test/project",
            "created_at": "2025-01-01T10:00:02Z",
        }

        mock_branch_results = [
            {
                "branch_name": "branch-1",
                "status": "success",
                "messages": [],
                "duration_ms": 100,
                "token_usage": None,
            },
            {
                "branch_name": "branch-2",
                "status": "success",
                "messages": [],
                "duration_ms": 100,
                "token_usage": None,
            },
            {
                "branch_name": "branch-3",
                "status": "success",
                "messages": [],
                "duration_ms": 100,
                "token_usage": None,
            },
        ]

        mock_comparison = {
            "successful": 3,
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
            # Mock state with is_completed/is_failed methods (Prefect 3.x API)
            mock_futures = []
            for result in mock_branch_results:
                mock_future = MagicMock()
                mock_future.state.is_completed.return_value = True
                mock_future.state.is_failed.return_value = False
                mock_future.result.return_value = result
                mock_futures.append(mock_future)

            mock_execute.submit.side_effect = mock_futures

            result = await ForkCompareFlow(request)

            # Verify submit was called for each branch
            assert mock_execute.submit.call_count == 3

            # All 3 branches should have results
            assert len(result["branches"]) == 3
            assert all(b["status"] == "success" for b in result["branches"])


# =============================================================================
# Tests for Result Persistence
# =============================================================================


class TestPrefectResultPersistence:
    """Tests for saving Prefect results to disk."""

    def test_result_can_be_saved_to_json(self, tmp_path):
        """Test that Prefect workflow result can be saved to JSON file."""
        result = {
            "request": {
                "conversation_id": "test-123",
                "fork_at_step": 5,
                "branches": [{"name": "test", "model": "claude-sonnet-4-20250514"}],
            },
            "checkpoint": {
                "conversation_id": "test-123",
                "step": 5,
                "messages": [],
                "project_path": "/test",
                "created_at": "2025-01-01T00:00:00Z",
            },
            "branches": [
                {
                    "branch_name": "test",
                    "status": "success",
                    "duration_ms": 1000,
                    "messages": [{"role": "assistant", "content": "Response", "timestamp": ""}],
                }
            ],
            "total_duration_ms": 1000,
            "comparison_summary": {"successful": 1, "failed": 0},
        }

        # Save to file
        result_file = tmp_path / "result.json"
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)

        # Verify it can be loaded back
        with open(result_file) as f:
            loaded = json.load(f)

        assert loaded["request"]["conversation_id"] == "test-123"
        assert len(loaded["branches"]) == 1
        assert loaded["comparison_summary"]["successful"] == 1


# =============================================================================
# Tests for Client API
# =============================================================================


class TestPrefectClientE2E:
    """End-to-end tests for Prefect client API."""

    @pytest.mark.asyncio
    async def test_run_fork_compare_flow_via_client(self):
        """Test running flow via client API."""
        from orchestrators.prefect.client import run_fork_compare_flow

        request = {
            "conversation_id": "test-client-e2e",
            "fork_at_step": 3,
            "branches": [
                {"name": "branch-1", "model": "claude-sonnet-4-20250514"},
                {"name": "branch-2", "model": "claude-haiku-4-20250514"},
                {"name": "branch-3", "model": "claude-sonnet-4-20250514"},
            ],
        }

        mock_conversation_data = {
            "session_id": "test-client-e2e",
            "project_path": "/test/project",
            "messages": [
                {"role": "user", "content": "Hello", "timestamp": "2025-01-01T10:00:00Z"},
                {"role": "assistant", "content": "Hi!", "timestamp": "2025-01-01T10:00:01Z"},
                {"role": "user", "content": "Question", "timestamp": "2025-01-01T10:00:02Z"},
            ],
            "step_count": 3,
        }

        mock_checkpoint_data = {
            "conversation_id": "test-client-e2e",
            "step": 3,
            "messages": mock_conversation_data["messages"],
            "project_path": "/test/project",
            "created_at": "2025-01-01T10:00:02Z",
        }

        mock_branch_results = [
            {
                "branch_name": "branch-1",
                "status": "success",
                "messages": [],
                "duration_ms": 500,
                "token_usage": None,
            },
            {
                "branch_name": "branch-2",
                "status": "success",
                "messages": [],
                "duration_ms": 300,
                "token_usage": None,
            },
            {
                "branch_name": "branch-3",
                "status": "success",
                "messages": [],
                "duration_ms": 500,
                "token_usage": None,
            },
        ]

        mock_comparison = {
            "successful": 3,
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
            # Mock state with is_completed/is_failed methods (Prefect 3.x API)
            mock_futures = []
            for result in mock_branch_results:
                mock_future = MagicMock()
                mock_future.state.is_completed.return_value = True
                mock_future.state.is_failed.return_value = False
                mock_future.result.return_value = result
                mock_futures.append(mock_future)

            mock_execute.submit.side_effect = mock_futures

            result = await run_fork_compare_flow(request)

            # Verify result structure
            assert "branches" in result
            assert len(result["branches"]) == 3
            assert result["comparison_summary"]["successful"] == 3

    def test_generate_flow_run_id(self):
        """Test flow run ID generation."""
        from orchestrators.prefect.client import generate_flow_run_id

        id1 = generate_flow_run_id("test-conv")
        id2 = generate_flow_run_id("test-conv")

        # IDs should start with expected prefix
        assert id1.startswith("fork-compare-test-conv-")
        assert id2.startswith("fork-compare-test-conv-")

        # IDs should be unique
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test Prefect health check."""
        from orchestrators.prefect.client import check_prefect_health

        result = await check_prefect_health()

        assert result["healthy"] is True
        assert result["mode"] == "ephemeral"
        assert "healthy" in result["message"].lower()


# =============================================================================
# Comparison with Temporal
# =============================================================================


class TestOrchestratorComparison:
    """Tests documenting behavior comparison between Prefect and Temporal."""

    def test_documented_differences(self):
        """Document differences between Prefect and Temporal implementations.

        Both orchestrators should:
        1. Execute the same workflow structure
        2. Return the same result format
        3. Handle partial failures identically
        4. Support parallel branch execution

        Key differences:
        - Prefect runs in ephemeral mode (no server required)
        - Temporal requires a server (temporal server start-dev)
        - Prefect uses @task/@flow decorators
        - Temporal uses @activity/@workflow decorators
        - Prefect uses .submit() for parallel tasks
        - Temporal uses asyncio.gather() for parallel activities
        """
        differences = {
            "server_required": {"prefect": False, "temporal": True},
            "parallel_mechanism": {
                "prefect": "task.submit() + wait()",
                "temporal": "asyncio.gather()",
            },
            "retry_config": {
                "prefect": "@task(retries=N)",
                "temporal": "RetryPolicy in activity options",
            },
            "execution_mode": {
                "prefect": "ephemeral (local)",
                "temporal": "worker-based (distributed)",
            },
        }

        # This test documents the differences
        assert differences["server_required"]["prefect"] is False
        assert differences["server_required"]["temporal"] is True


# =============================================================================
# Integration Test Summary
# =============================================================================


class TestIntegrationSummary:
    """Summary tests to document tested scenarios."""

    def test_documented_scenarios(self):
        """Document what E2E scenarios are covered by these tests."""
        scenarios = [
            "GreetingFlow executes in ephemeral mode",
            "ForkCompareFlow with 3 branches (all success)",
            "ForkCompareFlow with partial failure (1 success, 1 error)",
            "Branches submitted with Prefect .submit()",
            "Result can be saved to JSON",
            "Client API run_fork_compare_flow works",
            "Flow run ID generation is unique",
            "Health check passes in ephemeral mode",
        ]

        # This test documents what's tested
        assert len(scenarios) == 8
        assert "ForkCompareFlow" in str(scenarios)
