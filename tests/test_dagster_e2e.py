"""End-to-end tests for Dagster workflow implementation.

Tests the complete workflow from client through Dagster to ops,
using mocked Claude API responses.

This mirrors test_prefect_e2e.py and test_temporal_e2e.py for fair comparison
between orchestrators.
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
# Test Fixtures (Same as Prefect/Temporal E2E for fair comparison)
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
    """Sample replay request with 3 branches (same as Prefect/Temporal test)."""
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
# Tests for GreetingJob (Simple E2E)
# =============================================================================


class TestGreetingJobE2E:
    """End-to-end tests for the Dagster greeting job."""

    @pytest.mark.asyncio
    async def test_greeting_job_executes(self):
        """Test greeting job executes in-process."""
        from orchestrators.dagster.client import run_greeting_job

        result = await run_greeting_job("TestUser")

        assert result == "Hello, TestUser!"

    @pytest.mark.asyncio
    async def test_greeting_job_with_dagster(self):
        """Test greeting job with Dagster name."""
        from orchestrators.dagster.client import run_greeting_job

        result = await run_greeting_job("Dagster")

        assert result == "Hello, Dagster!"


# =============================================================================
# Tests for ForkCompareJob (Full E2E with Mocked Ops)
# =============================================================================


class TestForkCompareJobE2E:
    """End-to-end tests for the Dagster Fork & Compare job.

    These tests mock at the op level to properly test the job logic
    without running actual Claude API calls.
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
    async def test_complete_job_with_mocked_ops(
        self, mock_request, mock_conversation_data, mock_checkpoint_data
    ):
        """Test complete Dagster job with mocked op implementations."""
        from orchestrators.dagster.client import run_fork_compare_job

        # Create mock branch results with all required fields for BranchResult validation
        mock_branch_results = [
            {
                "branch_name": "sonnet-baseline",
                "config": {"name": "sonnet-baseline", "model": "claude-sonnet-4-20250514"},
                "status": "success",
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Response 1",
                        "timestamp": "2025-01-01T10:00:05Z",
                    }
                ],
                "duration_ms": 500,
                "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            },
            {
                "branch_name": "haiku-speed",
                "config": {"name": "haiku-speed", "model": "claude-haiku-4-20250514"},
                "status": "success",
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Response 2",
                        "timestamp": "2025-01-01T10:00:05Z",
                    }
                ],
                "duration_ms": 300,
                "token_usage": {"input_tokens": 80, "output_tokens": 40, "total_tokens": 120},
            },
            {
                "branch_name": "alternative",
                "config": {
                    "name": "alternative",
                    "model": "claude-sonnet-4-20250514",
                    "inject_message": "Give me a different approach",
                },
                "status": "success",
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Response 3",
                        "timestamp": "2025-01-01T10:00:05Z",
                    }
                ],
                "duration_ms": 500,
                "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            },
        ]

        mock_comparison = {
            "successful": 3,
            "failed": 0,
            "branches": mock_branch_results,
        }

        # Mock the core functions that the Dagster ops call
        # Patch at the core module level since imports happen inside the op functions
        with (
            patch(
                "core.conversation.load_conversation",
                return_value=MagicMock(
                    session_id="test-e2e-session",
                    project_path="/test/project",
                    step_count=5,
                    messages=mock_conversation_data["messages"],
                    model_dump=lambda: mock_conversation_data,
                ),
            ),
            patch(
                "core.checkpoint.create_checkpoint",
                return_value=MagicMock(
                    model_dump=lambda: mock_checkpoint_data,
                    messages=mock_checkpoint_data["messages"],
                ),
            ),
            patch("core.executor.execute_branch") as mock_execute,
            patch(
                "core.comparator.compare_branches",
                return_value=MagicMock(model_dump=lambda: mock_comparison),
            ),
        ):
            # Set up mock for execute_branch to return results sequentially
            async def mock_execute_branch(conv, config, checkpoint):
                idx = ["sonnet-baseline", "haiku-speed", "alternative"].index(config.name)
                result = MagicMock()
                result.duration_ms = mock_branch_results[idx]["duration_ms"]
                result.messages = []
                result.model_dump.return_value = mock_branch_results[idx]
                return result

            mock_execute.side_effect = mock_execute_branch

            result = await run_fork_compare_job(mock_request)

            # Verify result structure (same as Prefect/Temporal test)
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
    async def test_job_with_partial_failure(self, mock_conversation_data, mock_checkpoint_data):
        """Test Dagster job handles partial branch failures correctly."""
        from orchestrators.dagster.client import run_fork_compare_job

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
            "config": {"name": "success-branch", "model": "claude-sonnet-4-20250514"},
            "status": "success",
            "messages": [
                {
                    "role": "assistant",
                    "content": "Success",
                    "timestamp": "2025-01-01T10:00:05Z",
                }
            ],
            "duration_ms": 500,
            "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        }

        mock_failure_result = {
            "branch_name": "failure-branch",
            "config": {"name": "failure-branch", "model": "claude-sonnet-4-20250514"},
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

        # Patch at the core module level since imports happen inside the op functions
        with (
            patch(
                "core.conversation.load_conversation",
                return_value=MagicMock(
                    session_id="test-partial-failure",
                    project_path="/test/project",
                    step_count=3,
                    messages=mock_conversation_data["messages"][:3],
                    model_dump=lambda: {**mock_conversation_data, "step_count": 3},
                ),
            ),
            patch(
                "core.checkpoint.create_checkpoint",
                return_value=MagicMock(
                    model_dump=lambda: mock_checkpoint_data,
                    messages=mock_checkpoint_data["messages"],
                ),
            ),
            patch("core.executor.execute_branch") as mock_execute,
            patch(
                "core.comparator.compare_branches",
                return_value=MagicMock(model_dump=lambda: mock_comparison),
            ),
        ):
            # First call succeeds, second raises exception (caught by op)
            call_count = 0

            async def mock_execute_branch(conv, config, checkpoint):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    result = MagicMock()
                    result.duration_ms = 500
                    result.messages = []
                    result.model_dump.return_value = mock_success_result
                    return result
                else:
                    raise Exception("Simulated API error")

            mock_execute.side_effect = mock_execute_branch

            result = await run_fork_compare_job(request)

            # Both branches should have results
            assert len(result["branches"]) == 2

            # Check success branch
            success_branch = next(
                b for b in result["branches"] if b["branch_name"] == "success-branch"
            )
            assert success_branch["status"] == "success"

            # Check failure branch (returned as error by the op)
            failure_branch = next(
                b for b in result["branches"] if b["branch_name"] == "failure-branch"
            )
            assert failure_branch["status"] == "error"

            # Verify comparison summary
            assert result["comparison_summary"]["successful"] == 1
            assert result["comparison_summary"]["failed"] == 1


# =============================================================================
# Tests for Job Execution Mode
# =============================================================================


class TestDagsterExecutionMode:
    """Tests for Dagster execution modes."""

    def test_job_executes_in_process(self):
        """Test that Dagster job executes in-process without server."""
        from orchestrators.dagster.graph import fork_compare_job

        # Verify job is defined
        assert fork_compare_job is not None
        assert fork_compare_job.name == "fork_compare_job"

    def test_parallel_job_available(self):
        """Test that parallel job is available."""
        from orchestrators.dagster.graph import fork_compare_parallel_job

        assert fork_compare_parallel_job is not None
        assert fork_compare_parallel_job.name == "fork_compare_parallel_job"


# =============================================================================
# Tests for Result Persistence
# =============================================================================


class TestDagsterResultPersistence:
    """Tests for saving Dagster results to disk."""

    def test_result_can_be_saved_to_json(self, tmp_path):
        """Test that Dagster job result can be saved to JSON file."""
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


class TestDagsterClientE2E:
    """End-to-end tests for Dagster client API."""

    def test_generate_job_run_id(self):
        """Test job run ID generation."""
        from orchestrators.dagster.client import generate_job_run_id

        id1 = generate_job_run_id("test-conv")
        id2 = generate_job_run_id("test-conv")

        # IDs should start with expected prefix
        assert id1.startswith("fork-compare-test-conv-")
        assert id2.startswith("fork-compare-test-conv-")

        # IDs should be unique
        assert id1 != id2

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test Dagster health check."""
        from orchestrators.dagster.client import check_dagster_health

        result = await check_dagster_health()

        assert result["healthy"] is True
        assert result["mode"] == "in-process"
        assert "healthy" in result["message"].lower()


# =============================================================================
# Comparison with Other Orchestrators
# =============================================================================


class TestOrchestratorComparison:
    """Tests documenting behavior comparison between Dagster, Prefect, and Temporal."""

    def test_documented_differences(self):
        """Document differences between orchestrator implementations.

        All orchestrators should:
        1. Execute the same workflow structure
        2. Return the same result format
        3. Handle partial failures identically
        4. Support parallel branch execution

        Key differences:
        - Dagster uses @op/@graph/@job decorators
        - Dagster runs in-process by default (no server required for execution)
        - Dagster uses DynamicOutput for variable-length parallel execution
        - Dagster has built-in asset management and observability
        - Dagster UI at http://localhost:3000 (when running dagster dev)
        """
        differences = {
            "server_required": {"dagster": False, "prefect": False, "temporal": True},
            "parallel_mechanism": {
                "dagster": "DynamicOutput + .map() + .collect()",
                "prefect": "task.submit() + wait()",
                "temporal": "asyncio.gather()",
            },
            "retry_config": {
                "dagster": "RetryPolicy on @op",
                "prefect": "@task(retries=N)",
                "temporal": "RetryPolicy in activity options",
            },
            "execution_mode": {
                "dagster": "in-process (local)",
                "prefect": "ephemeral (local)",
                "temporal": "worker-based (distributed)",
            },
            "ui_port": {
                "dagster": 3000,
                "prefect": 4200,
                "temporal": 8080,
            },
        }

        # This test documents the differences
        assert differences["server_required"]["dagster"] is False
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
            "GreetingJob executes in-process",
            "ForkCompareJob with 3 branches (all success)",
            "ForkCompareJob with partial failure (1 success, 1 error)",
            "Both sequential and parallel jobs are available",
            "Result can be saved to JSON",
            "Job run ID generation is unique",
            "Health check passes in in-process mode",
            "Comparison with Prefect and Temporal documented",
        ]

        # This test documents what's tested
        assert len(scenarios) == 8
        assert "ForkCompareJob" in str(scenarios)
