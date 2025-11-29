# Prefect Integration Patterns for Claude Code SDK

This document captures patterns and lessons learned from integrating Prefect workflow orchestration with the Claude Code SDK for the agent-replay-lab project.

## Quick Start

### Prerequisites

```bash
# Install Prefect (with uv)
uv add prefect

# Or with pip
pip install prefect
```

That's it! Prefect 3.x runs in **ephemeral mode** by default - no server setup required.

### Basic Project Structure

```
orchestrators/prefect/
├── __init__.py      # Module exports
├── tasks.py         # Task definitions (@task decorated functions)
├── flows.py         # Flow definitions (@flow decorated functions)
└── client.py        # Client utilities for running flows
```

### Minimal Working Example

```python
# tasks.py
from prefect import task

@task(
    name="call_claude_api",
    retries=3,
    retry_delay_seconds=1,
)
async def call_claude_task(prompt: str) -> str:
    """Task wrapping Claude API call."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()
    response = await client.messages.create(...)
    return response.content[0].text

# flows.py
from prefect import flow
from .tasks import call_claude_task

@flow(name="simple-agent-flow")
async def SimpleAgentFlow(prompt: str) -> str:
    return await call_claude_task(prompt)

# Run it
result = await SimpleAgentFlow("Hello!")
```

### Optional: With Prefect Server

For persistence, monitoring, and the web UI:

```bash
# Terminal 1: Start server
uv run prefect server start

# Terminal 2: Configure and run
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
uv run python -m orchestrators.prefect.flows
```

Access the UI at http://localhost:4200

---

## Pattern 1: Wrapping SDK Calls as Tasks

### Problem

Claude Code SDK calls are I/O operations that can fail due to network issues, rate limits, or API errors. Prefect tasks provide automatic retry, timeout handling, and observability.

### Solution

Wrap each SDK operation in a dedicated task function:

```python
from prefect import task
from prefect.logging import get_run_logger

@task(
    name="execute_branch",
    description="Execute a conversation branch with Claude SDK",
    retries=5,
    retry_delay_seconds=1,
    retry_jitter_factor=1.0,  # Add randomness to prevent thundering herd
    timeout_seconds=300,       # 5 minutes
)
async def execute_branch_task(
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    This task wraps the Claude Code SDK executor and handles:
    - Conversation context restoration
    - Model selection
    - Message injection
    - Result capture
    """
    logger = get_run_logger()

    from core.executor import execute_branch
    from core.models import Conversation, ForkConfig, Checkpoint

    # Deserialize from flow-safe dicts
    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    logger.info(f"Executing branch '{config.name}' with model {config.model}")

    # Execute the actual SDK call
    result = await execute_branch(conversation, config, checkpoint)

    logger.info(f"Branch '{config.name}' completed in {result.duration_ms}ms")

    # Serialize back for flow
    return result.model_dump()
```

### Key Principles

1. **Tasks are atomic** - Each task does one thing
2. **Serialize at boundaries** - Use dicts/primitives for flow communication
3. **Let tasks fail** - Prefect handles retries automatically
4. **Use logging** - Prefect captures logs and shows them in the UI

---

## Pattern 2: Tiered Retry Configuration

### Problem

Different operations have different failure characteristics:
- API calls: May hit rate limits, need exponential backoff
- Local operations: Usually succeed or fail fast
- Compute operations: May take variable time

### Solution

Define retry configurations per operation category using dataclasses:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RetryConfig:
    """Retry configuration for different task types."""

    # For Claude API calls: exponential backoff for rate limits
    CLAUDE_API_RETRIES = 5
    CLAUDE_API_RETRY_DELAY = 1  # Initial delay in seconds
    CLAUDE_API_RETRY_JITTER = 1.0  # Random jitter factor
    CLAUDE_API_EXPONENTIAL_BACKOFF = 2  # Backoff coefficient

    # For local operations: quick retries for transient issues
    LOCAL_RETRIES = 3
    LOCAL_RETRY_DELAY = 0.1  # 100ms
    LOCAL_RETRY_JITTER = 0.5

    # For comparison/analysis: minimal retries (pure computation)
    COMPUTE_RETRIES = 2
    COMPUTE_RETRY_DELAY = 0.1

@dataclass(frozen=True)
class TaskTimeouts:
    """Timeout configurations for different task types."""

    LOCAL_TIMEOUT = 30       # seconds
    CLAUDE_API_TIMEOUT = 300 # 5 minutes
    COMPUTE_TIMEOUT = 30     # seconds
```

### Usage in Tasks

```python
@task(
    name="load_conversation",
    retries=RetryConfig.LOCAL_RETRIES,
    retry_delay_seconds=RetryConfig.LOCAL_RETRY_DELAY,
    retry_jitter_factor=RetryConfig.LOCAL_RETRY_JITTER,
    timeout_seconds=TaskTimeouts.LOCAL_TIMEOUT,
)
def load_conversation_task(conversation_id: str) -> dict:
    """Load a conversation - local operation with quick retries."""
    ...

@task(
    name="execute_branch",
    retries=RetryConfig.CLAUDE_API_RETRIES,
    retry_delay_seconds=RetryConfig.CLAUDE_API_RETRY_DELAY,
    retry_jitter_factor=RetryConfig.CLAUDE_API_RETRY_JITTER,
    timeout_seconds=TaskTimeouts.CLAUDE_API_TIMEOUT,
)
async def execute_branch_task(...) -> dict:
    """Execute branch - API call with exponential backoff."""
    ...
```

### Custom Retry Conditions

For fine-grained control, use `retry_condition_fn`:

```python
# Errors that should NOT trigger retries
NON_RETRYABLE_ERRORS = (
    ValueError,   # Bad input won't fix itself
    TypeError,    # Type errors are programming bugs
    KeyError,     # Missing keys indicate data issues
)

def should_retry(exc: Exception, retries: int) -> bool:
    """Determine if an exception should trigger a retry."""
    if isinstance(exc, NON_RETRYABLE_ERRORS):
        return False
    return retries > 0

@task(
    retries=5,
    retry_condition_fn=should_retry,
)
async def execute_branch_task(...):
    ...
```

---

## Pattern 3: Parallel Agent Execution (Task Mapping)

### Problem

When comparing multiple model configurations or approaches, running them sequentially is slow. We need parallel execution with proper error handling.

### Solution

Use `.submit()` for parallel task execution with the fan-out/fan-in pattern:

```python
from prefect import flow
from prefect.futures import wait

@flow(name="fork-compare-flow")
async def ForkCompareFlow(request_dict: dict) -> dict:
    from core.models import ReplayRequest

    request = ReplayRequest.model_validate(request_dict)

    # Step 1-2: Sequential setup (load conversation, create checkpoint)
    conversation_data = load_conversation_task(request.conversation_id)
    checkpoint_data = create_checkpoint_task(conversation_data, request.fork_at_step)

    # Step 3: PARALLEL branch execution using .submit()
    branch_futures = []
    for branch_config in request.branches:
        # .submit() returns immediately with a Future
        future = execute_branch_task.submit(
            conversation_data,
            branch_config.model_dump(),
            checkpoint_data,
        )
        branch_futures.append((branch_config.name, future))

    # Wait for all futures to complete
    futures_only = [f for _, f in branch_futures]
    wait(futures_only)

    # Process results with partial failure handling
    branch_results = []
    for branch_name, future in branch_futures:
        state = future.state
        if state.is_completed():
            branch_results.append(future.result())
        elif state.is_failed():
            branch_results.append({
                "branch_name": branch_name,
                "status": "error",
                "error": str(state.result(raise_on_failure=False)),
            })

    # Step 4: Compare results
    comparison = compare_results_task(branch_results)

    return {
        "branches": branch_results,
        "comparison_summary": comparison,
    }
```

### Key Points

1. **`.submit()` for parallelism** - Returns a Future immediately
2. **`wait()` for synchronization** - Waits for all futures to complete
3. **Check state methods** - Use `state.is_completed()` and `state.is_failed()` (not isinstance!)
4. **Handle partial failures** - Don't let one failure crash the whole flow

### Benefits

- **Speed**: N branches execute in ~1x time instead of Nx time
- **Isolation**: One branch failure doesn't stop others
- **Observability**: Each branch is a separate task in Prefect UI

---

## Pattern 4: Proper State Handling in Prefect 3.x

### Problem

Prefect 3.x state handling differs from traditional Python patterns. `Completed` and `Failed` are factory functions, not classes.

### Solution

Use state methods instead of isinstance checks:

```python
from prefect.futures import wait

def process_branch_futures(branch_futures):
    """Process futures with proper state handling."""
    results = []

    for branch_name, future in branch_futures:
        state = future.state

        # CORRECT: Use state methods
        if state.is_completed():
            results.append(future.result())
        elif state.is_failed():
            error = state.result(raise_on_failure=False)
            results.append(create_error_result(branch_name, error))
        else:
            # Handle Pending, Running, etc.
            results.append(create_error_result(
                branch_name,
                RuntimeError(f"Unexpected state: {state}")
            ))

    return results
```

### What NOT to Do

```python
from prefect.states import Completed, Failed

# WRONG - This will fail!
# Completed and Failed are functions, not classes
if isinstance(state, Completed):  # TypeError!
    ...

# WRONG - Don't try to use them as types
if type(state) == Completed:  # Won't work
    ...
```

---

## Pattern 5: Pydantic Model Serialization

### Problem

Prefect flows should work with simple, serializable types. Pydantic models need explicit serialization at task boundaries.

### Solution

Always convert to/from dicts at task boundaries:

```python
# In flow - serialize before calling task
@flow
async def MyFlow(request: dict) -> dict:
    # Tasks receive/return dicts
    result = await my_task(model.model_dump())
    return result

# In task - deserialize at start, serialize at end
@task
async def my_task(data: dict) -> dict:
    # Convert from dict at start
    model = MyModel.model_validate(data)

    # ... do work ...

    # Convert back to dict at end
    return result.model_dump()
```

### Why This Works

- Dicts are JSON-serializable (Prefect requirement for some features)
- Pydantic validation catches data issues early
- Type hints still work for development
- Works seamlessly with both ephemeral and server modes

---

## Gotchas & Lessons Learned

### 1. Completed/Failed Are Functions, Not Classes

**The Bug:**
```python
from prefect.states import Completed
if isinstance(state, Completed):  # TypeError!
```

**The Fix:**
```python
if state.is_completed():  # Use the method!
```

This is the most common mistake when migrating from other frameworks or older Prefect versions.

### 2. Logging in Tasks/Flows

Use Prefect's run logger for proper log capture:

```python
from prefect.logging import get_run_logger

def _get_logger():
    """Get logger with fallback for non-flow contexts."""
    try:
        return get_run_logger()
    except Exception:
        return logging.getLogger(__name__)

@task
def my_task():
    logger = _get_logger()
    logger.info("This shows in Prefect UI!")
```

### 3. Lazy Imports in Tasks

Import heavy dependencies inside task functions to speed up worker startup:

```python
# GOOD - lazy import
@task
async def execute_branch_task(data: dict) -> dict:
    from core.executor import execute_branch  # Import here
    return await execute_branch(...)

# AVOID - eager import (slows startup, may cause issues)
from core.executor import execute_branch  # Don't do this at module level
```

### 4. Rich Console Logging Conflicts

When running many flows sequentially (e.g., in tests), Prefect's Rich console logger may have issues with file handles. This is a known issue that doesn't affect results:

```
ValueError: I/O operation on closed file.
```

This typically happens during shutdown and can be safely ignored in test output.

### 5. Ephemeral vs Server Mode

- **Ephemeral mode** (default): Flows run locally, no persistence
- **Server mode**: Requires `prefect server start`, provides UI and persistence

Most development and testing works fine in ephemeral mode. Only use server mode when you need:
- Persistent run history
- Web UI for monitoring
- Scheduled runs
- Team collaboration

---

## Comparison with Temporal Patterns

| Aspect | Prefect | Temporal |
|--------|---------|----------|
| **Setup** | Zero config (ephemeral) | Requires server |
| **Tasks vs Activities** | `@task` decorator | `@activity.defn` decorator |
| **Flows vs Workflows** | `@flow` decorator | `@workflow.defn` class |
| **Parallelism** | `.submit()` + `wait()` | `asyncio.gather()` |
| **Retry Config** | Task decorator args | RetryPolicy objects |
| **State Checking** | `state.is_completed()` | `isinstance(state, Completed)` |
| **Serialization** | Dict at boundaries | Dict at boundaries |
| **Durability** | Optional (with server) | Always durable |
| **Complexity** | Lower | Higher |

### Key Differences

1. **Execution Model**:
   - Prefect: Direct Python execution
   - Temporal: Deterministic replay-based execution

2. **Parallelism API**:
   ```python
   # Prefect
   future = task.submit(...)
   wait([future])
   result = future.result()

   # Temporal
   task = workflow.execute_activity(...)
   results = await asyncio.gather(*tasks)
   ```

3. **State Handling**:
   ```python
   # Prefect - use methods
   if state.is_completed():
       ...

   # Temporal - use isinstance
   if isinstance(result, Exception):
       ...
   ```

---

## When to Use Prefect

### Good Fit

- **Rapid prototyping** - Zero-config ephemeral mode
- **Python-native workflows** - Decorators feel natural
- **Simple parallel execution** - `.submit()` is easy to use
- **Development/testing** - No server setup required
- **Short-lived workflows** - Don't need durability

### Consider Temporal Instead

- **Long-running workflows** - Hours or days of execution
- **Strong durability requirements** - Can't lose work on crashes
- **Complex retry/timeout policies** - Need fine-grained control
- **Multi-language support** - Need workers in different languages
- **Production systems** - Need guaranteed exactly-once execution

### Migration Path

1. Start with Prefect ephemeral mode for prototyping
2. Add Prefect server when you need visibility/persistence
3. If you hit Prefect's limits (durability, complexity), consider Temporal
4. Both use similar patterns (tasks/activities, flows/workflows) so migration is manageable

---

## Further Reading

- [Prefect 3.x Documentation](https://docs.prefect.io/)
- [Prefect Tasks Guide](https://docs.prefect.io/latest/concepts/tasks/)
- [Prefect Flows Guide](https://docs.prefect.io/latest/concepts/flows/)
- [Prefect State Management](https://docs.prefect.io/latest/concepts/states/)
- [Claude Code SDK Documentation](https://docs.anthropic.com/claude-code-sdk)
