"""Tests for Prefect client module.

Tests verify:
- FlowRunStatus enum values
- FlowRunInfo dataclass
- Flow run ID generation
- Client function signatures
- Health check functionality
"""

from unittest.mock import AsyncMock, patch

import pytest

# =============================================================================
# Tests for FlowRunStatus Enum
# =============================================================================


class TestFlowRunStatus:
    """Tests for FlowRunStatus enum."""

    def test_pending_status(self):
        """FlowRunStatus has pending value."""
        from orchestrators.prefect.client import FlowRunStatus

        assert FlowRunStatus.PENDING == "pending"

    def test_running_status(self):
        """FlowRunStatus has running value."""
        from orchestrators.prefect.client import FlowRunStatus

        assert FlowRunStatus.RUNNING == "running"

    def test_completed_status(self):
        """FlowRunStatus has completed value."""
        from orchestrators.prefect.client import FlowRunStatus

        assert FlowRunStatus.COMPLETED == "completed"

    def test_failed_status(self):
        """FlowRunStatus has failed value."""
        from orchestrators.prefect.client import FlowRunStatus

        assert FlowRunStatus.FAILED == "failed"

    def test_cancelled_status(self):
        """FlowRunStatus has cancelled value."""
        from orchestrators.prefect.client import FlowRunStatus

        assert FlowRunStatus.CANCELLED == "cancelled"


# =============================================================================
# Tests for FlowRunInfo Dataclass
# =============================================================================


class TestFlowRunInfo:
    """Tests for FlowRunInfo dataclass."""

    def test_create_flow_run_info(self):
        """FlowRunInfo can be created with required fields."""
        from orchestrators.prefect.client import FlowRunInfo, FlowRunStatus

        info = FlowRunInfo(
            flow_run_id="test-id",
            flow_name="test-flow",
            status=FlowRunStatus.RUNNING,
        )

        assert info.flow_run_id == "test-id"
        assert info.flow_name == "test-flow"
        assert info.status == FlowRunStatus.RUNNING
        assert info.result is None
        assert info.error is None

    def test_create_flow_run_info_with_result(self):
        """FlowRunInfo can be created with result."""
        from orchestrators.prefect.client import FlowRunInfo, FlowRunStatus

        info = FlowRunInfo(
            flow_run_id="test-id",
            flow_name="test-flow",
            status=FlowRunStatus.COMPLETED,
            result={"data": "test"},
        )

        assert info.result == {"data": "test"}

    def test_create_flow_run_info_with_error(self):
        """FlowRunInfo can be created with error."""
        from orchestrators.prefect.client import FlowRunInfo, FlowRunStatus

        info = FlowRunInfo(
            flow_run_id="test-id",
            flow_name="test-flow",
            status=FlowRunStatus.FAILED,
            error="Something went wrong",
        )

        assert info.error == "Something went wrong"


# =============================================================================
# Tests for Flow Run ID Generation
# =============================================================================


class TestGenerateFlowRunId:
    """Tests for generate_flow_run_id function."""

    def test_generate_flow_run_id_format(self):
        """generate_flow_run_id returns expected format."""
        from orchestrators.prefect.client import generate_flow_run_id

        result = generate_flow_run_id("test-conv")

        assert result.startswith("fork-compare-test-conv-")
        # Should have 8 hex chars at the end
        suffix = result.split("-")[-1]
        assert len(suffix) == 8
        # Should be valid hex
        int(suffix, 16)

    def test_generate_flow_run_id_unique(self):
        """generate_flow_run_id returns unique IDs."""
        from orchestrators.prefect.client import generate_flow_run_id

        id1 = generate_flow_run_id("test-conv")
        id2 = generate_flow_run_id("test-conv")

        assert id1 != id2


# =============================================================================
# Tests for run_fork_compare_flow
# =============================================================================


class TestRunForkCompareFlow:
    """Tests for run_fork_compare_flow function."""

    def test_run_fork_compare_flow_is_async(self):
        """run_fork_compare_flow is async."""
        import inspect

        from orchestrators.prefect.client import run_fork_compare_flow

        assert inspect.iscoroutinefunction(run_fork_compare_flow)

    @pytest.mark.asyncio
    async def test_run_fork_compare_flow_calls_flow(self):
        """run_fork_compare_flow calls ForkCompareFlow."""
        from orchestrators.prefect.client import run_fork_compare_flow

        mock_result = {"branches": [], "total_duration_ms": 100}
        mock_request = {"conversation_id": "test", "fork_at_step": 1, "branches": []}

        # ForkCompareFlow is an async flow, so mock must return awaitable
        mock_flow = AsyncMock(return_value=mock_result)
        with patch(
            "orchestrators.prefect.client.ForkCompareFlow",
            mock_flow,
        ):
            result = await run_fork_compare_flow(mock_request)

            mock_flow.assert_called_once_with(mock_request)
            assert result == mock_result


# =============================================================================
# Tests for run_greeting_flow_async
# =============================================================================


class TestRunGreetingFlowAsync:
    """Tests for run_greeting_flow_async function."""

    def test_run_greeting_flow_async_is_async(self):
        """run_greeting_flow_async is async."""
        import inspect

        from orchestrators.prefect.client import run_greeting_flow_async

        assert inspect.iscoroutinefunction(run_greeting_flow_async)


# =============================================================================
# Tests for get_flow_run_status
# =============================================================================


class TestGetFlowRunStatus:
    """Tests for get_flow_run_status function."""

    def test_get_flow_run_status_is_async(self):
        """get_flow_run_status is async."""
        import inspect

        from orchestrators.prefect.client import get_flow_run_status

        assert inspect.iscoroutinefunction(get_flow_run_status)

    @pytest.mark.asyncio
    async def test_get_flow_run_status_returns_info(self):
        """get_flow_run_status returns FlowRunInfo."""
        from orchestrators.prefect.client import FlowRunInfo, FlowRunStatus, get_flow_run_status

        result = await get_flow_run_status("test-id")

        assert isinstance(result, FlowRunInfo)
        assert result.flow_run_id == "test-id"
        # In ephemeral mode, always returns completed with error message
        assert result.status == FlowRunStatus.COMPLETED


# =============================================================================
# Tests for check_prefect_health
# =============================================================================


class TestCheckPrefectHealth:
    """Tests for check_prefect_health function."""

    def test_check_prefect_health_is_async(self):
        """check_prefect_health is async."""
        import inspect

        from orchestrators.prefect.client import check_prefect_health

        assert inspect.iscoroutinefunction(check_prefect_health)

    @pytest.mark.asyncio
    async def test_check_prefect_health_success(self):
        """check_prefect_health returns healthy status on success."""
        from orchestrators.prefect.client import check_prefect_health

        with patch(
            "orchestrators.prefect.client.run_greeting_flow",
            return_value="Hello, health-check!",
        ):
            result = await check_prefect_health()

            assert result["healthy"] is True
            assert result["mode"] == "ephemeral"
            assert "healthy" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_check_prefect_health_failure(self):
        """check_prefect_health returns unhealthy status on failure."""
        from orchestrators.prefect.client import check_prefect_health

        with patch(
            "orchestrators.prefect.client.run_greeting_flow",
            side_effect=RuntimeError("Prefect error"),
        ):
            result = await check_prefect_health()

            assert result["healthy"] is False
            assert "failed" in result["message"].lower()


# =============================================================================
# Tests for Module Exports
# =============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_exports_flow_run_status(self):
        """Module exports FlowRunStatus."""
        from orchestrators.prefect import FlowRunStatus

        assert FlowRunStatus is not None

    def test_exports_flow_run_info(self):
        """Module exports FlowRunInfo."""
        from orchestrators.prefect import FlowRunInfo

        assert FlowRunInfo is not None

    def test_exports_generate_flow_run_id(self):
        """Module exports generate_flow_run_id."""
        from orchestrators.prefect import generate_flow_run_id

        assert callable(generate_flow_run_id)

    def test_exports_check_prefect_health(self):
        """Module exports check_prefect_health."""
        from orchestrators.prefect import check_prefect_health

        assert callable(check_prefect_health)
