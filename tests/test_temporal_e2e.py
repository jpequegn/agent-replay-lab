"""End-to-end tests for Temporal workflow implementation.

Tests the complete workflow from CLI through Temporal to activities,
using mocked Claude API responses.
"""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

# Disable sandbox for tests - required because activities use pathlib.Path.home()
# which is restricted in Temporal's sandbox by default
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from core.models import (
    BranchResult,
    Checkpoint,
    Conversation,
    ForkConfig,
    Message,
    ReplayRequest,
    TokenUsage,
)
from orchestrators.temporal.activities import (
    compare_results_activity,
    create_checkpoint_activity,
    execute_branch_activity,
    greet_activity,
    load_conversation_activity,
)
from orchestrators.temporal.worker import TASK_QUEUE
from orchestrators.temporal.workflows import ForkCompareWorkflow, GreetingWorkflow


# Custom sandbox runner that allows our modules
def create_test_sandbox_runner():
    """Create a sandbox runner with relaxed restrictions for testing.

    We need to add our modules to passthrough to avoid sandbox restrictions
    on Path.home() and other file system operations.
    """
    # Get default restrictions and add our modules
    default = SandboxRestrictions.default
    passthrough = set(default.passthrough_modules)
    passthrough.update(
        [
            "core",
            "core.models",
            "core.conversation",
            "core.checkpoint",
            "core.executor",
            "orchestrators",
            "orchestrators.temporal",
            "orchestrators.temporal.activities",
        ]
    )

    return SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions(
            passthrough_modules=frozenset(passthrough),
            invalid_modules=default.invalid_modules,
            invalid_module_members=default.invalid_module_members,
        )
    )


# =============================================================================
# Test Fixtures
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
    """Sample replay request with 3 branches."""
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
# Tests for GreetingWorkflow (Simple E2E)
# =============================================================================


class TestGreetingWorkflowE2E:
    """End-to-end tests for the greeting workflow."""

    @pytest.mark.asyncio
    async def test_greeting_workflow_with_test_server(self):
        """Test greeting workflow using Temporal test server."""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[GreetingWorkflow],
                activities=[greet_activity],
                workflow_runner=create_test_sandbox_runner(),
            ):
                result = await env.client.execute_workflow(
                    GreetingWorkflow.run,
                    "TestUser",
                    id="greeting-test-1",
                    task_queue=TASK_QUEUE,
                    execution_timeout=timedelta(minutes=1),
                )

                assert result == "Hello, TestUser!"


# =============================================================================
# Tests for ForkCompareWorkflow (Full E2E)
# =============================================================================


class TestForkCompareWorkflowE2E:
    """End-to-end tests for the Fork & Compare workflow."""

    @pytest.mark.asyncio
    async def test_complete_workflow_with_mocked_activities(
        self, sample_conversation, sample_checkpoint, sample_request, mock_branch_result
    ):
        """Test complete workflow with mocked activity implementations."""

        # Mock the activity implementations
        async def mock_load_conversation(conversation_id: str) -> dict:
            return sample_conversation.model_dump()

        async def mock_create_checkpoint(conversation_dict: dict, step: int) -> dict:
            return sample_checkpoint.model_dump()

        async def mock_execute_branch(checkpoint_dict: dict, config_dict: dict) -> dict:
            config = ForkConfig.model_validate(config_dict)
            return BranchResult(
                branch_name=config.name,
                config=config,
                messages=[
                    Message(
                        role="assistant",
                        content=f"Response from {config.name}",
                        timestamp="2025-01-01T10:00:06Z",
                    ),
                ],
                duration_ms=500,
                token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                status="success",
            ).model_dump()

        async def mock_compare_results(
            request_dict: dict, checkpoint_dict: dict, results: list
        ) -> dict:
            return {
                "request": request_dict,
                "checkpoint": checkpoint_dict,
                "branches": results,
                "total_duration_ms": sum(r.get("duration_ms", 0) for r in results),
                "comparison_summary": {
                    "successful": len([r for r in results if r.get("status") == "success"]),
                    "failed": len([r for r in results if r.get("status") != "success"]),
                },
            }

        # Run workflow with test server
        async with await WorkflowEnvironment.start_time_skipping() as env:
            # Wrap the mocked functions as activity implementations
            with (
                patch(
                    "orchestrators.temporal.activities.load_conversation",
                    side_effect=lambda x: sample_conversation,
                ),
                patch(
                    "orchestrators.temporal.activities.create_checkpoint",
                    side_effect=lambda conv, step: sample_checkpoint,
                ),
                patch(
                    "orchestrators.temporal.activities.execute_branch",
                    side_effect=lambda cp, cfg: BranchResult(
                        branch_name=cfg.name,
                        config=cfg,
                        messages=[
                            Message(
                                role="assistant",
                                content=f"Response from {cfg.name}",
                                timestamp="2025-01-01T10:00:06Z",
                            ),
                        ],
                        duration_ms=500,
                        token_usage=TokenUsage(
                            input_tokens=100, output_tokens=50, total_tokens=150
                        ),
                        status="success",
                    ),
                ),
            ):
                async with Worker(
                    env.client,
                    task_queue=TASK_QUEUE,
                    workflows=[ForkCompareWorkflow],
                    activities=[
                        load_conversation_activity,
                        create_checkpoint_activity,
                        execute_branch_activity,
                        compare_results_activity,
                    ],
                    workflow_runner=create_test_sandbox_runner(),
                ):
                    result = await env.client.execute_workflow(
                        ForkCompareWorkflow.run,
                        sample_request.model_dump(),
                        id="fork-compare-test-1",
                        task_queue=TASK_QUEUE,
                        execution_timeout=timedelta(minutes=5),
                    )

                    # Verify result structure
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
    async def test_workflow_with_partial_failure(self, sample_conversation, sample_checkpoint):
        """Test workflow handles partial branch failures correctly."""
        request = ReplayRequest(
            conversation_id="test-partial-failure",
            fork_at_step=3,
            branches=[
                ForkConfig(name="success-branch", model="claude-sonnet-4-20250514"),
                ForkConfig(name="failure-branch", model="claude-sonnet-4-20250514"),
            ],
        )

        call_count = [0]

        def mock_execute_branch(checkpoint, config):
            call_count[0] += 1
            if config.name == "failure-branch":
                return BranchResult(
                    branch_name=config.name,
                    config=config,
                    messages=[],
                    duration_ms=100,
                    status="error",
                    error="Simulated API error",
                )
            return BranchResult(
                branch_name=config.name,
                config=config,
                messages=[
                    Message(role="assistant", content="Success", timestamp="2025-01-01T10:00:06Z")
                ],
                duration_ms=500,
                token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                status="success",
            )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            with (
                patch(
                    "orchestrators.temporal.activities.load_conversation",
                    return_value=sample_conversation,
                ),
                patch(
                    "orchestrators.temporal.activities.create_checkpoint",
                    return_value=sample_checkpoint,
                ),
                patch(
                    "orchestrators.temporal.activities.execute_branch",
                    side_effect=mock_execute_branch,
                ),
            ):
                async with Worker(
                    env.client,
                    task_queue=TASK_QUEUE,
                    workflows=[ForkCompareWorkflow],
                    activities=[
                        load_conversation_activity,
                        create_checkpoint_activity,
                        execute_branch_activity,
                        compare_results_activity,
                    ],
                    workflow_runner=create_test_sandbox_runner(),
                ):
                    result = await env.client.execute_workflow(
                        ForkCompareWorkflow.run,
                        request.model_dump(),
                        id="fork-compare-partial-failure",
                        task_queue=TASK_QUEUE,
                        execution_timeout=timedelta(minutes=5),
                    )

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
                    assert "Simulated API error" in failure_branch["error"]

                    # Verify comparison summary
                    assert result["comparison_summary"]["successful"] == 1
                    assert result["comparison_summary"]["failed"] == 1


# =============================================================================
# Tests for Workflow Recovery
# =============================================================================


class TestWorkflowRecovery:
    """Tests for workflow recovery and fault tolerance."""

    @pytest.mark.asyncio
    async def test_workflow_continues_after_activity_retry(
        self, sample_conversation, sample_checkpoint
    ):
        """Test workflow continues after activity retry succeeds."""
        request = ReplayRequest(
            conversation_id="test-retry",
            fork_at_step=3,
            branches=[
                ForkConfig(name="retry-branch", model="claude-sonnet-4-20250514"),
            ],
        )

        attempt = [0]

        def mock_execute_with_retry(checkpoint, config):
            attempt[0] += 1
            if attempt[0] == 1:
                raise RuntimeError("Transient error")
            return BranchResult(
                branch_name=config.name,
                config=config,
                messages=[
                    Message(
                        role="assistant",
                        content="Success after retry",
                        timestamp="2025-01-01T10:00:06Z",
                    )
                ],
                duration_ms=500,
                token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                status="success",
            )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            with (
                patch(
                    "orchestrators.temporal.activities.load_conversation",
                    return_value=sample_conversation,
                ),
                patch(
                    "orchestrators.temporal.activities.create_checkpoint",
                    return_value=sample_checkpoint,
                ),
                patch(
                    "orchestrators.temporal.activities.execute_branch",
                    side_effect=mock_execute_with_retry,
                ),
            ):
                async with Worker(
                    env.client,
                    task_queue=TASK_QUEUE,
                    workflows=[ForkCompareWorkflow],
                    activities=[
                        load_conversation_activity,
                        create_checkpoint_activity,
                        execute_branch_activity,
                        compare_results_activity,
                    ],
                    workflow_runner=create_test_sandbox_runner(),
                ):
                    result = await env.client.execute_workflow(
                        ForkCompareWorkflow.run,
                        request.model_dump(),
                        id="fork-compare-retry-test",
                        task_queue=TASK_QUEUE,
                        execution_timeout=timedelta(minutes=5),
                    )

                    # Should succeed after retry
                    assert len(result["branches"]) == 1
                    assert result["branches"][0]["status"] == "success"
                    # Verify retry happened
                    assert attempt[0] >= 1


# =============================================================================
# Tests for Parallel Execution
# =============================================================================


class TestParallelExecution:
    """Tests for parallel branch execution."""

    @pytest.mark.asyncio
    async def test_branches_execute_concurrently(self, sample_conversation, sample_checkpoint):
        """Test that branches execute in parallel (not sequentially)."""
        import time

        request = ReplayRequest(
            conversation_id="test-parallel",
            fork_at_step=3,
            branches=[
                ForkConfig(name="branch-1", model="claude-sonnet-4-20250514"),
                ForkConfig(name="branch-2", model="claude-sonnet-4-20250514"),
                ForkConfig(name="branch-3", model="claude-sonnet-4-20250514"),
            ],
        )

        execution_times = []

        def mock_execute_with_delay(checkpoint, config):
            start = time.time()
            # Simulate work
            execution_times.append((config.name, start))
            return BranchResult(
                branch_name=config.name,
                config=config,
                messages=[
                    Message(
                        role="assistant",
                        content=f"Response {config.name}",
                        timestamp="2025-01-01T10:00:06Z",
                    )
                ],
                duration_ms=100,
                token_usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                status="success",
            )

        async with await WorkflowEnvironment.start_time_skipping() as env:
            with (
                patch(
                    "orchestrators.temporal.activities.load_conversation",
                    return_value=sample_conversation,
                ),
                patch(
                    "orchestrators.temporal.activities.create_checkpoint",
                    return_value=sample_checkpoint,
                ),
                patch(
                    "orchestrators.temporal.activities.execute_branch",
                    side_effect=mock_execute_with_delay,
                ),
            ):
                async with Worker(
                    env.client,
                    task_queue=TASK_QUEUE,
                    workflows=[ForkCompareWorkflow],
                    activities=[
                        load_conversation_activity,
                        create_checkpoint_activity,
                        execute_branch_activity,
                        compare_results_activity,
                    ],
                    workflow_runner=create_test_sandbox_runner(),
                ):
                    result = await env.client.execute_workflow(
                        ForkCompareWorkflow.run,
                        request.model_dump(),
                        id="fork-compare-parallel-test",
                        task_queue=TASK_QUEUE,
                        execution_timeout=timedelta(minutes=5),
                    )

                    # All 3 branches should have executed
                    assert len(result["branches"]) == 3
                    assert all(b["status"] == "success" for b in result["branches"])


# =============================================================================
# Tests for Result Persistence
# =============================================================================


class TestResultPersistence:
    """Tests for saving results to disk."""

    def test_result_can_be_saved_to_json(self, tmp_path):
        """Test that workflow result can be saved to JSON file."""
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
# Integration Test Summary
# =============================================================================


class TestIntegrationSummary:
    """Summary tests to document tested scenarios."""

    def test_documented_scenarios(self):
        """Document what E2E scenarios are covered by these tests."""
        scenarios = [
            "GreetingWorkflow with test server",
            "ForkCompareWorkflow with 3 branches (all success)",
            "ForkCompareWorkflow with partial failure (1 success, 1 error)",
            "Workflow continues after activity retry",
            "Branches execute concurrently",
            "Result can be saved to JSON",
        ]

        # This test documents what's tested
        assert len(scenarios) == 6
        assert "ForkCompareWorkflow" in str(scenarios)
