"""Tests for agent_engine.reflect."""
import pytest
from agent_engine.reflect import Reflector, Reflection
from agent_engine.state import StateManager
from agent_engine.memory import MemoryManager
from agent_engine.types import Step, ToolCall


class TestReflectorRules:
    def test_detect_repetition_no_repeat(self):
        r = Reflector()
        steps = [
            Step(index=i, phase="act", tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": f"topic{i}"}))
            for i in range(5)
        ]
        assert r.detect_repetition(steps) is False

    def test_detect_repetition_same_call(self):
        r = Reflector()
        steps = [
            Step(index=i, phase="act", tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": "same thing"}))
            for i in range(3)
        ]
        assert r.detect_repetition(steps) is True

    def test_detect_repetition_different_tools(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="act", tool_call=ToolCall(id="0", tool_name="search", arguments={"q": "x"})),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="calc", arguments={"expr": "1+1"})),
            Step(index=2, phase="act", tool_call=ToolCall(id="2", tool_name="read", arguments={"path": "f.txt"})),
        ]
        assert r.detect_repetition(steps) is False

    def test_detect_off_track_relevant(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="think", thought="I need to search for the data"),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="search", arguments={"q": "data"})),
        ]
        score = r.detect_off_track("analyze data", steps)
        assert score < 0.5

    def test_detect_off_track_irrelevant(self):
        r = Reflector()
        steps = [
            Step(index=0, phase="think", thought="let me calculate something"),
            Step(index=1, phase="act", tool_call=ToolCall(id="1", tool_name="calc", arguments={"expr": "2+2"})),
        ]
        score = r.detect_off_track("analyze data", steps)
        assert score >= 0.5

    def test_summarize_errors(self):
        r = Reflector()
        errors = ["timeout", "timeout", "connection refused", "timeout"]
        summary = r.summarize_errors(errors)
        assert "connection refused" in summary
        assert "timeout" in summary


class TestReflection:
    def test_reflection_defaults(self):
        ref = Reflection()
        assert ref.should_continue is True
        assert ref.is_stuck is False
        assert ref.detected_loop is False


@pytest.mark.asyncio
async def test_reflect_without_llm():
    """Reflector should work without LLM (rule-based only)."""
    r = Reflector()
    sm = StateManager()
    sm.start("analyze sales data")
    for i in range(4):
        sm.add_step(Step(
            index=i, phase="act",
            tool_call=ToolCall(id=str(i), tool_name="search", arguments={"q": "sales"}),
        ))
    mm = MemoryManager()
    mm.add("user", "analyze sales data")

    from llm.callback import CallbackAdapter
    async def fake_llm(messages, tools=None):
        return "continue"
    adapter = CallbackAdapter(fake_llm)

    reflection = await r.reflect(sm.state, mm, adapter)
    assert isinstance(reflection, Reflection)
    assert reflection.detected_loop is True
