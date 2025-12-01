"""Dagster definitions for Fork & Compare workflow.

This module serves as the entry point for Dagster. The Definitions object
collects all assets, jobs, schedules, and sensors for the project.

Usage:
    uv run dagster dev -m orchestrators.dagster.definitions

This will start the Dagster UI at http://localhost:3000
"""

from dagster import Definitions, graph, job

from orchestrators.dagster.jobs import greeting_graph_job, greeting_job
from orchestrators.dagster.ops import (
    create_checkpoint_op,
    greet_op,
    load_conversation_op,
)

# =============================================================================
# Fork & Compare Graph
# =============================================================================


@graph(description="Graph for creating a checkpoint from a conversation")
def checkpoint_graph():
    """Create a checkpoint from a loaded conversation.

    This graph demonstrates composing ops:
    1. Load conversation by ID
    2. Create checkpoint at specified step

    Note: Inputs must be provided when executing the job.
    """
    conversation_data = load_conversation_op()
    return create_checkpoint_op(conversation_data)


# Create a job from the checkpoint graph
checkpoint_job = checkpoint_graph.to_job(
    name="checkpoint_job",
    description="Create a checkpoint from a conversation",
)


@job(description="Simple test job using greet_op")
def greet_op_job():
    """Test job for greet_op."""
    greet_op()


# =============================================================================
# Dagster Definitions
# =============================================================================

defs = Definitions(
    jobs=[
        greeting_job,
        greeting_graph_job,
        greet_op_job,
        checkpoint_job,
    ],
    # Future: Add assets, schedules, sensors, resources
    # assets=[...],
    # schedules=[...],
    # sensors=[...],
    # resources={...},
)
