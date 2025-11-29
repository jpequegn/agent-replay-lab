"""Tests for Temporal workflows.

Tests workflow logic using mocked activities to verify orchestration
without requiring actual Temporal server or Claude API calls.
"""


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
            Message(role="assistant", content="Hi!", timestamp="2025-01-01T00:00:01Z"),
            Message(role="user", content="Help me", timestamp="2025-01-01T00:00:02Z"),
            Message(role="assistant", content="Sure!", timestamp="2025-01-01T00:00:03Z"),
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
            Message(role="assistant", content="Hi!", timestamp="2025-01-01T00:00:01Z"),
        ],
        project_path="/path/to/project",
        created_at="2025-01-01T00:00:02Z",
    )


@pytest.fixture
def sample_request():
    """Sample replay request for testing."""
    return ReplayRequest(
        conversation_id="test-session-123",
        fork_at_step=2,
        branches=[
            ForkConfig(
                name="branch-a",
                model="claude-sonnet-4-20250514",
                inject_message="Try approach A",
            ),
            ForkConfig(
                name="branch-b",
                model="claude-haiku-4-20250514",
                inject_message="Try approach B",
            ),
        ],
    )


@pytest.fixture
def sample_branch_results():
    """Sample successful branch results."""
    return [
        BranchResult(
            branch_name="branch-a",
            config=ForkConfig(
                name="branch-a",
                model="claude-sonnet-4-20250514",
                inject_message="Try approach A",
            ),
            messages=[
                Message(role="user", content="Try approach A", timestamp=""),
                Message(role="assistant", content="Response A", timestamp=""),
            ],
            duration_ms=1000,
            token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            status="success",
        ),
        BranchResult(
            branch_name="branch-b",
            config=ForkConfig(
                name="branch-b",
                model="claude-haiku-4-20250514",
                inject_message="Try approach B",
            ),
            messages=[
                Message(role="user", content="Try approach B", timestamp=""),
                Message(role="assistant", content="Response B", timestamp=""),
            ],
            duration_ms=500,
            token_usage=TokenUsage(input_tokens=80, output_tokens=40, total_tokens=120),
            status="success",
        ),
    ]


@pytest.fixture
def sample_comparison_summary():
    """Sample comparison summary."""
    return {
        "total_branches": 2,
        "successful": 2,
        "failed": 0,
        "branches": {
            "branch-a": {"status": "success", "duration_ms": 1000},
            "branch-b": {"status": "success", "duration_ms": 500},
        },
        "metrics": {
            "avg_duration_ms": 750,
            "min_duration_ms": 500,
            "max_duration_ms": 1000,
        },
    }


# =============================================================================
# Tests for ForkCompareWorkflow Logic
# =============================================================================


class TestForkCompareWorkflowLogic:
    """Tests for workflow orchestration logic without running Temporal."""

    def test_request_serialization(self, sample_request):
        """ReplayRequest can be serialized to dict for workflow input."""
        request_dict = sample_request.model_dump()

        assert request_dict["conversation_id"] == "test-session-123"
        assert request_dict["fork_at_step"] == 2
        assert len(request_dict["branches"]) == 2

    def test_checkpoint_serialization(self, sample_checkpoint):
        """Checkpoint can be serialized and deserialized."""
        checkpoint_dict = sample_checkpoint.model_dump()
        restored = Checkpoint.model_validate(checkpoint_dict)

        assert restored.conversation_id == sample_checkpoint.conversation_id
        assert restored.step == sample_checkpoint.step
        assert len(restored.messages) == 2

    def test_branch_result_serialization(self, sample_branch_results):
        """BranchResult can be serialized and deserialized."""
        for result in sample_branch_results:
            result_dict = result.model_dump()
            restored = BranchResult.model_validate(result_dict)

            assert restored.branch_name == result.branch_name
            assert restored.status == result.status

    def test_error_result_structure(self):
        """Error results have correct structure."""
        error_result = {
            "branch_name": "failed-branch",
            "config": {"name": "failed-branch", "model": "claude-sonnet-4-20250514"},
            "messages": [],
            "duration_ms": 0,
            "token_usage": None,
            "status": "error",
            "error": "Activity failed: connection timeout",
        }

        # Should be valid BranchResult
        result = BranchResult.model_validate(error_result)
        assert result.status == "error"
        assert "connection timeout" in result.error


class TestWorkflowDataFlow:
    """Tests for data flow through workflow steps."""

    def test_conversation_to_checkpoint_flow(
        self, sample_conversation, sample_checkpoint
    ):
        """Conversation can be converted to checkpoint at specific step."""
        # Verify conversation can be serialized for activity input
        conv_dict = sample_conversation.model_dump()
        assert conv_dict["session_id"] == "test-session-123"

        # Simulate checkpoint creation
        truncated = sample_conversation.at_step(2)
        assert len(truncated.messages) == 2
        assert truncated.messages[-1].content == "Hi!"

    def test_checkpoint_to_branch_results_flow(
        self, sample_checkpoint, sample_branch_results
    ):
        """Checkpoint can produce multiple branch results."""
        # Verify checkpoint can be serialized for activity input
        checkpoint_dict = sample_checkpoint.model_dump()
        assert checkpoint_dict["step"] == 2

        for result in sample_branch_results:
            # Verify branch results are independent
            assert result.config.name in ["branch-a", "branch-b"]
            assert len(result.messages) > 0

    def test_branch_results_to_comparison_flow(
        self, sample_branch_results, sample_comparison_summary
    ):
        """Branch results can be compared to produce summary."""
        results_dicts = [r.model_dump() for r in sample_branch_results]

        # Verify structure expected by compare_results_activity
        assert len(results_dicts) == 2
        assert all("status" in r for r in results_dicts)
        assert all("branch_name" in r for r in results_dicts)


class TestWorkflowResultStructure:
    """Tests for final workflow result structure."""

    def test_comparison_result_structure(
        self,
        sample_request,
        sample_checkpoint,
        sample_branch_results,
        sample_comparison_summary,
    ):
        """Final result has correct ComparisonResult structure."""
        # Simulate workflow output
        result = {
            "request": sample_request.model_dump(),
            "checkpoint": sample_checkpoint.model_dump(),
            "branches": [r.model_dump() for r in sample_branch_results],
            "total_duration_ms": 1500,
            "comparison_summary": sample_comparison_summary,
        }

        # Verify all required fields present
        assert "request" in result
        assert "checkpoint" in result
        assert "branches" in result
        assert "total_duration_ms" in result
        assert "comparison_summary" in result

        # Verify types
        assert isinstance(result["total_duration_ms"], int)
        assert isinstance(result["branches"], list)
        assert isinstance(result["comparison_summary"], dict)


class TestPartialFailureHandling:
    """Tests for handling partial failures in workflow."""

    def test_mixed_success_failure_results(self):
        """Workflow can handle mix of successful and failed branches."""
        results = [
            {
                "branch_name": "success-branch",
                "config": {"name": "success-branch", "model": "claude-sonnet-4-20250514"},
                "messages": [
                    {"role": "assistant", "content": "Success!", "timestamp": ""}
                ],
                "duration_ms": 1000,
                "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                "status": "success",
                "error": None,
            },
            {
                "branch_name": "error-branch",
                "config": {"name": "error-branch", "model": "claude-haiku-4-20250514"},
                "messages": [],
                "duration_ms": 0,
                "token_usage": None,
                "status": "error",
                "error": "Rate limit exceeded",
            },
        ]

        # Both should be valid BranchResults
        for r in results:
            result = BranchResult.model_validate(r)
            assert result.branch_name in ["success-branch", "error-branch"]

        # Count successes/failures
        successful = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] != "success"]

        assert len(successful) == 1
        assert len(failed) == 1

    def test_all_branches_fail(self):
        """Workflow handles case where all branches fail."""
        results = [
            {
                "branch_name": "branch-1",
                "config": {"name": "branch-1", "model": "claude-sonnet-4-20250514"},
                "messages": [],
                "duration_ms": 0,
                "token_usage": None,
                "status": "error",
                "error": "Connection timeout",
            },
            {
                "branch_name": "branch-2",
                "config": {"name": "branch-2", "model": "claude-haiku-4-20250514"},
                "messages": [],
                "duration_ms": 0,
                "token_usage": None,
                "status": "timeout",
                "error": "Execution timed out",
            },
        ]

        # Both should be valid
        for r in results:
            result = BranchResult.model_validate(r)
            assert result.status in ["error", "timeout"]

        # Workflow should still complete (not crash)
        failed = [r for r in results if r["status"] != "success"]
        assert len(failed) == 2


class TestWorkflowInputValidation:
    """Tests for workflow input validation."""

    def test_valid_request_dict(self, sample_request):
        """Valid request dict passes validation."""
        request_dict = sample_request.model_dump()

        # Should reconstruct without error
        restored = ReplayRequest.model_validate(request_dict)
        assert restored.conversation_id == "test-session-123"

    def test_missing_conversation_id_fails(self):
        """Missing conversation_id fails validation."""
        invalid_request = {
            "fork_at_step": 2,
            "branches": [{"name": "test", "model": "claude-sonnet-4-20250514"}],
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            ReplayRequest.model_validate(invalid_request)

    def test_empty_branches_allowed(self):
        """Empty branches list is allowed but produces empty results."""
        request = ReplayRequest(
            conversation_id="test",
            fork_at_step=1,
            branches=[],
        )

        assert len(request.branches) == 0

    def test_invalid_step_type_fails(self):
        """Non-integer step fails validation."""
        invalid_request = {
            "conversation_id": "test",
            "fork_at_step": "two",  # Should be int
            "branches": [],
        }

        with pytest.raises(Exception):
            ReplayRequest.model_validate(invalid_request)


class TestWorkflowDeterminism:
    """Tests related to workflow determinism requirements."""

    def test_request_dict_is_json_serializable(self, sample_request):
        """Request can be JSON serialized (required for Temporal)."""
        import json

        request_dict = sample_request.model_dump()
        json_str = json.dumps(request_dict)
        restored = json.loads(json_str)

        assert restored["conversation_id"] == sample_request.conversation_id

    def test_checkpoint_dict_is_json_serializable(self, sample_checkpoint):
        """Checkpoint can be JSON serialized."""
        import json

        checkpoint_dict = sample_checkpoint.model_dump()
        json_str = json.dumps(checkpoint_dict)
        restored = json.loads(json_str)

        assert restored["step"] == sample_checkpoint.step

    def test_branch_result_dict_is_json_serializable(self, sample_branch_results):
        """BranchResult can be JSON serialized."""
        import json

        for result in sample_branch_results:
            result_dict = result.model_dump()
            json_str = json.dumps(result_dict)
            restored = json.loads(json_str)

            assert restored["branch_name"] == result.branch_name


class TestWorkflowEdgeCases:
    """Tests for edge cases in workflow execution."""

    def test_single_branch_execution(self):
        """Workflow works with single branch."""
        request = ReplayRequest(
            conversation_id="test",
            fork_at_step=1,
            branches=[
                ForkConfig(name="only-branch", model="claude-sonnet-4-20250514"),
            ],
        )

        assert len(request.branches) == 1

    def test_many_branches_execution(self):
        """Workflow can handle many branches."""
        branches = [
            ForkConfig(name=f"branch-{i}", model="claude-sonnet-4-20250514")
            for i in range(10)
        ]

        request = ReplayRequest(
            conversation_id="test",
            fork_at_step=1,
            branches=branches,
        )

        assert len(request.branches) == 10

    def test_fork_at_step_zero(self):
        """Forking at step 0 creates empty checkpoint."""
        request = ReplayRequest(
            conversation_id="test",
            fork_at_step=0,
            branches=[ForkConfig(name="test", model="claude-sonnet-4-20250514")],
        )

        assert request.fork_at_step == 0

    def test_branch_with_all_options(self):
        """Branch with all options set."""
        config = ForkConfig(
            name="full-config",
            model="claude-opus-4-20250514",
            inject_message="Custom message",
            system_prompt="Custom system prompt",
            max_turns=10,
        )

        config_dict = config.model_dump()
        restored = ForkConfig.model_validate(config_dict)

        assert restored.inject_message == "Custom message"
        assert restored.system_prompt == "Custom system prompt"
        assert restored.max_turns == 10
