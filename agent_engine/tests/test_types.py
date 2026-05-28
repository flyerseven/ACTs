"""Tests for agent_engine.types."""
import pytest
from datetime import datetime
from agent_engine.types import (
    ToolDef, ToolCall, Step, AgentState, Message, ToolCallRequest
)


class TestToolDef:
    def test_minimal_tool_def(self):
        t = ToolDef(name="test", description="A test tool", parameters={"type": "object", "properties": {}})
        assert t.name == "test"
        assert t.timeout_sec == 30.0
        assert t.max_retries == 2
        assert t.is_async is False
        assert t.func is None

    def test_tool_def_with_func(self):
        def my_func(x: int) -> str:
            return str(x)
        t = ToolDef(name="f", description="d", parameters={}, func=my_func, is_async=True, timeout_sec=10.0, max_retries=0)
        assert t.func is not None
        assert t.is_async is True
        assert t.timeout_sec == 10.0
        assert t.max_retries == 0


class TestToolCall:
    def test_tool_call_creation(self):
        tc = ToolCall(id="abc", tool_name="search", arguments={"q": "hello"})
        assert tc.result is None
        assert tc.error is None
        assert tc.finished_at is None

    def test_tool_call_duration_computed(self):
        tc = ToolCall(id="1", tool_name="t", arguments={})
        assert tc.duration_ms == 0.0


class TestStep:
    def test_step_defaults(self):
        s = Step(index=0, phase="observe")
        assert s.thought == ""
        assert s.tool_call is None
        assert s.is_completed is False


class TestAgentState:
    def test_initial_state(self):
        s = AgentState(goal="test goal")
        assert s.status == "idle"
        assert s.steps == []
        assert s.errors == []
        assert s.current_step_index == 0

    def test_state_status_values(self):
        s = AgentState(goal="g", status="running")
        assert s.status == "running"
        s.status = "done"
        assert s.status == "done"


class TestMessage:
    def test_message_creation(self):
        m = Message(role="user", content="hello")
        assert m.tool_call_id is None
        assert m.name is None

    def test_tool_message(self):
        m = Message(role="tool", content="result", tool_call_id="123", name="search")
        assert m.tool_call_id == "123"
        assert m.name == "search"
