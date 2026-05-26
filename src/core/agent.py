from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from core.models import AgentConfig, agent_config_from_dict
from llm.base import LLMAdapter, LLMResponse
from llm.factory import LLMAdapterFactory
from storage.file_store import FileStore
from storage.yaml_io import read_yaml
from security.vault import Vault

if TYPE_CHECKING:
    from core.token_tracker import TokenTracker


@dataclass
class LoadedSkill:
    name: str
    description: str
    type: str
    prompt_extension: str = ""


class Agent:
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMAdapter,
        token_tracker: "TokenTracker | None" = None,
    ) -> None:
        self.id = config.id
        self.name = config.name
        self.config = config
        self.llm = llm
        self.token_tracker = token_tracker

    @classmethod
    async def load(
        cls,
        agent_id: str,
        store: FileStore,
        vault: Vault,
        token_tracker: "TokenTracker | None" = None,
    ) -> "Agent":
        config_path = store.agent_yaml_path(agent_id)
        data = read_yaml(config_path)
        config = agent_config_from_dict(data)

        api_key = vault.resolve_key_ref(config.model.api_key_ref)
        llm = LLMAdapterFactory.create(config.model, api_key)
        return cls(config=config, llm=llm, token_tracker=token_tracker)

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, session_id: str = "") -> str:
        response = await self.llm.chat(
            messages=messages,
            model=self.config.model.name,
            temperature=self.config.model.temperature,
            max_tokens=self.config.model.max_tokens,
            tools=tools,
            stream=False,
        )
        self._record_usage(response.usage, session_id=session_id)
        return response.content

    async def chat_stream(self, messages: list[dict[str, Any]], session_id: str = ""):
        try:
            async for chunk in self.llm.chat_stream(
                messages=messages,
                model=self.config.model.name,
                temperature=self.config.model.temperature,
                max_tokens=self.config.model.max_tokens,
            ):
                yield chunk
        finally:
            self._record_usage(self.llm.last_usage, session_id=session_id)

    def _record_usage(self, usage: dict[str, int] | None, session_id: str = "") -> None:
        if not self.token_tracker or not usage:
            return
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total = usage.get("total_tokens", 0) or prompt + completion
        self.token_tracker.record(
            model=self.config.model.name,
            provider=self.config.model.provider,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            agent_id=self.id,
            session_id=session_id,
        )
