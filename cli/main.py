"""CLI entry point for agent-replay-lab."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from core.config import ConfigError, load_config
from core.conversation import list_conversations, load_conversation
from core.models import ReplayRequest

app = typer.Typer(
    name="agent-replay-lab",
    help="Compare orchestration tools for Claude Code agent workflows",
)
console = Console()


# =============================================================================
# Orchestrator Dispatch Functions
# =============================================================================


async def _run_temporal_workflow(
    request: ReplayRequest,
    output_dir: Path,
) -> dict:
    """Run workflow via Temporal orchestrator.

    Args:
        request: The replay request to execute
        output_dir: Directory to save results

    Returns:
        ComparisonResult as dict
    """
    from orchestrators.temporal.client import (
        WorkflowStatus,
        get_client,
        get_workflow_status,
        start_fork_compare_workflow,
    )

    # Connect to Temporal
    client = await get_client()

    # Start workflow (non-blocking)
    handle = await start_fork_compare_workflow(
        request_dict=request.model_dump(),
        client=client,
    )
    workflow_id = handle.id

    console.print(f"[green]✓[/green] Workflow started: [cyan]{workflow_id}[/cyan]")
    console.print()

    # Poll for completion with progress display
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Executing workflow...", total=None)

        while True:
            info = await get_workflow_status(workflow_id, client=client)

            if info.status == WorkflowStatus.COMPLETED:
                progress.update(task, description="[green]Workflow completed[/green]")
                break
            elif info.status == WorkflowStatus.FAILED:
                progress.update(task, description="[red]Workflow failed[/red]")
                raise typer.Exit(1)
            elif info.status == WorkflowStatus.CANCELLED:
                progress.update(task, description="[yellow]Workflow cancelled[/yellow]")
                raise typer.Exit(1)
            elif info.status == WorkflowStatus.TIMED_OUT:
                progress.update(task, description="[red]Workflow timed out[/red]")
                raise typer.Exit(1)

            # Update progress with branch count if available
            progress.update(task, description=f"Executing workflow ({info.status.value})...")

            await asyncio.sleep(1)

    # Get result
    result = await handle.result()

    # Save results
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result_file = output_dir / f"result-{workflow_id}-{timestamp}.json"

    with open(result_file, "w") as f:
        json.dump(result, f, indent=2, default=str)

    console.print(f"[green]✓[/green] Results saved to: [cyan]{result_file}[/cyan]")

    return result


def _display_results(result: dict) -> None:
    """Display workflow results in a formatted table.

    Args:
        result: ComparisonResult as dict
    """
    console.print()
    console.print(
        Panel(
            f"[bold]Total Duration:[/bold] {result.get('total_duration_ms', 0)}ms\n"
            f"[bold]Branches:[/bold] {len(result.get('branches', []))}",
            title="Results Summary",
            border_style="green",
        )
    )
    console.print()

    # Branch results table
    branches = result.get("branches", [])
    if branches:
        table = Table(title="Branch Results")
        table.add_column("Branch", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Messages", justify="right")
        table.add_column("Tokens", justify="right")

        for branch in branches:
            status = branch.get("status", "unknown")
            status_style = {
                "success": "[green]✓ success[/green]",
                "error": "[red]✗ error[/red]",
                "timeout": "[yellow]⏱ timeout[/yellow]",
            }.get(status, f"[dim]{status}[/dim]")

            duration = f"{branch.get('duration_ms', 0)}ms"
            messages = str(len(branch.get("messages", [])))

            # Token usage
            token_usage = branch.get("token_usage")
            tokens = "-"
            if token_usage:
                tokens = str(token_usage.get("total_tokens", 0))

            table.add_row(
                branch.get("branch_name", "unknown"),
                status_style,
                duration,
                messages,
                tokens,
            )

        console.print(table)

    # Show errors if any
    errors = [b for b in branches if b.get("error")]
    if errors:
        console.print()
        console.print("[red]Errors:[/red]")
        for branch in errors:
            console.print(f"  • [cyan]{branch.get('branch_name')}[/cyan]: {branch.get('error')}")

    # Comparison summary
    summary = result.get("comparison_summary")
    if summary:
        console.print()
        console.print(
            f"[dim]Summary: {summary.get('successful', 0)} successful, "
            f"{summary.get('failed', 0)} failed[/dim]"
        )


@app.command(name="list")
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
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Project", style="green")
    table.add_column("Messages", style="yellow", justify="right")
    table.add_column("Last Modified", style="dim")

    for conv in conversations:
        # Format session ID (first 12 chars)
        session_id = conv["session_id"][:12] + "..."

        # Format project path (remove leading dash, shorten if needed)
        project_path = conv["project_path"]
        if project_path.startswith("-"):
            project_path = project_path[1:].replace("-", "/")
        if len(project_path) > 40:
            project_path = "..." + project_path[-37:]

        # Format timestamp
        modified = ""
        if conv.get("last_timestamp"):
            try:
                dt = datetime.fromisoformat(conv["last_timestamp"].replace("Z", "+00:00"))
                modified = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                pass

        table.add_row(
            session_id,
            project_path,
            str(conv.get("message_count", "?")),
            modified,
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(conversations)} conversations[/dim]")


@app.command()
def inspect(
    conversation_id: Annotated[str, typer.Argument(help="Session ID to inspect")],
    step: Annotated[int | None, typer.Option(help="Show specific step")] = None,
    full: Annotated[bool, typer.Option(help="Show full content (no truncation)")] = False,
):
    """Inspect a conversation to find fork points."""
    conv = load_conversation(conversation_id)

    if not conv:
        console.print(f"[red]Conversation not found: {conversation_id}[/red]")
        raise typer.Exit(1)

    # Header
    console.print(
        Panel(
            f"[bold cyan]{conv.session_id}[/bold cyan]\n"
            f"[dim]Project:[/dim] {conv.project_path}\n"
            f"[dim]Total steps:[/dim] {conv.step_count}",
            title="Conversation",
            border_style="blue",
        )
    )
    console.print()

    if step:
        # Show specific step
        if step < 1 or step > conv.step_count:
            console.print(f"[red]Step {step} out of bounds (1-{conv.step_count})[/red]")
            raise typer.Exit(1)

        msg = conv.messages[step - 1]
        role_color = "blue" if msg.role == "user" else "green"

        # Build content display
        content = msg.content
        truncated = False
        if not full and len(content) > 1000:
            content = content[:1000]
            truncated = True

        console.print(
            Panel(
                content,
                title=f"Step {step} [{msg.role}]",
                border_style=role_color,
            )
        )

        if truncated:
            console.print("[dim]... content truncated. Use --full to see all.[/dim]")

        # Show tool calls if present
        if msg.tool_calls:
            console.print(f"\n[yellow]Tool Calls ({len(msg.tool_calls)}):[/yellow]")
            for tc in msg.tool_calls:
                console.print(f"  • [cyan]{tc.name}[/cyan] (id: {tc.id[:8]}...)")

        # Show tool results if present
        if msg.tool_results:
            console.print(f"\n[yellow]Tool Results ({len(msg.tool_results)}):[/yellow]")
            for tr in msg.tool_results:
                status = "[red]error[/red]" if tr.is_error else "[green]ok[/green]"
                console.print(f"  • {status} (id: {tr.tool_call_id[:8]}...)")

    else:
        # Show overview of all steps
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Role", width=10)
        table.add_column("Preview")
        table.add_column("Tools", width=8, justify="center")

        for i, msg in enumerate(conv.messages, 1):
            # Format preview
            preview = msg.content[:60].replace("\n", " ").strip()
            if len(msg.content) > 60:
                preview += "..."

            # Role styling
            role_color = "blue" if msg.role == "user" else "green"
            role_text = Text(msg.role, style=role_color)

            # Tool indicator
            tools = ""
            if msg.tool_calls:
                tools = f"[cyan]↗{len(msg.tool_calls)}[/cyan]"
            elif msg.tool_results:
                tools = f"[yellow]↩{len(msg.tool_results)}[/yellow]"

            table.add_row(str(i), role_text, preview, tools)

        console.print(table)
        console.print("\n[dim]Use --step N to see full content. Tools: ↗=calls, ↩=results[/dim]")


@app.command()
def run(
    conversation: Annotated[str, typer.Option(help="Conversation ID")],
    fork_at: Annotated[int, typer.Option(help="Step to fork at")],
    orchestrator: Annotated[
        str, typer.Option(help="Orchestrator to use (temporal|prefect|dagster)")
    ],
    config_path: Annotated[Path, typer.Option("--config", help="Path to fork config YAML")],
):
    """Run a fork & compare workflow."""
    # Load and validate configuration
    try:
        config = load_config(config_path)
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e.message}")
        if e.details:
            for detail in e.details:
                console.print(f"  [dim]• {detail}[/dim]")
        raise typer.Exit(1)

    # Display configuration summary
    console.print(
        Panel(
            f"[bold]Conversation:[/bold] {conversation}\n"
            f"[bold]Fork at step:[/bold] {fork_at}\n"
            f"[bold]Orchestrator:[/bold] {orchestrator}\n"
            f"[bold]Branches:[/bold] {len(config.branches)}",
            title="Fork & Compare",
            border_style="blue",
        )
    )
    console.print()

    # Show branch configurations
    table = Table(title="Branch Configurations")
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Max Turns", justify="right")
    table.add_column("Inject Message")

    for branch in config.branches:
        inject = branch.inject_message[:30] + "..." if branch.inject_message else "-"
        table.add_row(
            branch.name,
            branch.model.replace("claude-", "").replace("-20250514", ""),
            str(branch.max_turns),
            inject,
        )

    console.print(table)
    console.print()

    # Show settings
    console.print(
        f"[dim]Settings: timeout={config.settings.timeout_seconds}s, "
        f"output={config.settings.output_dir}[/dim]"
    )
    console.print()

    # Build ReplayRequest
    request = ReplayRequest(
        conversation_id=conversation,
        fork_at_step=fork_at,
        branches=config.branches,
    )

    # Dispatch to orchestrator
    if orchestrator == "temporal":
        try:
            result = asyncio.run(
                _run_temporal_workflow(
                    request=request,
                    output_dir=Path(config.settings.output_dir),
                )
            )
            _display_results(result)
        except ConnectionRefusedError:
            console.print("[red]Error: Cannot connect to Temporal server[/red]")
            console.print("[dim]Make sure Temporal is running: temporal server start-dev[/dim]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
    elif orchestrator in ("prefect", "dagster"):
        console.print(f"[yellow]Orchestrator '{orchestrator}' not yet implemented[/yellow]")
        console.print("[dim]Coming soon in future releases[/dim]")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown orchestrator: {orchestrator}[/red]")
        console.print("[dim]Valid options: temporal, prefect, dagster[/dim]")
        raise typer.Exit(1)


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
