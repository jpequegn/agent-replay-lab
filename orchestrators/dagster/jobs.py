"""Dagster job definitions for Fork & Compare workflow.

Jobs are the main unit of execution in Dagster. They:
- Group related ops together
- Define execution dependencies
- Enable configuration and resources
- Provide observability and logging

Dagster jobs can be run:
- Via the Dagster UI (dagster dev)
- Programmatically via Python
- Via the Dagster CLI (dagster job execute)
"""

from dagster import In, Out, graph, job, op


@op(description="A simple greeting operation for testing Dagster setup")
def greet(name: str) -> str:
    """Generate a greeting message.

    This op demonstrates basic Dagster functionality:
    - Input parameters
    - Return values
    - Logging (via op context)

    Args:
        name: The name to greet

    Returns:
        A greeting message
    """
    return f"Hello, {name}!"


@op(
    ins={"greeting": In(str)},
    out=Out(str),
    description="Log the greeting message",
)
def log_greeting(context, greeting: str) -> str:
    """Log a greeting message.

    This op demonstrates:
    - Using Dagster context for logging
    - Chaining ops together

    Args:
        context: Dagster op context for logging
        greeting: The greeting message to log

    Returns:
        The same greeting message
    """
    context.log.info(f"Greeting: {greeting}")
    return greeting


@job(description="Simple greeting job for testing Dagster setup")
def greeting_job():
    """Execute a simple greeting workflow.

    This job tests basic Dagster functionality:
    - Op execution
    - Op chaining
    - Logging
    - Return values

    Run with:
        uv run dagster job execute -f orchestrators/dagster/jobs.py -j greeting_job
    """
    log_greeting(greet())


# =============================================================================
# Graph-based job (alternative pattern)
# =============================================================================


@graph(description="Graph-based greeting workflow")
def greeting_graph():
    """Define a greeting workflow as a graph.

    Graphs are reusable and can be converted to jobs with different
    configurations for different environments.
    """
    return log_greeting(greet())


# Create a job from the graph
greeting_graph_job = greeting_graph.to_job(
    name="greeting_graph_job",
    description="Greeting job created from a graph",
)


# =============================================================================
# Main entry point
# =============================================================================

if __name__ == "__main__":
    # Test the job locally
    result = greeting_job.execute_in_process(
        run_config={
            "ops": {
                "greet": {
                    "inputs": {"name": "Dagster"},
                },
            },
        },
    )
    print(f"\nJob execution: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Greeting output: {result.output_for_node('log_greeting')}")
