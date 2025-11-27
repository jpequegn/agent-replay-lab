"""Claude SDK executor for running agent branches."""

import time
from typing import Any

from anthropic import Anthropic

from .checkpoint import checkpoint_to_messages
from .models import (
    BranchResult,
    Checkpoint,
    ForkConfig,
    Message,
    TokenUsage,
)


def execute_branch(
    checkpoint: Checkpoint,
    config: ForkConfig,
    client: Anthropic | None = None,
) -> BranchResult:
    """Execute a single branch from a checkpoint.

    Args:
        checkpoint: Starting checkpoint
        config: Branch configuration (model, injected message, etc.)
        client: Anthropic client (creates one if not provided)

    Returns:
        BranchResult with execution outcome
    """
    if client is None:
        client = Anthropic()

    start_time = time.time()
    messages = checkpoint_to_messages(checkpoint)
    new_messages: list[Message] = []
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        # Inject different user message if specified
        if config.inject_message:
            messages.append({
                "role": "user",
                "content": config.inject_message,
            })
            new_messages.append(Message(
                role="user",
                content=config.inject_message,
                timestamp="",
            ))

        # Execute turns
        for turn in range(config.max_turns):
            # Build request
            request_kwargs: dict[str, Any] = {
                "model": config.model,
                "max_tokens": 4096,
                "messages": messages,
            }

            if config.system_prompt:
                request_kwargs["system"] = config.system_prompt

            # Call Claude
            response = client.messages.create(**request_kwargs)

            # Track tokens
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Extract response content
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            # Record assistant message
            assistant_msg = Message(
                role="assistant",
                content=content,
                timestamp="",
            )
            new_messages.append(assistant_msg)
            messages.append({
                "role": "assistant",
                "content": content,
            })

            # Check if we should stop
            if response.stop_reason == "end_turn":
                break

        duration_ms = int((time.time() - start_time) * 1000)

        return BranchResult(
            branch_name=config.name,
            config=config,
            messages=new_messages,
            duration_ms=duration_ms,
            token_usage=TokenUsage(
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                total_tokens=total_input_tokens + total_output_tokens,
            ),
            status="success",
        )

    except TimeoutError:
        duration_ms = int((time.time() - start_time) * 1000)
        return BranchResult(
            branch_name=config.name,
            config=config,
            messages=new_messages,
            duration_ms=duration_ms,
            status="timeout",
            error="Execution timed out",
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return BranchResult(
            branch_name=config.name,
            config=config,
            messages=new_messages,
            duration_ms=duration_ms,
            status="error",
            error=str(e),
        )
