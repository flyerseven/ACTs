"""Tests for agent_engine.llm."""
import pytest
from agent_engine.llm import LLMAdapter, LLMResponse, CallbackAdapter, OpenAIAdapter
from agent_engine.types import ToolCallRequest


class TestLLMResponse:
    def test_response_defaults(self):
        r = LLMResponse(content="hello")
        assert r.content == "hello"
        assert r.tool_calls == []
        assert r.usage == {}

    def test_response_with_tool_calls(self):
        tc = ToolCallRequest(id="1", name="search", arguments={"q": "test"})
        r = LLMResponse(content="", tool_calls=[tc])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "search"


class TestCallbackAdapter:
    @pytest.mark.asyncio
    async def test_callback_adapter_passthrough(self):
        async def my_chat(messages, tools=None):
            return "response from callback"

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}])
        assert resp.content == "response from callback"
        assert resp.tool_calls == []

    @pytest.mark.asyncio
    async def test_callback_adapter_with_tools(self):
        async def my_chat(messages, tools=None):
            return "used tools: " + str(len(tools) if tools else 0)

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}], tools=[{"name": "t"}])
        assert "1" in resp.content

    @pytest.mark.asyncio
    async def test_callback_adapter_streaming(self):
        async def my_chat(messages, tools=None):
            for c in "hello":
                yield c

        adapter = CallbackAdapter(my_chat)
        chunks = []
        async for chunk in adapter.chat_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        assert "".join(chunks) == "hello"
