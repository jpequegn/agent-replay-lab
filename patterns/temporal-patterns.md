# Temporal Integration Patterns for Claude Code SDK

This document captures patterns and lessons learned from integrating Temporal workflow orchestration with the Claude Code SDK for the agent-replay-lab project.

## Quick Start

### Prerequisites

```bash
# Install Temporal CLI
brew install temporal

# Start local development server
temporal server start-dev

# Install Python dependencies
pip install temporalio
```

### Basic Project Structure

```
orchestrators/temporal/
├── __init__.py
├── activities.py    # Atomic work units
├── workflows.py     # Orchestration logic
├── worker.py        # Worker configuration
└── client.py        # Client utilities
```

### Minimal Working Example

```python
# activities.py
from temporalio import activity

@activity.defn
async def call_claude_api(prompt: str) -> str:
    """Activity wrapping Claude API call."""
    # Your Claude SDK call here
    return response

# workflows.py
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class SimpleAgentWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        return await workflow.execute_activity(
            call_claude_api,
            prompt,
            start_to_close_timeout=timedelta(minutes=5),
        )
```

---

## Pattern 1: Wrapping SDK Calls as Activities

### Problem

Claude Code SDK calls are I/O operations that can fail due to network issues, rate limits, or API errors. Temporal activities provide automatic retry, timeout handling, and observability.

### Solution

Wrap each SDK operation in a dedicated activity function:

```python
from temporalio import activity
from datetime import timedelta

@activity.defn
async def execute_branch_activity(
    conversation_data: dict,
    branch_config: dict,
    checkpoint_data: dict,
) -> dict:
    """Execute a single conversation branch.

    This activity wraps the Claude Code SDK executor and handles:
    - Conversation context restoration
    - Model selection
    - Message injection
    - Result capture
    """
    from core.executor import execute_branch
    from core.models import Conversation, ForkConfig, Checkpoint

    # Deserialize from workflow-safe dicts
    conversation = Conversation.model_validate(conversation_data)
    config = ForkConfig.model_validate(branch_config)
    checkpoint = Checkpoint.model_validate(checkpoint_data)

    # Execute the actual SDK call
    result = await execute_branch(conversation, config, checkpoint)

    # Serialize back for workflow
    return result.model_dump()
```

### Key Principles

1. **Activities are atomic** - Each activity does one thing
2. **Serialize at boundaries** - Use dicts/primitives for workflow communication
3. **Let activities fail** - Temporal handles retries automatically
4. **Use heartbeats for long operations** - Prevent premature timeouts

---

## Pattern 2: Tiered Retry Policies

### Problem

Different operations have different failure characteristics:
- API calls: May hit rate limits, need exponential backoff
- Local operations: Usually succeed or fail fast
- Compute operations: May take variable time

### Solution

Define retry policies per operation category:

```python
from temporalio.common import RetryPolicy
from datetime import timedelta

# For Claude API calls - exponential backoff for rate limits
CLAUDE_API_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=5,
    non_retryable_error_types=[
        "InvalidRequestError",      # Bad input won't fix itself
        "AuthenticationError",      # Need human intervention
        "InsufficientQuotaError",   # Need human intervention
    ],
)

# For local operations - quick retries
LOCAL_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(milliseconds=100),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)

# For compute-heavy operations
COMPUTE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)
```

### Usage in Workflows

```python
@workflow.run
async def run(self, request: dict) -> dict:
    # Local operation - fast retry
    conversation = await workflow.execute_activity(
        load_conversation_activity,
        request["conversation_id"],
        start_to_close_timeout=timedelta(seconds=30),
        retry_policy=LOCAL_RETRY_POLICY,
    )

    # API call - exponential backoff
    result = await workflow.execute_activity(
        execute_branch_activity,
        args=[conversation, config, checkpoint],
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=CLAUDE_API_RETRY_POLICY,
    )
```

---

## Pattern 3: Parallel Agent Execution

### Problem

When comparing multiple model configurations or approaches, running them sequentially is slow. We need parallel execution with proper error handling.

### Solution

Use `asyncio.gather` with `return_exceptions=True`:

```python
@workflow.defn
class ForkCompareWorkflow:
    @workflow.run
    async def run(self, request_dict: dict) -> dict:
        request = ReplayRequest.model_validate(request_dict)

        # Step 1-2: Load conversation and create checkpoint (sequential)
        conversation = await workflow.execute_activity(...)
        checkpoint = await workflow.execute_activity(...)

        # Step 3: Execute branches IN PARALLEL
        branch_tasks = []
        for branch_config in request.branches:
            task = workflow.execute_activity(
                execute_branch_activity,
                args=[
                    conversation.model_dump(),
                    branch_config.model_dump(),
                    checkpoint.model_dump(),
                ],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=CLAUDE_API_RETRY_POLICY,
            )
            branch_tasks.append(task)

        # Wait for all branches, capturing any errors
        results = await asyncio.gather(*branch_tasks, return_exceptions=True)

        # Step 4: Process results, converting exceptions to error results
        branch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                branch_results.append({
                    "branch_name": request.branches[i].name,
                    "status": "error",
                    "error": str(result),
                })
            else:
                branch_results.append(result)

        # Step 5: Compare results
        comparison = await workflow.execute_activity(
            compare_results_activity,
            branch_results,
            start_to_close_timeout=timedelta(seconds=30),
        )

        return comparison
```

### Benefits

- **Speed**: N branches execute in ~1x time instead of Nx time
- **Isolation**: One branch failure doesn't stop others
- **Observability**: Each branch is a separate activity in Temporal UI

---

## Pattern 4: Activity Timeout Configuration

### Problem

Different operations need different timeout configurations. Too short = premature failures. Too long = zombie activities.

### Solution

Create a timeout configuration class:

```python
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class ActivityTimeouts:
    """Centralized timeout configuration for activities."""

    # Fast local operations
    LOCAL_QUICK = timedelta(seconds=30)

    # File I/O operations
    FILE_IO = timedelta(minutes=1)

    # Claude API calls (can be slow)
    CLAUDE_API = timedelta(minutes=10)

    # Long-running compute
    COMPUTE_HEAVY = timedelta(minutes=30)

    # Heartbeat interval for long operations
    HEARTBEAT = timedelta(seconds=30)
```

### Usage

```python
TIMEOUTS = ActivityTimeouts()

# In workflow
result = await workflow.execute_activity(
    execute_branch_activity,
    args=[...],
    start_to_close_timeout=TIMEOUTS.CLAUDE_API,
    heartbeat_timeout=TIMEOUTS.HEARTBEAT,
    retry_policy=CLAUDE_API_RETRY_POLICY,
)
```

---

## Pattern 5: Pydantic Model Serialization

### Problem

Temporal workflows must be deterministic and serializable. Pydantic models don't serialize automatically across workflow boundaries.

### Solution

Always convert to/from dicts at activity boundaries:

```python
# In workflow - serialize before calling activity
await workflow.execute_activity(
    my_activity,
    args=[model.model_dump()],  # Convert to dict
    ...
)

# In activity - deserialize at start
@activity.defn
async def my_activity(data: dict) -> dict:
    model = MyModel.model_validate(data)  # Convert from dict

    # ... do work ...

    return result.model_dump()  # Convert back to dict
```

### Why This Works

- Dicts are JSON-serializable (Temporal requirement)
- Pydantic validation catches data issues early
- Type hints still work for development

---

## Gotchas & Lessons Learned

### 1. Sandbox Restrictions in Testing

Temporal runs workflows in a sandbox that restricts certain operations. In tests, you may need to configure passthrough modules:

```python
from temporalio.worker import SandboxedWorkflowRunner, SandboxRestrictions

def create_test_sandbox_runner():
    """Create a sandbox runner with relaxed restrictions for testing."""
    default = SandboxRestrictions.default
    passthrough = set(default.passthrough_modules)
    passthrough.update([
        "core",
        "core.models",
        "core.conversation",
        "orchestrators.temporal.activities",
    ])
    return SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions(
            passthrough_modules=frozenset(passthrough),
            invalid_modules=default.invalid_modules,
            invalid_module_members=default.invalid_module_members,
        )
    )
```

### 2. Workflow Code Must Be Deterministic

**Don't do this in workflows:**
```python
# BAD - non-deterministic
import random
value = random.randint(1, 100)

# BAD - non-deterministic
from datetime import datetime
now = datetime.now()

# BAD - I/O in workflow
result = requests.get("https://api.example.com")
```

**Do this instead:**
```python
# GOOD - use workflow APIs
import workflow
value = workflow.random().randint(1, 100)

# GOOD - use workflow time
now = workflow.now()

# GOOD - use activities for I/O
result = await workflow.execute_activity(fetch_data_activity, ...)
```

### 3. Activity Imports Should Be Lazy

Import heavy dependencies inside activity functions, not at module level:

```python
# GOOD - lazy import
@activity.defn
async def execute_branch_activity(data: dict) -> dict:
    from core.executor import execute_branch  # Import here
    return await execute_branch(...)

# BAD - eager import (slows worker startup)
from core.executor import execute_branch  # Don't do this at module level

@activity.defn
async def execute_branch_activity(data: dict) -> dict:
    return await execute_branch(...)
```

### 4. Use Time-Skipping in Tests

For fast tests, use Temporal's time-skipping test environment:

```python
@pytest.fixture
async def temporal_env():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env
```

This makes workflows that use `workflow.sleep()` or timeouts run instantly in tests.

### 5. Handle Partial Failures Gracefully

When running parallel activities, some may succeed while others fail. Design your workflow to handle this:

```python
results = await asyncio.gather(*tasks, return_exceptions=True)

successful = [r for r in results if not isinstance(r, Exception)]
failed = [r for r in results if isinstance(r, Exception)]

# Decide what to do:
# - Fail entire workflow if any failed?
# - Return partial results?
# - Log failures and continue?
```

---

## When to Use Temporal

### Good Fit

- **Long-running agent workflows** - Multi-turn conversations, tool use loops
- **Parallel execution** - Comparing models, A/B testing prompts
- **Reliability requirements** - Production systems that can't lose work
- **Complex orchestration** - Multi-step workflows with dependencies
- **Visibility needs** - When you need to debug/monitor agent behavior

### Not Needed

- **Simple single API calls** - Just call the API directly
- **Low-latency requirements** - Temporal adds overhead (~100ms)
- **Stateless operations** - No need for durability
- **Prototype/experimentation** - Start simple, add Temporal later

### Migration Path

1. Start with direct SDK calls
2. Add retry logic manually when you hit reliability issues
3. When you need parallel execution or complex workflows, introduce Temporal
4. Gradually move activities to Temporal as reliability requirements grow

---

## Further Reading

- [Temporal Python SDK Documentation](https://docs.temporal.io/develop/python)
- [Claude Code SDK Documentation](https://docs.anthropic.com/claude-code-sdk)
- [Temporal Best Practices](https://docs.temporal.io/develop/python/core-application)
- [Testing Temporal Workflows](https://docs.temporal.io/develop/python/testing)
