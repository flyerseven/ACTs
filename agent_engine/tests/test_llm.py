"""Tests for src/llm adapters (previously agent_engine.llm)."""
import pytest
from llm.base import LLMAdapter, LLMResponse
from llm.callback import CallbackAdapter
from llm.deepseek import DeepSeekAdapter


class TestLLMResponse:
    def test_response_defaults(self):
        r = LLMResponse(content="hello")
        assert r.content == "hello"
        assert r.tool_calls == []
        assert r.usage is None

    def test_response_with_tool_calls(self):
        tc = {"id": "1", "name": "search", "arguments": {"q": "test"}}
        r = LLMResponse(content="", tool_calls=[tc])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "search"


class TestCallbackAdapter:
    @pytest.mark.asyncio
    async def test_callback_adapter_passthrough(self):
        async def my_chat(messages, tools=None):
            return "response from callback"

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat([{"role": "user", "content": "hi"}], model="test")
        assert resp.content == "response from callback"
        assert resp.tool_calls == []

    @pytest.mark.asyncio
    async def test_callback_adapter_with_tools(self):
        async def my_chat(messages, tools=None):
            return "used tools: " + str(len(tools) if tools else 0)

        adapter = CallbackAdapter(my_chat)
        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            tools=[{"name": "t"}],
        )
        assert "1" in resp.content

    @pytest.mark.asyncio
    async def test_callback_adapter_streaming(self):
        async def my_chat(messages, tools=None):
            for c in "hello":
                yield c

        adapter = CallbackAdapter(my_chat)
        chunks = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "hi"}], model="test",
        ):
            chunks.append(chunk)
        assert "".join(chunks) == "hello"

    @pytest.mark.asyncio
    async def test_chat_on_chunk_with_async_generator(self):
        async def my_chat(messages, tools=None):
            for c in "streaming":
                yield c

        adapter = CallbackAdapter(my_chat)
        received: list[str] = []

        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            on_chunk=lambda chunk: received.append(chunk),
        )
        assert resp.content == "streaming"
        assert received == list("streaming")

    @pytest.mark.asyncio
    async def test_chat_on_chunk_with_awaitable(self):
        async def my_chat(messages, tools=None):
            return "full response"

        adapter = CallbackAdapter(my_chat)
        received: list[str] = []

        resp = await adapter.chat(
            [{"role": "user", "content": "hi"}],
            model="test",
            on_chunk=lambda chunk: received.append(chunk),
        )
        assert resp.content == "full response"
        assert received == ["full response"]


class TestToolCallDeltaAccumulation:
    """Unit tests for tool call delta accumulation in streaming responses."""

    @staticmethod
    def _make_sse_line(data: dict) -> str:
        import json
        return "data: " + json.dumps(data)

    @staticmethod
    def _make_mock_stream(sse_lines: list[str]):
        from unittest.mock import AsyncMock, MagicMock

        mock_response = MagicMock()
        async def _aiter_lines():
            for line in sse_lines:
                yield line
        mock_response.aiter_lines = _aiter_lines

        mock_response_cls = MagicMock()
        mock_response_cls.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cls.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_response_cls)
        return mock_client

    @pytest.mark.asyncio
    async def test_tool_call_deltas_assembled_from_sse_stream(self):
        from unittest.mock import AsyncMock

        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"content": "Let me search that"}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "search"}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"q":'}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"test"}'}}]}}]}),
            self._make_sse_line({"choices": [{"delta": {"content": "."}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        received: list[str] = []
        resp = await adapter.chat(
            [{"role": "user", "content": "search for test"}],
            model="deepseek-chat",
            tools=[{"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}}],
            on_chunk=lambda c: received.append(c),
        )

        assert resp.content == "Let me search that."
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["id"] == "call_1"
        assert resp.tool_calls[0]["name"] == "search"
        assert resp.tool_calls[0]["arguments"] == {"q": "test"}
        assert received == ["Let me search that", "."]

    @pytest.mark.asyncio
    async def test_tool_call_deltas_multiple_tools(self):
        from unittest.mock import AsyncMock

        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_a", "function": {"name": "calc"}},
                {"index": 1, "id": "call_b", "function": {"name": "search"}},
            ]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '{"expr":"2+2"}'}},
            ]}}]}),
            self._make_sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 1, "function": {"arguments": '{"q":"test"}'}},
            ]}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        resp = await adapter.chat(
            [{"role": "user", "content": "calc and search"}],
            model="deepseek-chat",
            tools=[
                {"name": "calc", "description": "Calculate", "parameters": {"type": "object", "properties": {}}},
                {"name": "search", "description": "Search", "parameters": {"type": "object", "properties": {}}},
            ],
            on_chunk=lambda c: None,
        )

        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0]["name"] == "calc"
        assert resp.tool_calls[0]["arguments"] == {"expr": "2+2"}
        assert resp.tool_calls[1]["name"] == "search"
        assert resp.tool_calls[1]["arguments"] == {"q": "test"}
