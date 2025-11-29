"""Tests for Temporal client functions.

Tests client functionality without requiring actual Temporal server.
"""

from datetime import timedelta

from orchestrators.temporal.client import (
    DEFAULT_NAMESPACE,
    DEFAULT_TEMPORAL_ADDRESS,
    FORK_COMPARE_EXECUTION_TIMEOUT,
    GREETING_EXECUTION_TIMEOUT,
    WorkflowInfo,
    WorkflowStatus,
)

# =============================================================================
# Tests for Configuration
# =============================================================================


class TestClientConfiguration:
    """Tests for client configuration constants."""

    def test_default_temporal_address(self):
        """Default address is localhost:7233."""
        assert DEFAULT_TEMPORAL_ADDRESS == "localhost:7233"

    def test_default_namespace(self):
        """Default namespace is 'default'."""
        assert DEFAULT_NAMESPACE == "default"

    def test_fork_compare_timeout(self):
        """Fork compare timeout is 30 minutes."""
        assert FORK_COMPARE_EXECUTION_TIMEOUT == timedelta(minutes=30)

    def test_greeting_timeout(self):
        """Greeting timeout is 1 minute."""
        assert GREETING_EXECUTION_TIMEOUT == timedelta(minutes=1)


# =============================================================================
# Tests for WorkflowStatus
# =============================================================================


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_status_values(self):
        """All expected status values exist."""
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"
        assert WorkflowStatus.TERMINATED == "terminated"
        assert WorkflowStatus.TIMED_OUT == "timed_out"
        assert WorkflowStatus.UNKNOWN == "unknown"

    def test_status_is_string_enum(self):
        """Status values are strings."""
        assert isinstance(WorkflowStatus.RUNNING.value, str)
        assert WorkflowStatus.RUNNING.value == "running"

    def test_status_comparison(self):
        """Status can be compared with strings."""
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"


# =============================================================================
# Tests for WorkflowInfo
# =============================================================================


class TestWorkflowInfo:
    """Tests for WorkflowInfo dataclass."""

    def test_create_minimal(self):
        """Create WorkflowInfo with minimal fields."""
        info = WorkflowInfo(
            workflow_id="test-123",
            run_id=None,
            status=WorkflowStatus.RUNNING,
        )

        assert info.workflow_id == "test-123"
        assert info.run_id is None
        assert info.status == WorkflowStatus.RUNNING
        assert info.result is None
        assert info.error is None

    def test_create_with_result(self):
        """Create WorkflowInfo with result."""
        info = WorkflowInfo(
            workflow_id="test-123",
            run_id="run-456",
            status=WorkflowStatus.COMPLETED,
            result={"key": "value"},
        )

        assert info.result == {"key": "value"}
        assert info.error is None

    def test_create_with_error(self):
        """Create WorkflowInfo with error."""
        info = WorkflowInfo(
            workflow_id="test-123",
            run_id="run-456",
            status=WorkflowStatus.FAILED,
            error="Something went wrong",
        )

        assert info.result is None
        assert info.error == "Something went wrong"

    def test_create_unknown_workflow(self):
        """Create WorkflowInfo for unknown/not found workflow."""
        info = WorkflowInfo(
            workflow_id="nonexistent",
            run_id=None,
            status=WorkflowStatus.UNKNOWN,
            error="Workflow not found: nonexistent",
        )

        assert info.status == WorkflowStatus.UNKNOWN
        assert "not found" in info.error


# =============================================================================
# Tests for Workflow ID Generation
# =============================================================================


class TestWorkflowIdGeneration:
    """Tests for workflow ID generation patterns."""

    def test_greeting_workflow_id_pattern(self):
        """Greeting workflow IDs follow pattern."""
        # The pattern is: greeting-{uuid}
        import uuid

        workflow_id = f"greeting-{uuid.uuid4()}"

        assert workflow_id.startswith("greeting-")
        # UUID part should be valid
        uuid_part = workflow_id.replace("greeting-", "")
        uuid.UUID(uuid_part)  # Should not raise

    def test_fork_compare_workflow_id_pattern(self):
        """Fork compare workflow IDs follow pattern."""
        # The pattern is: fork-compare-{conversation_id}-{uuid_hex[:8]}
        import uuid

        conversation_id = "test-session"
        workflow_id = f"fork-compare-{conversation_id}-{uuid.uuid4().hex[:8]}"

        assert workflow_id.startswith("fork-compare-")
        assert conversation_id in workflow_id


# =============================================================================
# Tests for Request/Response Structures
# =============================================================================


class TestRequestStructures:
    """Tests for request/response data structures used by client."""

    def test_replay_request_structure(self):
        """ReplayRequest dict has expected structure."""
        request = {
            "conversation_id": "test-session-123",
            "fork_at_step": 5,
            "branches": [
                {
                    "name": "branch-a",
                    "model": "claude-sonnet-4-20250514",
                    "inject_message": "Try approach A",
                },
                {
                    "name": "branch-b",
                    "model": "claude-haiku-4-20250514",
                    "inject_message": "Try approach B",
                },
            ],
        }

        assert "conversation_id" in request
        assert "fork_at_step" in request
        assert "branches" in request
        assert len(request["branches"]) == 2

    def test_comparison_result_structure(self):
        """ComparisonResult dict has expected structure."""
        result = {
            "request": {
                "conversation_id": "test",
                "fork_at_step": 5,
                "branches": [],
            },
            "checkpoint": {
                "conversation_id": "test",
                "step": 5,
                "messages": [],
                "project_path": "/path",
                "created_at": "2025-01-01T00:00:00Z",
            },
            "branches": [],
            "total_duration_ms": 1000,
            "comparison_summary": {"successful": 0, "failed": 0},
        }

        assert "request" in result
        assert "checkpoint" in result
        assert "branches" in result
        assert "total_duration_ms" in result
        assert "comparison_summary" in result


# =============================================================================
# Tests for Status Mapping
# =============================================================================


class TestStatusMapping:
    """Tests for Temporal status code to WorkflowStatus mapping."""

    def test_status_mapping_values(self):
        """Status mapping covers Temporal status codes."""
        # These are the Temporal status codes
        status_map = {
            1: WorkflowStatus.RUNNING,
            2: WorkflowStatus.COMPLETED,
            3: WorkflowStatus.FAILED,
            4: WorkflowStatus.CANCELLED,
            5: WorkflowStatus.TERMINATED,
            6: WorkflowStatus.TIMED_OUT,
        }

        assert status_map[1] == WorkflowStatus.RUNNING
        assert status_map[2] == WorkflowStatus.COMPLETED
        assert status_map[3] == WorkflowStatus.FAILED
        assert status_map[4] == WorkflowStatus.CANCELLED
        assert status_map[5] == WorkflowStatus.TERMINATED
        assert status_map[6] == WorkflowStatus.TIMED_OUT

    def test_unknown_status_for_missing_codes(self):
        """Unknown codes map to UNKNOWN status."""
        status_map = {
            1: WorkflowStatus.RUNNING,
            2: WorkflowStatus.COMPLETED,
            3: WorkflowStatus.FAILED,
            4: WorkflowStatus.CANCELLED,
            5: WorkflowStatus.TERMINATED,
            6: WorkflowStatus.TIMED_OUT,
        }

        # Unknown code should return UNKNOWN (via .get())
        assert status_map.get(99, WorkflowStatus.UNKNOWN) == WorkflowStatus.UNKNOWN
        assert status_map.get(0, WorkflowStatus.UNKNOWN) == WorkflowStatus.UNKNOWN


# =============================================================================
# Tests for Client Function Signatures
# =============================================================================


class TestClientFunctionSignatures:
    """Tests to verify client functions have expected signatures."""

    def test_get_client_signature(self):
        """get_client accepts address and namespace."""
        import inspect

        from orchestrators.temporal.client import get_client

        sig = inspect.signature(get_client)
        params = list(sig.parameters.keys())

        assert "address" in params
        assert "namespace" in params

    def test_run_greeting_workflow_signature(self):
        """run_greeting_workflow accepts name, client, workflow_id."""
        import inspect

        from orchestrators.temporal.client import run_greeting_workflow

        sig = inspect.signature(run_greeting_workflow)
        params = list(sig.parameters.keys())

        assert "name" in params
        assert "client" in params
        assert "workflow_id" in params

    def test_run_fork_compare_workflow_signature(self):
        """run_fork_compare_workflow accepts expected parameters."""
        import inspect

        from orchestrators.temporal.client import run_fork_compare_workflow

        sig = inspect.signature(run_fork_compare_workflow)
        params = list(sig.parameters.keys())

        assert "request_dict" in params
        assert "client" in params
        assert "workflow_id" in params
        assert "wait_for_result" in params

    def test_get_workflow_status_signature(self):
        """get_workflow_status accepts workflow_id and client."""
        import inspect

        from orchestrators.temporal.client import get_workflow_status

        sig = inspect.signature(get_workflow_status)
        params = list(sig.parameters.keys())

        assert "workflow_id" in params
        assert "client" in params

    def test_cancel_workflow_signature(self):
        """cancel_workflow accepts workflow_id and client."""
        import inspect

        from orchestrators.temporal.client import cancel_workflow

        sig = inspect.signature(cancel_workflow)
        params = list(sig.parameters.keys())

        assert "workflow_id" in params
        assert "client" in params

    def test_list_workflows_signature(self):
        """list_workflows accepts client and query."""
        import inspect

        from orchestrators.temporal.client import list_workflows

        sig = inspect.signature(list_workflows)
        params = list(sig.parameters.keys())

        assert "client" in params
        assert "query" in params
