# Agent Replay Lab

Compare orchestration tools (Temporal, Prefect, Dagster) for Claude Code agent workflows.

## Overview

This project implements a **Fork & Compare** system that:
1. Loads past Claude Code conversations from episodic memory
2. Replays them to any checkpoint
3. Forks into parallel branches with variations (different models, prompts, messages)
4. Compares results across branches

The same workflow is implemented in three orchestration frameworks to evaluate which best fits Claude Code agent integration.

## Project Status

- [ ] Core library (conversation loading, models, comparison)
- [ ] Temporal implementation
- [ ] Prefect implementation
- [ ] Dagster implementation
- [ ] Pattern documentation
- [ ] Comparison analysis

## Quick Start

```bash
# Install dependencies
uv sync

# List available conversations
agent-replay-lab list

# Run a fork & compare workflow
agent-replay-lab run \
  --conversation <id> \
  --fork-at <step> \
  --orchestrator temporal \
  --config examples/fork-config.yaml
```

## Documentation

- [Design Document](docs/plans/2025-11-27-fork-compare-design.md) - Full project design and architecture
- [Temporal Patterns](patterns/temporal-patterns.md) - Integration patterns for Temporal
- [Prefect Patterns](patterns/prefect-patterns.md) - Integration patterns for Prefect
- [Dagster Patterns](patterns/dagster-patterns.md) - Integration patterns for Dagster

## Project Structure

```
agent-replay-lab/
├── core/                    # Shared logic (orchestrator-agnostic)
├── orchestrators/           # Temporal, Prefect, Dagster implementations
├── cli/                     # Command-line interface
├── patterns/                # Integration pattern documentation
├── comparisons/             # Results and analysis
└── docs/plans/              # Design documents
```

## License

MIT
