"""Tests for Prefect development environment setup.

Tests verify:
- Prefect is installed correctly
- Tasks and flows can be defined and executed
- Basic flow execution works in ephemeral mode
"""

import inspect

# =============================================================================
# Tests for Prefect Installation
# =============================================================================


class TestPrefectInstallation:
    """Tests for Prefect package installation."""

    def test_prefect_import(self):
        """Prefect can be imported."""
        import prefect

        assert prefect is not None

    def test_prefect_version(self):
        """Prefect version is 3.x."""
        import prefect

        version = prefect.__version__
        major_version = int(version.split(".")[0])
        assert major_version >= 3, f"Expected Prefect 3.x, got {version}"

    def test_prefect_task_decorator(self):
        """Task decorator is available."""
        from prefect import task

        assert callable(task)

    def test_prefect_flow_decorator(self):
        """Flow decorator is available."""
        from prefect import flow

        assert callable(flow)


# =============================================================================
# Tests for Task Definitions
# =============================================================================


class TestTaskDefinitions:
    """Tests for Prefect task definitions."""

    def test_greet_task_exists(self):
        """greet_task is defined."""
        from orchestrators.prefect.tasks import greet_task

        assert greet_task is not None

    def test_greet_task_is_prefect_task(self):
        """greet_task is a Prefect task."""
        from orchestrators.prefect.tasks import greet_task

        # Prefect tasks have a __wrapped__ attribute or are PrefectTask instances
        assert hasattr(greet_task, "fn") or hasattr(greet_task, "__wrapped__")

    def test_load_conversation_task_exists(self):
        """load_conversation_task is defined."""
        from orchestrators.prefect.tasks import load_conversation_task

        assert load_conversation_task is not None

    def test_create_checkpoint_task_exists(self):
        """create_checkpoint_task is defined."""
        from orchestrators.prefect.tasks import create_checkpoint_task

        assert create_checkpoint_task is not None

    def test_execute_branch_task_exists(self):
        """execute_branch_task is defined."""
        from orchestrators.prefect.tasks import execute_branch_task

        assert execute_branch_task is not None

    def test_compare_results_task_exists(self):
        """compare_results_task is defined."""
        from orchestrators.prefect.tasks import compare_results_task

        assert compare_results_task is not None


# =============================================================================
# Tests for Flow Definitions
# =============================================================================


class TestFlowDefinitions:
    """Tests for Prefect flow definitions."""

    def test_greeting_flow_exists(self):
        """GreetingFlow is defined."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow is not None

    def test_fork_compare_flow_exists(self):
        """ForkCompareFlow is defined."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow is not None

    def test_run_greeting_flow_exists(self):
        """run_greeting_flow is defined."""
        from orchestrators.prefect.flows import run_greeting_flow

        assert run_greeting_flow is not None


# =============================================================================
# Tests for Module Exports
# =============================================================================


class TestModuleExports:
    """Tests for module exports."""

    def test_init_exports_greet_task(self):
        """__init__ exports greet_task."""
        from orchestrators.prefect import greet_task

        assert greet_task is not None

    def test_init_exports_greeting_flow(self):
        """__init__ exports GreetingFlow."""
        from orchestrators.prefect import GreetingFlow

        assert GreetingFlow is not None

    def test_init_exports_run_greeting_flow(self):
        """__init__ exports run_greeting_flow."""
        from orchestrators.prefect import run_greeting_flow

        assert callable(run_greeting_flow)


# =============================================================================
# Tests for Basic Flow Execution
# =============================================================================


class TestBasicFlowExecution:
    """Tests for basic flow execution in ephemeral mode."""

    def test_greet_task_execution(self):
        """greet_task executes correctly."""
        from orchestrators.prefect.tasks import greet_task

        # Call the underlying function directly
        result = greet_task.fn("Test")
        assert result == "Hello, Test!"

    def test_greeting_flow_execution(self):
        """GreetingFlow executes correctly."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow("Prefect")
        assert result == "Hello, Prefect!"

    def test_greeting_flow_default_name(self):
        """GreetingFlow uses default name."""
        from orchestrators.prefect.flows import run_greeting_flow

        result = run_greeting_flow()
        assert result == "Hello, Prefect!"


# =============================================================================
# Tests for Task Configuration
# =============================================================================


class TestTaskConfiguration:
    """Tests for task configuration options."""

    def test_greet_task_has_retries(self):
        """greet_task is configured with retries."""
        from orchestrators.prefect.tasks import greet_task

        # Prefect tasks have retry config
        assert greet_task.retries == 3

    def test_greet_task_has_name(self):
        """greet_task has a name."""
        from orchestrators.prefect.tasks import greet_task

        assert greet_task.name == "greet"

    def test_greet_task_has_description(self):
        """greet_task has a description."""
        from orchestrators.prefect.tasks import greet_task

        assert greet_task.description is not None
        assert "greeting" in greet_task.description.lower()


# =============================================================================
# Tests for Flow Configuration
# =============================================================================


class TestFlowConfiguration:
    """Tests for flow configuration options."""

    def test_greeting_flow_has_name(self):
        """GreetingFlow has a name."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow.name == "greeting-flow"

    def test_greeting_flow_has_description(self):
        """GreetingFlow has a description."""
        from orchestrators.prefect.flows import GreetingFlow

        assert GreetingFlow.description is not None

    def test_fork_compare_flow_has_name(self):
        """ForkCompareFlow has a name."""
        from orchestrators.prefect.flows import ForkCompareFlow

        assert ForkCompareFlow.name == "fork-compare-flow"


# =============================================================================
# Tests for Async Support
# =============================================================================


class TestAsyncSupport:
    """Tests for async task and flow support."""

    def test_execute_branch_task_is_async(self):
        """execute_branch_task is async."""
        from orchestrators.prefect.tasks import execute_branch_task

        # Check if the underlying function is a coroutine function
        assert inspect.iscoroutinefunction(execute_branch_task.fn)

    def test_fork_compare_flow_is_async(self):
        """ForkCompareFlow is async."""
        from orchestrators.prefect.flows import ForkCompareFlow

        # Check if the underlying function is a coroutine function
        assert inspect.iscoroutinefunction(ForkCompareFlow.fn)
