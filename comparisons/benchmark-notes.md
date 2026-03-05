# Orchestrator Benchmark Notes

**Date:** 2026-03-05
**Environment:** macOS, Python 3.12, uv package manager
**Benchmark version:** 1.0

---

## Methodology

### What Was Measured

All three orchestrators were run against the **same Fork & Compare workflow**:

- **Conversation:** `benchmark-conv-001` — 6 messages (Python help session)
- **Fork at step:** 5
- **Branches:** 3 (sonnet-baseline, haiku-speed, sonnet-inject)
- **Runs per orchestrator:** 3

### Claude API Simulation

Real Claude API calls were **mocked with a fixed 50ms latency** per branch. This isolates orchestrator framework overhead from actual LLM response time.

With 3 parallel branches and 50ms each, minimum possible total time is ~50ms. Total wall time in excess of that is orchestrator overhead.

### How to Reproduce

```bash
# All three orchestrators (requires temporalio installed as extra)
uv run --extra temporal python scripts/benchmark.py

# Specific orchestrators
uv run --extra temporal python scripts/benchmark.py --orchestrators prefect dagster
uv run --extra temporal python scripts/benchmark.py --runs 5
```

---

## Results Summary

| Orchestrator | Runs | Success Rate | Mean (ms) | Median (ms) | Overhead Mean (ms) |
|-------------|------|-------------|-----------|-------------|-------------------|
| **Temporal** | 3/3 | 100% | 248 | 176 | **98** |
| **Dagster** | 3/3 | 100% | 277 | 194 | **127** |
| **Prefect** | 3/3 | 100% | 1,084 | 152 | **936** |

> **Overhead** = total time − (3 branches × 50ms simulated API latency)
> Simulated API calls run in parallel, so the deducted baseline is 50ms (not 150ms)

---

## Per-Run Timings

### Prefect

| Run | Total (ms) |
|-----|-----------|
| 1   | 2,957 |
| 2   | 152 |
| 3   | 144 |

**Note:** Run 1 includes Prefect server startup (~2.8s). Runs 2-3 are fast because the server stays running. This is a significant first-run penalty compared to the other orchestrators.

### Dagster

| Run | Total (ms) |
|-----|-----------|
| 1   | 448 |
| 2   | 191 |
| 3   | 194 |

**Note:** Run 1 includes Dagster's in-process initialization and IO manager setup (~300ms one-time cost). Subsequent runs are faster.

### Temporal

| Run | Total (ms) |
|-----|-----------|
| 1   | 395 |
| 2   | 176 |
| 3   | 174 |

**Note:** Run 1 includes Temporal test environment (time-skipping) startup. Subsequent runs are consistently fast. In production (with a running Temporal server), startup cost would be incurred once at worker launch, not per workflow.

---

## Observations & Anomalies

### 1. Prefect First-Run Penalty Is Large

Prefect starts a temporary local API server on the first flow run (`Starting temporary server on http://127.0.0.1:...`). This adds ~2.8s to run 1 but is essentially free for subsequent runs in the same process. In production, a dedicated Prefect server eliminates this entirely.

**Impact:** If you're running many flows in a single process session, amortize this cost — it's a one-time setup fee.

### 2. All Orchestrators Are Fast After Warmup

Once initialized, all three orchestrators complete the 3-branch workflow in **~150–200ms** when API latency is 50ms. Pure framework overhead is:

- Temporal: ~25ms (warmup-adjusted median)
- Dagster: ~43ms
- Prefect: ~2ms (warmup-adjusted median — Prefect has minimal overhead once running)

### 3. Temporal Requires Extra Dependency

Temporal's `temporalio` package is an optional dependency (`uv add --extra temporal`). The other two run with the default project setup. This is a practical adoption barrier.

### 4. Dagster Logs Are Verbose

Dagster emits detailed DEBUG logs per run (resource init, step start/success, engine events). This is useful for production debugging but noisy for benchmarking. Log level can be controlled with `DAGSTER_LOGGING_LEVEL`.

### 5. All Three Handle Parallel Branches Correctly

All orchestrators successfully ran 3 branches in parallel and merged results:
- **Prefect:** `task.submit()` + `wait()` fan-out/fan-in
- **Dagster:** Sequential in the simplified job (parallel version uses `DynamicOutput`)
- **Temporal:** `asyncio.gather()` across activities

> **Note:** The Dagster benchmark uses the simplified sequential job (`fork_compare_job`), not the parallel `fork_compare_parallel_job`. Using the parallel job would likely reduce branch execution time.

---

## Interpretation

### For This Workload (3 branches, fast API calls)

All three orchestrators are fast enough to be irrelevant compared to real LLM latency (typically 1–10 seconds per branch). The choice of orchestrator should be driven by features, not raw overhead.

### If API Latency Is High (e.g., 5s per branch)

With real Claude API calls (~5s per branch, parallel execution = ~5s total):
- Prefect warmup overhead becomes negligible (~0.5%)
- Dagster overhead becomes negligible (~0.8%)
- Temporal overhead becomes negligible (~0.5%)

All three orchestrators' overhead would be less than 1% of total workflow time.

### When Overhead Matters

Overhead matters if you're running **many short workflows** in rapid succession (< 100ms API calls). In that case, Prefect's ~2ms post-warmup overhead makes it the lightest option, but this scenario is unlikely for Claude SDK workloads.

---

## Recommendations Based on Benchmark

| Use Case | Recommended |
|----------|-------------|
| Rapid prototyping, quick scripts | **Prefect** (zero config, low overhead post-warmup) |
| Production with UI/visibility | **Dagster** (best UI, persistent run history) |
| Mission-critical, must not lose work | **Temporal** (best durability, crash recovery) |
| Long-running multi-turn agents | **Temporal** (durable execution over hours/days) |
| Data pipeline / asset tracking | **Dagster** (native asset management) |

---

## Issues & Anomalies

| Issue | Orchestrator | Severity | Notes |
|-------|-------------|----------|-------|
| First-run server startup | Prefect | Low | ~2.8s one-time; use dedicated server in production |
| `temporalio` optional dependency | Temporal | Medium | Must install separately; not in default deps |
| Verbose DEBUG logs | Dagster | Low | Controllable via `DAGSTER_LOGGING_LEVEL` |
| Sequential branches in default job | Dagster | Medium | Use `fork_compare_parallel_job` for parallelism |
| Sandbox conflicts with Rich console | Temporal | Low | Known issue in test env; not present in production |

---

## Next Steps

- Issue #26: Write comparison matrix using these results
- Issue #27: Choose winner and document decision
- Issue #28: Production-quality expansion of chosen winner
