"""Tests for agent_engine.engine."""
import pytest
from agent_engine.engine import AgentEngine
from agent_engine.llm import CallbackAdapter
from agent_engine.config import EngineConfig


class TestAgentEngine:
    @pytest.mark.asyncio
    async def test_run_completes_when_llm_says_done(self):
        """Agent should stop when LLM indicates completion."""
        call_count = [0]

        async def chat(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return "Let me think about this task."
            return "The analysis is complete. DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=10, reflect_interval=10),
        )
        state = await engine.run("Analyze something")
        assert state.status == "done"
        assert state.goal == "Analyze something"
        assert len(state.steps) > 0

    @pytest.mark.asyncio
    async def test_max_steps_stops(self):
        """Agent should stop when max_steps is reached."""
        async def chat(messages, tools=None):
            return "Still working on it..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=3, reflect_interval=10),
        )
        state = await engine.run("An impossible task")
        assert state.status == "failed"
        assert len(state.steps) >= 3

    @pytest.mark.asyncio
    async def test_emergency_stop(self):
        """Requesting stop should halt the agent."""
        async def chat(messages, tools=None):
            return "Working..."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=20, reflect_interval=10),
        )

        import asyncio
        async def delayed_stop():
            await asyncio.sleep(0.2)
            engine.request_stop()

        task = asyncio.create_task(delayed_stop())
        state = await engine.run("Some goal")
        await task
        assert state.status == "stopped"

    @pytest.mark.asyncio
    async def test_step_recorded(self):
        """Each iteration should record a step."""
        async def chat(messages, tools=None):
            return "DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=5, reflect_interval=10),
        )
        state = await engine.run("Goal")
        assert len(state.steps) >= 1
        assert state.steps[0].phase == "think"

    @pytest.mark.asyncio
    async def test_engine_with_tool_registry(self):
        """Engine should pass tool schemas to LLM."""
        tool_schemas_seen = []

        async def chat(messages, tools=None):
            tool_schemas_seen.append(tools)
            return "DONE."

        engine = AgentEngine(
            llm=CallbackAdapter(chat),
            config=EngineConfig(max_steps=5, reflect_interval=10),
        )
        engine.tools.register_from_func(lambda x: x * 2, name="double")
        await engine.run("Test")
        assert tool_schemas_seen[0] is not None
        assert len(tool_schemas_seen[0]) == 1
        assert tool_schemas_seen[0][0]["name"] == "double"
