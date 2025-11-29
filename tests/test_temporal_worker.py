"""Tests for Temporal worker configuration.

Tests worker configuration without requiring actual Temporal server.
"""

import inspect

import pytest

from orchestrators.temporal.worker import (
    ACTIVITIES,
    DEFAULT_NAMESPACE,
    DEFAULT_TEMPORAL_ADDRESS,
    TASK_QUEUE,
    WORKFLOWS,
    WorkerShutdownError,
    create_worker,
    run_worker,
)

# =============================================================================
# Tests for Worker Configuration
# =============================================================================


class TestWorkerConfiguration:
    """Tests for worker configuration constants."""

    def test_task_queue_name(self):
        """Task queue has expected name."""
        assert TASK_QUEUE == "fork-compare-queue"

    def test_default_temporal_address(self):
        """Default address is localhost:7233."""
        assert DEFAULT_TEMPORAL_ADDRESS == "localhost:7233"

    def test_default_namespace(self):
        """Default namespace is 'default'."""
        assert DEFAULT_NAMESPACE == "default"


# =============================================================================
# Tests for Registered Workflows
# =============================================================================


class TestRegisteredWorkflows:
    """Tests for registered workflows."""

    def test_workflows_list_not_empty(self):
        """Workflows list is not empty."""
        assert len(WORKFLOWS) > 0

    def test_greeting_workflow_registered(self):
        """GreetingWorkflow is registered."""
        workflow_names = [w.__name__ for w in WORKFLOWS]
        assert "GreetingWorkflow" in workflow_names

    def test_fork_compare_workflow_registered(self):
        """ForkCompareWorkflow is registered."""
        workflow_names = [w.__name__ for w in WORKFLOWS]
        assert "ForkCompareWorkflow" in workflow_names

    def test_workflows_are_classes(self):
        """All workflows are classes."""
        for workflow in WORKFLOWS:
            assert inspect.isclass(workflow)


# =============================================================================
# Tests for Registered Activities
# =============================================================================


class TestRegisteredActivities:
    """Tests for registered activities."""

    def test_activities_list_not_empty(self):
        """Activities list is not empty."""
        assert len(ACTIVITIES) > 0

    def test_greet_activity_registered(self):
        """greet_activity is registered."""
        activity_names = [a.__name__ for a in ACTIVITIES]
        assert "greet_activity" in activity_names

    def test_load_conversation_activity_registered(self):
        """load_conversation_activity is registered."""
        activity_names = [a.__name__ for a in ACTIVITIES]
        assert "load_conversation_activity" in activity_names

    def test_create_checkpoint_activity_registered(self):
        """create_checkpoint_activity is registered."""
        activity_names = [a.__name__ for a in ACTIVITIES]
        assert "create_checkpoint_activity" in activity_names

    def test_execute_branch_activity_registered(self):
        """execute_branch_activity is registered."""
        activity_names = [a.__name__ for a in ACTIVITIES]
        assert "execute_branch_activity" in activity_names

    def test_compare_results_activity_registered(self):
        """compare_results_activity is registered."""
        activity_names = [a.__name__ for a in ACTIVITIES]
        assert "compare_results_activity" in activity_names

    def test_activities_are_functions(self):
        """All activities are functions."""
        for activity in ACTIVITIES:
            assert callable(activity)


# =============================================================================
# Tests for WorkerShutdown Exception
# =============================================================================


class TestWorkerShutdownError:
    """Tests for WorkerShutdownError exception."""

    def test_worker_shutdown_is_exception(self):
        """WorkerShutdownError is an Exception."""
        assert issubclass(WorkerShutdownError, Exception)

    def test_worker_shutdown_can_be_raised(self):
        """WorkerShutdownError can be raised and caught."""
        with pytest.raises(WorkerShutdownError):
            raise WorkerShutdownError("Test shutdown")

    def test_worker_shutdown_message(self):
        """WorkerShutdownError preserves message."""
        try:
            raise WorkerShutdownError("Shutdown requested")
        except WorkerShutdownError as e:
            assert str(e) == "Shutdown requested"


# =============================================================================
# Tests for Function Signatures
# =============================================================================


class TestFunctionSignatures:
    """Tests for worker function signatures."""

    def test_create_worker_signature(self):
        """create_worker accepts expected parameters."""
        sig = inspect.signature(create_worker)
        params = list(sig.parameters.keys())

        assert "address" in params
        assert "namespace" in params
        assert "task_queue" in params

    def test_run_worker_signature(self):
        """run_worker accepts expected parameters."""
        sig = inspect.signature(run_worker)
        params = list(sig.parameters.keys())

        assert "address" in params
        assert "namespace" in params
        assert "task_queue" in params
        assert "graceful_shutdown" in params

    def test_create_worker_defaults(self):
        """create_worker has expected default values."""
        sig = inspect.signature(create_worker)

        assert sig.parameters["address"].default == DEFAULT_TEMPORAL_ADDRESS
        assert sig.parameters["namespace"].default == DEFAULT_NAMESPACE
        assert sig.parameters["task_queue"].default == TASK_QUEUE

    def test_run_worker_defaults(self):
        """run_worker has expected default values."""
        sig = inspect.signature(run_worker)

        assert sig.parameters["address"].default == DEFAULT_TEMPORAL_ADDRESS
        assert sig.parameters["namespace"].default == DEFAULT_NAMESPACE
        assert sig.parameters["task_queue"].default == TASK_QUEUE
        assert sig.parameters["graceful_shutdown"].default is True


# =============================================================================
# Tests for create_worker Context Manager
# =============================================================================


class TestCreateWorkerContextManager:
    """Tests for create_worker context manager."""

    def test_create_worker_is_async_context_manager(self):
        """create_worker is an async context manager."""

        # Verify it returns an async context manager
        result = create_worker()

        # Should have __aenter__ and __aexit__
        assert hasattr(result, "__aenter__")
        assert hasattr(result, "__aexit__")


# =============================================================================
# Tests for Workflow and Activity Count
# =============================================================================


class TestWorkflowActivityCounts:
    """Tests for expected workflow and activity counts."""

    def test_workflow_count(self):
        """Expected number of workflows are registered."""
        # GreetingWorkflow + ForkCompareWorkflow = 2
        assert len(WORKFLOWS) == 2

    def test_activity_count(self):
        """Expected number of activities are registered."""
        # greet + load_conversation + create_checkpoint +
        # execute_branch + compare_results = 5
        assert len(ACTIVITIES) == 5
