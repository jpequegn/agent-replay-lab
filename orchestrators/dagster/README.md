# Dagster Orchestrator for Fork & Compare

This directory contains the Dagster implementation for the Fork & Compare workflow.

## Quick Start

### Prerequisites

```bash
# Install Dagster (already included in project dependencies)
uv add dagster dagster-webserver
```

### Start Dagster Development Server

```bash
# From project root
uv run dagster dev -m orchestrators.dagster.definitions
```

Access the Dagster UI at http://localhost:3000

### Run a Test Job

```bash
# Execute the greeting job directly
uv run python orchestrators/dagster/jobs.py
```

## Project Structure

```
orchestrators/dagster/
├── __init__.py       # Module exports
├── definitions.py    # Dagster Definitions entry point
├── jobs.py          # Job and op definitions
└── README.md        # This file
```

## Components

### Ops (Operations)

Ops are the basic unit of computation in Dagster:

```python
from dagster import op

@op(description="A simple greeting operation")
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

### Jobs

Jobs group related ops together:

```python
from dagster import job

@job(description="Simple greeting job")
def greeting_job():
    log_greeting(greet())
```

### Definitions

The `Definitions` object collects all Dagster objects:

```python
from dagster import Definitions
from orchestrators.dagster.jobs import greeting_job

defs = Definitions(jobs=[greeting_job])
```

## Running Jobs

### Via Dagster UI

1. Start the dev server: `uv run dagster dev -m orchestrators.dagster.definitions`
2. Open http://localhost:3000
3. Navigate to Jobs > greeting_job
4. Click "Launch Run"
5. Configure inputs and execute

### Via Python

```python
from orchestrators.dagster.jobs import greeting_job

result = greeting_job.execute_in_process(
    run_config={
        "ops": {
            "greet": {
                "inputs": {"name": "World"},
            },
        },
    },
)

print(f"Success: {result.success}")
print(f"Output: {result.output_for_node('log_greeting')}")
```

### Via CLI

```bash
# Execute a job
uv run dagster job execute -m orchestrators.dagster.definitions -j greeting_job

# With configuration
uv run dagster job execute -m orchestrators.dagster.definitions -j greeting_job \
  --config '{"ops": {"greet": {"inputs": {"name": "CLI"}}}}'
```

## Dagster Concepts

### Ops vs Tasks (Prefect)

| Dagster Op | Prefect Task |
|------------|--------------|
| `@op` decorator | `@task` decorator |
| Returns values directly | Returns values directly |
| Uses context for logging | Uses `get_run_logger()` |
| Type annotations | Type annotations |

### Jobs vs Flows (Prefect)

| Dagster Job | Prefect Flow |
|-------------|--------------|
| `@job` decorator | `@flow` decorator |
| Groups ops | Groups tasks |
| No retries by default | Configurable retries |
| Always requires server | Ephemeral mode available |

### Key Differences from Prefect

1. **Server Requirement**: Dagster dev server is always needed for the UI
2. **Definitions Object**: All objects must be registered in a central `Definitions`
3. **Run Configuration**: Jobs accept configuration via `run_config` dict
4. **Op Context**: Logging uses `context.log` instead of `get_run_logger()`

## Configuration Options

### Environment Variables

```bash
# Set a persistent storage location
export DAGSTER_HOME=/path/to/dagster/home

# Start dev server
uv run dagster dev -m orchestrators.dagster.definitions
```

### dagster.yaml (Optional)

Create `$DAGSTER_HOME/dagster.yaml` for persistent configuration:

```yaml
telemetry:
  enabled: false  # Opt-out of telemetry

storage:
  sqlite:
    base_dir: /path/to/storage
```

## Troubleshooting

### Common Issues

**1. Import errors with relative imports**
```
ImportError: attempted relative import with no known parent package
```
Solution: Use absolute imports (`from orchestrators.dagster.jobs import ...`)

**2. Module not found**
```
ModuleNotFoundError: No module named 'orchestrators'
```
Solution: Run from project root directory

**3. Port already in use**
```
Address already in use
```
Solution: Kill existing process or use a different port:
```bash
uv run dagster dev -m orchestrators.dagster.definitions -p 3001
```

### Debugging Tips

1. **Check logs**: Dagster logs appear in the terminal and UI
2. **View run history**: Available in the Dagster UI under "Runs"
3. **Inspect op execution**: Click on individual ops in the run view

## Next Steps

1. Add assets for data pipeline patterns
2. Implement Fork & Compare workflow as a job
3. Add resources for external services
4. Configure schedules and sensors

## Resources

- [Dagster Docs](https://docs.dagster.io/)
- [Dagster Tutorial](https://docs.dagster.io/getting-started/quickstart)
- [Dagster Concepts](https://docs.dagster.io/concepts)
- [Dagster API Reference](https://docs.dagster.io/_apidocs)
