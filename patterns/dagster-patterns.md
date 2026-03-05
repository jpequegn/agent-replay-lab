# Dagster Integration Patterns for Claude Code SDK

This document captures patterns and lessons learned from integrating Dagster workflow orchestration with the Claude Code SDK for the agent-replay-lab project.

## Quick Start

### Prerequisites

```bash
# Install Dagster (with uv)
uv add dagster dagster-webserver
```

Dagster requires a running dev server for the UI, but jobs can also execute **in-process** without a server.

### Basic Project Structure

```
orchestrators/dagster/
├── __init__.py       # Module exports
├── definitions.py    # Dagster Definitions entry point (registers all objects)
├── ops.py            # Op definitions and retry policies
├── graph.py          # Graph and job definitions
├── jobs.py           # Simple job definitions
└── client.py         # Client utilities for running jobs
```

### Minimal Working Example

```python
# ops.py
from dagster import op, OpExecutionContext

@op(description="Execute a single conversation branch")
def execute_branch_op(context: OpExecutionContext, data: dict) -> dict:
    context.log.info("Executing branch...")
    return {"status": "success"}

# jobs.py
from dagster import job
from .ops import execute_branch_op

@job
def my_job():
    execute_branch_op()

# Run it in-process (no server needed)
result = my_job.execute_in_process(
    run_config={"ops": {"execute_branch_op": {"inputs": {"data": {}}}}}
)
print(result.success)
```

### With Dagster UI

```bash
# Start dev server (provides UI + persistence)
uv run dagster dev -m orchestrators.dagster.definitions

# Access UI at http://localhost:3000
```

### Via CLI

```bash
# Execute a job
uv run dagster job execute -m orchestrators.dagster.definitions -j greeting_job

# With configuration
uv run dagster job execute -m orchestrators.dagster.definitions -j fork_compare_job \
  --config '{"ops": {"fork_compare_all_in_one": {"config": {"conversation_id": "conv-123"}}}}'
```

---

## Pattern 1: Wrapping SDK Calls as Ops

### Problem

Claude Code SDK calls are I/O operations that can fail due to network issues, rate limits, or API errors. Dagster ops provide automatic retry, timeout handling, and observability.

### Solution

Wrap each SDK operation in a dedicated `@op` function:

```python
from dagster import op, OpExecutionContext, In, Out, RetryPolicy

CLAUDE_API_RETRY_POLICY = RetryPolicy(
    max_retries=5,
    delay=1.0,
)

@op(
    name="execute_branch",
    description="Execute a conversation branch with Claude SDK",
    retry_policy=CLAUDE_API_RETRY_POLICY,
    ins={
        "conversation_data": In(dict, description="Conversation data dict"),
        "branch_config": In(dict, description="Branch configuration dict"),
        "checkpoint_data": In(dict, description="Checkpoint data dict"),
    },
    out=Out(dict, description="Branch result dictionary"),
)
def execute_branch_op(
    context: OpExecutionContext,
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    This op calls the Claude API and may take several minutes.
    """
    import asyncio
    from core.executor import execute_branch
    from core.models import Checkpoint, Conversation, ForkConfig

    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    context.log.info(f"Executing branch '{config.name}' with model {config.model}")

    try:
        result = asyncio.run(execute_branch(conversation, config, checkpoint))
        context.log.info(f"Branch '{config.name}' completed in {result.duration_ms}ms")
        return result.model_dump()
    except Exception as e:
        context.log.error(f"Branch '{config.name}' failed: {e}")
        raise
```

### Key Principles

1. **Ops are atomic** - Each op does one thing
2. **Serialize at boundaries** - Use dicts/primitives for op communication
3. **Let ops fail** - Dagster handles retries via `retry_policy`
4. **Use `context.log`** - Logs appear in both terminal and Dagster UI

---

## Pattern 2: Tiered Retry Policies

### Problem

Different operations have different failure characteristics:
- API calls: May hit rate limits, need exponential backoff
- Local operations: Usually succeed or fail fast
- Compute operations: May take variable time

### Solution

Define `RetryPolicy` objects per operation category:

```python
from dagster import RetryPolicy
from dataclasses import dataclass

@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for different operation types."""
    CLAUDE_API_MAX_RETRIES = 5
    CLAUDE_API_DELAY = 1.0   # Initial delay in seconds

    LOCAL_MAX_RETRIES = 3
    LOCAL_DELAY = 0.1        # 100ms

    COMPUTE_MAX_RETRIES = 2
    COMPUTE_DELAY = 0.1

# Retry policies for different op types
LOCAL_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.LOCAL_MAX_RETRIES,
    delay=RetryConfig.LOCAL_DELAY,
)

CLAUDE_API_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.CLAUDE_API_MAX_RETRIES,
    delay=RetryConfig.CLAUDE_API_DELAY,
)

COMPUTE_RETRY_POLICY = RetryPolicy(
    max_retries=RetryConfig.COMPUTE_MAX_RETRIES,
    delay=RetryConfig.COMPUTE_DELAY,
)
```

### Usage in Ops

```python
# Local operation - fast retry
@op(retry_policy=LOCAL_RETRY_POLICY)
def load_conversation_op(context: OpExecutionContext, conversation_id: str) -> dict:
    ...

# Claude API call - exponential-style retry
@op(retry_policy=CLAUDE_API_RETRY_POLICY)
def execute_branch_op(context: OpExecutionContext, ...) -> dict:
    ...
```

### Important Difference from Temporal/Prefect

Dagster's `RetryPolicy` uses a flat `delay` parameter. For exponential backoff, set `backoff=None` and manage delay manually, or use a larger initial `delay` value:

```python
# Prefect: retry_delay_seconds=1, retry_jitter_factor=1.0, exponential backoff built-in
# Temporal: RetryPolicy(initial_interval=..., backoff_coefficient=2.0, ...)
# Dagster: RetryPolicy(max_retries=5, delay=2.0)  -- flat delay, no built-in exponential
```

---

## Pattern 3: Parallel Agent Execution (Dynamic Outputs)

### Problem

When comparing multiple model configurations, running them sequentially is slow. Dagster's `DynamicOutput` enables true parallel execution across multiple workers.

### Solution

Use `DynamicOut` / `DynamicOutput` for fan-out, then `.map()` and `.collect()` for fan-in:

```python
from dagster import DynamicOut, DynamicOutput, graph, op, In, OpExecutionContext

@op(
    name="fan_out_branches",
    ins={
        "conversation_data": In(dict),
        "checkpoint_data": In(dict),
    },
    out=DynamicOut(dict),  # Variable number of outputs
)
def fan_out_branches_op(
    context: OpExecutionContext,
    config: ForkCompareConfig,
    conversation_data: dict,
    checkpoint_data: dict,
):
    """Yield one DynamicOutput per branch - they execute in parallel."""
    import json

    branches = json.loads(config.branches_json)
    context.log.info(f"Fanning out {len(branches)} branches")

    for i, branch_config in enumerate(branches):
        branch_name = branch_config.get("name", f"branch-{i}")
        # mapping_key must be a valid Python identifier
        mapping_key = branch_name.replace("-", "_").replace(" ", "_")

        yield DynamicOutput(
            value={
                "conversation_data": conversation_data,
                "checkpoint_data": checkpoint_data,
                "branch_config": branch_config,
            },
            mapping_key=mapping_key,
        )


@graph
def fork_compare_graph():
    """Execute Fork & Compare with parallel branch execution."""
    # Sequential setup
    conversation_data = load_conversation_op()
    checkpoint_data = create_checkpoint_op(conversation_data)

    # Fan out - yields DynamicOutput for each branch
    branch_contexts = fan_out_branches_op(conversation_data, checkpoint_data)

    # .map() executes execute_single_branch_op for EACH dynamic output in parallel
    branch_results = branch_contexts.map(execute_single_branch_op)

    # .collect() fan-in - waits for all to complete, returns list
    collected = branch_results.collect()

    # Compare final results
    return compare_results_op(collected)
```

### Partial Failure Handling

Unlike Temporal where you catch exceptions in `asyncio.gather`, Dagster handles this in the op itself:

```python
@op(retry_policy=CLAUDE_API_RETRY_POLICY)
def execute_single_branch_op(
    context: OpExecutionContext,
    branch_context: dict,
) -> dict:
    try:
        result = asyncio.run(execute_branch(...))
        return result.model_dump()
    except Exception as e:
        context.log.error(f"Branch failed: {e}")
        # Return error dict instead of raising - allows partial success
        return {
            "branch_name": branch_context["branch_config"]["name"],
            "status": "error",
            "error": str(e),
            "messages": [],
            "duration_ms": 0,
        }
```

### Benefits

- **Speed**: N branches execute in ~1x time instead of Nx time
- **Isolation**: One branch failure doesn't stop others (with error dict pattern)
- **Observability**: Each branch is a separate op execution in the Dagster UI
- **Dynamic**: Number of branches doesn't need to be known at compile time

---

## Pattern 4: Op Configuration with Config Classes

### Problem

Dagster ops need to accept configuration (like which model to use, which conversation to load) without hardcoding values. Dagster provides `Config` classes for type-safe configuration.

### Solution

Use `Config` subclasses to define typed op configuration:

```python
from dagster import Config, op, OpExecutionContext

class ForkCompareConfig(Config):
    """Configuration for the fork_compare job."""
    conversation_id: str
    fork_at_step: int
    branches_json: str  # JSON-encoded list of branch configs (Dagster can't pass lists natively)

@op
def fork_compare_all_in_one_op(
    context: OpExecutionContext,
    config: ForkCompareConfig,  # Injected by Dagster
) -> dict:
    import json
    branches = json.loads(config.branches_json)
    context.log.info(f"Processing {config.conversation_id} with {len(branches)} branches")
    ...
```

### Passing Config in run_config

```python
result = my_job.execute_in_process(
    run_config={
        "ops": {
            "fork_compare_all_in_one": {
                "config": {
                    "conversation_id": "conv-123",
                    "fork_at_step": 3,
                    "branches_json": json.dumps([
                        {"name": "sonnet", "model": "claude-sonnet-4-20250514"},
                        {"name": "opus", "model": "claude-opus-4-20250514"},
                    ]),
                }
            }
        }
    }
)
```

### Note: Lists in Config

Dagster Config classes don't natively support list fields well when passing via `run_config`. The workaround is to JSON-encode lists as strings:

```python
# Workaround: JSON-encode lists
class MyConfig(Config):
    branches_json: str  # Pass as json.dumps([...])

# Not ideal but works:
class MyConfig(Config):
    branches: list[str]  # Works for simple types
```

---

## Pattern 5: Graphs vs Jobs vs the `@job` Decorator

### Problem

Dagster has three ways to define workflows: `@job`, `@graph` + `.to_job()`, and inline `@job` with direct op calls. When should you use each?

### Solution

| Approach | When to Use |
|----------|------------|
| `@job` decorator | Simple, single-purpose jobs with no reuse |
| `@graph` + `.to_job()` | When the same workflow needs multiple job variants |
| `@graph` + `.to_job()` x N | When you need different configs per environment (dev/prod) |

```python
# Simple job
@job
def greeting_job():
    log_greeting(greet())

# Reusable graph → multiple jobs
@graph
def fork_compare_graph():
    ...

# Create different jobs from the same graph
fork_compare_job = fork_compare_graph.to_job(
    name="fork_compare_job",
    description="Sequential execution",
)

fork_compare_parallel_job = fork_compare_parallel_graph.to_job(
    name="fork_compare_parallel_job",
    description="Parallel execution via dynamic outputs",
)
```

### The Definitions Object

All jobs, assets, and resources must be registered in a central `Definitions` object:

```python
# definitions.py
from dagster import Definitions
from orchestrators.dagster.jobs import greeting_job
from orchestrators.dagster.graph import fork_compare_job, fork_compare_parallel_job

defs = Definitions(
    jobs=[greeting_job, fork_compare_job, fork_compare_parallel_job],
)
```

This is required for the `dagster dev` server to discover your jobs.

---

## Pattern 6: Async in Dagster (Sync Wrapper)

### Problem

Dagster ops are synchronous by default. The Claude Code SDK is async. You need to bridge this gap without blocking the event loop.

### Solution

Use `asyncio.run()` inside ops, and `loop.run_in_executor()` in the client:

```python
# In ops.py - wrap async in sync
@op
def execute_branch_op(context: OpExecutionContext, ...) -> dict:
    import asyncio
    from core.executor import execute_branch

    # asyncio.run() creates a new event loop for this call
    result = asyncio.run(execute_branch(conversation, config, checkpoint))
    return result.model_dump()


# In client.py - run Dagster job without blocking the outer async loop
async def run_fork_compare_job(request_dict: dict) -> dict:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _execute_job_sync(run_config, run_id),
    )
    return result

def _execute_job_sync(run_config: dict, run_id: str) -> dict:
    result = fork_compare_job.execute_in_process(
        run_config=run_config,
        raise_on_error=False,
    )
    if not result.success:
        raise RuntimeError("Job execution failed")
    return result.output_for_node("fork_compare_all_in_one")
```

### Why This Pattern

- `asyncio.run()` in ops works because Dagster runs each op in its own context
- `run_in_executor()` prevents blocking the FastAPI event loop when calling Dagster
- This is a known Dagster limitation - native async op support is limited

---

## Pattern 7: Pydantic Model Serialization

### Problem

Dagster ops communicate via typed inputs/outputs. Pydantic models don't serialize automatically across op boundaries - Dagster expects simple Python types.

### Solution

Always convert to/from dicts at op boundaries:

```python
# In graph/job - serialize before calling op
@op
def load_conversation_op(context: OpExecutionContext, conversation_id: str) -> dict:
    from core.conversation import load_conversation
    from core.models import Conversation

    conversation = load_conversation(conversation_id)
    return conversation.model_dump()  # Convert to dict

# In next op - deserialize at start
@op
def create_checkpoint_op(
    context: OpExecutionContext,
    conversation_data: dict,  # Receive as dict
    step: int,
) -> dict:
    from core.models import Conversation

    conversation = Conversation.model_validate(conversation_data)  # Convert from dict
    # ... do work ...
    return checkpoint.model_dump()  # Convert back to dict
```

### Why This Works

- Dicts are Dagster-serializable (required for UI/persistence)
- Pydantic validation catches data issues at deserialization
- Op type annotations (`In(dict)`, `Out(dict)`) are explicit about the contract

---

## Gotchas & Lessons Learned

### 1. mapping_key Must Be a Valid Python Identifier

When using `DynamicOutput`, the `mapping_key` must only contain letters, numbers, and underscores:

```python
# BAD - hyphens are not allowed
yield DynamicOutput(value=..., mapping_key="my-branch")

# GOOD - convert to valid identifier
mapping_key = branch_name.replace("-", "_").replace(" ", "_")
yield DynamicOutput(value=..., mapping_key=mapping_key)
```

### 2. Op Context Logging vs Python Logging

Always use `context.log` inside ops - it integrates with the Dagster UI:

```python
# BAD - won't appear in Dagster UI
import logging
logger = logging.getLogger(__name__)
logger.info("Running branch...")

# GOOD - appears in Dagster UI run view
context.log.info("Running branch...")
```

For code that runs outside op context (e.g., helper functions), use a fallback:

```python
def _get_logger(context=None):
    if context is not None:
        return context.log
    return logging.getLogger("orchestrators.dagster.ops")
```

### 3. Definitions Registration Is Required

Every job, asset, and resource must be in the `Definitions` object - unlike Prefect where you just call the flow:

```python
# REQUIRED for dagster dev to find your jobs
defs = Definitions(jobs=[greeting_job, fork_compare_job])
```

### 4. In-Process Mode vs Server Mode

Dagster supports two execution modes:

- **In-process** (`execute_in_process`): Runs locally, no server needed. Good for testing and simple use cases.
- **Server mode** (`dagster dev`): Requires server, provides UI, persistent run history, scheduling.

Unlike Prefect's ephemeral mode, Dagster's in-process mode doesn't provide a web UI. Start the dev server when you need visibility.

### 5. result.output_for_node() Uses the Op Name

When extracting output after `execute_in_process`, use the op's registered name (not the function name):

```python
# Op defined as:
@op(name="fork_compare_all_in_one")
def fork_compare_all_in_one_op(...):
    ...

# Get output by NAME (not function name)
output = result.output_for_node("fork_compare_all_in_one")  # CORRECT
output = result.output_for_node("fork_compare_all_in_one_op")  # WRONG
```

### 6. Import Errors with Relative Imports

Running Dagster files directly fails with relative imports. Always run from project root:

```bash
# WRONG
cd orchestrators/dagster && python jobs.py

# CORRECT
cd /project/root && uv run python -m orchestrators.dagster.client
```

---

## When to Use Dagster

### Good Fit

- **Data pipeline patterns** - Dagster was built for data assets/pipelines; native asset tracking
- **Graph-based workflows** - Complex op DAGs with explicit dependency visualization
- **Dynamic parallelism** - `DynamicOutput` for variable-length parallel execution
- **Production systems** - Built-in UI, run history, schedules, and sensors
- **Long-running workflows** - Persistent state via Dagster server

### Consider Prefect Instead

- **Rapid prototyping** - Prefect's ephemeral mode requires zero setup
- **Simple retry logic** - Prefect's `@task` decorator is simpler for basic retries
- **Python-native feel** - Prefect flows feel more like regular Python functions
- **No server required** - Prefect works fully offline without UI setup

### Consider Temporal Instead

- **Strong durability requirements** - Temporal's replay-based execution survives crashes
- **Long-running multi-turn agents** - Temporal excels at workflows spanning hours/days
- **Complex retry/timeout policies** - Temporal's `RetryPolicy` is more expressive
- **Multi-language workers** - Temporal supports Go, Java, TypeScript alongside Python

### Migration Path

1. Start with direct SDK calls for prototyping
2. Add Prefect for retry logic and parallel execution
3. Move to Dagster when you need asset tracking, UI, or complex DAGs
4. Consider Temporal if you need guaranteed durability or crash recovery

---

## Comparison with Temporal and Prefect

| Aspect | Dagster | Prefect | Temporal |
|--------|---------|---------|----------|
| **Setup** | Server for UI, in-process without | Zero config (ephemeral) | Always requires server |
| **Core Unit** | Op (`@op`) | Task (`@task`) | Activity (`@activity.defn`) |
| **Orchestration** | Graph/Job (`@graph`, `@job`) | Flow (`@flow`) | Workflow class (`@workflow.defn`) |
| **Parallelism** | `DynamicOutput` + `.map()` | `.submit()` + `wait()` | `asyncio.gather()` |
| **Retry Config** | `RetryPolicy(max_retries, delay)` | Task decorator args | `RetryPolicy` with backoff coefficient |
| **Logging** | `context.log` | `get_run_logger()` | Standard Python logging |
| **Serialization** | Dict at boundaries | Dict at boundaries | Dict at boundaries |
| **Async Support** | Sync wrapper required | Native async | Native async |
| **Config Injection** | `Config` class (typed) | Flow/task args | Workflow input |
| **Durability** | Optional (with server) | Optional (with server) | Always durable |
| **Primary Use Case** | Data pipelines, asset tracking | General workflow orchestration | Long-running reliable workflows |

### Key API Differences

**Parallel Execution:**
```python
# Dagster - DynamicOutput fan-out/fan-in
branch_outputs = fan_out_op()                   # yields DynamicOutput
results = branch_outputs.map(execute_branch_op)  # parallel map
collected = results.collect()                    # fan-in

# Prefect - submit + wait
futures = [execute_branch_task.submit(...) for _ in branches]
wait(futures)
results = [f.result() for f in futures]

# Temporal - asyncio.gather
tasks = [workflow.execute_activity(execute_branch, ...) for _ in branches]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Configuration:**
```python
# Dagster - Config class with run_config dict
class MyConfig(Config):
    conversation_id: str
run_config = {"ops": {"my_op": {"config": {"conversation_id": "123"}}}}

# Prefect - Flow/task arguments
@flow
async def my_flow(conversation_id: str): ...

# Temporal - Workflow input dict
await client.start_workflow(MyWorkflow.run, {"conversation_id": "123"})
```

**State Checking:**
```python
# Dagster - result object from execute_in_process
if result.success:
    output = result.output_for_node("my_op")

# Prefect - future state methods
if future.state.is_completed():
    output = future.result()

# Temporal - exception handling in asyncio.gather
if isinstance(result, Exception):
    # handle failure
```

---

## Further Reading

- [Dagster Documentation](https://docs.dagster.io/)
- [Dagster Ops Guide](https://docs.dagster.io/concepts/ops-jobs-graphs/ops)
- [Dagster Dynamic Outputs](https://docs.dagster.io/concepts/ops-jobs-graphs/dynamic-graphs)
- [Dagster Config & Resources](https://docs.dagster.io/concepts/configuration/config-schema)
- [Dagster Testing](https://docs.dagster.io/concepts/testing)
- [Claude Code SDK Documentation](https://docs.anthropic.com/claude-code-sdk)
