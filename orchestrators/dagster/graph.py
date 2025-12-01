"""Dagster graphs for Fork & Compare workflow.

Graphs in Dagster define the structure of a computation without
specifying execution details. They can be converted to jobs for
different execution contexts.

This module provides:
- fork_compare_graph: The main Fork & Compare workflow
- Supporting ops for dynamic branch execution
- Partial failure handling

Dagster's execution model differs from Prefect:
- Graphs define op dependencies, not execution order
- DynamicOutput enables variable-length parallel execution
- Partial failures are handled via op-level retry policies
"""

import time

from dagster import (
    Config,
    DynamicOut,
    DynamicOutput,
    In,
    OpExecutionContext,
    Out,
    graph,
    op,
)

from orchestrators.dagster.ops import (
    CLAUDE_API_RETRY_POLICY,
    COMPUTE_RETRY_POLICY,
    LOCAL_RETRY_POLICY,
    compare_results_op,
    create_checkpoint_op,
    load_conversation_op,
)

# =============================================================================
# Configuration Classes
# =============================================================================


class ForkCompareConfig(Config):
    """Configuration for fork_compare_graph.

    Attributes:
        conversation_id: ID of conversation to fork
        fork_at_step: Step number to create checkpoint at
        branches: JSON-encoded list of branch configurations
            Each branch should have: name, model, temperature (optional),
            system_prompt (optional), inject_message (optional)
    """

    conversation_id: str
    fork_at_step: int
    branches_json: str  # JSON-encoded list of branch configs


# =============================================================================
# Dynamic Branch Execution Ops
# =============================================================================


@op(
    name="fan_out_branches",
    description="Create dynamic outputs for each branch configuration",
    retry_policy=LOCAL_RETRY_POLICY,
    ins={
        "conversation_data": In(dict, description="Conversation data dict"),
        "checkpoint_data": In(dict, description="Checkpoint data dict"),
    },
    out=DynamicOut(dict, description="Branch execution context for each branch"),
)
def fan_out_branches_op(
    context: OpExecutionContext,
    config: ForkCompareConfig,
    conversation_data: dict,
    checkpoint_data: dict,
):
    """Fan out to create dynamic outputs for each branch.

    This op parses the branch configurations and yields a DynamicOutput
    for each branch, enabling parallel execution.

    Args:
        context: Dagster op context
        config: ForkCompareConfig with branches_json
        conversation_data: Loaded conversation data
        checkpoint_data: Created checkpoint data

    Yields:
        DynamicOutput for each branch with execution context
    """
    import json

    branches = json.loads(config.branches_json)
    context.log.info(f"Fanning out {len(branches)} branches for parallel execution")

    for i, branch_config in enumerate(branches):
        branch_name = branch_config.get("name", f"branch-{i}")
        context.log.info(f"  → Creating output for branch: {branch_name}")

        # Yield dynamic output with branch context
        yield DynamicOutput(
            value={
                "conversation_data": conversation_data,
                "checkpoint_data": checkpoint_data,
                "branch_config": branch_config,
            },
            mapping_key=branch_name.replace("-", "_").replace(" ", "_"),
        )


@op(
    name="execute_single_branch",
    description="Execute a single conversation branch",
    retry_policy=CLAUDE_API_RETRY_POLICY,
    ins={"branch_context": In(dict, description="Branch execution context")},
    out=Out(dict, description="Branch result dictionary"),
)
def execute_single_branch_op(
    context: OpExecutionContext,
    branch_context: dict,
) -> dict:
    """Execute a single branch from the dynamic fan-out.

    This op wraps the core execute_branch function for dynamic execution.
    It handles the async nature of the Claude SDK call.

    Args:
        context: Dagster op context
        branch_context: Dict containing conversation_data, checkpoint_data, branch_config

    Returns:
        Branch result as a dict
    """
    import asyncio

    from core.executor import execute_branch
    from core.models import Checkpoint, Conversation, ForkConfig

    conversation_data = branch_context["conversation_data"]
    checkpoint_data = branch_context["checkpoint_data"]
    branch_config = branch_context["branch_config"]

    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    context.log.info(f"Executing branch '{config.name}' with model {config.model}")

    try:
        result = asyncio.run(execute_branch(conversation, config, checkpoint))
        context.log.info(
            f"Branch '{config.name}' completed in {result.duration_ms}ms "
            f"with {len(result.messages)} messages"
        )
        return result.model_dump()
    except Exception as e:
        context.log.error(f"Branch '{config.name}' failed: {e}")
        # Return error result instead of raising to allow partial success
        return {
            "branch_name": config.name,
            "config": config.model_dump(),
            "status": "error",
            "error": str(e),
            "messages": [],
            "duration_ms": 0,
            "token_usage": None,
        }


@op(
    name="collect_branch_results",
    description="Collect results from all branch executions",
    retry_policy=COMPUTE_RETRY_POLICY,
    ins={"branch_results": In(list, description="List of branch result dicts")},
    out=Out(list, description="Collected branch results"),
)
def collect_branch_results_op(
    context: OpExecutionContext,
    branch_results: list[dict],
) -> list[dict]:
    """Collect and log branch results.

    This op serves as a fan-in point for dynamic branch results.

    Args:
        context: Dagster op context
        branch_results: List of branch result dictionaries

    Returns:
        The same list of results (pass-through with logging)
    """
    successful = sum(1 for r in branch_results if r.get("status") != "error")
    failed = len(branch_results) - successful

    context.log.info(
        f"Collected {len(branch_results)} branch results: {successful} successful, {failed} failed"
    )

    return branch_results


@op(
    name="build_final_result",
    description="Build the final Fork & Compare result",
    retry_policy=COMPUTE_RETRY_POLICY,
    ins={
        "checkpoint_data": In(dict, description="Checkpoint data"),
        "branch_results": In(list, description="Branch results"),
        "comparison_summary": In(dict, description="Comparison summary"),
    },
    out=Out(dict, description="Final Fork & Compare result"),
)
def build_final_result_op(
    context: OpExecutionContext,
    config: ForkCompareConfig,
    checkpoint_data: dict,
    branch_results: list[dict],
    comparison_summary: dict,
    start_time: float,
) -> dict:
    """Build the final result dictionary.

    Args:
        context: Dagster op context
        config: Fork & Compare configuration
        checkpoint_data: Created checkpoint
        branch_results: Results from all branches
        comparison_summary: Comparison analysis
        start_time: Workflow start time

    Returns:
        ComparisonResult as a dict
    """
    import json

    total_duration_ms = int((time.time() - start_time) * 1000)

    successful = sum(1 for r in branch_results if r.get("status") != "error")

    context.log.info(
        f"Fork & Compare completed in {total_duration_ms}ms "
        f"({successful}/{len(branch_results)} branches successful)"
    )

    return {
        "request": {
            "conversation_id": config.conversation_id,
            "fork_at_step": config.fork_at_step,
            "branches": json.loads(config.branches_json),
        },
        "checkpoint": checkpoint_data,
        "branches": branch_results,
        "total_duration_ms": total_duration_ms,
        "comparison_summary": comparison_summary,
    }


# =============================================================================
# Simplified Fork & Compare Op (Non-Dynamic Version)
# =============================================================================


@op(
    name="fork_compare_all_in_one",
    description="Execute complete Fork & Compare workflow in a single op",
    retry_policy=CLAUDE_API_RETRY_POLICY,
    out=Out(dict, description="Fork & Compare result"),
)
def fork_compare_all_in_one_op(
    context: OpExecutionContext,
    config: ForkCompareConfig,
) -> dict:
    """Execute the complete Fork & Compare workflow.

    This op executes all steps of the workflow in sequence:
    1. Load conversation
    2. Create checkpoint
    3. Execute all branches (sequentially for simplicity)
    4. Compare results

    For production use with many branches, consider the graph-based
    approach with dynamic outputs for parallelism.

    Args:
        context: Dagster op context
        config: ForkCompareConfig with all parameters

    Returns:
        ComparisonResult as a dict
    """
    import asyncio
    import json

    from core.checkpoint import create_checkpoint
    from core.comparator import compare_branches
    from core.conversation import load_conversation
    from core.executor import execute_branch
    from core.models import BranchResult, ForkConfig

    start_time = time.time()

    # Step 1: Load conversation
    context.log.info(f"Step 1: Loading conversation {config.conversation_id}...")
    conversation = load_conversation(config.conversation_id)
    if conversation is None:
        raise ValueError(f"Conversation not found: {config.conversation_id}")
    context.log.info(f"  Loaded conversation with {conversation.step_count} steps")

    # Step 2: Create checkpoint
    context.log.info(f"Step 2: Creating checkpoint at step {config.fork_at_step}...")
    checkpoint = create_checkpoint(conversation, config.fork_at_step)
    context.log.info(f"  Checkpoint created with {len(checkpoint.messages)} messages")

    # Step 3: Execute branches
    branches = json.loads(config.branches_json)
    context.log.info(f"Step 3: Executing {len(branches)} branches...")

    branch_results = []
    for branch_config in branches:
        fork_config = ForkConfig.model_validate(branch_config)
        context.log.info(f"  → Executing branch: {fork_config.name}")

        try:
            result = asyncio.run(execute_branch(conversation, fork_config, checkpoint))
            branch_results.append(result.model_dump())
            context.log.info(f"    ✓ Completed in {result.duration_ms}ms")
        except Exception as e:
            context.log.error(f"    ✗ Failed: {e}")
            branch_results.append(
                {
                    "branch_name": fork_config.name,
                    "config": fork_config.model_dump(),
                    "status": "error",
                    "error": str(e),
                    "messages": [],
                    "duration_ms": 0,
                    "token_usage": None,
                }
            )

    # Step 4: Compare results
    context.log.info("Step 4: Comparing results...")
    valid_results = [BranchResult.model_validate(r) for r in branch_results]
    comparison = compare_branches(valid_results)

    # Build final result
    total_duration_ms = int((time.time() - start_time) * 1000)
    successful = sum(1 for r in branch_results if r.get("status") != "error")

    context.log.info(
        f"Fork & Compare completed in {total_duration_ms}ms "
        f"({successful}/{len(branch_results)} branches successful)"
    )

    return {
        "request": {
            "conversation_id": config.conversation_id,
            "fork_at_step": config.fork_at_step,
            "branches": branches,
        },
        "checkpoint": checkpoint.model_dump(),
        "branches": branch_results,
        "total_duration_ms": total_duration_ms,
        "comparison_summary": comparison.model_dump(),
    }


# =============================================================================
# Fork & Compare Graph (Dynamic Version)
# =============================================================================

# Note: Dagster's dynamic outputs require careful graph construction.
# For simplicity, we provide both:
# 1. fork_compare_graph: Uses dynamic outputs for parallel branch execution
# 2. fork_compare_simple_graph: Uses the all-in-one op for simpler execution


@graph(description="Fork & Compare workflow with dynamic branch parallelism")
def fork_compare_graph():
    """Execute Fork & Compare with parallel branch execution.

    This graph orchestrates the complete workflow:
    1. Load conversation
    2. Create checkpoint
    3. Fan out to execute branches in parallel (via DynamicOutput)
    4. Collect results (fan-in)
    5. Compare and build final result

    Note: Due to Dagster's graph construction model, the dynamic
    fan-out/fan-in is handled by the map() operation on dynamic outputs.
    """
    # Load and checkpoint
    conversation_data = load_conversation_op()
    checkpoint_data = create_checkpoint_op(conversation_data)

    # Fan out branches - yields DynamicOutput for each branch
    branch_contexts = fan_out_branches_op(conversation_data, checkpoint_data)

    # Execute each branch in parallel via map
    branch_results = branch_contexts.map(execute_single_branch_op)

    # Collect results (fan-in)
    collected_results = branch_results.collect()

    # Compare and finalize
    comparison = compare_results_op(collected_results)

    return comparison


@graph(description="Simplified Fork & Compare workflow (single op)")
def fork_compare_simple_graph():
    """Execute Fork & Compare in a single op.

    This is a simplified version that executes all steps sequentially
    in a single op. Useful for:
    - Simple use cases with few branches
    - Debugging and development
    - When dynamic parallelism isn't needed
    """
    return fork_compare_all_in_one_op()


# =============================================================================
# Jobs from Graphs
# =============================================================================

# Create jobs from graphs for different execution contexts

fork_compare_job = fork_compare_simple_graph.to_job(
    name="fork_compare_job",
    description="Execute Fork & Compare workflow (simplified sequential execution)",
)

fork_compare_parallel_job = fork_compare_graph.to_job(
    name="fork_compare_parallel_job",
    description="Execute Fork & Compare with parallel branch execution",
)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Configuration
    "ForkCompareConfig",
    # Ops
    "fan_out_branches_op",
    "execute_single_branch_op",
    "collect_branch_results_op",
    "build_final_result_op",
    "fork_compare_all_in_one_op",
    # Graphs
    "fork_compare_graph",
    "fork_compare_simple_graph",
    # Jobs
    "fork_compare_job",
    "fork_compare_parallel_job",
]
