# Orchestrator Decision: Winner Selection

**Date:** 2026-03-05
**Author:** agent-replay-lab team
**Status:** ✅ Final

---

## Decision

**Winner: Temporal**

For production expansion of the Fork & Compare workflow, we are choosing **Temporal** as the orchestrator.

---

## Evidence Reviewed

Before this decision, we completed:

| Artifact | Location | Key Finding |
|----------|----------|-------------|
| Prefect implementation | `orchestrators/prefect/` | Clean async integration, zero-config ephemeral mode |
| Dagster implementation | `orchestrators/dagster/` | Best UI, but async requires `asyncio.run()` wrapper |
| Temporal implementation | `orchestrators/temporal/` | Most complex setup, strongest durability guarantees |
| Benchmark results | `comparisons/benchmark-results.json` | All three < 1% overhead vs real LLM latency |
| Benchmark notes | `comparisons/benchmark-notes.md` | Prefect has ~2.8s first-run penalty; others are consistent |
| Comparison matrix | `comparisons/comparison-matrix.md` | Prefect 4.4 > Temporal 3.9 > Dagster 3.6 (weighted) |
| Pattern docs | `patterns/` | Each orchestrator's retry/parallel patterns documented |

---

## Why Not the Scorecard Winner?

The comparison matrix scored **Prefect highest (4.4/5)**. Temporal still wins. Here's why:

### The matrix was weighted for general use. This project has specific requirements.

The Fork & Compare workflow has two properties that flip the decision:

**1. Claude SDK calls are long-running and expensive.**

Each branch can take 10–60 seconds and costs real money. If a process crashes halfway through a 3-branch workflow, we want those results — not to start from scratch. Temporal is the only orchestrator that survives a process crash and resumes from where it left off.

**2. This is a research tool, not a prototype.**

Issue #28 asks for "production-quality expansion." Production means we care about:
- Run history that persists indefinitely
- Ability to inspect any past workflow's full event timeline
- Retry policies that handle rate limits without losing progress
- A stable foundation to build on as the workflow grows in complexity

Prefect's ephemeral mode — its biggest advantage for prototyping — becomes a liability here.

### The scorecard penalty for "setup complexity" is a one-time cost.

Temporal scored 2/5 on setup simplicity. But that cost is paid once during initial configuration. Once running, the developer loop is just as fast (write activity, submit workflow, check UI). The comparison matrix unfairly penalizes Temporal's one-time setup against Prefect's zero-config default that doesn't scale to production.

---

## Decision Rationale

### For

| Reason | Weight | Notes |
|--------|--------|-------|
| Durable execution — survives crashes | **Critical** | Claude API calls are expensive; losing work is unacceptable |
| Exactly-once semantics for activities | **Critical** | No double-billing on retries, no duplicate API calls |
| Expressive retry policies | **High** | True exponential backoff + non-retryable error classification |
| Persistent run history | **High** | Audit trail for all fork-compare experiments |
| Signals & queries for future extensibility | **Medium** | Human-in-the-loop and dynamic workflow control |
| Multi-language worker support | **Low** | Future-proofing if we add non-Python components |

### Against

| Concern | Mitigation |
|---------|-----------|
| Server required (higher ops burden) | Temporal Cloud removes this; self-hosted is well-documented |
| Steepest learning curve | Team already implemented it — learning is done |
| `temporalio` is an optional dependency | Make it a required dep in production config |
| Determinism constraints in workflows | Already handled correctly in our implementation |
| No built-in jitter in retry policies | Can be implemented with custom retry logic in activities |

### Why Not Dagster

Dagster's async limitation is a first-class problem for this use case. Every Claude SDK call requires `asyncio.run()` inside a sync op — this works but creates a new event loop per op, and becomes progressively more awkward as the workflow grows. Its strengths (asset tracking, UI) are secondary to our needs.

### Why Not Prefect

Prefect is excellent for what it is. For a researcher running one-off experiments, Prefect would be the right call. But the production criteria in issue #28 require durability, and Prefect only delivers that with a server — at which point its zero-config advantage is gone and Temporal's superior retry semantics and event sourcing become the deciding factors.

---

## Final Scorecard (Re-weighted for Production)

Adjusting weights for production agent workflow criteria:

| Dimension | Weight | Temporal | Prefect | Dagster |
|-----------|--------|----------|---------|---------|
| Durability / crash recovery | **25%** | 5 | 2 | 2 |
| Claude SDK fit (async) | **20%** | 5 | 5 | 3 |
| Retry semantics | **20%** | 5 | 4 | 3 |
| Observability / UI | **15%** | 4 | 4 | 5 |
| Setup & learning curve | **10%** | 2 | 5 | 4 |
| Local dev story | **10%** | 3 | 5 | 5 |
| **Weighted total** | | **4.3** | **3.9** | **3.2** |

---

## Next Steps (Issue #28)

The production expansion should focus on:

1. **Make `temporalio` a required dependency** — remove the `--extra temporal` flag requirement
2. **Add worker configuration** — configurable concurrency, task queue naming, worker options
3. **Add schedule support** — periodic fork-compare runs via Temporal schedules
4. **Improve error surfacing** — map Temporal failure types to user-friendly CLI messages
5. **Add workflow cancellation** — `agent-replay-lab cancel <workflow-id>`
6. **Persist results to disk automatically** — wire result saving into the Temporal client, not just the CLI
7. **Add a `status` command** — `agent-replay-lab status --orchestrator temporal` that actually works
8. **Write production deployment guide** — Docker Compose setup with Temporal server + worker

---

## Alternatives Considered

### "Use Prefect with server mode"

This closes the durability gap but doesn't close the retry expressiveness gap. Temporal's event sourcing model is fundamentally more durable than Prefect's database-backed model — Temporal can replay from scratch even if the database is partially corrupted.

### "Use Dagster with parallel job"

The parallel `fork_compare_parallel_job` using `DynamicOutput` is more capable than we benchmarked (we benchmarked the sequential job). However, the async-in-sync constraint remains, and Dagster's durability model is the same as Prefect's.

### "Build without an orchestrator"

For simple use cases, direct `asyncio.gather()` calls to the Claude SDK work fine. But this foregoes retry logic, observability, and persistent history — all of which we identified as production requirements.

---

## Confidence

**High.** The decision is grounded in implementation experience (not benchmarks alone), and the primary deciding factor — durability for expensive, long-running API calls — is an objective requirement, not a preference.

The one area of uncertainty is operational burden: Temporal's server requirements add infrastructure complexity that Prefect avoids. If the team finds this burden unacceptable in practice, **Prefect with server mode** is the recommended fallback.
