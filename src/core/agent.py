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
    from agent_engine.engine import AgentEngine


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

    # Mapping from skill names (configured on the agent) to builtin tool
    # functions.  Only tools whose skill name appears in agent.config.skills
    # are registered; an empty skills list means no tools at all.
    _SKILL_TOOL_MAP: dict[str, list] = {}

    @classmethod
    def _get_skill_tool_map(cls) -> dict[str, list]:
        if cls._SKILL_TOOL_MAP:
            return cls._SKILL_TOOL_MAP

        name_to_func: dict[str, object] = {}
        try:
            from agent_engine.builtin_tools import (
                calculate, read_file, write_file, list_files, web_search, execute_python,
            )
            name_to_func = {
                "calculate": calculate,
                "read_file": read_file,
                "write_file": write_file,
                "list_files": list_files,
                "web_search": web_search,
                "execute_python": execute_python,
            }
            cls._SKILL_TOOL_MAP = {
                "calculator": [calculate],
                "files": [read_file, write_file, list_files],
                "search": [web_search],
                "code_exec": [execute_python],
            }
        except ImportError:
            pass

        # Discover skills and add dynamic entries from their ``requires`` field.
        from pathlib import Path
        from core.skill import discover_skills
        skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        for _, skill in discover_skills(skills_dir):
            if skill.requires:
                funcs = [name_to_func[n] for n in skill.requires if n in name_to_func]
                if funcs:
                    cls._SKILL_TOOL_MAP[skill.name] = funcs

        return cls._SKILL_TOOL_MAP

    def create_engine(self, api_key: str) -> "AgentEngine":
        """Create an AgentEngine configured from this agent's settings.

        Tools are registered from skills matching ``agent.config.skills``.
        When no skills are configured, all available builtin tools are
        registered by default.
        """
        from agent_engine.engine import AgentEngine
        from agent_engine.config import EngineConfig
        from agent_engine.tools import ToolRegistry
        from llm.factory import LLMAdapterFactory
        from core.models import LLMConfig

        llm_config = LLMConfig(
            provider=self.config.model.provider or "deepseek",
            name=self.config.model.name,
            base_url=self.config.model.base_url or "https://api.deepseek.com",
        )
        engine_llm = LLMAdapterFactory.create(llm_config, api_key)
        engine_config = EngineConfig(
            llm_api_key=api_key,
            llm_base_url=self.config.model.base_url or "https://api.deepseek.com",
            llm_model=self.config.model.name,
            llm_temperature=self.config.model.temperature,
            llm_max_tokens=self.config.model.max_tokens,
        )
        tools = ToolRegistry()
        skill_map = self._get_skill_tool_map()
        skills = self.config.skills or []
        has_skills = bool(skills)
        if has_skills:
            print(f"  [create_engine] enabled skills: {skills}", flush=True)
            print(f"  [create_engine] skill→tool map keys: {list(skill_map.keys())}", flush=True)
        enabled = set(skills)
        for skill_name, funcs in skill_map.items():
            if not has_skills or skill_name in enabled:
                for func in funcs:
                    print(f"  [create_engine] registering tool: {func.__name__} (from skill '{skill_name}')", flush=True)
                    tools.register_from_func(func)
        if has_skills and not tools.list_tools():
            print(f"  [create_engine] WARNING: no tools matched! skills={list(enabled)}, map={list(skill_map.keys())}", flush=True)

        # Build skill→tool_names map for the engine's schema filtering.
        skill_tool_names: dict[str, set[str]] = {}
        for skill_name, funcs in skill_map.items():
            skill_tool_names[skill_name] = {f.__name__ for f in funcs}

        return AgentEngine(llm=engine_llm, config=engine_config, tools=tools,
                            skill_tool_map=skill_tool_names)

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
