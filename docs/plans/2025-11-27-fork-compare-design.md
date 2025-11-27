# Agent Replay Lab - Fork & Compare Design

**Date:** 2025-11-27
**Status:** Approved
**Project:** agent-replay-lab

---

## Overview

### Purpose

Compare Temporal, Prefect, and Dagster for Claude Code agent orchestration through hands-on implementation of the same workflow.

### Core Workflow - "Fork & Compare"

1. Load a past conversation from episodic memory
2. Replay it to a chosen checkpoint (step N)
3. Fork into multiple branches with variations:
   - Different follow-up messages ("what if user asked X instead?")
   - Different models (Sonnet vs Haiku vs Opus)
   - Different system prompts or settings
4. Execute all branches in parallel
5. Collect and compare results (structured diff/comparison)

### Deliverables

- 3 working prototypes (Temporal, Prefect, Dagster)
- Integration pattern documentation for each
- Comparison matrix based on real implementation experience
- Reusable code/patterns for future projects

### Success Criteria

- Can replay any conversation from episodic memory archives
- Can fork at any step with configurable variations
- Parallel execution works correctly
- Results are comparable (structured output)
- Clear winner emerges for production investment

### Timeline

- **Week 1**: Temporal implementation
- **Week 2**: Prefect implementation
- **Week 3**: Dagster implementation
- **Week 4**: Comparison, documentation, pattern extraction

---

## Architecture

### Project Structure

```
agent-replay-lab/
├── core/                    # Shared logic (used by all orchestrators)
│   ├── conversation.py      # Load/parse episodic memory archives
│   ├── checkpoint.py        # Extract state at any conversation step
│   ├── executor.py          # Claude SDK wrapper for agent execution
│   ├── comparator.py        # Compare branch results
│   └── models.py            # Shared data models (Pydantic)
│
├── orchestrators/
│   ├── temporal/            # Temporal implementation
│   ├── prefect/             # Prefect implementation
│   └── dagster/             # Dagster implementation
│
├── cli/                     # Command-line interface
│   └── main.py              # Entry point for all operations
│
├── patterns/                # Extracted integration patterns (docs)
│   ├── temporal-patterns.md
│   ├── prefect-patterns.md
│   └── dagster-patterns.md
│
└── comparisons/             # Results and analysis
    └── comparison-matrix.md
```

### Key Architectural Decisions

1. **Shared Core** - Conversation loading, checkpointing, and comparison logic is orchestrator-agnostic. Each orchestrator only handles workflow coordination.

2. **Pluggable Orchestrators** - Same CLI interface, swap orchestrator via flag: `--orchestrator temporal|prefect|dagster`

3. **SDK-First Execution** - Agent calls go through Claude SDK (not CLI subprocess), giving fine-grained control over messages, models, and settings.

4. **File-Based State** - Checkpoints and results stored as JSON files, aligning with Claude Code's file-system-first philosophy.

---

## Data Models

### Conversation Model

```python
from pydantic import BaseModel
from typing import Literal

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None

class Conversation(BaseModel):
    session_id: str
    project_path: str
    messages: list[Message]

    def at_step(self, n: int) -> "Conversation":
        """Return conversation truncated to step N"""
        return Conversation(
            session_id=self.session_id,
            project_path=self.project_path,
            messages=self.messages[:n]
        )
```

### Fork Configuration

```python
class ForkConfig(BaseModel):
    name: str                          # Branch identifier
    inject_message: str | None = None  # Different user message
    model: str = "claude-sonnet-4-20250514"       # Model override (configurable)
    system_prompt: str | None = None   # System prompt override
    max_turns: int = 5                 # How far to continue

class ReplayRequest(BaseModel):
    conversation_id: str       # Which conversation to replay
    fork_at_step: int          # Where to fork
    branches: list[ForkConfig] # Parallel variations to run
```

### Branch Result

```python
class BranchResult(BaseModel):
    branch_name: str
    config: ForkConfig
    messages: list[Message]    # New messages after fork
    duration_ms: int
    token_usage: TokenUsage
    status: Literal["success", "error", "timeout"]
    error: str | None = None
```

---

## Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  1. LOAD CONVERSATION                                       │
│     - Read from episodic memory archive                     │
│     - Parse JSONL → Conversation model                      │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  2. CREATE CHECKPOINT                                       │
│     - Truncate to step N                                    │
│     - Extract context (messages, tool state)                │
│     - Save checkpoint to file (for replay/debugging)        │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  3. FORK INTO BRANCHES (parallel)                           │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│     │ Branch A │  │ Branch B │  │ Branch C │  ...          │
│     │ (Sonnet) │  │ (Haiku)  │  │ (Opus)   │               │
│     └────┬─────┘  └────┬─────┘  └────┬─────┘               │
│          ▼             ▼             ▼                      │
│     ┌──────────────────────────────────────┐               │
│     │  Execute via Claude SDK              │               │
│     │  - Inject variation (message/model)  │               │
│     │  - Run up to max_turns               │               │
│     │  - Capture result + metrics          │               │
│     └──────────────────────────────────────┘               │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  4. AGGREGATE RESULTS                                       │
│     - Collect all branch results                            │
│     - Handle partial failures (some branches may fail)      │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  5. COMPARE & REPORT                                        │
│     - Structured comparison (cost, speed, output quality)   │
│     - Generate comparison artifact (JSON + markdown)        │
│     - Save to comparisons/ directory                        │
└─────────────────────────────────────────────────────────────┘
```

### Orchestrator Responsibilities

- Step 3 parallelism (fan-out)
- Retry on transient failures (API errors, timeouts)
- Step 4 aggregation (fan-in, handle partial failures)
- Checkpointing for recovery if workflow interrupted

### Core Library Responsibilities

- Steps 1, 2, 5 (conversation loading, checkpointing, comparison)
- Claude SDK execution logic (used by orchestrator activities)

---

## Orchestrator Implementations

### Temporal

```python
@workflow.defn
class ForkCompareWorkflow:
    @workflow.run
    async def run(self, request: ReplayRequest) -> ComparisonResult:
        # Step 1-2: Load and checkpoint (activity)
        checkpoint = await workflow.execute_activity(
            create_checkpoint, request, start_to_close_timeout=timedelta(seconds=30)
        )

        # Step 3: Fan-out to parallel branches
        branch_tasks = [
            workflow.execute_activity(
                execute_branch, checkpoint, branch_config,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            for branch_config in request.branches
        ]
        results = await asyncio.gather(*branch_tasks, return_exceptions=True)

        # Step 4-5: Aggregate and compare
        return await workflow.execute_activity(compare_results, results)
```

**Strength**: Event-sourced durability, automatic replay on failure.

### Prefect

```python
@flow(name="fork-compare")
async def fork_compare_flow(request: ReplayRequest) -> ComparisonResult:
    # Step 1-2
    checkpoint = await create_checkpoint(request)

    # Step 3: Parallel branches via task mapping
    results = await execute_branch.map(
        [checkpoint] * len(request.branches),
        request.branches
    )

    # Step 4-5
    return await compare_results(results)

@task(retries=3, retry_delay_seconds=10)
async def execute_branch(checkpoint, config) -> BranchResult:
    ...
```

**Strength**: Pythonic DX, easy local development, good UI.

### Dagster

```python
@op(retry_policy=RetryPolicy(max_retries=3))
def execute_branch(context, checkpoint: Checkpoint, config: ForkConfig) -> BranchResult:
    ...

@graph
def fork_compare_graph():
    checkpoint = create_checkpoint()
    results = [execute_branch(checkpoint, config) for config in configs]
    return compare_results(results)
```

**Strength**: Asset-oriented, strong typing, great observability UI.

---

## CLI Interface

### Commands

```bash
# List available conversations from episodic memory
agent-replay-lab list [--project <path>] [--limit 20]

# Inspect a conversation (show steps, find fork points)
agent-replay-lab inspect <conversation-id> [--step N]

# Run a fork & compare workflow
agent-replay-lab run \
  --conversation <id> \
  --fork-at <step> \
  --orchestrator temporal|prefect|dagster \
  --config <path-to-fork-config.yaml>

# Compare results from a previous run
agent-replay-lab compare <run-id>

# Show orchestrator status/health
agent-replay-lab status --orchestrator temporal|prefect|dagster
```

### Fork Config File

```yaml
# fork-config.yaml
branches:
  - name: "sonnet-baseline"
    model: "claude-sonnet-4-20250514"

  - name: "haiku-speed"
    model: "claude-haiku-4-20250514"

  - name: "opus-quality"
    model: "claude-opus-4-20250514"

  - name: "alternative-question"
    model: "claude-sonnet-4-20250514"
    inject_message: "What if we used a different approach?"

settings:
  max_turns: 5
  timeout_seconds: 300
  save_results: true
  output_dir: "./results"
```

### Output

- Progress displayed in terminal (branch status, completion %)
- Results saved to `results/<run-id>/` as JSON + markdown summary
- Comparison table printed at end

---

## Pattern Library

### Pattern Categories (per orchestrator)

1. **Setup & Configuration**
   - Installing and configuring the orchestrator
   - Connecting to Claude SDK
   - Environment/secrets management
   - Local dev vs production setup

2. **Activity/Task Design**
   - How to wrap Claude SDK calls as activities/tasks
   - Timeout and retry configuration
   - Error handling and failure modes
   - Input/output serialization

3. **Parallelism Patterns**
   - Fan-out (spawn parallel branches)
   - Fan-in (aggregate results)
   - Handling partial failures
   - Concurrency limits

4. **State & Checkpointing**
   - How state is persisted
   - Recovery from interruption
   - Accessing workflow history
   - Debugging failed runs

5. **Observability**
   - Logging integration
   - Metrics and monitoring
   - UI/dashboard usage
   - Tracing distributed execution

### Pattern Document Template

```markdown
# {Orchestrator} + Claude Code Integration Patterns

## Quick Start
[Minimal working example]

## Pattern: Wrapping SDK Calls
[Code + explanation]

## Pattern: Parallel Agent Execution
[Code + explanation]

## Pattern: Retry with Backoff
[Code + explanation]

## Gotchas & Lessons Learned
[What surprised you, what to watch out for]

## When to Use {Orchestrator}
[Best fit scenarios based on your experience]
```

---

## Integration Approach

**Hybrid Pattern**: SDK for agent reasoning, orchestrator for durability

```
Orchestrator (Temporal/Prefect/Dagster)
  → Workflow coordinates steps
    → Activity calls Claude SDK
      → SDK handles agent reasoning
        → Result returned to workflow
          → Workflow checkpoints state
            → Next activity or completion
```

### Conversation Source

Existing episodic memory archives:
- Location: `~/.config/superpowers/conversation-archive/`
- Format: JSONL files
- Direct integration, no conversion layer needed

---

## Next Steps

1. Create initial project structure
2. Implement core library (conversation loading, models, comparator)
3. Week 1: Temporal implementation
4. Week 2: Prefect implementation
5. Week 3: Dagster implementation
6. Week 4: Comparison analysis, pattern extraction, documentation
7. Choose winner and expand to production-quality

---

## Open Questions (to resolve during implementation)

- [ ] How to handle tool calls/results in replay (re-execute or mock?)
- [ ] Rate limiting across parallel branches (shared budget?)
- [ ] Best approach for comparing "quality" of different model outputs
- [ ] Whether to support live recording of new conversations

---

**Design Status:** Approved - Ready for implementation
