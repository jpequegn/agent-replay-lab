"""Tests for CLI commands.

Tests CLI functionality without requiring actual Temporal server or conversations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli.main import _display_results, app

runner = CliRunner()


# =============================================================================
# Tests for Run Command Validation
# =============================================================================


class TestRunCommandValidation:
    """Tests for run command argument validation."""

    def test_run_missing_conversation(self, tmp_path):
        """Run command requires --conversation."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--fork-at",
                "5",
                "--orchestrator",
                "temporal",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--conversation" in result.output

    def test_run_missing_fork_at(self, tmp_path):
        """Run command requires --fork-at."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--orchestrator",
                "temporal",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--fork-at" in result.output

    def test_run_missing_orchestrator(self, tmp_path):
        """Run command requires --orchestrator."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--orchestrator" in result.output

    def test_run_missing_config(self):
        """Run command requires --config."""
        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "temporal",
            ],
        )

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--config" in result.output


# =============================================================================
# Tests for Configuration Handling
# =============================================================================


class TestRunConfigHandling:
    """Tests for run command configuration handling."""

    def test_run_config_file_not_found(self):
        """Run command fails gracefully when config file not found."""
        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "temporal",
                "--config",
                "/nonexistent/config.yaml",
            ],
        )

        assert result.exit_code == 1
        assert "Configuration error" in result.output or "not found" in result.output

    def test_run_invalid_yaml(self, tmp_path):
        """Run command fails gracefully with invalid YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: syntax: [")

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "temporal",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "Configuration error" in result.output

    def test_run_missing_branches(self, tmp_path):
        """Run command fails when config has no branches."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
settings:
  max_turns: 10
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "temporal",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "Configuration error" in result.output or "branches" in result.output


# =============================================================================
# Tests for Orchestrator Dispatch
# =============================================================================


class TestOrchestratorDispatch:
    """Tests for orchestrator dispatch logic."""

    def test_unknown_orchestrator(self, tmp_path):
        """Unknown orchestrator returns error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "unknown",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "Unknown orchestrator" in result.output

    def test_prefect_not_implemented(self, tmp_path):
        """Prefect orchestrator shows not implemented message."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "prefect",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "not yet implemented" in result.output

    def test_dagster_not_implemented(self, tmp_path):
        """Dagster orchestrator shows not implemented message."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
branches:
  - name: test
    model: claude-sonnet-4-20250514
"""
        )

        result = runner.invoke(
            app,
            [
                "run",
                "--conversation",
                "test-123",
                "--fork-at",
                "5",
                "--orchestrator",
                "dagster",
                "--config",
                str(config_file),
            ],
        )

        assert result.exit_code == 1
        assert "not yet implemented" in result.output


# =============================================================================
# Tests for Display Results
# =============================================================================


class TestDisplayResults:
    """Tests for _display_results function."""

    def test_display_results_basic(self, capsys):
        """Display results shows summary panel."""
        result = {
            "total_duration_ms": 1000,
            "branches": [
                {
                    "branch_name": "branch-a",
                    "status": "success",
                    "duration_ms": 500,
                    "messages": [],
                    "token_usage": {"total_tokens": 100},
                },
            ],
            "comparison_summary": {"successful": 1, "failed": 0},
        }

        _display_results(result)

        # Results should be displayed (function uses console.print)
        # We can't easily capture Rich output in tests, but we verify no errors

    def test_display_results_with_errors(self, capsys):
        """Display results shows errors section."""
        result = {
            "total_duration_ms": 1000,
            "branches": [
                {
                    "branch_name": "branch-a",
                    "status": "error",
                    "duration_ms": 500,
                    "messages": [],
                    "error": "Test error message",
                },
            ],
            "comparison_summary": {"successful": 0, "failed": 1},
        }

        _display_results(result)

        # No exception = success

    def test_display_results_multiple_branches(self):
        """Display results handles multiple branches."""
        result = {
            "total_duration_ms": 2000,
            "branches": [
                {
                    "branch_name": "branch-a",
                    "status": "success",
                    "duration_ms": 1000,
                    "messages": [{"role": "assistant", "content": "hello"}],
                    "token_usage": {"total_tokens": 100},
                },
                {
                    "branch_name": "branch-b",
                    "status": "timeout",
                    "duration_ms": 1000,
                    "messages": [],
                    "token_usage": None,
                },
            ],
            "comparison_summary": {"successful": 1, "failed": 1},
        }

        _display_results(result)

        # No exception = success

    def test_display_results_empty_branches(self):
        """Display results handles empty branches list."""
        result = {
            "total_duration_ms": 0,
            "branches": [],
            "comparison_summary": None,
        }

        _display_results(result)

        # No exception = success


# =============================================================================
# Tests for Temporal Workflow Runner
# =============================================================================


class TestTemporalWorkflowRunner:
    """Tests for _run_temporal_workflow function."""

    @pytest.mark.asyncio
    async def test_run_temporal_workflow_connection_error(self, tmp_path):
        """Workflow runner handles connection errors."""
        from core.models import ForkConfig, ReplayRequest

        request = ReplayRequest(
            conversation_id="test-123",
            fork_at_step=5,
            branches=[
                ForkConfig(name="test", model="claude-sonnet-4-20250514"),
            ],
        )

        # Mock get_client at the source module to raise connection error
        with patch(
            "orchestrators.temporal.client.get_client",
            side_effect=ConnectionRefusedError(),
        ):
            from cli.main import _run_temporal_workflow

            with pytest.raises(ConnectionRefusedError):
                await _run_temporal_workflow(request, tmp_path / "output")

    @pytest.mark.asyncio
    async def test_run_temporal_workflow_success(self, tmp_path):
        """Workflow runner completes successfully."""
        from core.models import ForkConfig, ReplayRequest
        from orchestrators.temporal.client import WorkflowStatus

        request = ReplayRequest(
            conversation_id="test-123",
            fork_at_step=5,
            branches=[
                ForkConfig(name="test", model="claude-sonnet-4-20250514"),
            ],
        )

        # Mock Temporal client and workflow
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_handle.id = "test-workflow-id"
        mock_handle.result = AsyncMock(
            return_value={
                "total_duration_ms": 1000,
                "branches": [],
                "comparison_summary": {"successful": 0, "failed": 0},
            }
        )

        # Mock workflow status to return COMPLETED
        mock_info = MagicMock()
        mock_info.status = WorkflowStatus.COMPLETED

        with (
            patch(
                "orchestrators.temporal.client.get_client",
                new_callable=AsyncMock,
                return_value=mock_client,
            ),
            patch(
                "orchestrators.temporal.client.start_fork_compare_workflow",
                new_callable=AsyncMock,
                return_value=mock_handle,
            ),
            patch(
                "orchestrators.temporal.client.get_workflow_status",
                new_callable=AsyncMock,
                return_value=mock_info,
            ),
        ):
            from cli.main import _run_temporal_workflow

            result = await _run_temporal_workflow(request, tmp_path / "output")

            assert result is not None
            # Verify output file was created
            output_files = list((tmp_path / "output").glob("result-*.json"))
            assert len(output_files) == 1


# =============================================================================
# Tests for Other Commands
# =============================================================================


class TestListCommand:
    """Tests for list command."""

    def test_list_command_exists(self):
        """List command is registered."""
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        assert "List available conversations" in result.output


class TestInspectCommand:
    """Tests for inspect command."""

    def test_inspect_command_exists(self):
        """Inspect command is registered."""
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Inspect a conversation" in result.output


class TestCompareCommand:
    """Tests for compare command."""

    def test_compare_command_exists(self):
        """Compare command is registered."""
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0


class TestStatusCommand:
    """Tests for status command."""

    def test_status_command_exists(self):
        """Status command is registered."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "Check orchestrator health" in result.output
