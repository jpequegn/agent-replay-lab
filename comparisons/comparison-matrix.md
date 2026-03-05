# Orchestrator Comparison Matrix

Comprehensive comparison of Temporal, Prefect, and Dagster for Claude Code SDK agent workflows.
Based on direct implementation experience building the Fork & Compare workflow on all three.

> **Ratings:** ⭐⭐⭐⭐⭐ = Excellent · ⭐⭐⭐⭐ = Good · ⭐⭐⭐ = Adequate · ⭐⭐ = Poor · ⭐ = Very Poor

---

## TL;DR

| Dimension | Winner | Runner-up |
|-----------|--------|-----------|
| Setup simplicity | Prefect | Dagster |
| Developer experience | Prefect | Temporal |
| Parallel execution | Temporal | Dagster |
| Observability / UI | Dagster | Temporal |
| Durability / reliability | Temporal | — |
| Claude SDK integration | Prefect | Dagster |
| Production operations | Dagster | Temporal |
| Learning curve | Prefect | Dagster |

---

## 1. Developer Experience

### Setup Complexity

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Server required** | Always | Optional (ephemeral mode) | Optional (in-process) |
| **Install command** | `uv add temporalio` (extra dep) | `uv add prefect` | `uv add dagster dagster-webserver` |
| **Start server** | `temporal server start-dev` | `prefect server start` (optional) | `uv run dagster dev -m ...` (optional) |
| **First workflow running** | ~10 min (server + worker + workflow) | ~2 min (decorators only) | ~5 min (ops + definitions) |
| **Rating** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

**Notes:**
- **Prefect** wins: `pip install prefect`, add `@task`/`@flow` decorators, call the flow. Done.
- **Dagster** is close: requires a `Definitions` object to register everything, but `execute_in_process()` skips the server entirely.
- **Temporal** requires: install server binary, start server, start worker process, then submit workflow. Three moving parts before a single line runs.

### Learning Curve

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Core concepts to learn** | Workflow, Activity, Worker, Client, TaskQueue | Flow, Task, Future | Op, Job, Graph, Definitions, Config |
| **Determinism constraints** | Strict (no I/O, no random, no datetime in workflows) | None | None |
| **Serialization rules** | Manual (dicts at activity boundaries) | Manual (dicts at task boundaries) | Manual (dicts at op boundaries) |
| **State handling** | replay-based (must be deterministic) | Direct Python | Direct Python |
| **Rating** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

**Notes:**
- **Temporal**'s determinism requirement is the steepest learning curve. Every `datetime.now()`, `random()`, or direct I/O in a workflow body will cause replay bugs that are hard to debug.
- **Prefect** feels like plain Python. Decorators wrap existing functions — minimal new concepts.
- **Dagster** has more concepts (Op/Graph/Job split, Definitions, Config classes), but they compose cleanly once understood.

### Local Development Story

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Run without server** | No (requires running server) | Yes (ephemeral mode) | Yes (`execute_in_process`) |
| **Hot reload** | No (restart worker manually) | Yes (flows re-import on each run) | Partial (restart `dagster dev`) |
| **Test without server** | Yes (time-skipping test env) | Yes (direct function call) | Yes (`execute_in_process`) |
| **Rating** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

### Debugging Experience

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Error messages** | Verbose workflow task failure with stack trace | Clear Python tracebacks | Clear step failure with stack trace |
| **Replay debugging** | Temporal UI shows full event history | Prefect UI shows task logs | Dagster UI shows op logs and events |
| **Local debugging** | Difficult (requires running server + worker) | Easy (direct function call) | Easy (`execute_in_process`) |
| **Log capture** | Standard Python logging | `get_run_logger()` + Prefect UI | `context.log` + Dagster UI |
| **Rating** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 2. Architecture

### Execution Model

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Model** | Durable replay-based execution | Direct Python execution | In-process job execution |
| **Persistence** | Always (event sourcing) | Optional (with server) | Optional (with server) |
| **Workflow state** | Reconstructed from event history on restart | Lost on process death | Lost on process death (without server) |
| **Execution unit** | Activity (run in worker, any language) | Task (run in process/thread) | Op (run in executor) |
| **Determinism required** | Yes (workflow code only) | No | No |

### State Management

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Survives process crash** | ✅ Yes (replays from history) | ❌ No (ephemeral) / ✅ with server | ❌ No / ✅ with server |
| **Survives server restart** | ✅ Yes | ✅ With server | ✅ With server |
| **Workflow pause/resume** | ✅ Built-in (signals, queries) | ❌ No | ❌ No |
| **Long-running support** | ✅ Days/weeks/months | ⚠️ Hours (with server) | ⚠️ Hours (with server) |
| **Rating** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

### Parallelism Approach

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Parallel API** | `asyncio.gather(*activity_tasks)` | `task.submit()` + `wait()` | `DynamicOutput` + `.map()` + `.collect()` |
| **Dynamic branching** | Yes (runtime loop) | Yes (runtime loop) | Yes (`DynamicOutput`) |
| **Partial failure** | Via `return_exceptions=True` in gather | Via `state.is_failed()` on futures | Return error dict instead of raising |
| **Max parallelism** | Worker thread pool limit | Concurrency task runner limit | Worker thread pool limit |
| **Ease of use** | ⭐⭐⭐⭐⭐ (familiar asyncio) | ⭐⭐⭐⭐ (clean future API) | ⭐⭐⭐ (DynamicOutput is complex) |

**Parallelism code comparison:**

```python
# Temporal - asyncio.gather (most Pythonic)
tasks = [workflow.execute_activity(execute_branch, args=[...]) for b in branches]
results = await asyncio.gather(*tasks, return_exceptions=True)

# Prefect - submit + wait
futures = [execute_branch_task.submit(...) for b in branches]
wait(futures)
results = [f.result() for f in futures if f.state.is_completed()]

# Dagster - DynamicOutput (most complex, most explicit)
branch_contexts = fan_out_op(conversation, checkpoint)       # yields DynamicOutput
branch_results = branch_contexts.map(execute_single_branch)  # parallel map
collected = branch_results.collect()                         # fan-in
```

### Error Handling & Recovery

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Automatic retry** | ✅ RetryPolicy per activity | ✅ `@task(retries=N)` | ✅ `RetryPolicy` per op |
| **Retry backoff** | ✅ Configurable coefficient | ✅ Jitter factor | ⚠️ Flat delay only |
| **Non-retryable errors** | ✅ `non_retryable_error_types` | ✅ `retry_condition_fn` | ❌ Not built-in |
| **Workflow-level retry** | ✅ (configure at client level) | ✅ Flow retries | ✅ Job retries |
| **Partial failure support** | ✅ gather with return_exceptions | ✅ State-based checks | ✅ Error dict pattern |
| **Rating** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 3. Operations

### Monitoring & Observability

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Web UI** | ✅ (port 8080) | ✅ (port 4200) | ✅ (port 3000) |
| **Real-time logs** | ✅ Per activity | ✅ Per task | ✅ Per op |
| **Run history** | ✅ Permanent (event sourcing) | ✅ With server | ✅ With server |
| **Workflow graph visualization** | ✅ Activity DAG | ✅ Task flow | ✅ Op graph (best-in-class) |
| **Metrics / alerting** | ✅ Via Prometheus | ✅ Built-in notifications | ✅ Built-in alerts |
| **Rating** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**Notes:**
- **Dagster** has the best UI: interactive op graph, asset lineage, run timeline, structured event log.
- **Temporal** shows full event history (every state transition), invaluable for debugging replay failures.
- **Prefect** has a clean UI with good task-level details; the notification system is mature.

### UI Quality (Subjective)

| Aspect | Temporal | Prefect | Dagster |
|--------|----------|---------|---------|
| **Workflow graph** | Event timeline (linear) | Dependency graph | Interactive DAG ⭐⭐⭐⭐⭐ |
| **Log viewing** | Per-activity logs | Per-task logs with filtering | Structured event log ⭐⭐⭐⭐⭐ |
| **Run comparison** | Basic | Basic | Asset-based comparison ⭐⭐⭐⭐ |
| **Mobile/responsive** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

### Cloud Options

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Managed cloud** | Temporal Cloud (paid) | Prefect Cloud (free tier) | Dagster+ (paid) |
| **Self-hosted** | Yes (Temporal server + DB) | Yes (Prefect server + DB) | Yes (Dagster + DB) |
| **Kubernetes ready** | ✅ Helm charts available | ✅ Helm charts available | ✅ Helm charts available |
| **Serverless execution** | ❌ Requires workers | ✅ Prefect Cloud workers | ✅ Dagster Cloud serverless |
| **Rating** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

### Self-Hosted Complexity

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Minimum components** | Server + Elasticsearch/Cassandra + Worker | Server + DB + Worker | Server + DB + Worker |
| **Database** | Cassandra or PostgreSQL + Elasticsearch | PostgreSQL | SQLite (dev) / PostgreSQL (prod) |
| **Production setup effort** | High | Medium | Medium |
| **Rating** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 4. Claude Code SDK Fit

### SDK Integration Ease

The core pattern is identical across all three: wrap `execute_branch()` (async) in the orchestrator's execution unit, serialize at boundaries.

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Async/await native** | ✅ Activities are async | ✅ Tasks are async | ⚠️ Ops are sync (use `asyncio.run()` wrapper) |
| **Serialization overhead** | Dicts at activity boundaries | Dicts at task boundaries | Dicts at op boundaries |
| **Error propagation** | Raises on activity failure | Via state API | Via exception or error dict |
| **SDK call pattern** | `await execute_branch(...)` in activity | `await execute_branch(...)` in task | `asyncio.run(execute_branch(...))` in op |
| **Rating** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

**Dagster async limitation:** Ops run in a synchronous executor. The `asyncio.run()` workaround works but creates a new event loop per op — fine for correctness but slightly inefficient and requires careful handling if there's an outer event loop.

### Long-Running Workflow Support

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Multi-hour workflows** | ✅ Natively durable | ⚠️ Requires server (not default) | ⚠️ Requires server (not default) |
| **Multi-turn agent loops** | ✅ Ideal (signals, timers) | ⚠️ Possible but not designed for it | ⚠️ Possible but not designed for it |
| **Human-in-the-loop** | ✅ Signals, queries | ⚠️ Via webhooks | ⚠️ Via sensors |
| **Rating** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

### Retry Semantics for API Rate Limits

All three support retries, but with different expressiveness:

```python
# Temporal - most expressive
RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,          # True exponential backoff
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=5,
    non_retryable_error_types=["AuthenticationError"],  # Skip retries on auth failures
)

# Prefect - good, with jitter
@task(retries=5, retry_delay_seconds=1, retry_jitter_factor=1.0)  # Jitter prevents thundering herd

# Dagster - functional but basic
RetryPolicy(max_retries=5, delay=1.0)  # Flat delay, no exponential, no non-retryable types
```

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Exponential backoff** | ✅ | ✅ (via jitter) | ❌ (flat delay) |
| **Non-retryable errors** | ✅ | ✅ (via condition fn) | ❌ |
| **Jitter** | ❌ | ✅ | ❌ |
| **Rating** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

### Cost Implications

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **License** | MIT (open source) | Apache 2.0 | Apache 2.0 |
| **Managed service** | Temporal Cloud: action-based pricing | Prefect Cloud: free tier + usage | Dagster+: seat-based + usage |
| **Self-hosted infra cost** | Higher (Elasticsearch adds cost) | Medium | Medium |
| **Token cost** | Same (orchestrator doesn't affect Claude) | Same | Same |

---

## 5. Benchmark Results (From Implementation)

> Full details: `comparisons/benchmark-results.json` and `comparisons/benchmark-notes.md`

| | Temporal | Prefect | Dagster |
|---|---|---|---|
| **Mean total time** | 248ms | 1,084ms* | 277ms |
| **Post-warmup median** | 176ms | 152ms | 194ms |
| **Framework overhead** | ~25ms | ~2ms | ~43ms |
| **Success rate** | 100% | 100% | 100% |

*Prefect mean includes one-time ~2.8s server startup on first run.

**Key insight:** At real Claude API latency (1–10s per branch), all three add < 1% overhead. This is not a deciding factor.

---

## 6. Summary Scorecard

Scoring 1–5 per dimension (5 = best):

| Dimension | Weight | Temporal | Prefect | Dagster |
|-----------|--------|----------|---------|---------|
| Setup simplicity | 15% | 2 | 5 | 4 |
| Learning curve | 10% | 2 | 5 | 4 |
| Local dev story | 10% | 3 | 5 | 5 |
| Parallelism | 15% | 5 | 4 | 3 |
| Error handling / retry | 10% | 5 | 4 | 3 |
| Durability / recovery | 15% | 5 | 3 | 3 |
| Observability / UI | 10% | 4 | 4 | 5 |
| Claude SDK fit | 15% | 5 | 5 | 3 |
| **Weighted total** | | **3.9** | **4.4** | **3.6** |

---

## 7. Decision Framework

### Use Temporal if:
- Workflows may run for hours, days, or longer
- Process crashes must not lose work (payment processing, critical agents)
- You need signals/queries for human-in-the-loop or dynamic control
- Distributed workers across multiple machines is a requirement
- Your team has infrastructure experience to manage the server

### Use Prefect if:
- Rapid prototyping or early-stage projects
- Simplicity and fast onboarding matter more than durability
- Python-native feel and minimal boilerplate are priorities
- Free cloud tier is attractive (Prefect Cloud free tier is generous)
- Workflows complete within a session (hours, not days)

### Use Dagster if:
- You're building data pipelines alongside agent workflows
- Asset lineage tracking matters (who produced what data, when)
- The UI/observability story is important for your team
- You want explicit op-level type checking and configuration

### For This Project (Fork & Compare Lab):

Based on the implementation experience and benchmark data, the recommendation for each use case:

| Use Case | Recommendation | Rationale |
|----------|---------------|-----------|
| Quick experiments, notebooks | **Prefect** | Zero config, fast iteration |
| Production multi-turn agents | **Temporal** | Durability, crash recovery |
| Data pipeline with UI visibility | **Dagster** | Best-in-class asset tracking + UI |
| Claude SDK fork-compare workflow | **Prefect** | Simplest integration, native async |

---

## 8. Migration Considerations

### Prefect → Temporal

- Replace `@flow` with `@workflow.defn` class
- Replace `@task` with `@activity.defn`
- Move all I/O out of workflow body into activities
- Replace `task.submit()` + `wait()` with `asyncio.gather()` on activity handles
- Add determinism discipline to workflow code (no `datetime.now()`, no random)

### Temporal → Prefect

- Replace `@workflow.defn` class with `@flow` function
- Replace `@activity.defn` with `@task`
- Move I/O back into the flow if desired (not required)
- Replace `asyncio.gather()` with `task.submit()` + `wait()`
- Remove determinism constraints

### Prefect → Dagster

- Replace `@flow` with `@job` or `@graph`
- Replace `@task` with `@op`
- Add `Definitions` registration
- Convert async tasks to sync ops with `asyncio.run()` wrapper
- Replace `task.submit()` with `DynamicOutput` for parallelism
- Add `Config` classes for op configuration

---

## 9. Quick Reference

| Question | Answer |
|----------|--------|
| "I need to get something working today" | Prefect |
| "My workflow needs to survive a server restart" | Temporal |
| "I need the best debugging/UI experience" | Dagster |
| "I'm comparing agent outputs across models" | Any (overhead is negligible) |
| "My agents run for hours with user interactions" | Temporal |
| "I want to add scheduling to my workflows" | Prefect or Dagster |
| "I need workers in Go and Python" | Temporal (multi-language) |
| "I want free managed hosting" | Prefect Cloud |
