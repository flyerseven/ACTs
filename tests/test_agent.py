import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agent import Agent
from core.models import AgentConfig, LLMConfig, agent_config_to_dict
from security.vault import Vault
from storage.file_store import FileStore
from storage.yaml_io import write_yaml


def test_agent_mock_chat(tmp_path: Path) -> None:
    store = FileStore(root_dir=tmp_path / "Acts")
    store.ensure_structure()

    config = AgentConfig(
        id="a1b2",
        name="Mock Agent",
        model=LLMConfig(provider="mock", name="mock"),
    )
    write_yaml(store.agent_yaml_path("a1b2"), agent_config_to_dict(config))

    vault = Vault(store.vault_path, use_keyring=False)
    vault.load()

    agent = asyncio.run(Agent.load("a1b2", store, vault))
    response = asyncio.run(agent.chat([{"role": "user", "content": "ping"}]))
    assert "ping" in response


class TestInterruptionNotice:
    """Tests for interruption notice appended when finish_reason indicates
    the response was cut short."""

    def _make_mock_adapter(self, chunks: list[str], finish_reason: str = ""):
        """Create a mock LLMAdapter that yields chunks and sets last_finish_reason."""
        from llm.base import LLMAdapter, LLMResponse

        class MockStreamAdapter(LLMAdapter):
            def __init__(self):
                super().__init__()
                self._chunks = chunks
                self._finish_reason = finish_reason

            async def chat(self, **kwargs):
                return LLMResponse(content="".join(self._chunks))

            async def chat_stream(self, **kwargs):
                for c in self._chunks:
                    yield c
                self.last_finish_reason = self._finish_reason

        return MockStreamAdapter()

    @pytest.mark.asyncio
    async def test_finish_reason_length_adds_notice(self):
        """When finish_reason is 'length', an interruption notice is yielded."""
        adapter = self._make_mock_adapter(["Hello"], finish_reason="length")
        agent = Agent(
            config=AgentConfig(
                id="test", name="Test",
                model=LLMConfig(provider="mock", name="mock"),
            ),
            llm=adapter,
        )

        chunks: list[str] = []
        async for chunk in agent.chat_stream(
            [{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

        full = "".join(chunks)
        assert "Hello" in full
        assert "token 上限" in full or "token" in full
        assert "截断" in full

    @pytest.mark.asyncio
    async def test_finish_reason_stop_no_notice(self):
        """When finish_reason is 'stop', no interruption notice is yielded."""
        adapter = self._make_mock_adapter(["Done"], finish_reason="stop")
        agent = Agent(
            config=AgentConfig(
                id="test", name="Test",
                model=LLMConfig(provider="mock", name="mock"),
            ),
            llm=adapter,
        )

        chunks: list[str] = []
        async for chunk in agent.chat_stream(
            [{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

        full = "".join(chunks)
        assert full == "Done"

    @pytest.mark.asyncio
    async def test_finish_reason_content_filter_adds_notice(self):
        """When finish_reason is 'content_filter', an interruption notice is yielded."""
        adapter = self._make_mock_adapter(["Part"], finish_reason="content_filter")
        agent = Agent(
            config=AgentConfig(
                id="test", name="Test",
                model=LLMConfig(provider="mock", name="mock"),
            ),
            llm=adapter,
        )

        chunks: list[str] = []
        async for chunk in agent.chat_stream(
            [{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

        full = "".join(chunks)
        assert "Part" in full
        assert "过滤" in full

    @pytest.mark.asyncio
    async def test_no_finish_reason_no_notice(self):
        """When finish_reason is empty, no interruption notice is yielded."""
        adapter = self._make_mock_adapter(["Normal"], finish_reason="")
        agent = Agent(
            config=AgentConfig(
                id="test", name="Test",
                model=LLMConfig(provider="mock", name="mock"),
            ),
            llm=adapter,
        )

        chunks: list[str] = []
        async for chunk in agent.chat_stream(
            [{"role": "user", "content": "test"}],
        ):
            chunks.append(chunk)

        full = "".join(chunks)
        assert full == "Normal"
