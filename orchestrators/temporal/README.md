# Temporal Orchestrator for Fork & Compare

This directory contains the Temporal implementation of the Fork & Compare workflow.

## Prerequisites

### 1. Install Temporal CLI

```bash
# macOS
brew install temporal

# Other platforms: https://docs.temporal.io/cli#install
```

### 2. Install Python Dependencies

```bash
# From the project root
uv sync --extra temporal
```

## Quick Start

### Step 1: Start Temporal Server

```bash
temporal server start-dev
```

This starts a local Temporal server with:
- gRPC frontend on port 7233
- Web UI at http://localhost:8233

### Step 2: Start the Worker

In a new terminal:

```bash
uv run python -m orchestrators.temporal.worker
```

You should see:
```
Starting Temporal worker on task queue: fork-compare-queue
Registered workflows: GreetingWorkflow
Press Ctrl+C to stop
```

### Step 3: Run a Test Workflow

In another terminal:

```bash
uv run python -m orchestrators.temporal.client
```

Expected output:
```
Testing Temporal setup...

✅ Workflow executed successfully!
   Result: Hello, Temporal!

Temporal setup is working correctly.
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│   Client    │────▶│   Temporal   │────▶│   Worker   │
│             │     │   Server     │     │            │
└─────────────┘     └──────────────┘     └────────────┘
      │                    │                    │
      │ execute_workflow   │ schedule task      │ run activity
      └────────────────────┴────────────────────┘
```

### Components

| File | Purpose |
|------|---------|
| `activities.py` | Activity definitions - the actual work |
| `workflows.py` | Workflow definitions - orchestration logic |
| `worker.py` | Worker process - executes workflows and activities |
| `client.py` | Client utilities - start and query workflows |

### Activities

- `greet_activity` - Simple test activity
- `load_conversation_activity` - Load conversation from episodic memory
- `create_checkpoint_activity` - Create checkpoint at a step
- `execute_branch_activity` - Execute a branch with Claude SDK

### Workflows

- `GreetingWorkflow` - Simple test workflow
- `ForkCompareWorkflow` - Main workflow (coming in issue #8)

## Web UI

Access the Temporal Web UI at http://localhost:8233 to:
- View running workflows
- Inspect workflow history
- Debug failed workflows
- Manage task queues

## Troubleshooting

### "Connection refused" error

Make sure the Temporal server is running:
```bash
temporal server start-dev
```

### "No workers for queue" error

Make sure the worker is running:
```bash
uv run python -m orchestrators.temporal.worker
```

### Import errors

Make sure you installed the temporal dependencies:
```bash
uv sync --extra temporal
```

## Development Notes

### Why Temporal?

1. **Durability**: Workflows survive process crashes and server restarts
2. **Visibility**: Full execution history in the Web UI
3. **Reliability**: Automatic retries with configurable policies
4. **Scalability**: Distribute work across multiple workers

### Design Decisions

1. **Activities are async**: Even though some work is synchronous, we use async
   activities for consistency and to allow concurrent execution.

2. **Serialization**: We pass Pydantic model dicts rather than objects to activities
   because Temporal requires JSON-serializable arguments.

3. **Task queue**: All workflows and activities use the same task queue for simplicity.
   This can be split later for better scaling.

## Next Steps

- [ ] Issue #7: Implement Temporal activities for core operations
- [ ] Issue #8: Implement ForkCompareWorkflow
- [ ] Issue #9: Create Temporal worker and client integration
- [ ] Issue #10: Wire CLI run command to Temporal orchestrator
