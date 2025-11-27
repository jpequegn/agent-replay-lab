"""Shared data models for agent-replay-lab."""

from typing import Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool call made by the assistant."""

    id: str
    name: str
    input: dict


class ToolResult(BaseModel):
    """Result from a tool execution."""

    tool_call_id: str
    output: str
    is_error: bool = False


class Message(BaseModel):
    """A single message in a conversation."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None


class Conversation(BaseModel):
    """A complete conversation from episodic memory."""

    session_id: str
    project_path: str
    messages: list[Message]

    def at_step(self, n: int) -> "Conversation":
        """Return conversation truncated to step N."""
        return Conversation(
            session_id=self.session_id,
            project_path=self.project_path,
            messages=self.messages[:n],
        )

    @property
    def step_count(self) -> int:
        """Number of messages in the conversation."""
        return len(self.messages)


class Checkpoint(BaseModel):
    """A checkpoint representing conversation state at a specific step."""

    conversation_id: str
    step: int
    messages: list[Message]
    project_path: str
    created_at: str


class ForkConfig(BaseModel):
    """Configuration for a single branch in a fork operation."""

    name: str = Field(..., description="Branch identifier")
    inject_message: str | None = Field(None, description="Different user message to inject")
    model: str = Field("claude-sonnet-4-20250514", description="Model to use for this branch")
    system_prompt: str | None = Field(None, description="System prompt override")
    max_turns: int = Field(5, description="Maximum turns to execute after fork")


class ReplayRequest(BaseModel):
    """Request to replay and fork a conversation."""

    conversation_id: str = Field(..., description="Which conversation to replay")
    fork_at_step: int = Field(..., description="Step number to fork at")
    branches: list[ForkConfig] = Field(..., description="Branch configurations to run")


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class BranchResult(BaseModel):
    """Result from executing a single branch."""

    branch_name: str
    config: ForkConfig
    messages: list[Message] = Field(default_factory=list, description="Messages after fork")
    duration_ms: int = 0
    token_usage: TokenUsage | None = None
    status: Literal["success", "error", "timeout"] = "success"
    error: str | None = None


class ComparisonResult(BaseModel):
    """Result of comparing multiple branch executions."""

    request: ReplayRequest
    checkpoint: Checkpoint
    branches: list[BranchResult]
    total_duration_ms: int
    comparison_summary: dict | None = None
