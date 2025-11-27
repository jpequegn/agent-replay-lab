"""CLI entry point for agent-replay-lab."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from core.conversation import list_conversations, load_conversation

app = typer.Typer(
    name="agent-replay-lab",
    help="Compare orchestration tools for Claude Code agent workflows",
)
console = Console()


@app.command()
def list_cmd(
    project: Annotated[str | None, typer.Option(help="Filter by project path")] = None,
    limit: Annotated[int, typer.Option(help="Maximum conversations to show")] = 20,
):
    """List available conversations from episodic memory."""
    conversations = list_conversations(project_filter=project, limit=limit)

    if not conversations:
        console.print("[yellow]No conversations found[/yellow]")
        return

    table = Table(title="Available Conversations")
    table.add_column("Session ID", style="cyan")
    table.add_column("Project", style="green")

    for conv in conversations:
        table.add_row(conv["session_id"][:16] + "...", conv["project_path"])

    console.print(table)
    console.print(f"\n[dim]Showing {len(conversations)} conversations[/dim]")


@app.command()
def inspect(
    conversation_id: Annotated[str, typer.Argument(help="Session ID to inspect")],
    step: Annotated[int | None, typer.Option(help="Show specific step")] = None,
):
    """Inspect a conversation to find fork points."""
    conv = load_conversation(conversation_id)

    if not conv:
        console.print(f"[red]Conversation not found: {conversation_id}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Conversation: {conv.session_id}[/bold]")
    console.print(f"Project: {conv.project_path}")
    console.print(f"Total steps: {conv.step_count}")
    console.print()

    if step:
        if step < 1 or step > conv.step_count:
            console.print(f"[red]Step {step} out of bounds (1-{conv.step_count})[/red]")
            raise typer.Exit(1)

        msg = conv.messages[step - 1]
        console.print(f"[bold]Step {step}[/bold] ({msg.role})")
        console.print(msg.content[:500])
        if len(msg.content) > 500:
            console.print("[dim]... (truncated)[/dim]")
    else:
        # Show overview of all steps
        for i, msg in enumerate(conv.messages, 1):
            preview = msg.content[:80].replace("\n", " ")
            if len(msg.content) > 80:
                preview += "..."
            role_color = "blue" if msg.role == "user" else "green"
            console.print(f"[{role_color}]{i}. [{msg.role}][/{role_color}] {preview}")


@app.command()
def run(
    conversation: Annotated[str, typer.Option(help="Conversation ID")],
    fork_at: Annotated[int, typer.Option(help="Step to fork at")],
    orchestrator: Annotated[
        str, typer.Option(help="Orchestrator to use (temporal|prefect|dagster)")
    ],
    config: Annotated[Path, typer.Option(help="Path to fork config YAML")],
):
    """Run a fork & compare workflow."""
    console.print(f"[bold]Fork & Compare[/bold]")
    console.print(f"Conversation: {conversation}")
    console.print(f"Fork at step: {fork_at}")
    console.print(f"Orchestrator: {orchestrator}")
    console.print(f"Config: {config}")
    console.print()

    # TODO: Implement orchestrator dispatch
    console.print(f"[yellow]Orchestrator '{orchestrator}' not yet implemented[/yellow]")
    console.print("[dim]Coming soon: Temporal, Prefect, Dagster implementations[/dim]")


@app.command()
def compare(
    run_id: Annotated[str, typer.Argument(help="Run ID to compare")],
):
    """Compare results from a previous run."""
    # TODO: Implement result comparison
    console.print(f"[yellow]Compare not yet implemented for run: {run_id}[/yellow]")


@app.command()
def status(
    orchestrator: Annotated[
        str, typer.Option(help="Orchestrator to check (temporal|prefect|dagster)")
    ],
):
    """Check orchestrator health/status."""
    # TODO: Implement status checks
    console.print(f"[yellow]Status check not yet implemented for: {orchestrator}[/yellow]")


if __name__ == "__main__":
    app()
