"""Compare results from multiple branch executions."""

from .models import BranchResult, ComparisonResult


def compare_branches(results: list[BranchResult]) -> dict:
    """Generate comparison summary from branch results.

    Args:
        results: List of branch execution results

    Returns:
        Comparison summary dict
    """
    successful = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status != "success"]

    summary = {
        "total_branches": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "branches": {},
    }

    # Per-branch metrics
    for result in results:
        branch_summary = {
            "status": result.status,
            "duration_ms": result.duration_ms,
            "message_count": len(result.messages),
            "model": result.config.model,
        }

        if result.token_usage:
            branch_summary["tokens"] = {
                "input": result.token_usage.input_tokens,
                "output": result.token_usage.output_tokens,
                "total": result.token_usage.total_tokens,
            }

        if result.error:
            branch_summary["error"] = result.error

        # Output preview (first 200 chars of last message)
        if result.messages:
            last_msg = result.messages[-1]
            branch_summary["output_preview"] = last_msg.content[:200]

        summary["branches"][result.branch_name] = branch_summary

    # Aggregate metrics for successful branches
    if successful:
        durations = [r.duration_ms for r in successful]
        summary["metrics"] = {
            "avg_duration_ms": sum(durations) // len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
        }

        total_tokens = [
            r.token_usage.total_tokens for r in successful if r.token_usage
        ]
        if total_tokens:
            summary["metrics"]["avg_tokens"] = sum(total_tokens) // len(total_tokens)

    return summary


def format_comparison_markdown(comparison: ComparisonResult) -> str:
    """Format comparison result as markdown.

    Args:
        comparison: The comparison result to format

    Returns:
        Markdown formatted string
    """
    lines = [
        "# Fork & Compare Results",
        "",
        f"**Conversation:** {comparison.checkpoint.conversation_id}",
        f"**Fork at step:** {comparison.checkpoint.step}",
        f"**Total duration:** {comparison.total_duration_ms}ms",
        "",
        "## Branch Results",
        "",
        "| Branch | Model | Status | Duration | Tokens | Output Preview |",
        "|--------|-------|--------|----------|--------|----------------|",
    ]

    for result in comparison.branches:
        tokens = result.token_usage.total_tokens if result.token_usage else "-"
        preview = ""
        if result.messages:
            preview = result.messages[-1].content[:50].replace("\n", " ")
            if len(result.messages[-1].content) > 50:
                preview += "..."

        lines.append(
            f"| {result.branch_name} | {result.config.model.split('/')[-1]} | "
            f"{result.status} | {result.duration_ms}ms | {tokens} | {preview} |"
        )

    if comparison.comparison_summary:
        lines.extend([
            "",
            "## Summary",
            "",
        ])

        if "metrics" in comparison.comparison_summary:
            metrics = comparison.comparison_summary["metrics"]
            lines.extend([
                f"- **Average duration:** {metrics.get('avg_duration_ms', '-')}ms",
                f"- **Average tokens:** {metrics.get('avg_tokens', '-')}",
            ])

    return "\n".join(lines)
