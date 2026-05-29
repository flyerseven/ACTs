"""Tests for LLM adapter implementations."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm.deepseek import DeepSeekAdapter


async def _async_iter(items: list[str]):
    """Helper: yield each item asynchronously."""
    for item in items:
        yield item


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
