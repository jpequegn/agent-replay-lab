#!/usr/bin/env python3
"""Standardized benchmark for comparing orchestrators.

Runs the same Fork & Compare workflow on all three orchestrators
(Prefect, Dagster, Temporal) with mocked Claude API responses to
measure orchestrator overhead without real API costs.

Usage:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --runs 5
    uv run python scripts/benchmark.py --orchestrators prefect dagster
    uv run python scripts/benchmark.py --output comparisons/benchmark-results.json

Metrics collected:
    - Total execution time (wall clock)
    - Per-branch execution time
    - Orchestrator setup/teardown overhead
    - Success/failure rate
    - Memory usage (before/after each run)
"""

import argparse
import asyncio
import gc
import json
import os
import statistics
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Benchmark configuration
# ---------------------------------------------------------------------------

# Standard conversation used across all orchestrators
BENCHMARK_CONVERSATION = {
    "session_id": "benchmark-conv-001",
    "project_path": "/benchmark/project",
    "messages": [
        {"role": "user", "content": "Hello, I need help with Python", "timestamp": "2025-01-01T10:00:00Z"},
        {"role": "assistant", "content": "Hello! I'd be happy to help with Python.", "timestamp": "2025-01-01T10:00:01Z"},
        {"role": "user", "content": "How do I read a file?", "timestamp": "2025-01-01T10:00:02Z"},
        {"role": "assistant", "content": "You can use open() or pathlib", "timestamp": "2025-01-01T10:00:03Z"},
        {"role": "user", "content": "Show me pathlib example", "timestamp": "2025-01-01T10:00:04Z"},
        {"role": "assistant", "content": "Here's an example: Path('file.txt').read_text()", "timestamp": "2025-01-01T10:00:05Z"},
    ],
    "step_count": 6,
}

BENCHMARK_CHECKPOINT = {
    "conversation_id": "benchmark-conv-001",
    "step": 5,
    "messages": BENCHMARK_CONVERSATION["messages"][:5],
    "project_path": "/benchmark/project",
    "created_at": "2025-01-01T10:00:04Z",
}

# Standard request - 3 branches, same across all orchestrators
BENCHMARK_REQUEST = {
    "conversation_id": "benchmark-conv-001",
    "fork_at_step": 5,
    "branches": [
        {"name": "sonnet-baseline", "model": "claude-sonnet-4-20250514", "max_turns": 1},
        {"name": "haiku-speed", "model": "claude-haiku-4-20250514", "max_turns": 1},
        {"name": "sonnet-inject", "model": "claude-sonnet-4-20250514", "max_turns": 1, "inject_message": "Give me a different approach"},
    ],
}

# Simulated API latency per branch (ms) - realistic but fast for benchmarking
SIMULATED_BRANCH_LATENCY_MS = 50

# Branch results returned by mock
def make_mock_branch_result(branch_name: str, model: str, latency_ms: int) -> dict:
    return {
        "branch_name": branch_name,
        "config": {"name": branch_name, "model": model},
        "status": "success",
        "messages": [{"role": "assistant", "content": f"Mock response for {branch_name}", "timestamp": "2025-01-01T10:00:06Z"}],
        "duration_ms": latency_ms,
        "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }


# ---------------------------------------------------------------------------
# Memory measurement
# ---------------------------------------------------------------------------

def get_memory_mb() -> float:
    """Get current process memory in MB."""
    try:
        import resource
        # macOS/Linux: getrusage returns bytes on Linux, KB on macOS
        usage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024 * 1024)  # bytes → MB on macOS
        else:
            return usage.ru_maxrss / 1024  # KB → MB on Linux
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Mock setup helpers
# ---------------------------------------------------------------------------

def make_mock_conversation():
    conv = MagicMock()
    conv.session_id = "benchmark-conv-001"
    conv.project_path = "/benchmark/project"
    conv.step_count = 6
    conv.messages = BENCHMARK_CONVERSATION["messages"]
    conv.model_dump.return_value = BENCHMARK_CONVERSATION
    return conv


def make_mock_checkpoint():
    chk = MagicMock()
    chk.messages = BENCHMARK_CHECKPOINT["messages"]
    chk.model_dump.return_value = BENCHMARK_CHECKPOINT
    return chk


async def mock_execute_branch(conversation, config, checkpoint):
    """Mock Claude API call - returns quickly with deterministic result."""
    await asyncio.sleep(SIMULATED_BRANCH_LATENCY_MS / 1000)
    result = MagicMock()
    result.duration_ms = SIMULATED_BRANCH_LATENCY_MS
    result.messages = [MagicMock()]
    result.model_dump.return_value = make_mock_branch_result(
        config.name, config.model, SIMULATED_BRANCH_LATENCY_MS
    )
    return result


def make_mock_comparison(branch_results: list) -> dict:
    return {
        "successful": sum(1 for r in branch_results if r.get("status") == "success"),
        "failed": sum(1 for r in branch_results if r.get("status") != "success"),
        "branches": branch_results,
    }


# ---------------------------------------------------------------------------
# Prefect benchmark
# ---------------------------------------------------------------------------

async def run_prefect_once() -> dict:
    """Run one Prefect benchmark iteration."""
    from orchestrators.prefect.client import run_fork_compare_flow

    mock_conv = make_mock_conversation()
    mock_chk = make_mock_checkpoint()
    mock_comparison = MagicMock()

    branch_results = [
        make_mock_branch_result(b["name"], b["model"], SIMULATED_BRANCH_LATENCY_MS)
        for b in BENCHMARK_REQUEST["branches"]
    ]
    mock_comparison.model_dump.return_value = make_mock_comparison(branch_results)

    with (
        patch("core.conversation.load_conversation", return_value=mock_conv),
        patch("core.checkpoint.create_checkpoint", return_value=mock_chk),
        patch("core.executor.execute_branch", new=AsyncMock(side_effect=mock_execute_branch)),
        patch("core.comparator.compare_branches", return_value=mock_comparison),
    ):
        start = time.perf_counter()
        result = await run_fork_compare_flow(request_dict=BENCHMARK_REQUEST)
        elapsed_ms = (time.perf_counter() - start) * 1000

    return {"result": result, "elapsed_ms": elapsed_ms}


# ---------------------------------------------------------------------------
# Dagster benchmark
# ---------------------------------------------------------------------------

async def run_dagster_once() -> dict:
    """Run one Dagster benchmark iteration."""
    from orchestrators.dagster.client import run_fork_compare_job

    mock_conv = make_mock_conversation()
    mock_chk = make_mock_checkpoint()
    mock_comparison = MagicMock()

    branch_results = [
        make_mock_branch_result(b["name"], b["model"], SIMULATED_BRANCH_LATENCY_MS)
        for b in BENCHMARK_REQUEST["branches"]
    ]
    mock_comparison.model_dump.return_value = make_mock_comparison(branch_results)

    with (
        patch("core.conversation.load_conversation", return_value=mock_conv),
        patch("core.checkpoint.create_checkpoint", return_value=mock_chk),
        patch("core.executor.execute_branch", new=AsyncMock(side_effect=mock_execute_branch)),
        patch("core.comparator.compare_branches", return_value=mock_comparison),
    ):
        start = time.perf_counter()
        result = await run_fork_compare_job(request_dict=BENCHMARK_REQUEST)
        elapsed_ms = (time.perf_counter() - start) * 1000

    return {"result": result, "elapsed_ms": elapsed_ms}


# ---------------------------------------------------------------------------
# Temporal benchmark
# ---------------------------------------------------------------------------

async def run_temporal_once() -> dict:
    """Run one Temporal benchmark iteration using time-skipping test environment.

    Uses mock activities registered by name to avoid Temporal sandbox isolation
    issues with module-level patches.
    """
    from temporalio import activity
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker
    from temporalio.worker.workflow_sandbox import SandboxRestrictions, SandboxedWorkflowRunner

    from orchestrators.temporal.worker import TASK_QUEUE
    from orchestrators.temporal.workflows import ForkCompareWorkflow

    branch_results = [
        make_mock_branch_result(b["name"], b["model"], SIMULATED_BRANCH_LATENCY_MS)
        for b in BENCHMARK_REQUEST["branches"]
    ]
    mock_comparison_dict = make_mock_comparison(branch_results)

    # Define mock activities with the same names as the real ones.
    # The workflow dispatches by name, so these intercept all activity calls.
    @activity.defn(name="load_conversation_activity")
    async def _mock_load_conversation(session_id: str) -> dict | None:
        return BENCHMARK_CONVERSATION

    @activity.defn(name="create_checkpoint_activity")
    async def _mock_create_checkpoint(conversation_dict: dict, step: int) -> dict:
        return BENCHMARK_CHECKPOINT

    @activity.defn(name="execute_branch_activity")
    async def _mock_execute_branch(checkpoint_dict: dict, config_dict: dict) -> dict:
        await asyncio.sleep(SIMULATED_BRANCH_LATENCY_MS / 1000)
        name = config_dict.get("name", "unknown")
        model = config_dict.get("model", "unknown")
        return make_mock_branch_result(name, model, SIMULATED_BRANCH_LATENCY_MS)

    @activity.defn(name="compare_results_activity")
    async def _mock_compare_results(branch_results_arg: list) -> dict:
        return mock_comparison_dict

    @activity.defn(name="greet_activity")
    async def _mock_greet(name: str) -> str:
        return f"Hello, {name}!"

    default = SandboxRestrictions.default
    passthrough = set(default.passthrough_modules)
    passthrough.update([
        "core", "orchestrators", "orchestrators.temporal",
        "orchestrators.temporal.workflows",
    ])

    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions(
            passthrough_modules=frozenset(passthrough),
            invalid_modules=default.invalid_modules,
            invalid_module_members=default.invalid_module_members,
        )
    )

    start = time.perf_counter()

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[ForkCompareWorkflow],
            activities=[
                _mock_load_conversation,
                _mock_create_checkpoint,
                _mock_execute_branch,
                _mock_compare_results,
                _mock_greet,
            ],
            workflow_runner=sandbox_runner,
        ):
            result = await env.client.execute_workflow(
                ForkCompareWorkflow.run,
                BENCHMARK_REQUEST,
                id=f"benchmark-{int(time.time() * 1000)}",
                task_queue=TASK_QUEUE,
            )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return {"result": result, "elapsed_ms": elapsed_ms}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

async def run_orchestrator_benchmark(
    name: str,
    run_fn,
    num_runs: int,
) -> dict:
    """Run an orchestrator benchmark N times and collect metrics."""
    print(f"\n  Running {name} ({num_runs}x)...", end="", flush=True)

    timings = []
    errors = []
    memory_deltas = []

    for i in range(num_runs):
        gc.collect()
        mem_before = get_memory_mb()

        try:
            run_result = await run_fn()
            elapsed = run_result["elapsed_ms"]
            timings.append(elapsed)
            mem_after = get_memory_mb()
            memory_deltas.append(max(0, mem_after - mem_before))
            print(f" {elapsed:.0f}ms", end="", flush=True)
        except Exception as e:
            errors.append({"run": i + 1, "error": str(e), "traceback": traceback.format_exc()})
            print(f" ERR", end="", flush=True)

    print()

    success_count = len(timings)
    failure_count = len(errors)

    metrics = {
        "orchestrator": name,
        "num_runs": num_runs,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_count / num_runs if num_runs > 0 else 0,
        "timings_ms": timings,
        "errors": errors,
    }

    if timings:
        metrics.update({
            "mean_ms": statistics.mean(timings),
            "median_ms": statistics.median(timings),
            "min_ms": min(timings),
            "max_ms": max(timings),
            "stdev_ms": statistics.stdev(timings) if len(timings) > 1 else 0,
        })

    if memory_deltas:
        metrics["mean_memory_delta_mb"] = statistics.mean(memory_deltas)

    # Subtract simulated API latency to get pure orchestrator overhead
    # Each run has 3 branches × 50ms simulated latency
    simulated_total_ms = 3 * SIMULATED_BRANCH_LATENCY_MS
    if timings:
        overhead_timings = [max(0, t - simulated_total_ms) for t in timings]
        metrics["overhead_ms"] = {
            "mean": statistics.mean(overhead_timings),
            "median": statistics.median(overhead_timings),
            "min": min(overhead_timings),
            "max": max(overhead_timings),
        }

    return metrics


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args):
    orchestrators_to_run = args.orchestrators
    num_runs = args.runs
    output_path = Path(args.output)

    print(f"=== Agent Replay Lab: Orchestrator Benchmark ===")
    print(f"  Date:        {datetime.now(timezone.utc).isoformat()}")
    print(f"  Runs:        {num_runs}x per orchestrator")
    print(f"  Branches:    {len(BENCHMARK_REQUEST['branches'])} (3 models)")
    print(f"  API latency: {SIMULATED_BRANCH_LATENCY_MS}ms (mocked)")
    print(f"  Orchestrators: {', '.join(orchestrators_to_run)}")

    runners = {
        "prefect": run_prefect_once,
        "dagster": run_dagster_once,
        "temporal": run_temporal_once,
    }

    all_results = []
    environment_info = {
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "benchmark_config": {
            "num_runs": num_runs,
            "num_branches": len(BENCHMARK_REQUEST["branches"]),
            "simulated_api_latency_ms": SIMULATED_BRANCH_LATENCY_MS,
            "conversation_id": BENCHMARK_REQUEST["conversation_id"],
            "fork_at_step": BENCHMARK_REQUEST["fork_at_step"],
        },
    }

    for name in orchestrators_to_run:
        if name not in runners:
            print(f"\n  [SKIP] Unknown orchestrator: {name}")
            continue

        metrics = await run_orchestrator_benchmark(name, runners[name], num_runs)
        all_results.append(metrics)

    # Build output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": environment_info,
        "benchmark_request": BENCHMARK_REQUEST,
        "results": all_results,
    }

    # Save JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved: {output_path}")

    # Print summary table
    print(f"\n{'Orchestrator':<12} {'Runs':>5} {'Success':>8} {'Mean ms':>9} {'Median ms':>10} {'Overhead ms':>12}")
    print("-" * 62)
    for r in all_results:
        if r["success_count"] > 0:
            overhead = r.get("overhead_ms", {}).get("mean", 0)
            print(
                f"{r['orchestrator']:<12} {r['num_runs']:>5} {r['success_count']:>8} "
                f"{r['mean_ms']:>9.1f} {r['median_ms']:>10.1f} {overhead:>12.1f}"
            )
        else:
            print(f"{r['orchestrator']:<12} {r['num_runs']:>5} {'FAILED':>8}")

    return output


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark orchestrators for agent-replay-lab")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per orchestrator")
    parser.add_argument(
        "--orchestrators", nargs="+",
        default=["prefect", "dagster", "temporal"],
        choices=["prefect", "dagster", "temporal"],
        help="Which orchestrators to benchmark",
    )
    parser.add_argument(
        "--output", default="comparisons/benchmark-results.json",
        help="Output path for JSON results",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
