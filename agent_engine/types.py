"""Core data models for the Agent decision engine.

All shared types are defined here as Pydantic models to ensure
type safety and automatic validation across all modules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field


class ToolDef(BaseModel):
    """Definition of a tool that the Agent can call.

    Supports both OpenAI Function Calling JSON Schema format and
    direct Python function references. Parameters are validated
    by Pydantic at registration time.
    """
    name: str
    description: str
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    func: Callable | None = Field(default=None, exclude=True)
    is_async: bool = False
    timeout_sec: float = 30.0
    max_retries: int = 2


class ToolCallRequest(BaseModel):
    """A tool call requested by the LLM (before execution)."""
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Record of a completed tool invocation."""
    id: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    retry_count: int = 0


class Step(BaseModel):
    """One iteration of the decision loop."""
    index: int
    phase: Literal["observe", "think", "act", "reflect"]
    thought: str = ""
    tool_call: ToolCall | None = None
    observation: str = ""
    reflection: str = ""
    is_completed: bool = False


class AgentState(BaseModel):
    """Full runtime state of the Agent."""
    goal: str
    sub_goals: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    current_step_index: int = 0
    status: Literal["idle", "running", "paused", "done", "failed", "stopped"] = "idle"
    errors: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Message(BaseModel):
    """A single chat message in the conversation history."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict] | None = None
