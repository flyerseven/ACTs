"""Tests for LLM adapter implementations."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm.base import LLMResponse, LLMAdapter
from llm.deepseek import DeepSeekAdapter


async def _async_iter(items: list[str]):
    """Helper: yield each item asynchronously."""
    for item in items:
        yield item


class TestLLMResponse:
    """Tests for LLMResponse dataclass fields."""

    def test_finish_reason_default(self):
        """finish_reason defaults to empty string."""
        resp = LLMResponse(content="test")
        assert resp.finish_reason == ""


class TestLLMAdapterFinishReason:
    """Tests for LLMAdapter last_finish_reason attribute."""

    def test_last_finish_reason_default(self):
        """Adapter starts with empty last_finish_reason."""

        class ConcreteAdapter(LLMAdapter):
            async def chat(self, **kwargs):
                return LLMResponse(content="")

            async def chat_stream(self, **kwargs):
                yield ""

        adapter = ConcreteAdapter()
        assert adapter.last_finish_reason == ""


class TestParseResponse:
    """Tests for DeepSeekAdapter._parse_response tool call argument handling."""

    @staticmethod
    def _make_tool_call_response(arguments) -> dict:
        """Build a minimal OpenAI-style non-streaming response with one tool call."""
        return {
            "choices": [{
                "message": {
                    "content": "Let me write the file.",
                    "tool_calls": [{
                        "id": "call_test123",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": arguments,
                        },
                    }],
                },
            }],
        }

    def test_arguments_as_json_string(self):
        """arguments is a JSON-encoded string — the standard OpenAI format."""
        adapter = DeepSeekAdapter(api_key="test-key")
        data = self._make_tool_call_response(
            '{"filepath": "test.html", "content": "<p>hello</p>"}',
        )
        result = adapter._parse_response(data)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "write_file"
        assert result.tool_calls[0]["arguments"] == {
            "filepath": "test.html",
            "content": "<p>hello</p>",
        }

    def test_arguments_as_dict(self):
        """arguments is already a dict — some providers return this in non-streaming mode."""
        adapter = DeepSeekAdapter(api_key="test-key")
        data = self._make_tool_call_response({
            "filepath": "test.html",
            "content": "<p>hello</p>",
        })
        result = adapter._parse_response(data)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "write_file"
        assert result.tool_calls[0]["arguments"] == {
            "filepath": "test.html",
            "content": "<p>hello</p>",
        }

    def test_arguments_as_empty_string(self):
        """arguments is an empty string — should default to {}."""
        adapter = DeepSeekAdapter(api_key="test-key")
        data = self._make_tool_call_response("")
        result = adapter._parse_response(data)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["arguments"] == {}

    def test_arguments_as_malformed_string(self):
        """arguments is a malformed JSON string — should default to {}."""
        adapter = DeepSeekAdapter(api_key="test-key")
        data = self._make_tool_call_response(
            '{"filepath": "test.html", "content": "<p>hello</p>',
        )
        result = adapter._parse_response(data)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["arguments"] == {}

    def test_no_tool_calls(self):
        """Response with no tool_calls — should return empty list."""
        adapter = DeepSeekAdapter(api_key="test-key")
        data = {
            "choices": [{
                "message": {
                    "content": "Task completed.",
                },
            }],
        }
        result = adapter._parse_response(data)
        assert result.tool_calls == []
        assert result.content == "Task completed."


class TestToolCallDeltaAccumulation:
    """Tests for DeepSeekAdapter SSE delta parsing."""

    @staticmethod
    def _make_sse_line(data: dict) -> str:
        """Create an SSE data: line from a JSON-serializable dict."""
        return f"data: {json.dumps(data)}"

    @staticmethod
    def _make_mock_stream(sse_lines: list[str]):
        """Create a mock httpx.AsyncClient that streams the given SSE lines."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(sse_lines))

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        return mock_client

    @pytest.mark.asyncio
    async def test_reasoning_content_forwarded_to_on_thought(self):
        """When SSE delta contains reasoning_content, on_thought is called."""
        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"reasoning_content": "Let me think"}}]}),
            self._make_sse_line({"choices": [{"delta": {"reasoning_content": " about this."}}]}),
            self._make_sse_line({"choices": [{"delta": {"content": "Here is the answer."}}]}),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        thoughts: list[str] = []
        received: list[str] = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "test"}],
            model="deepseek-chat",
            on_thought=lambda t: thoughts.append(t),
        ):
            received.append(chunk)

        assert "".join(thoughts) == "Let me think about this."
        assert "".join(received) == "Here is the answer."

    @pytest.mark.asyncio
    async def test_finish_reason_captured_in_chat_stream(self):
        """chat_stream captures finish_reason from SSE deltas."""
        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"content": "Hello"}}]}),
            self._make_sse_line({
                "choices": [{"delta": {"content": ""}, "finish_reason": "length"}],
            }),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        received: list[str] = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "test"}],
            model="deepseek-chat",
        ):
            received.append(chunk)

        assert "".join(received) == "Hello"
        assert adapter.last_finish_reason == "length"

    @pytest.mark.asyncio
    async def test_finish_reason_normal_stop_in_chat_stream(self):
        """chat_stream: finish_reason 'stop' is captured (normal completion)."""
        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"content": "Done"}}]}),
            self._make_sse_line({
                "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
            }),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        received: list[str] = []
        async for chunk in adapter.chat_stream(
            [{"role": "user", "content": "test"}],
            model="deepseek-chat",
        ):
            received.append(chunk)

        assert "".join(received) == "Done"
        assert adapter.last_finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_finish_reason_captured_in_chat_with_on_chunk(self):
        """chat() with on_chunk captures finish_reason in LLMResponse."""
        sse_lines = [
            self._make_sse_line({"choices": [{"delta": {"content": "Hello"}}]}),
            self._make_sse_line({
                "choices": [{"delta": {"content": ""}, "finish_reason": "length"}],
            }),
            "data: [DONE]",
        ]

        mock_client = self._make_mock_stream(sse_lines)

        adapter = DeepSeekAdapter(api_key="test-key")
        adapter._get_client = AsyncMock(return_value=mock_client)

        chunks: list[str] = []
        result = await adapter.chat(
            [{"role": "user", "content": "test"}],
            model="deepseek-chat",
            on_chunk=lambda c: chunks.append(c),
            thinking=False,
        )

        assert "".join(chunks) == "Hello"
        assert result.finish_reason == "length"
        assert adapter.last_finish_reason == "length"
