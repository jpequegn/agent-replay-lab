# Production Expansion Plan: Temporal Orchestrator

**Date:** 2026-03-05
**Decision reference:** `comparisons/decision.md`
**Orchestrator:** Temporal (selected winner)
**Phase:** 5 — Production Quality

---

## Executive Summary

The Fork & Compare workflow runs correctly on Temporal today. Phase 5 upgrades it from "working prototype" to "production-quality tool" — reliable enough for daily research use, observable enough to trust results, and deployable without a PhD in infrastructure.

Eight workstreams are planned. They are independent and can be parallelized across a team, or sequenced by a single developer over 2–3 weeks.

---

## Current State Assessment

### What Works Today

| Component | Status | Notes |
|-----------|--------|-------|
| Fork & Compare workflow | ✅ Working | `orchestrators/temporal/` |
| CLI `run` command | ✅ Working | Temporal path functional |
| CLI `list` / `inspect` | ✅ Working | Conversation browsing |
| Activity retry policies | ✅ Working | Tiered: local, API, compute |
| Parallel branch execution | ✅ Working | `asyncio.gather()` |
| Unit + E2E tests | ✅ Working | Full coverage in `tests/` |

### Known Gaps (Production Blockers)

| Gap | Severity | Impact |
|-----|----------|--------|
| `temporalio` is an optional dependency | **High** | Users must pass `--extra temporal`; confusing |
| `status` command is a stub | **High** | Can't check if Temporal is healthy |
| `compare` command is a stub | **High** | Can't compare past runs |
| Results not auto-saved in Temporal path | **Medium** | Data lost if CLI exits before saving |
| No Docker Compose for local Temporal server | **Medium** | Setup requires manual multi-step process |
| No workflow cancellation | **Medium** | Can't stop a stuck workflow from CLI |
| Error messages from Temporal are raw | **Medium** | Workflow failures show SDK stack traces |
| No schedule/recurring runs | **Low** | Manual only |

---

## Phase 5 Workstreams

### Workstream 1: Make Temporal a First-Class Dependency

**Goal:** Remove the `--extra temporal` friction. `temporalio` becomes a required dep.

**Tasks:**
- Move `temporalio>=1.7` from `[project.optional-dependencies]` to `[project.dependencies]`
- Update `pyproject.toml`, `README.md`, and any docs that mention the extra flag
- Verify `uv run agent-replay-lab run --orchestrator temporal ...` works without extras
- Remove `--extra temporal` from `scripts/benchmark.py` and CI if present

**Effort:** 1 hour
**Files:** `pyproject.toml`, `README.md`, `scripts/benchmark.py`

---

### Workstream 2: Implement `status` Command

**Goal:** `agent-replay-lab status --orchestrator temporal` shows health, active runs, and server info.

**Tasks:**
- Implement `check_temporal_health()` in `orchestrators/temporal/client.py`
  - Try connecting to Temporal server (catch `ConnectionRefusedError`)
  - Return server version, namespace, task queue health
- Wire into CLI `status` command (currently a TODO stub)
- Add status output for Prefect and Dagster (can reuse existing `check_dagster_health()`)
- Show: server reachable, active workflow count, last N run IDs

**Effort:** 3–4 hours
**Files:** `cli/main.py`, `orchestrators/temporal/client.py`

**Example output:**
```
┌─ Temporal Status ──────────────────────────────┐
│ Server:     localhost:7233              ✓ OK    │
│ Namespace:  default                             │
│ Task Queue: fork-compare-queue          ✓ OK    │
│ Active runs: 0                                  │
│ Last run:   fork-compare-conv123-a1b2   SUCCESS │
└────────────────────────────────────────────────┘
```

---

### Workstream 3: Implement `compare` Command

**Goal:** `agent-replay-lab compare <run-id>` loads and displays a past run's results.

**Tasks:**
- Define result file naming convention: `results/<workflow-id>.json`
- Implement `load_result(run_id)` that finds the JSON file
- Implement `compare` CLI command:
  - Load result from disk
  - Display branch table (reuse `_display_results()`)
  - Show diff between branches (response length, token count)
  - Allow `--raw` flag to dump full JSON
- Support `agent-replay-lab compare --list` to show all saved runs

**Effort:** 4–6 hours
**Files:** `cli/main.py`, new `core/results.py`

---

### Workstream 4: Auto-Save Results in Temporal Path

**Goal:** Results are always persisted to disk, even if the CLI crashes after workflow completion.

**Tasks:**
- In `_run_temporal_workflow()`, save result immediately after `handle.result()` returns
- Use a deterministic filename: `results/<workflow-id>-<timestamp>.json`
- Create `results/` directory automatically if missing
- Add result path to CLI success output
- Ensure Prefect and Dagster paths do the same (they already do but inconsistently)

**Effort:** 2 hours
**Files:** `cli/main.py`

---

### Workstream 5: Workflow Cancellation

**Goal:** `agent-replay-lab cancel <workflow-id>` stops a running Temporal workflow gracefully.

**Tasks:**
- Add `cancel_workflow(workflow_id, client)` to `orchestrators/temporal/client.py`
  - Use `client.get_workflow_handle(workflow_id).cancel()`
- Add `cancel` CLI command:
  ```
  agent-replay-lab cancel fork-compare-conv123-a1b2
  ```
- Handle: workflow not found, already completed, cancellation timeout
- Add `--force` flag that terminates instead of cancels (for stuck workflows)

**Effort:** 3 hours
**Files:** `cli/main.py`, `orchestrators/temporal/client.py`

---

### Workstream 6: Improved Error Messages

**Goal:** Replace raw Temporal SDK stack traces with user-friendly CLI messages.

**Tasks:**
- Map common Temporal exceptions to actionable messages:
  - `ServiceUnavailableError` → "Cannot connect to Temporal server. Run: temporal server start-dev"
  - `WorkflowAlreadyStartedError` → "Workflow ID already in use. Use --run-id to specify a unique ID."
  - `ActivityError` wrapping `ValueError` → Extract inner message, show branch name
  - `WorkflowFailureError` → Show which activity failed and why
- Add `--verbose` / `--debug` flag to CLI to show raw SDK errors when needed
- Wrap all Temporal calls in `cli/main.py` with the error mapper

**Effort:** 4 hours
**Files:** `cli/main.py`, new `core/errors.py`

---

### Workstream 7: Docker Compose for Local Development

**Goal:** One command to start the full Temporal stack for local development.

**Tasks:**
- Create `docker-compose.yml` at project root:
  - `temporal` service (official Temporal server image)
  - `temporal-ui` service (Temporal Web UI)
  - `temporal-admin-tools` service (for `tctl` access)
  - SQLite storage for simplicity (no Cassandra/Postgres required for dev)
- Create `scripts/start-temporal.sh` as an alternative for non-Docker setups
- Update `orchestrators/temporal/README.md` with both options
- Add health check to `docker-compose.yml`

**Effort:** 3–4 hours
**Files:** `docker-compose.yml`, `scripts/start-temporal.sh`, `orchestrators/temporal/README.md`

**docker-compose.yml sketch:**
```yaml
services:
  temporal:
    image: temporalio/auto-setup:latest
    ports: ["7233:7233"]
    environment:
      - DB=sqlite

  temporal-ui:
    image: temporalio/ui:latest
    ports: ["8080:8080"]
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
```

---

### Workstream 8: Enhanced Progress Display

**Goal:** Real-time branch-level progress during workflow execution (not just a spinner).

**Tasks:**
- Add Temporal workflow query handler to `ForkCompareWorkflow`:
  ```python
  @workflow.query
  def get_progress(self) -> dict:
      return {"completed_branches": self._completed, "total": self._total}
  ```
- Update CLI polling loop to query progress every second and display:
  - Which branches are running / completed / failed
  - Elapsed time per branch
  - Overall completion percentage
- Use Rich `Progress` with multiple task bars (one per branch)

**Effort:** 5–6 hours
**Files:** `orchestrators/temporal/workflows.py`, `cli/main.py`

---

## Sequencing Recommendation

If implementing solo, this order minimizes blocked time:

| Week | Workstreams | Rationale |
|------|-------------|-----------|
| Week 1, Day 1 | WS1 (deps) + WS4 (auto-save) | Unblocks everything else; low risk |
| Week 1, Day 2–3 | WS2 (status) + WS6 (errors) | Core UX improvements |
| Week 1, Day 4–5 | WS7 (Docker Compose) | Removes biggest setup friction |
| Week 2, Day 1–2 | WS3 (compare command) | Needs WS4's save format |
| Week 2, Day 3 | WS5 (cancellation) | Standalone, low risk |
| Week 2, Day 4–5 | WS8 (progress display) | Needs WS2's query infrastructure |

---

## Effort Summary

| Workstream | Effort | Priority |
|------------|--------|----------|
| WS1: Required dependency | 1h | P0 |
| WS4: Auto-save results | 2h | P0 |
| WS2: Status command | 4h | P1 |
| WS6: Error messages | 4h | P1 |
| WS7: Docker Compose | 4h | P1 |
| WS5: Cancellation | 3h | P2 |
| WS3: Compare command | 6h | P2 |
| WS8: Progress display | 6h | P3 |
| **Total** | **~30h** | |

---

## Success Criteria for Phase 5

- [ ] `uv run agent-replay-lab run --orchestrator temporal ...` works without `--extra temporal`
- [ ] `agent-replay-lab status --orchestrator temporal` shows real server health
- [ ] Results are always saved to disk automatically
- [ ] A crashed CLI can be resumed with `agent-replay-lab compare <run-id>`
- [ ] `agent-replay-lab cancel <workflow-id>` stops a running workflow
- [ ] All Temporal errors produce actionable CLI messages
- [ ] `docker compose up` starts a working Temporal development stack
- [ ] Branch-level progress is visible during execution

---

## Out of Scope for Phase 5

- **Temporal Cloud integration** — Production cloud deployment is Phase 6
- **Multi-tenant / team support** — Single user for now
- **Result visualization (charts/graphs)** — Phase 6
- **Live conversation recording** — Future integration with Claude Code hooks
- **Integration with episodic memory for results** — Phase 6 (separate from run storage)
- **Scheduled recurring runs** — Phase 6 (requires Temporal schedules + cron config)
